/* Capture only the native source-dimension dictionary during page initialization. */
function installJDDimensionCapture(){
  if(location.origin!=='https://jdsz.jd.com' || location.pathname!=='/szweb/view/view-source/view-flow.html')return;
  const slot='__shopdataJDDimension',endpoint='https://szgateway.jd.com/api/lowcode/common/getDimensionTree.ajax';
  globalThis.__shopdataJDDimensionStarted=Date.now();
  const originalFetch=globalThis.fetch,proto=XMLHttpRequest.prototype,open=proto.open,send=proto.send,requests=new WeakMap();
  let active=true,timer;
  function identity(){const anchors=[...new Set([...document.querySelectorAll('a[href]')].map(a=>a.href.split(/[?#]/)[0]).filter(h=>/^https:\/\/mall\.jd\.com\/index-\d+\.html$/.test(h)))];return anchors.length===1?anchors[0]:null;}
  const matches=(raw,method)=>{
    try{const url=new URL(raw,location.origin);return String(method).toUpperCase()==='GET' && url.origin+url.pathname===endpoint &&
      url.searchParams.get('startDimName')==='jdr_sch_traffic_cha_last_field_src_rmad_sz_1' && url.searchParams.get('endDimName')==='jdr_sch_traffic_cha_last_field_src_rmad_sz_4';}catch(_){return false;}
  };
  function stop(){active=false;clearTimeout(timer);if(globalThis.fetch===wrappedFetch)globalThis.fetch=originalFetch;if(proto.open===wrappedOpen)proto.open=open;if(proto.send===wrappedSend)proto.send=send;}
  function save(status,text,timestamp,startIdentity){
    if(!active || status!==200 || typeof text!=='string' || !text.length || text.length>2000000)return;
    try{if(JSON.parse(text).header?.code!==0)return;}catch(_){return;}
    if(!startIdentity || startIdentity!==identity()){globalThis[slot]={capture_status:'identity_not_verified',captured_at:Date.now()};stop();return;}
    globalThis[slot]={status,text,method:'GET',url:endpoint,request_timestamp:timestamp,source:'native-page-dimension-response',captured_at:Date.now(),identity_anchor:startIdentity};stop();
  }
  const wrappedFetch=function(resource,options){
    const url=typeof resource==='string' || resource instanceof URL?String(resource):resource?.url;
    const selected=active && matches(url,options?.method || resource?.method || 'GET'),timestamp=new Date().toISOString();
    const startIdentity=selected?identity():null;
    const result=originalFetch.apply(this,arguments);
    if(selected)Promise.resolve(result).then(async response=>{try{save(response.status,await response.clone().text(),timestamp,startIdentity);}catch(_){}},()=>{});
    return result;
  };
  const wrappedOpen=function(method,url){requests.set(this,{method,url});return open.apply(this,arguments);};
  const wrappedSend=function(){const entry=requests.get(this);if(active && entry && matches(entry.url,entry.method)){
    const timestamp=new Date().toISOString(),startIdentity=identity();this.addEventListener('loadend',()=>{try{save(this.status,this.responseType==='json'?JSON.stringify(this.response):this.responseType==='' || this.responseType==='text'?this.responseText:null,timestamp,startIdentity);}catch(_){}},{once:true});
  }return send.apply(this,arguments);};
  globalThis.fetch=wrappedFetch;proto.open=wrappedOpen;proto.send=wrappedSend;timer=setTimeout(stop,60000);
}
function readJDDimensionCapture(){
  const result=globalThis.__shopdataJDDimension;
  const anchors=[...new Set([...document.querySelectorAll('a[href]')].map(a=>a.href.split(/[?#]/)[0]).filter(h=>/^https:\/\/mall\.jd\.com\/index-\d+\.html$/.test(h)))];
  if(!result || Date.now()-result.captured_at>600000){
    const entries=typeof performance!=='undefined'?performance.getEntriesByType('resource').filter(e=>{
      try{return new URL(e.name).pathname==='/api/lowcode/common/getDimensionTree.ajax';}catch(_){return false;}
    }).slice(-3).map(e=>{const url=new URL(e.name);return {endpoint:url.origin+url.pathname,startDimName:url.searchParams.get('startDimName'),endDimName:url.searchParams.get('endDimName')};}):[];
    return {capture_status:result?'expired':'not_observed',observer_started:globalThis.__shopdataJDDimensionStarted || null,resource_metadata:entries};
  }
  if(!result.identity_anchor || anchors.length!==1 || result.identity_anchor!==anchors[0])return {capture_status:'identity_not_verified'};
  return result;
}
if(typeof location!=='undefined')installJDDimensionCapture();
if(typeof module!=='undefined')module.exports={installJDDimensionCapture,readJDDimensionCapture};
