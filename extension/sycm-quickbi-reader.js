// Fixed native QuickBI definition read. Auth values never leave this function.
async function pageQuickbiDefinition(viewUrl, readStatistics=false) {
  try {
    const u=new URL(viewUrl),id=u.searchParams.get('pageId');
    if(u.origin!=='https://bi.taobao.com'||u.pathname!=='/token3rd/dashboard/view/pc.htm'||u.username||u.password||!id||!/^[A-Za-z0-9_-]{1,100}$/.test(id))return {error:'Unregistered native BI report URL'};
    const response=await fetch(viewUrl,{credentials:'include',signal:AbortSignal.timeout(45000)});
    if(response.status!==200)return {error:'Native BI view HTTP '+response.status};
    const html=await response.text();
    if(html.length>5000000)return {error:'Native BI view exceeds bounded source limit'};
    const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);
    const block=scripts.find(s=>/window\.pageConfig\s*=/.test(s))||'';
    function token(name){
      const re=new RegExp('(?:["\\\']?'+name+'["\\\']?)\\s*:\\s*("(?:\\\\.|[^"\\\\])*"|\'(?:\\\\.|[^\'\\\\])*\')');
      const m=block.match(re);if(!m)return '';
      if(m[1][0]==='"'){try{return JSON.parse(m[1]);}catch(_){return '';}}
      return m[1].slice(1,-1).replace(/\\u([a-f0-9]{4})/gi,(_,n)=>String.fromCharCode(parseInt(n,16))).replace(/\\'/g,"'").replace(/\\\\/g,'\\');
    }
    const csrf=token('csrfToken'),access=token('accessToken');
    const headers={'x-requested-with':'XMLHttpRequest','X-GW-Referer':viewUrl};
    if(csrf)headers['x-csrf-token']=csrf;if(access)headers['x-dlpj']=access;
    const result=await fetch('https://bi.taobao.com/api/v2/dashboard/'+encodeURIComponent(id)+'?viewType=view',{method:'GET',credentials:'include',headers,signal:AbortSignal.timeout(45000)});
    const definitionText=await result.text();
    const reply={status:result.status,text:definitionText,auth_context_used:{csrf_token:!!csrf,access_token:!!access},phase:'definition'};
    if(readStatistics){
      // Official qbi 4.3.167: module 2767 field/paging/filter/queryConfig;
      // module 293 sends string-valued form fields, preserving native view auth.
      if(id!=='6c681235-8bac-4df2-8a50-e9ed0efa641b')return {error:'Statistics supported only for registered apparel report'};
      const definition=JSON.parse(definitionText),components=definition.data?.components;
      if(!definition.success||!Array.isArray(components))return {error:'Statistics require a valid native definition'};
      const decode=v=>typeof v==='string'?JSON.parse(v):v;
      const chart=components.find(c=>c.componentType===53&&c.componentId==='8a76f2cd-d181-48fb-8428-f9651e568d28');
      const control=components.find(c=>c.componentType===60),config=decode(control?.componentContent)?.modelConfig?.fieldConfigs?.[0];
      const defaults=config?.config?.defaultConfig;
      if(!chart||!['startTimeConfig','endTimeConfig'].every(k=>defaults?.[k]?.timeSettingType==='relative'&&defaults[k].relativeTimeValue===-2)||!config.graphMappings?.some(m=>m.pathId==='185cbd005a'&&m.cubeId==='9864dcd8-f289-4582-a4da-f0acc1b8c13b'))return {error:'Official apparel default date contract changed'};
      const input=decode(chart.queryInput);
      if(input.sourceId!=='9864dcd8-f289-4582-a4da-f0acc1b8c13b')return {error:'Official apparel cube contract changed'};
      const rows=input.area.filter(a=>a.queryAxis==='row').flatMap(a=>a.columnList),measures=input.area.filter(a=>a.queryAxis==='column').flatMap(a=>a.columnList);
      if(rows.length!==1||rows[0].levels?.[0]?.pathId!=='185cbd005a'||rows[0].levels[0].type!=='dateRegion'||measures.length!==2||measures.map(m=>m.pathId).join(',')!=='0d5239fc1c,6cc25324bb'||measures.some(m=>m.useaggregator!=='sum'))return {error:'Official apparel field contract changed'};
      const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const day=new Date(Date.parse(today+'T00:00:00Z')-2*86400000).toISOString().slice(0,10),cube=input.sourceId;
      const fields=[{guid:rows[0].uuid,fid:'185cbd005a',areaType:'row',dateTrunc:'day'},...measures.map(m=>({guid:m.uuid,fid:m.pathId,areaType:'column',aggregate:'sum'}))];
      const packet={reportId:id,dataType:'pivot',componentId:chart.componentId,configs:[{type:'field',cubeId:cube,config:{fields}},{type:'paging',cubeId:cube,config:{limit:500,offset:0}},{type:'beforeAggregateCondition',cubeId:cube,config:{logicalOperator:'AND',conditions:['greaterThanOrEqual','lessThanOrEqual'].map(op=>({field:{fid:'185cbd005a',dateTrunc:'day'},functionalOperator:op,args:[{valueType:'string',value:day.replace(/-/g,'')}]}))}},{type:'queryConfig',cubeId:cube,config:{needCount:false,queryCount:false,queryDetail:false}}]};
      const body=new URLSearchParams({olapQueryParam:JSON.stringify(packet),componentId:chart.componentId,reportId:id}).toString();
      const statistics=await fetch('https://bi.taobao.com/api/v2/biPlatform/query/byQueryParam',{method:'POST',credentials:'include',headers:{...headers,'content-type':'application/x-www-form-urlencoded; charset=UTF-8'},body,signal:AbortSignal.timeout(45000)});
      reply.statistics={status:statistics.status,text:await statistics.text(),requested_date:day,date_rule:'official_default_minus_2_days',request_date_format:'YYYYMMDD',row_limit:500,component_id:chart.componentId};
      reply.phase='statistics';
    }
    return reply;
  }catch(error){return {error:'Native BI definition read failed: '+error.name};}
}
