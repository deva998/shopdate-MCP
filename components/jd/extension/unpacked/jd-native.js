/* Serialized in MAIN world. Observe only page-originated, registered requests. */
function jdNativeObserver(input) {
  const slot='__shopdataJDNativeObserver';
  const active=globalThis[slot];
  if(input.op==='clear'){
    if(active?.id===input.id){active.cleanup();delete globalThis[slot];}
    return {cleared:true};
  }
  function identity(){
    if(location.origin+location.pathname!==input.page)throw new Error('报表页面已变化');
    const links=[...new Map([...document.querySelectorAll('a[href]')]
      .filter(a=>/^https:\/\/mall\.jd\.com\/index-\d+\.html(?:[?#].*)?$/.test(a.href) && (a.innerText || a.textContent || '').trim())
      .map(a=>[a.href.split(/[?#]/)[0],a])).values()];
    if(links.length!==1 || links[0].href.split(/[?#]/)[0]!=='https://mall.jd.com/index-'+String(input.store).replace('jd:mall:','')+'.html')throw new Error('页面店铺身份不匹配');
    return {platform:'jd',store_key:input.store,name:(links[0].innerText || links[0].textContent).trim(),identity_kind:'page_mall_link',identity_anchor:links[0].href.split(/[?#]/)[0]};
  }
  if(input.op==='read'){
    identity();
    if(!active || active.id!==input.id)throw new Error('原生响应监听任务不存在或已超时');
    return {result:active.result,error:active.error || null};
  }
  if(input.op!=='install')throw new Error('未知监听操作');
  if(active)throw new Error('已有原生取数任务，请等待完成');
  const registered={
    'https://jdsz.jd.com/szweb/view/tradeAnalysis/tradeSummary.html':'https://szgateway.jd.com/api/lowcode/tradeSummary/summary/getSummary.ajax',
    'https://jdsz.jd.com/szweb/view/product/productDetail.html':'https://szgateway.jd.com/api/lowcode/productDetail/table/productTable.ajax',
    'https://jdsz.jd.com/szweb/view/view-source/view-flow.html':'https://szgateway.jd.com/api/lowcode/flowSource/sourceTable/table.ajax'};
  if(registered[input.page]!==input.endpoint)throw new Error('接口未登记');
  const issued=Date.parse(input.requested_after);
  if(!Number.isFinite(issued) || issued>Date.now())throw new Error('任务时间无效');
  identity();
  const verified=new Date().toISOString(),started=Date.now();
  const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v && typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
  function matches(url,method,body){
    try{return new URL(url,location.origin).href===input.endpoint && String(method).toUpperCase()==='POST' && stable(JSON.parse(body))===stable(input.expected);}catch(_){return false;}
  }
  function requestIdentity(url,method){
    try{
      if(new URL(url,location.origin).href!==input.endpoint || String(method).toUpperCase()!=='POST')return true;
      identity();return true;
    }catch(error){state.error=String(error.message || error);return false;}
  }
  const state={id:input.id,result:null,error:null};
  const originalFetch=globalThis.fetch,proto=XMLHttpRequest.prototype,originalOpen=proto.open,originalSend=proto.send,requests=new WeakMap();
  function save(status,text,timestamp){
    if(globalThis[slot]!==state || state.result || Date.parse(timestamp)<Date.parse(verified))return;
    try{
      const actual=identity();
      if(typeof text!=='string' || !text.length || text.length>20000000)throw new Error('原生响应为空或超过20MB');
      if(!Number.isInteger(status) || status<100)throw new Error('原生请求尚未完成');
      state.result={status,text,identity:actual,identity_verified_at:verified,request_timestamp:timestamp,
        source:'native-page-response',capture_ms:Date.now()-started};
    }catch(error){state.error=String(error.message || error);}
  }
  const wrappedFetch=function(resource,options){
    const timestamp=new Date().toISOString();
    let selected=Promise.resolve(false);
    try{
      const url=typeof resource==='string' || resource instanceof URL?String(resource):resource.url;
      const method=options?.method || resource?.method || 'GET';
      const correctIdentity=requestIdentity(url,method);
      if(correctIdentity && options?.body!==undefined)selected=Promise.resolve(matches(url,method,options.body));
      else if(correctIdentity && resource?.clone && url===input.endpoint && method.toUpperCase()==='POST')selected=resource.clone().text().then(body=>matches(url,method,body),()=>false);
    }catch(_){}
    const response=originalFetch.apply(this,arguments);
    Promise.resolve(response).then(async value=>{
      if(await selected){try{save(value.status,await value.clone().text(),timestamp);}catch(error){state.error=String(error);}}
    },()=>{}).catch(()=>{});
    return response;
  };
  const wrappedOpen=function(method,url){requests.set(this,{method,url});return originalOpen.apply(this,arguments);};
  const wrappedSend=function(body){
    const info=requests.get(this);
    if(info && requestIdentity(info.url,info.method) && matches(info.url,info.method,body)){
      const timestamp=new Date().toISOString();
      this.addEventListener('loadend',()=>{
        try{save(this.status,this.responseType==='json'?JSON.stringify(this.response):this.responseType==='' || this.responseType==='text'?this.responseText:null,timestamp);}catch(error){state.error=String(error);}
      },{once:true});
    }
    return originalSend.apply(this,arguments);
  };
  let timer;
  state.cleanup=()=>{
    clearTimeout(timer);
    if(globalThis.fetch===wrappedFetch)globalThis.fetch=originalFetch;
    if(proto.open===wrappedOpen)proto.open=originalOpen;
    if(proto.send===wrappedSend)proto.send=originalSend;
    state.result=null;
  };
  globalThis[slot]=state;globalThis.fetch=wrappedFetch;proto.open=wrappedOpen;proto.send=wrappedSend;
  timer=setTimeout(()=>{if(globalThis[slot]===state){state.cleanup();delete globalThis[slot];}},Math.min(130000,Math.max(10,Number(input.timeout_ms)||120000)));
  return {identity_verified_at:verified,identity:identity()};
}
if(typeof module!=='undefined')module.exports={jdNativeObserver};
