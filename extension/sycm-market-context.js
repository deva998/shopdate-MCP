// Diagnostics only: inspect an already open official market page. No fetch, UI,
// cookies, storage, downloaded script execution or business writes.
function pageSycmMarketContext(expectedPath) {
  const paths=['/mc/free/market_rank','/mc/free/market_insight','/mc/free/search_rank','/mc/free/channel_goods','/mc/free/class_dig','/mc/free/class_analysis'];
  if(!paths.includes(expectedPath)||location.origin!=='https://sycm.taobao.com'||location.pathname!==expectedPath)return {error:'Matching official market page is not open'};
  const safeKeys=new Set(['location','lowcodeVersion','cateId','cateFlag','dateType','dateRange','queryType','source','age','crowd','price','priceSeg','priceSegId','minPrice','maxPrice','rankType','sellerType','styleId','style','styles','trendType','trendId','tag','tagId','tagName','priceRange','priceRangeId','avgPrice','page','pageSize','order','orderBy','marketVersion','type','context','attributeType','heatValue','sortType','indType','device','kwType','version','pageCode']);
  const write=/(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)/i;
  const entries=performance.getEntriesByType('resource').slice(-500),scripts=new Set(),requests=[];
  for(const raw of [...Array.from(document.scripts||[],s=>s.src),...entries.map(e=>e.name)]){
    try{const u=new URL(raw);if(u.origin==='https://g.alicdn.com'&&u.pathname.startsWith('/dt/')&&u.pathname.endsWith('.js'))scripts.add(u.origin+u.pathname);}catch(_){}
  }
  for(const e of entries){
    try{const u=new URL(e.name);if(u.origin!=='https://sycm.taobao.com'||!u.pathname.endsWith('.json')||write.test(u.pathname))continue;
      const filters={};for(const [key,value] of u.searchParams){if(safeKeys.has(key)&&value.length<=200)filters[key]=value;}
      requests.push({path:u.pathname,query_keys:[...new Set(u.searchParams.keys())],filters});
    }catch(_){}
  }
  const frames=[];for(const frame of Array.from(document.querySelectorAll?.('iframe')||[])){try{const u=new URL(frame.src);if(u.protocol==='https:')frames.push({origin:u.origin,path:u.pathname,query_keys:[...new Set(u.searchParams.keys())]});}catch(_){}}
  const visible_labels=['行业趋势赛道','AI趋势挖掘','趋势标签','平均件单价','市场趋势'].filter(s=>(document.body?.innerText||'').includes(s));
  return {status:200,text:JSON.stringify({page:location.origin+location.pathname,scripts:[...scripts],requests,frames,visible_labels,scope:'existing_page_diagnostics_not_business_statistics',credentials_omitted:true})};
}
