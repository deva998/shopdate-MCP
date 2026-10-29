/* Fixed order-list reads. Full customer data never leaves the page. */
const JD_ORDER_PAGE='https://shop.jd.com/jdm/trade/orders/order-list?tabType=allOrders';
const JD_ORDER_URL='https://sff.jd.com/api?v=1.0&appId=COCX0HBWR4BA7RDVDBIQ&api=dsm.order.bff.orderListBffService.queryOrderPage';
const JD_ORDER_SHOP_PAGE='https://shop.jd.com/jdm/seller/shop/information?_JDMOMID_=1201,6571';
const jdOrderLastPage=new Map();
const jdOrderLookupPages=new Map();
function validateOrderJob(job,template){
 const stable=v=>Array.isArray(v)?v.map(stable):v && typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
 if(job.probe_key==='order-lookup'){
  const scope=job.lookup_scope,ids=scope?.order_ids,end=scope?.end_day,stamp=Date.parse(end+'T00:00:00Z');
  if(!scope||Object.keys(scope).sort().join(',')!=='end_day,order_ids'||!/^\d{4}-\d\d-\d\d$/.test(end||'')||!Number.isFinite(stamp)||new Date(stamp).toISOString().slice(0,10)!==end||!Array.isArray(ids)||ids.length<1||ids.length>50||new Set(ids).size!==ids.length||ids.some(i=>typeof i!=='string'||! /^[1-9]\d{0,19}$/.test(i)))throw new Error('原订单精确查询范围无效');
  const begin=new Date(stamp-179*86400000).toISOString().slice(0,10),expected=JSON.parse(JSON.stringify(template));
  Object.assign(expected.request.data,{orderIds:ids,orderCreateTimeBegin:begin+' 00:00:00',orderCreateTimeEnd:end+' 23:59:59',current:1,pageSize:50});
  let body;try{body=JSON.parse(job.body);}catch(_){throw new Error('原订单查询正文无效');}
  if(job.operation!=='registered-api'||job.transport!=='background-native'||job.method!=='POST'||job.url!==JD_ORDER_URL||job.launch!==JD_ORDER_PAGE||job.expected_store?.platform!=='jd'||!/^jd:mall:\d+$/.test(job.expected_store.store_key||'')||JSON.stringify(stable(body))!==JSON.stringify(stable(expected)))throw new Error('原订单查询超出登记只读范围');
  if(!Number.isFinite(Date.parse(job.requested_after))||Math.abs(Date.now()-Date.parse(job.requested_after))>60000)throw new Error('原订单任务过期');
  return {url:JD_ORDER_URL,body:job.body,date:end,page:1,lookup_ids:ids};
 }
 const scope=job.order_scope;
 if(!scope || Object.keys(scope).sort().join(',')!=='date,page' || !/^\d{4}-\d{2}-\d{2}$/.test(scope.date || '') || !Number.isInteger(scope.page) || scope.page<1 || scope.page>1000)throw new Error('订单日期或分页范围无效');
 const parsed=Date.parse(scope.date+'T00:00:00Z');
 if(!Number.isFinite(parsed) || new Date(parsed).toISOString().slice(0,10)!==scope.date)throw new Error('订单日期无效');
 let body;try{body=JSON.parse(job.body);}catch(_){throw new Error('订单请求体无效');}
 const expected=JSON.parse(JSON.stringify(template));Object.assign(expected.request.data,{orderCreateTimeBegin:scope.date+' 00:00:00',orderCreateTimeEnd:scope.date+' 23:59:59',current:scope.page});
 if(job.operation!=='registered-api' || job.transport!=='background-native' || job.probe_key!=='order-list' || job.method!=='POST' || job.url!==JD_ORDER_URL || job.launch!==JD_ORDER_PAGE || job.expected_store?.platform!=='jd' || !/^jd:mall:\d+$/.test(job.expected_store.store_key || '') || JSON.stringify(stable(body))!==JSON.stringify(stable(expected)))throw new Error('订单任务超出登记只读范围');
 if(!Number.isFinite(Date.parse(job.requested_after)) || Math.abs(Date.now()-Date.parse(job.requested_after))>60000)throw new Error('订单任务过期');
 return {url:JD_ORDER_URL,body:job.body,date:scope.date,page:scope.page};
}
function readJDOrderMerchant(){
 if(location.origin!=='https://shop.jd.com' || location.pathname!=='/jdm/seller/shop/information')return null;
 const anchors=Array.from(document.querySelectorAll('a[href]')).map(e=>e.href).filter(h=>/^https?:\/\/mall\.jd\.com\/index-\d+\.html(?:[?#].*)?$/.test(h));
 const malls=Array.from(new Set(anchors.map(h=>h.replace(/^http:/,'https:').split(/[?#]/)[0])));
 const rows=Array.from(document.querySelectorAll('.cq-shop-info__bottom--item')).filter(e=>e.querySelector('.item-label')?.textContent.trim()==='商家ID');
 const merchant=rows.length===1?rows[0].querySelector('.item-value .content')?.textContent.trim():null;
 if(malls.length!==1 || !/^[1-9]\d{0,19}$/.test(merchant || ''))return null;
 const name=document.querySelector('.cq-shop-info__top-right--name > div')?.textContent.trim() || '京东店铺';
 return {platform:'jd',store_key:'jd:mall:'+(/index-(\d+)\.html/.exec(malls[0])[1]),name,merchant_id:merchant,identity_anchor:malls[0],kind:'official_shop_information'};
}
async function prepareJDOrderPage(){
 if(location.origin!=='https://shop.jd.com'||location.pathname!=='/jdm/trade/orders/order-list')return {error:'订单准备页面不符'};
 const until=Date.now()+15000;let state;
 do{
  const fields=Array.from(document.querySelectorAll('.jd-range-input'));
  const queries=Array.from(document.querySelectorAll('button')).filter(e=>e.textContent.trim()==='查询');
  state={ready:fields.length===2&&queries.length===1&&!queries[0].disabled&&!!document.querySelector('input[placeholder="多个查询请以逗号/空格隔开"]'),field_count:fields.length,query_count:queries.length,visibility:document.visibilityState};
  if(state.ready)return state;
  await new Promise(resolve=>setTimeout(resolve,200));
 }while(Date.now()<until);
 return state;
}
async function orderNativeRead(input){
 let open,send,wrappedOpen,wrappedSend,timer,lastMismatch=null;
 const XHR=XMLHttpRequest,requests=new WeakMap();
 try{
  if(location.origin!=='https://shop.jd.com' || location.pathname!=='/jdm/trade/orders/order-list')throw new Error('订单执行页面不符');
  let fields=Array.from(document.querySelectorAll('.jd-range-input'));const readyUntil=Date.now()+5000;
  while(fields.length!==2 && Date.now()<readyUntil){await new Promise(r=>setTimeout(r,100));fields=Array.from(document.querySelectorAll('.jd-range-input'));}
  if(fields.length!==2)throw new Error('订单下单日期控件尚未就绪或不唯一');
  const stable=v=>Array.isArray(v)?v.map(stable):v && typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
  const request=JSON.parse(input.body),pageSize=request.request.data.pageSize;
  if(pageSize!==50)throw new Error('订单仅使用官方50条分页');
  const expected=JSON.stringify(stable(request));let matchingStarted=false;
  let accept,reject;const pending=new Promise((resolve,fail)=>{accept=resolve;reject=fail;});pending.catch(()=>{});
  open=XHR.prototype.open;send=XHR.prototype.send;
  wrappedOpen=function(method,url,...rest){requests.set(this,{method,url:String(url)});return open.call(this,method,url,...rest);};
  wrappedSend=function(body){
   const meta=requests.get(this);let match=false;
   try{
    const url=new URL(meta.url,location.href),wanted=new URL(input.url);
    if(meta.method.toUpperCase()==='POST' && url.origin===wanted.origin && url.pathname===wanted.pathname && ['v','appId','api'].every(k=>url.searchParams.get(k)===wanted.searchParams.get(k))){
     const parsed=JSON.parse(body);match=JSON.stringify(stable(parsed))===expected;
     if(!match){const d=parsed.request?.data || {};lastMismatch={begin:d.orderCreateTimeBegin,end:d.orderCreateTimeEnd,page:d.current,pageSize:d.pageSize,tab:d.orderTab};}
    }
   }catch(_){}
   if(match){
    matchingStarted=true;
    const started=new Date().toISOString();
    this.addEventListener('loadend',async()=>{
     try{
      if(this.status!==200)throw new Error('订单HTTP状态：'+this.status);
      const raw=this.responseText;if(raw.length>12*1024*1024)throw new Error('订单页超过读取上限');
      const value=JSON.parse(raw),data=value.data;
      if(value.code===605)throw new Error('官方安全验证605：已停止，请人工完成网页验证后重新发起；不自动重试');
      const totals=[data?.total,data?.totalItem].filter(v=>v!=null);
      const rows=data?.results==null&&totals.length>0&&totals.every(v=>Number.isSafeInteger(v)&&v===0)?[]:data?.results;
      if(value.code!==200 || !data || !Array.isArray(rows) || rows.length>pageSize)throw new Error('订单列表结构未核验：code='+String(value.code)+'；data字段='+Object.keys(data && typeof data==='object'?data:{}).join(','));
      if(data.venderId!=null && String(data.venderId)!==input.merchant_id){
       const observed=/^\d+$/.test(String(data.venderId))?String(data.venderId):'missing';
       throw new Error('订单响应商家与官方店铺映射不符；response_vender='+observed+'；official_merchant='+input.merchant_id+'；data字段='+Object.keys(data).join(','));
      }
      // Explicit allowlist projection, never spread a raw order/customer object.
      const pick=(obj,keys)=>Object.fromEntries(keys.map(k=>[k,obj?.[k] ?? null]));
      const results=rows.map(row=>{
       if(typeof row.orderId==='number' && !Number.isSafeInteger(row.orderId))throw new Error('订单编号超过安全整数范围');
       if(typeof row.parentId==='number'&&!Number.isSafeInteger(row.parentId))throw new Error('父订单编号超过安全整数范围');
       const state=row.orderStatusInfo || row.orderStatusVo || {},payment=row.orderPaymentInfo || row;
       const items=row.orderItems;
       if(!Array.isArray(items))throw new Error('订单商品结构未核验');
       return {orderId:String(row.orderId),...(Object.hasOwn(row,'parentId')?{parentId:row.parentId==null?null:String(row.parentId)}:{}),...pick(row,['orderCreateTime','paymentConfirmTime','orderCompleteTime','skuTotalNum']),
        orderStatusInfo:pick(state,['orderStatus','orderStatusName']),orderPaymentInfo:pick(payment,['receivables','shouldPay','orderSum','freight']),
        orderItems:items.map(item=>{if(typeof item.skuId==='number' && !Number.isSafeInteger(item.skuId))throw new Error('SKU编号超过安全整数范围');return {...pick(item,['skuName','num','jdPrice','itemNum']),skuId:String(item.skuId)};})};
      });
      const projected={projection:'order-business-v1',code:200,data:{venderId:data.venderId==null?null:String(data.venderId),...pick(data,['total','totalItem','totalReceivables']),results},
       schema:{row_fields:rows.length?Object.keys(rows[0]):[],item_fields:rows[0]?.orderItems?.length?Object.keys(rows[0].orderItems[0]):[]}};
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))).map(b=>b.toString(16).padStart(2,'0')).join('');
      accept({status:200,text:JSON.stringify(projected),request_started_at:started,received_at:new Date().toISOString(),request_mode:'official-ui-observer-business-projection',raw_response_sha256:digest});
     }catch(error){reject(error);}
    },{once:true});
   }
   return send.call(this,body);
  };
  XHR.prototype.open=wrappedOpen;XHR.prototype.send=wrappedSend;
  timer=setTimeout(()=>reject(new Error('未收到精确匹配的订单请求；实际条件='+JSON.stringify(lastMismatch))),18000);
  if(input.page===1){
   const orderIds=document.querySelector('input[placeholder="多个查询请以逗号/空格隔开"]');
   if(input.lookup_ids&&!orderIds)throw new Error('原订单编号筛选控件缺失');
   if(orderIds){const value=input.lookup_ids?input.lookup_ids.join(','):'';if(orderIds.value!==value){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(orderIds,value);orderIds.dispatchEvent(new Event('input',{bubbles:true}));orderIds.dispatchEvent(new Event('change',{bubbles:true}));orderIds.blur();await new Promise(r=>setTimeout(r,200));}}
   const dates=input.lookup_ids?[request.request.data.orderCreateTimeBegin,request.request.data.orderCreateTimeEnd]:[input.date+' 00:00:00',input.date+' 23:59:59'];
   for(let i=0;i<2;i++){
    fields[i].focus?.();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(fields[i],dates[i]);
    fields[i].dispatchEvent(new Event('input',{bubbles:true}));fields[i].dispatchEvent(new Event('change',{bubbles:true}));
    fields[i].dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));fields[i].blur();
    // The range component commits both endpoints asynchronously; submitting
    // the second field in the same turn can restore the old first endpoint.
    await new Promise(resolve=>setTimeout(resolve,200));
   }
   await new Promise(resolve=>setTimeout(resolve,200));
   const size=document.querySelector('.jd-pagination__sizes');
   if(!size&&input.verified_page_size!==pageSize)throw new Error('订单每页条数控件缺失，且没有同页已验证的分页大小');
   if(size&&!size.textContent.replace(/\s/g,'').includes(pageSize+'条/页')){
    const combo=document.querySelector('.jd-pagination__sizes [role="combobox"]');
    if(!combo)throw new Error('订单每页条数下拉框缺失');combo.click();
    let option;const until=Date.now()+2000;
    do{const list=document.getElementById(combo.getAttribute('aria-controls'));option=Array.from(list?.querySelectorAll('[role="option"]') || []).find(e=>e.textContent.replace(/\s/g,'')===pageSize+'条/页');if(option)break;await new Promise(r=>setTimeout(r,50));}while(Date.now()<until);
    if(!option)throw new Error('官方50条选项不可用');option.click();
    await new Promise(resolve=>setTimeout(resolve,200));
   }
   // Changing the official page-size control can submit the exact query.
   // Do not issue a second identical request if it has already started.
   if(matchingStarted)return await pending;
   const buttons=Array.from(document.querySelectorAll('button')).filter(e=>e.textContent.trim()==='查询');
   if(buttons.length!==1 || buttons[0].disabled)throw new Error('订单查询按钮未就绪');buttons[0].click();
  }else{
   if(!document.querySelector('.jd-pagination__sizes')?.textContent.replace(/\s/g,'').includes(pageSize+'条/页'))throw new Error('订单每页条数改变，请重新读取第1页');
   if(fields[0].value!==input.date+' 00:00:00' || fields[1].value!==input.date+' 23:59:59')throw new Error('订单翻页日期改变，请重新读取第1页');
   const next=document.querySelector('button.btn-next[aria-label="下一页"]');
   if(!next || next.disabled || next.getAttribute('aria-disabled')==='true')throw new Error('订单下一页不可用');next.click();
  }
  return await pending;
 }catch(error){return {error:'订单读取失败：'+String(error?.message || error)};}
 finally{clearTimeout(timer);if(XHR.prototype.open===wrappedOpen)XHR.prototype.open=open;if(XHR.prototype.send===wrappedSend)XHR.prototype.send=send;}
}
async function runJDOrderJob(job){
 const template=await (await fetch(chrome.runtime.getURL('order-template.json'))).json();
 const input=validateOrderJob(job,template),created=[],deadline=Date.now()+55000;
 async function execute(tabId,func,args=[],timeout=4000){
  timeout=Math.min(timeout,Math.max(1,deadline-Date.now()));
  let timer;try{
   const result=await Promise.race([chrome.scripting.executeScript({target:{tabId},world:'MAIN',injectImmediately:true,func,args}),new Promise((_,fail)=>{timer=setTimeout(()=>{const error=new Error('订单页面执行超时：'+func.name);error.orderTimeout=true;fail(error);},timeout);})]);
   const value=result?.[0]?.result;if(!value || typeof value!=='object')throw new Error('订单页面未返回：'+func.name);if(value.error)throw new Error(value.error);return value;
  }finally{clearTimeout(timer);}
 }
 async function ready(tab,expected){const start=Date.now();do{const current=await chrome.tabs.get(tab.id);if(current.discarded||current.frozen){const error=new Error('订单任务页已暂停');error.orderTimeout=true;throw error;}if(current.status==='complete'&&current.url&&current.url!=='about:blank'){if(current.url.split('?')[0]!==expected.split('?')[0])throw new Error('订单任务页跳离官方目标；实际路径='+new URL(current.url).origin+new URL(current.url).pathname);return current;}await new Promise(r=>setTimeout(r,200));}while(Date.now()-start<12000);throw new Error('订单页面未就绪');}
 const store=job.expected_store.store_key,diagnostics=[];
 async function discardLookup(){
  const pool=jdOrderLookupPages.get(store);if(!pool)return;
  clearTimeout(pool.timer);jdOrderLookupPages.delete(store);
  // Every pool entry originates from our own tabs.create, never user tabs.
  await chrome.tabs.remove(pool.id);
 }
 async function lookupPage(){
  const pool=jdOrderLookupPages.get(store);
  if(pool){clearTimeout(pool.timer);try{const tab=await chrome.tabs.get(pool.id);if(tab.status==='complete'&&!tab.discarded&&!tab.frozen&&tab.url?.split('?')[0]===JD_ORDER_PAGE.split('?')[0])return tab;}catch(_){}await discardLookup();}
  const tab=await chrome.tabs.create({url:JD_ORDER_PAGE,active:false});
  jdOrderLookupPages.set(store,{id:tab.id});
  await chrome.tabs.update(tab.id,{autoDiscardable:false});
  return await ready(tab,JD_ORDER_PAGE);
 }
 async function prepareLookup(tab){
  let state=await execute(tab.id,prepareJDOrderPage,[],18000);
  const current=await chrome.tabs.get(tab.id);
  // The official micro-app can defer initial date controls in a never-visible
  // tab. Initialize only our own tab, then restore the previous selection
  // before any order request. Never focus a browser window or user report.
  if(!state.ready&&state.field_count===0&&state.query_count===1&&state.visibility==='hidden'&&!current.active&&Number.isInteger(current.windowId)&&deadline-Date.now()>10000){
   const previous=(await chrome.tabs.query({active:true,windowId:current.windowId}))[0];
   if(previous&&previous.id!==tab.id){
    let restored=false;
    try{await chrome.tabs.update(tab.id,{active:true});state=await execute(tab.id,prepareJDOrderPage,[],18000);}
    finally{
     try{const now=await chrome.tabs.get(tab.id);if(now.active){await chrome.tabs.get(previous.id);await chrome.tabs.update(previous.id,{active:true});restored=true;}}catch(_){}
     diagnostics.push({stage:'order-page-visible-initialization',tab_id:tab.id,previous_tab_restored:restored});
     if((await chrome.tabs.get(tab.id)).active)throw new Error('未能恢复原标签页，停止订单查询');
    }
   }
  }
  diagnostics.push({stage:'order-page-prepared',tab_id:tab.id,ready:!!state.ready,visibility:state.visibility,active:!!(await chrome.tabs.get(tab.id)).active});
  if(!state.ready)throw new Error('订单报表控件未就绪；date_fields='+state.field_count+'；query_buttons='+state.query_count);
 }
 try{
  const infoTabs=await chrome.tabs.query({url:'https://shop.jd.com/jdm/seller/shop/information*'});
  let info=infoTabs.filter(t=>!t.discarded && t.status==='complete').sort((a,b)=>b.id-a.id)[0];
  if(!info){info=await chrome.tabs.create({url:JD_ORDER_SHOP_PAGE,active:false});created.push(info.id);info=await ready(info,JD_ORDER_SHOP_PAGE);}
  let merchant=null;const until=Date.now()+10000;
  do{try{merchant=await execute(info.id,readJDOrderMerchant);if(merchant)break;}catch(_){}await new Promise(r=>setTimeout(r,200));}while(Date.now()<until);
  if(!merchant || merchant.store_key!==job.expected_store.store_key)throw new Error('京麦商家与指定商智商城不一致或身份页未就绪');
  const tabs=input.lookup_ids?[]:await chrome.tabs.query({url:'https://shop.jd.com/jdm/trade/orders/order-list*'});
  const lookupOwned=new Set([...jdOrderLookupPages.values()].map(p=>p.id));
  let tab=input.lookup_ids?await lookupPage():tabs.filter(t=>!lookupOwned.has(t.id)&&!t.discarded&&!t.frozen&&t.status==='complete').sort((a,b)=>b.id-a.id)[0];
  // Keep a newly opened report page available for the next read-only page.
  if(!tab){tab=await chrome.tabs.create({url:JD_ORDER_PAGE,active:false});tab=await ready(tab,JD_ORDER_PAGE);}
  const cacheKey=job.expected_store.store_key+'|'+input.date;
  const prior=jdOrderLastPage.get(cacheKey);
  if(input.page>1 && (!prior || prior.tab!==tab.id || prior.page!==input.page-1 || prior.merchant!==merchant.merchant_id))throw new Error('订单分页会话变化，请先重新读取第1页；不跳页或猜测覆盖');
  let result;
  for(let attempt=0;attempt<2;attempt++){
   try{
    if(input.lookup_ids)await prepareLookup(tab);
    result=await execute(tab.id,orderNativeRead,[{...input,merchant_id:merchant.merchant_id,verified_page_size:input.lookup_ids?jdOrderLookupPages.get(store)?.pageSize:undefined}],28000);break;
   }
   catch(error){
    // Only execution timeout on an owned exact-ID context is recoverable.
    // Destroying it cancels pending hooks; no retry of 605/business rejection.
    if(!input.lookup_ids||!error.orderTimeout||attempt!==0)throw error;
    if(deadline-Date.now()<12000)throw error;
    await discardLookup();diagnostics.push({stage:'order-page-recovery',attempt:1,reason:'execution-timeout'});
    tab=await lookupPage();
    const current=await execute(info.id,readJDOrderMerchant);
    if(current.store_key!==merchant.store_key||current.merchant_id!==merchant.merchant_id)throw new Error('订单恢复期间店铺身份改变');
   }
  }
  const merchantAfter=await execute(info.id,readJDOrderMerchant);
  if(merchantAfter.store_key!==merchant.store_key || merchantAfter.merchant_id!==merchant.merchant_id)throw new Error('订单读取期间店铺身份改变');
  if(input.lookup_ids&&jdOrderLookupPages.get(store)?.id===tab.id)jdOrderLookupPages.get(store).pageSize=50;
  if(!input.lookup_ids)jdOrderLastPage.set(cacheKey,{tab:tab.id,page:input.page,merchant:merchant.merchant_id});
  const merchantBinding=JSON.parse(result.text).data.venderId==null?'same_origin_official_shop_information':'response_vendor_and_official_information';
  return {...result,diagnostics,identity:{...merchantAfter,identity_kind:'official_shop_information_and_mall_link',merchant_identity_kind:merchant.kind,merchant_identity_anchor:JD_ORDER_SHOP_PAGE,merchant_binding:merchantBinding},source:'registered-api',transport:'registered-api',execution_page:tab.url};
 }catch(error){if(input.lookup_ids)try{await discardLookup();}catch(_){}throw error;}
 finally{
  const pool=input.lookup_ids&&jdOrderLookupPages.get(store);
  if(pool){clearTimeout(pool.timer);pool.timer=setTimeout(()=>{if(jdOrderLookupPages.get(store)===pool)discardLookup().catch(()=>{});},120000);}
  for(const id of created)try{await chrome.tabs.remove(id);}catch(_){}
 }
}
if(typeof module!=='undefined')module.exports={validateOrderJob,readJDOrderMerchant,prepareJDOrderPage,orderNativeRead,runJDOrderJob};
