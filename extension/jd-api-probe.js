/* Registered browser-session reads, shared by formal reports and development probes. */
function validateIndustryRequest(job) {
  const host='https://szgateway.jd.com',pages='https://jdsz.jd.com/szweb/view/industry/';
  const paths={
    'industry-options':['GET','/api/common/getDims.ajax?menuCode=industrySummary','industrySummary.html'],
    'industry-overview':['POST','/api/lowcode/industrySummary/core/summaryv2.ajax','industrySummary.html'],
    'industry-products':['POST','/api/lowcode/industryTop/indProductRank/productRank.ajax','industry-top.html'],
    'industry-shops':['POST','/api/lowcode/industryTop/indShopRank/shopRankList.ajax','industry-top.html']};
  const spec=paths[job.probe_key];
  if(!spec || job.method!==spec[0] || job.url!==host+spec[1] || job.launch!==pages+spec[2])throw new Error('行业接口超出登记只读范围');
  if(spec[0]==='GET'){if(job.body!==undefined)throw new Error('行业选项GET不接受body');return;}
  let body;try{body=JSON.parse(job.body);}catch(_){throw new Error('行业请求体无效');}
  const allowed=new Set(['channel','popBusiness','dateType','startDate','endDate','compareType','compareStartDate','compareEndDate','realtime','interval','indicators','rankTab','sortField','sortOrder','skuSpuType','saleOrdCate2','saleOrdCate3','bsIndCate2','bsIndCate3','onlySelf','onlyMonitor']);
  if(!body || Array.isArray(body) || Object.keys(body).some(k=>!allowed.has(k)))throw new Error('行业请求含未登记字段');
  for(const key of ['startDate','endDate']){
    const value=body[key],time=Date.parse(value+'T00:00:00Z');
    if(!/^\d{4}-\d{2}-\d{2}$/.test(value||'') || !Number.isFinite(time) || new Date(time).toISOString().slice(0,10)!==value)throw new Error('行业日期无效');
  }
  const today=new Date(Date.now()+8*3600000).toISOString().slice(0,10);
  if(body.startDate>body.endDate || body.endDate>=today || body.realtime!==false || !Array.isArray(body.indicators) || !body.indicators.length || body.indicators.some(x=>typeof x!=='string'||!x))throw new Error('行业查询超出完整历史范围');
}
async function jdApiPageRead(input) {
  const routes={
    'industry-options':['GET','https://szgateway.jd.com/api/common/getDims.ajax?menuCode=industrySummary'],
    'industry-overview':['POST','https://szgateway.jd.com/api/lowcode/industrySummary/core/summaryv2.ajax'],
    'industry-products':['POST','https://szgateway.jd.com/api/lowcode/industryTop/indProductRank/productRank.ajax'],
    'industry-shops':['POST','https://szgateway.jd.com/api/lowcode/industryTop/indShopRank/shopRankList.ajax'],
    'new-products':['POST','https://szgateway.jd.com/szpaas/lowcode/szajax/query/markNewProduct.ajax'],
    'task-list':['GET','https://szgateway.jd.com/api/common/downloadCenter/getTaskList.ajax'],
    'overview':['POST','https://szgateway.jd.com/api/lowcode/tradeSummary/summary/getSummary.ajax'],
    'overview-realtime':['POST','https://szgateway.jd.com/api/lowcode/tradeSummary/summary/getSummary.ajax'],
    'traffic-level1':['POST','https://szgateway.jd.com/api/lowcode/flowSource/sourceTable/table.ajax'],
    'traffic-level2':['POST','https://szgateway.jd.com/api/lowcode/flowSource/sourceTable/table.ajax'],
    'traffic-tree':['POST','https://szgateway.jd.com/api/lowcode/flowSource/sourceTable/table.ajax'],
    'traffic-channel':['POST','https://szgateway.jd.com/api/lowcode/flowSummary/getCoreSummary.ajax'],
    'export-submit':['POST','https://szgateway.jd.com/api/lowcode/download/productDetail/table/offlineProductTable.ajax'],
    'source-dictionary':['GET','https://szgateway.jd.com/api/lowcode/common/getDimensionTree.ajax?startDimName=jdr_sch_traffic_cha_last_field_src_rmad_sz_1&endDimName=jdr_sch_traffic_cha_last_field_src_rmad_sz_4']
  };
  if(input.key==='task-file' && /^\d{16,24}$/.test(input.task_id || ''))routes['task-file']=['GET','https://szgateway.jd.com/api/common/downloadCenter/getFileLink.ajax?taskId='+input.task_id];
  const route=routes[input.key];
  if(location.origin!=='https://jdsz.jd.com' || !route || input.method!==route[0] || input.url!==route[1])throw new Error('接口未登记');
  const since=Date.parse(input.requested_after),now=Date.now();
  if(!Number.isFinite(since) || now-since>60000 || since>now+5000)throw new Error('接口验证任务已过期');
  const h=input.headers || {},names=Object.keys(h).sort().join(',');
  if(names!=='User-mnp,User-mup,X-Requested-With,uuid' || !/^[0-9a-f-]{36}$/.test(h.uuid) ||
    !/^\d{13}$/.test(h['User-mup']) || Math.abs(now-Number(h['User-mup']))>60000 ||
    !/^[0-9a-f]{32}$/.test(h['User-mnp']) || h['X-Requested-With']!=='XMLHttpRequest')throw new Error('请求头不符合已核实页面规则');
  if(input.method==='GET' && input.body!==undefined)throw new Error('GET不接受请求体');
  if(input.method==='POST' && (typeof input.body!=='string' || input.body.length>200000))throw new Error('请求体无效');
  const headers={...h,Accept:'application/json, text/plain, */*'};
  if(input.method==='POST')headers['Content-Type']='application/json';
  const requestStarted=new Date().toISOString();
  const target=new URL(input.url);
  if(input.key==='new-products')for(const name of ['uuid','User-mup','User-mnp'])target.searchParams.set(name,h[name]);
  const response=await fetch(input.key==='new-products'?target.href:input.url,{method:input.method,headers,body:input.body,
    credentials:'include',redirect:'error',signal:AbortSignal.timeout(20000)});
  if(response.status!==200)throw new Error('接口 HTTP '+response.status);
  const reader=response.body.getReader(),chunks=[];let length=0;
  for(;;){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;
    if(length>8*1024*1024){await reader.cancel();throw new Error('接口响应超过8MB验证上限');}chunks.push(value);}
  const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  const text=new TextDecoder().decode(bytes);let data;
  try{data=JSON.parse(text);}catch(_){throw new Error('接口响应不是JSON');}
  if(data?.header?.code!==(input.key==='new-products'?'200':0) || (data.errors && (!Array.isArray(data.errors) || data.errors.length)))throw new Error('接口业务错误，code='+String(data?.header?.code));
  return {status:response.status,text,request_timestamp:requestStarted,request_started_at:requestStarted,received_at:new Date().toISOString(),source:'registered-api-probe'};
}

