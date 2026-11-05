// Observe newly generated resource descriptors only. No fetch/XHR patching,
// credentials, storage, downloaded code execution or business/UI changes.
function pageSycmMarketObserve(expectedPath,action) {
  const paths=['/mc/free/market_rank','/mc/free/market_insight','/mc/free/search_rank','/mc/free/channel_goods','/mc/free/class_dig','/mc/free/class_analysis'];
  if(location.origin!=='https://sycm.taobao.com'||location.pathname!==expectedPath||!paths.includes(expectedPath)||!['start','read','stop'].includes(action))return {error:'Unsupported market observation page/action'};
  const key='__shopdateMarketCaptureV1',result=x=>({status:200,text:JSON.stringify(x)});
  if(action!=='start'){
    const state=window[key];if(!state)return result({status:'not_armed',records:[]});
    state.observer.disconnect();clearTimeout(state.timer);delete window[key];
    return result({status:action==='stop'?'stopped':'captured',records:action==='stop'?[]:state.records,started_at:state.started,ended_at:new Date().toISOString(),scope:'diagnostic_request_descriptors_not_statistics',credentials_omitted:true});
  }
  if(window[key]){window[key].observer.disconnect();clearTimeout(window[key].timer);delete window[key];}
  const hosts=new Set(['sycm.taobao.com','qn.taobao.com','h5api.m.taobao.com','g.alicdn.com']);
  const safe=new Set(['api','domainCode','pageCode','pageName','sceneCode','cateId','categoryId','firstCateId','leafCateId','cateFlag','dateType','dateRange','queryType','source','age','crowd','price','priceSeg','priceSegId','minPrice','maxPrice','rankType','sellerType','styleId','styleName','style','styles','trendType','trendId','trackId','trackName','tag','tagId','tagName','priceRange','priceRangeId','avgPrice','page','pageSize','order','orderBy','marketVersion','type','context','attributeType','heatValue','sortType','indType','device','kwType','version','location']);
  const write=/(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)/i;
  const state={records:[],started:new Date().toISOString()};
  function fields(value,output,depth=0){
    if(!value||typeof value!=='object'||depth>3)return;
    for(const [k,v] of Object.entries(value)){
      if(safe.has(k)&&['string','number','boolean'].includes(typeof v)&&String(v).length<=200&&!/[?&](?:token|sign|signature|x5sec)/i.test(String(v)))output[k]=v;
      else if(['params','data','query','filter'].includes(k)){
        if(typeof v==='string'&&v.length<=20000){try{fields(JSON.parse(v),output,depth+1);}catch(_){}}
        else fields(v,output,depth+1);
      }
    }
  }
  state.observer=new PerformanceObserver(list=>{
    for(const e of list.getEntries()){
      if(state.records.length>=200){state.observer.disconnect();break;}
      try{const u=new URL(e.name);if(u.protocol!=='https:'||u.username||u.password||!hosts.has(u.hostname)||write.test(u.pathname))continue;
        if(!['fetch','xmlhttprequest','script'].includes(e.initiatorType)&&!(/\.(?:js|json|html?)$/.test(u.pathname)||u.pathname.startsWith('/h5/')))continue;
        const filters={};fields(Object.fromEntries(u.searchParams),filters);
        state.records.push({origin:u.origin,path:u.pathname,query_keys:[...new Set(u.searchParams.keys())].filter(k=>k.length<=100),filters,initiator_type:e.initiatorType||null,...(u.hostname==='g.alicdn.com'&&!u.search&&u.pathname.endsWith('.js')?{public_script:u.origin+u.pathname}:{})});
      }catch(_){}
    }
  });
  state.observer.observe({type:'resource',buffered:false});
  state.timer=setTimeout(()=>{state.observer.disconnect();if(window[key]===state)delete window[key];},120000);
  window[key]=state;
  return result({status:'armed',started_at:state.started,expires_after_seconds:120,maximum_records:200,scope:'diagnostic_request_descriptors_not_statistics',credentials_omitted:true});
}
