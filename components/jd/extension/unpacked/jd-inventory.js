/* One registered read-only SKU method; no stock/price/status writes. */
const JD_INVENTORY_PAGE='https://wares-jdm.jd.com/ware/wareList?activeTab=OnsaleWare&businessModel=0';
const JD_INVENTORY_URL='https://sff.jd.com/api?v=1.0&appId=3MC69M4R3HFKCQ4S01DN&api=dsm.product.manage.SkuInfoReadViewService.querySkuList';
const jdInventoryBatches=new Map();
function inventoryBody(product){
 if(!/^[1-9]\d{0,19}$/.test(product || '') || !Number.isSafeInteger(Number(product)))throw new Error('库存商品编码无效');
 return {skuListQueryReq:{productId:Number(product),skuName:null,skuStatusList:[4],categoryIds:[],brandIdList:[],itemNum:null,skuType:null,startCreated:null,endCreated:null,startModified:null,endModified:null,sortMap:{created:'asc'},supplyVenderId:null},accessContext:{source:'web',businessModel:'0',proxyBelongBizId:'',originType:null}};
}
function inventoryRequest(job){
 // JSON arrays must retain array type while normalizing object key order.
 const canonical=v=>Array.isArray(v)?v.map(canonical):v && typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
 let body;try{body=JSON.parse(job.body);}catch(_){throw new Error('库存请求体无效');}
 if(!['api-probe','registered-api'].includes(job.operation) || job.transport!=='background-native' || job.probe_key!=='inventory-sku' || job.url!==JD_INVENTORY_URL || job.launch!==JD_INVENTORY_PAGE || job.method!=='POST' || job.expected_store?.platform!=='jd' || !/^jd:mall:\d+$/.test(job.expected_store.store_key || '') || JSON.stringify(canonical(body))!==JSON.stringify(canonical(inventoryBody(job.inventory_product_id))))throw new Error('库存请求超出登记只读范围');
 if(!Number.isFinite(Date.parse(job.requested_after)) || Math.abs(Date.now()-Date.parse(job.requested_after))>60000)throw new Error('库存任务过期');
 return {url:JD_INVENTORY_URL,body:JSON.stringify(body),product:job.inventory_product_id};
}
async function inventoryPreparePage(){
 try{
  if(location.origin!=='https://wares-jdm.jd.com' || location.pathname!=='/ware/wareList')throw new Error('库存准备页面不符');
  // One shared budget: slow list refresh gets the unused preparation time,
  // while the 12s outer execution deadline retains a 2s scheduling margin.
  const deadline=Date.now()+10000;
  const wait=async(check,message)=>{
   do{if(check())return;await new Promise(resolve=>setTimeout(resolve,100));}while(Date.now()<deadline);
   throw new Error(message);
  };
  const selected=()=>document.getElementById('tab-OnsaleWare')?.getAttribute('aria-selected')==='true';
  await wait(()=>!!document.getElementById('tab-OnsaleWare'),'库存售卖中页签未就绪');
  const tab=document.getElementById('tab-OnsaleWare');
  if(!tab)throw new Error('库存售卖中页签不存在');
  if(!selected())tab.click();
  await wait(selected,'库存未切换到售卖中');
  let resets;
  await wait(()=>{
   resets=Array.from(document.querySelectorAll('button')).filter(e=>e.textContent.trim()==='重置' && e.getClientRects().length);
   return resets.length===1 && !resets[0].disabled;
  },'库存重置控件未就绪或不唯一');
  resets[0].click();
  // The official resetFields and input components use nested Vue nextTick
  // updates. Drain that event turn before observing readiness or submitting.
  await new Promise(resolve=>setTimeout(resolve,0));
  await wait(()=>{
   const labels=Array.from(document.querySelectorAll('label'));
   return selected() && ['商品名称','SKU编码','商品编码'].every(name=>{
    const matches=labels.filter(e=>e.textContent.trim()===name && e.htmlFor);
    const field=matches.length===1 && document.getElementById(matches[0].htmlFor);
    return field && field.value==='';
   });
  },'库存筛选未清空或售卖中状态丢失');
  // Reset triggers an asynchronous list request. Do not race it with the
  // product-specific query, which could otherwise be overwritten/ignored.
  await wait(()=>!Array.from(document.querySelectorAll('.jd-loading-mask')).some(e=>e.getClientRects().length),'库存重置后的列表刷新未完成');
  return {ready:true,tab:'OnsaleWare',filters_reset:true};
 }catch(error){return {error:'库存页面准备失败：'+String(error?.message || error)};}
}
async function inventoryPageRead(input){
 try{
 if(location.origin!=='https://wares-jdm.jd.com' || location.pathname!=='/ware/wareList' || input.url!=='https://sff.jd.com/api?v=1.0&appId=3MC69M4R3HFKCQ4S01DN&api=dsm.product.manage.SkuInfoReadViewService.querySkuList')throw new Error('库存执行页面或接口不符');
 const started=new Date().toISOString(),visibilityStarted=typeof document!=='undefined'?document.visibilityState:null;
 // Match the public DSM SDK's fixed desktop request metadata. Credentials
 // remain browser-managed; no cookie, token or signature is exported.
 const response=await fetch(input.url,{method:'POST',headers:{'Content-Type':'application/json;charset=UTF-8','Accept':'application/json','X-Requested-With':'XMLHttpRequest','dsm-platform':'pc','dsm-site':'','dsm-lang':'zh_CN'},credentials:'include',body:input.body,redirect:'error',signal:AbortSignal.timeout(20000)});
 if(response.status!==200)throw new Error('库存HTTP状态：'+response.status);
 const text=await response.text();if(text.length>8*1024*1024)throw new Error('库存响应超过上限');
 let value;try{value=JSON.parse(text);}catch(_){throw new Error('库存响应不是JSON');}
 if(value.code!==200 || !Array.isArray(value.data?.data) || value.data?.status==='session_close' || value.data?.api==='openUrl')throw new Error('未取得库存列表：code='+String(value.code)+'；data.status='+String(value.data?.status)+'；data字段='+Object.keys(value.data && typeof value.data==='object'?value.data:{}).join(','));
 if(!Number.isSafeInteger(value.data.totalCount) || value.data.totalCount!==value.data.data.length || value.data.data.some(r=>String(r.productId)!==input.product))throw new Error('库存商品归属或返回行数不符');
 return {status:200,text,request_started_at:started,received_at:new Date().toISOString(),execution_visibility:{start:visibilityStarted,end:typeof document!=='undefined'?document.visibilityState:null}};
 }catch(error){return {error:'库存请求失败：'+String(error?.message || error)};}
}
async function runJDInventoryJob(job){
 const input=inventoryRequest(job),owned=new Set(),diagnostics=[],deadline=Date.now()+50000;
 const batch=job.inventory_batch;
 if(batch!==undefined && (!/^[0-9a-f]{32}$/.test(batch) || typeof job.inventory_batch_last!=='boolean'))throw new Error('库存批次标识不符');
 let pool=batch?jdInventoryBatches.get(batch):null,retained=false;
 if(pool){
  if(pool.store!==job.expected_store.store_key)throw new Error('库存批次店铺不符');
  clearTimeout(pool.timer);
  // Pause idle eviction while borrowed. A bounded watchdog still cleans
  // owned pages if discovery itself rejects before the main try/finally.
  pool.timer=setTimeout(async()=>{
   if(jdInventoryBatches.get(batch)!==pool)return;
   jdInventoryBatches.delete(batch);
   for(const id of pool.owned)try{await chrome.tabs.remove(id);}catch(_){}
  },70000);
  for(const id of pool.owned)owned.add(id);
 }
 async function execute(tabId,func,args,timeout=5000,stage=func.name){
  if(Date.now()>=deadline)throw new Error('库存后台任务总预算已用尽；阶段='+stage);
  timeout=Math.min(timeout,Math.max(1,deadline-Date.now()));
  const started=Date.now();let timer;try{
   const value=await Promise.race([chrome.scripting.executeScript({target:{tabId},world:'MAIN',injectImmediately:true,func,args}),new Promise((_,reject)=>{timer=setTimeout(()=>{const error=new Error('库存页面执行超时；阶段='+stage+'；上限='+timeout+'ms');error.inventoryTimeout=true;reject(error);},timeout);})]);
   if(!value?.[0]?.result || typeof value[0].result!=='object')throw new Error('库存页面未返回有效结果：'+func.name+'；tab='+tabId);
   if(value[0].result.error)throw new Error(String(value[0].result.error));
   diagnostics.push({stage,tab_id:tabId,status:'ok',elapsed_ms:Date.now()-started});
   return value[0].result;
  }catch(error){
   error.inventoryStage=stage;
   diagnostics.push({stage,tab_id:tabId,status:error.inventoryTimeout?'timeout':'error',elapsed_ms:Date.now()-started,error:String(error.message || error)});
   throw error;
  }finally{clearTimeout(timer);}
 }
 const identities=await chrome.tabs.query({url:'https://jdsz.jd.com/szweb/view/*'});
 const identityPaths=['/szweb/view/index/home.html','/szweb/view/tradeAnalysis/tradeSummary.html','/szweb/view/product/productDetail.html','/szweb/view/view-source/view-flow.html','/szweb/view/product/mark-new-product-temp.html','/szweb/view/flow/flow-summary.html'];
 // Match stores' read-only DOM discovery: lifecycle flags are advisory, not
 // authentication evidence. Probe every eligible identity page with a bound.
 const anchors=await Promise.all(identities.filter(t=>!t.discarded && t.status!=='loading' && t.url && identityPaths.includes(new URL(t.url).pathname)).map(async tab=>{
  try{const actual=await execute(tab.id,readJDIdentity,[new URL(tab.url).pathname],2500,'identity-before');return sameStore(job.expected_store,actual)?{tab,actual}:null;}
  catch(_){return null;}
 }));
 let anchor=anchors.find(a=>a?.tab.id===pool?.anchor?.tab.id)||anchors.find(Boolean);
 async function closeOwned(id){
  if(!owned.has(id))return;
  await chrome.tabs.remove(id);owned.delete(id);
 }
 async function freshPage(){
  if(pool?.tab){
   try{
    const reused=await chrome.tabs.get(pool.tab.id);
    if(reused.status==='complete' && !reused.discarded && !reused.frozen && reused.url?.split(/[?#]/)[0]===JD_INVENTORY_PAGE.split('?')[0]){
     diagnostics.push({stage:'batch-page-reused',tab_id:reused.id,status:'ok'});return reused;
    }
   }catch(_){}
   await closeOwned(pool.tab.id);pool.tab=null;
  }
  if(deadline-Date.now()<5000)throw new Error('库存后台恢复预算已用尽，未发起新查询');
  const created=await chrome.tabs.create({url:JD_INVENTORY_PAGE,active:false});owned.add(created.id);
  // Only this task's ephemeral tab is protected. Do not activate user tabs or
  // change global browser settings. autoDiscardable is not a freeze guarantee.
  await chrome.tabs.update(created.id,{autoDiscardable:false});
  const until=Math.min(deadline,Date.now()+12000);
  do{
   const tab=await chrome.tabs.get(created.id);
   if(tab.discarded || tab.frozen){const error=new Error('库存临时后台页已暂停，未执行查询');error.inventoryTimeout=true;throw error;}
   if(tab.status==='complete'){
    const url=new URL(tab.url);
    if(url.origin!=='https://wares-jdm.jd.com' || url.pathname!=='/ware/wareList')throw new Error('库存临时页未进入商品列表，请检查官方页面登录或验证状态');
    diagnostics.push({stage:'background-page',tab_id:tab.id,status:'ok',active:!!tab.active,discarded:!!tab.discarded,frozen:!!tab.frozen});
    return tab;
   }
   await new Promise(resolve=>setTimeout(resolve,200));
  }while(Date.now()<until);
  const error=new Error('库存临时后台页加载超时');error.inventoryTimeout=true;throw error;
 }
 async function freshIdentity(){
  if(deadline-Date.now()<4000)throw new Error('后台店铺身份恢复预算不足；未保存结果');
  const url='https://jdsz.jd.com/szweb/view/index/home.html';
  const created=await chrome.tabs.create({url,active:false});owned.add(created.id);
  await chrome.tabs.update(created.id,{autoDiscardable:false});
  const until=Math.min(deadline,Date.now()+10000);
  do{
   const tab=await chrome.tabs.get(created.id);
   if(tab.status==='complete' && tab.url?.split(/[?#]/)[0]!==url)throw new Error('身份复核页跳离商智首页，请检查官方登录状态');
   if(tab.url?.split(/[?#]/)[0]===url){
    try{
     const actual=await execute(tab.id,readJDIdentity,['/szweb/view/index/home.html'],2500,'identity-recovery');
     diagnostics.push({stage:'identity-recovery-page',tab_id:tab.id,status:'ok',active:!!tab.active});
     return {...actual,tab_id:tab.id};
    }catch(error){if(Date.now()>=until)throw error;}
   }
   await new Promise(resolve=>setTimeout(resolve,200));
  }while(Date.now()<until);
  throw new Error('后台店铺身份复核未完成；未保存结果');
 }
 try{
  if(!anchor){
   const actual=await freshIdentity();
   if(!sameStore(job.expected_store,actual))throw new Error('库存任务无法核验指定商智店铺；未查询库存');
   anchor={actual,tab:{id:actual.tab_id,url:'https://jdsz.jd.com/szweb/view/index/home.html'}};
  }
  let tab,result;
  for(let attempt=0;attempt<2;attempt++){
   try{
    tab=await freshPage();
    const preparation=await execute(tab.id,inventoryPreparePage,[],12000,'prepare');
    if(preparation.ready!==true)throw new Error('库存页面准备未通过核验');
    try{result=await execute(tab.id,inventoryPageRead,[input],24000,'inventory-fetch');}
    catch(error){
     if(!String(error.message || error).startsWith('库存请求失败：未取得库存列表：code=601；'))throw error;
     result=await execute(tab.id,inventoryNativeRead,[input],24000,'inventory-native');
    }
    break;
   }catch(error){
    // Closing our abandoned context cancels its queued reset/XHR callbacks.
    // Never recover a business denial (especially 605/session failures).
    if(!error.inventoryTimeout || ['inventory-fetch','inventory-native'].includes(error.inventoryStage) || attempt===1 || deadline-Date.now()<5000)throw error;
    for(const id of [...owned])if(id!==anchor.tab.id)await closeOwned(id);
    diagnostics.push({stage:'background-recovery',status:'retry',attempt:attempt+1,error:String(error.message || error)});
   }
  }
  let after;
  try{after=await execute(anchor.tab.id,readJDIdentity,[new URL(anchor.tab.url).pathname],5000,'identity-after');}
  catch(error){
   // Identity is a synchronous DOM-only read: retry its dispatch once on a
   // browser execution timeout, without repeating any successful stock read.
   if(!error.inventoryTimeout)throw error;
   try{after=await execute(anchor.tab.id,readJDIdentity,[new URL(anchor.tab.url).pathname],5000,'identity-after');}
   catch(second){if(!second.inventoryTimeout)throw second;after=await freshIdentity();}
  }
  if(!sameStore(job.expected_store,after))throw new Error('库存读取期间商智店铺改变');
  const finalTab=await chrome.tabs.get(tab.id);
  if(batch && !job.inventory_batch_last){
   if(after.tab_id && after.tab_id!==anchor.tab.id)anchor={actual:after,tab:{id:after.tab_id,url:'https://jdsz.jd.com/szweb/view/index/home.html'}};
   if(pool)clearTimeout(pool.timer);
   const entry={store:job.expected_store.store_key,tab,anchor,owned:new Set(owned)};
   entry.timer=setTimeout(async()=>{
    if(jdInventoryBatches.get(batch)!==entry)return;
    jdInventoryBatches.delete(batch);
    for(const id of entry.owned)try{await chrome.tabs.remove(id);}catch(_){}
   },120000);
   jdInventoryBatches.set(batch,entry);retained=true;
  }
  return {...result,identity:after,source:'registered-api',transport:'registered-api',execution_page:tab.url,inventory_execution_mode:'owned-background-page',
   execution_tab_id:tab.id,execution_tab_state:{active:!!finalTab.active,discarded:!!finalTab.discarded,frozen:!!finalTab.frozen},inventory_diagnostics:diagnostics};
 }finally{
  if(!retained){if(pool)clearTimeout(pool.timer);if(batch)jdInventoryBatches.delete(batch);for(const id of [...owned])try{await closeOwned(id);}catch(_){}}
 }
}
async function inventoryNativeRead(input){
 let open,send,patchedOpen,patchedSend,deadline;
 const XHR=XMLHttpRequest,requests=new WeakMap();
 try{
  if(location.origin!=='https://wares-jdm.jd.com' || location.pathname!=='/ware/wareList')throw new Error('库存原生页面不符');
  let accept,reject;
  const responsePromise=new Promise((resolve,fail)=>{accept=resolve;reject=fail;});
  // Attach a handler immediately, including when a control lookup fails.
  responsePromise.catch(()=>{});
  const stable=v=>Array.isArray(v)?v.map(stable):v && typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
  const expected=JSON.stringify(stable(JSON.parse(input.body)));
  open=XHR.prototype.open;send=XHR.prototype.send;
  patchedOpen=function(method,url,...rest){requests.set(this,{method,url:String(url)});return open.call(this,method,url,...rest);};
  patchedSend=function(body){
   const meta=requests.get(this);let match=false;
   try{
    const url=new URL(meta.url,location.href),wanted=new URL(input.url);
    match=meta.method.toUpperCase()==='POST' && url.origin===wanted.origin && url.pathname===wanted.pathname && ['v','appId','api'].every(k=>url.searchParams.get(k)===wanted.searchParams.get(k)) && JSON.stringify(stable(JSON.parse(body)))===expected;
   }catch(_){}
   if(match){
    const started=new Date().toISOString();
    this.addEventListener('loadend',()=>{
     try{
      if(this.status!==200)throw new Error('库存原生HTTP状态：'+this.status);
      const text=this.responseText,value=JSON.parse(text);
      if(value.code!==200 || !Array.isArray(value.data?.data) || value.data.data.length!==value.data.totalCount || value.data.data.some(row=>String(row.productId)!==input.product))throw new Error('库存原生列表或商品校验失败：code='+String(value.code));
      accept({status:200,text,request_started_at:started,received_at:new Date().toISOString(),request_mode:'official-ui-observer'});
     }catch(error){reject(error);}
    },{once:true});
   }
   return send.call(this,body);
  };
  XHR.prototype.open=patchedOpen;XHR.prototype.send=patchedSend;
  deadline=setTimeout(()=>reject(new Error('库存原生请求等待超时；未收到该商品精确匹配的库存响应')),18000);
  const labels=Array.from(document.querySelectorAll('label')).filter(e=>e.textContent.trim().startsWith('商品编码') && e.htmlFor);
  if(labels.length!==1)throw new Error('库存商品编码筛选控件不唯一');
  const field=document.getElementById(labels[0].htmlFor),buttons=Array.from(document.querySelectorAll('button')).filter(e=>e.textContent.trim()==='查询');
  if(!field || buttons.length!==1 || buttons[0].disabled)throw new Error('库存原生查询控件未就绪');
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,input.product);
  field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  if(field.value!==input.product || document.getElementById(labels[0].htmlFor)!==field)throw new Error('库存商品编码输入尚未稳定');
  buttons[0].click();
  const until=Date.now()+10000;let row;
  do{
   const rows=Array.from(document.querySelectorAll('tr.render-row')).filter(e=>e.textContent.includes('商品编码：'+input.product));
   if(rows.length===1){row=rows[0];break;}await new Promise(resolve=>setTimeout(resolve,150));
  }while(Date.now()<until);
  const expand=row?.querySelector('.row-expand');if(!expand)throw new Error('库存原生查询没有找到指定商品展开按钮');
  expand.click();return await responsePromise;
 }catch(error){return {error:'库存原生读取失败：'+String(error?.message || error)};}
 finally{
  clearTimeout(deadline);
  if(XHR.prototype.open===patchedOpen)XHR.prototype.open=open;
  if(XHR.prototype.send===patchedSend)XHR.prototype.send=send;
 }
}
if(typeof module!=='undefined')module.exports={inventoryBody,inventoryRequest,inventoryPreparePage,inventoryPageRead,inventoryNativeRead,runJDInventoryJob};