const jdApiLastTabs=new Map();
const jdApiRecoveryTabs=new Map();
const jdApiNeedsRecovery=new Set();
async function runJDApiProbeJob(job) {
  if(['order-list','order-lookup'].includes(job.probe_key))return runJDOrderJob(job);
  if(job.probe_key==='inventory-sku')return runJDInventoryJob(job);
  if(job.probe_key==='after-sales-list')return runJDAfterSalesJob(job);
  if(!['api-probe','registered-api'].includes(job.operation) || job.transport!=='background-native' || job.expected_store?.platform!=='jd' || !/^jd:mall:\d+$/.test(job.expected_store.store_key))throw new Error('接口验证缺少指定店铺');
  const contracts=await (await fetch(chrome.runtime.getURL('report-contracts.json'))).json();
  const key=job.probe_key;
  const business=key==='business-stats';
    const insights=business?await jdBusinessStatsRead({...job,validateOnly:true}):key==='shop-insights'?await jdShopInsightsRead({...job,validateOnly:true}):null;
  if(key.startsWith('industry-'))validateIndustryRequest(job);
  if(key==='overview-realtime')realtimeRequest(job,await (await fetch(chrome.runtime.getURL('realtime-contract.json'))).json());
  const page=insights?insights.page:key.startsWith('industry-')?'https://jdsz.jd.com/szweb/view/industry/'+(['industry-products','industry-shops'].includes(key)?'industry-top.html':'industrySummary.html'):key==='overview-realtime'?contracts.overview.page:key==='traffic-channel'?'https://jdsz.jd.com/szweb/view/flow/flow-summary.html':key==='new-products'?'https://jdsz.jd.com/szweb/view/product/mark-new-product-temp.html':key==='source-dictionary' || key.startsWith('traffic-')?contracts['traffic-level1'].page:contracts['products-spu'].page;
  if(job.launch!==(insights?insights.page:page))throw new Error('接口验证页面不符');
  if(key==='task-file'){
    const task=job.export_task,day=job.export_day;
    const prefix=job.expected_store.store_key.slice(8)+'_商品明细_离线_不包括对比时间_汇总下载_'+day+'_'+day;
    if(!/^\d{4}-\d{2}-\d{2}$/.test(day || '') || task?.taskName!==prefix || task?.taskStatues!==2 || !/^\d{16,24}$/.test(String(task?.taskId || '')))throw new Error('导出任务店铺、日期或状态不符');
  }
  if(key==='new-products'){
    const templates=await (await fetch(chrome.runtime.getURL('new-product-contracts.json'))).json();
    validateNewProductRequest(job,templates);
  }
  if(key==='traffic-channel')validateTrafficChannelRequest(job,await (await fetch(chrome.runtime.getURL('traffic-channel-contract.json'))).json());
  if(key==='overview')reportRequest({...job,launch:contracts.overview.page},contracts.overview.template,contracts.overview);
  if(key==='traffic-level1' || key==='traffic-level2')reportRequest(job,contracts[key].template,contracts[key]);
  if(key==='traffic-tree')trafficTreeRequest(job,contracts['traffic-level1']);
  if(key==='export-submit'){
    const contract=contracts['products-'+job.export_dimension];let body;
    try{body=JSON.parse(job.body);}catch(_){throw new Error('导出请求体无效');}
    if(!contract || body.cmpFlag!==0 || body.trendType!==null || job.url!=='https://szgateway.jd.com/api/lowcode/download/productDetail/table/offlineProductTable.ajax')throw new Error('导出范围未登记');
    const {cmpFlag,trendType,...base}=body;
    reportRequest({...job,launch:contract.page,url:contract.endpoint,body:JSON.stringify(base)},contract.template,contract);
  }
  async function execute(tabId,func,args,phase,timeout){
    let timer;try{
      const result=await Promise.race([chrome.scripting.executeScript({target:{tabId},world:'MAIN',injectImmediately:true,func,args}),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('页面执行超时：'+phase+'；tab='+tabId)),timeout);})]);
      if(!result?.length || result[0].result===undefined)throw new Error('页面未返回结果：'+phase+'；tab='+tabId);
      return result[0].result;
    }finally{clearTimeout(timer);}
  }
  // Logical report/request scope stays fixed; execution can recover on a
  // responsive same-origin page whose shop is verified before and after read.
  const tabs=await chrome.tabs.query({url:'https://jdsz.jd.com/szweb/view/*'});
  const diagnostics=[];let observedOtherStore=false,recoveryPageCreated=false;
  const cacheKey=job.expected_store.store_key+'|'+page;
  const identityPaths=['/szweb/view/index/home.html','/szweb/view/tradeAnalysis/tradeSummary.html','/szweb/view/product/productDetail.html','/szweb/view/view-source/view-flow.html','/szweb/view/product/mark-new-product-temp.html','/szweb/view/flow/flow-summary.html'];
  const matching=tabs.filter(t=>!t.discarded && t.status!=='loading' && t.url && new URL(t.url).origin==='https://jdsz.jd.com' && identityPaths.includes(new URL(t.url).pathname));
  async function identify(tab){
    try{const identity=await execute(tab.id,readJDIdentity,[new URL(tab.url).pathname],'identify',4000);
      if(identity?.store_key && !sameStore(job.expected_store,identity))observedOtherStore=true;
      return sameStore(job.expected_store,identity)?{tab,identity}:null;
    }catch(error){diagnostics.push(String(error.message || error));return null;}
  }
  const forceRecovery=jdApiNeedsRecovery.has(job.expected_store.store_key);
  const cached=forceRecovery?null:matching.find(tab=>tab.id===jdApiLastTabs.get(cacheKey));
  let chosen=cached?await identify(cached):null;
  if(!chosen && !forceRecovery){
    jdApiLastTabs.delete(cacheKey);
    try{chosen=await Promise.any(matching.filter(tab=>!cached || tab.id!==cached.id).map(async tab=>{const result=await identify(tab);if(!result)throw new Error('非指定店铺');return result;}));}catch(_){chosen=null;}
  }
  if(!chosen && !observedOtherStore && typeof chrome.tabs.create==='function'){
    const store=job.expected_store.store_key,home='https://jdsz.jd.com/szweb/view/index/home.html';
    const prior=matching.find(tab=>tab.id===jdApiRecoveryTabs.get(store));
    if(prior && !forceRecovery)chosen=await identify(prior);
    if(!chosen){
      // Only extension-created recovery pages may be replaced or closed.
      const owned=jdApiRecoveryTabs.get(store);
      if(owned){try{await chrome.tabs.remove(owned);}catch(_){}jdApiRecoveryTabs.delete(store);}
      const fresh=await chrome.tabs.create({url:home,active:false});
      const tab={...fresh,url:home},begin=Date.now();
      do{
        chosen=await identify(tab);
        if(chosen || observedOtherStore)break;
        await new Promise(resolve=>setTimeout(resolve,250));
      }while(Date.now()-begin<10000);
      if(chosen){jdApiRecoveryTabs.set(store,tab.id);recoveryPageCreated=true;}
      else{try{await chrome.tabs.remove(tab.id);}catch(_){}}
    }
  }
  if(chosen){
    try{
    const {tab,identity:before}=chosen;
    // After a request starts, never try another page: export submission may have succeeded.
    const input={key,url:job.url,method:job.method,body:job.body,headers:job.probe_headers,requested_after:job.requested_after,task_id:String(job.export_task?.taskId || '')};
    if(insights)Object.assign(input,{insights_report:job.insights_report,insights_params:job.insights_params,business_report:job.business_report,business_params:job.business_params,business_date:job.business_date,launch:job.launch});
    const result=await execute(tab.id,business?jdBusinessStatsRead:insights?jdShopInsightsRead:jdApiPageRead,[input],'request:'+key,25000);
    if(insights && result?.probe_error)throw new Error(result.probe_error);
    if(insights && (!result || result.status!==200 || typeof result.text!=='string'))throw new Error('类目/用户浏览器执行未返回有效业务响应');
    const after=await execute(tab.id,readJDIdentity,[new URL(tab.url).pathname],'verify',4000);
    if(!sameStore(before,after))throw new Error('接口验证期间店铺变化');
    jdApiLastTabs.set(cacheKey,tab.id);
    jdApiNeedsRecovery.delete(job.expected_store.store_key);
    const source=job.operation==='registered-api'?'registered-api':'registered-api-probe';
    return {...result,identity:{...after,tab_id:tab.id},execution_page:tab.url,recovery_page_created:recoveryPageCreated,source,transport:source};
    }catch(error){
      jdApiLastTabs.delete(cacheKey);
      if(key!=='export-submit' && String(error.message || error).includes('页面执行超时'))jdApiNeedsRecovery.add(job.expected_store.store_key);
      throw error;
    }
  }
  jdApiLastTabs.delete(cacheKey);
  throw new Error('未找到指定店铺已就绪页面；未发送接口请求；'+diagnostics.join('；'));
}

function validateNewProductRequest(job,templates){
 const dim=job.new_dimension,template=templates[dim];let body;
 try{body=JSON.parse(job.body);}catch(_){throw new Error('新品请求体无效');}
 if(!template || !['sku','spu'].includes(dim) || job.method!=='POST' || job.url!=='https://szgateway.jd.com/szpaas/lowcode/szajax/query/markNewProduct.ajax')throw new Error('新品接口未登记');
 const p=body.commonParam,day=p?.date;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day||'') || new Date(day).toISOString().slice(0,10)!==day || !Number.isInteger(p.page) || p.page<1 || p.page>1000 || !/^[0-9a-f-]{36}$/.test(p.traceId||'') || !/^[0-9a-f-]{36}$/.test(p.batchId||''))throw new Error('新品日期或分页无效');
 const expected=JSON.parse(JSON.stringify(template));
 for(const f of expected.filterList)if(f.propertyName==='dt')f.values=[day];
 Object.assign(expected.commonParam,{date:day,startDate:day,endDate:day,page:p.page,traceId:p.traceId,batchId:p.batchId});
 function stable(v){if(Array.isArray(v))return v.map(stable);if(v && typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])]));return v;}
 if(JSON.stringify(stable(body))!==JSON.stringify(stable(expected)))throw new Error('新品请求超出登记范围');
 return body;
}

function validateTrafficChannelRequest(job,spec){
 let body;try{body=JSON.parse(job.body);}catch(_){throw new Error('终端请求体无效');}
 const day=body.startDate,scope=job.channel_scope;
 if(job.method!=='POST' || job.url!==spec.endpoint || job.launch!==spec.page || !scope || Object.keys(scope).join(',')!=='channel' || !Object.hasOwn(spec.channels,scope.channel) || body.channel!==scope.channel)throw new Error('终端查询范围未登记');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day||'') || !Number.isFinite(Date.parse(day+'T00:00:00Z')) || new Date(day).toISOString().slice(0,10)!==day)throw new Error('终端日期无效');
 const previous=new Date(Date.parse(day+'T00:00:00Z')-86400000).toISOString().slice(0,10);
 const expected={...spec.template,startDate:day,endDate:day,compareStartDate:previous,compareEndDate:previous,channel:scope.channel};
 const stable=v=>JSON.stringify(Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))));
 if(stable(body)!==stable(expected))throw new Error('终端请求超出单日前日环比登记范围');
 return body;
}
