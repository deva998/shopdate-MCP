/* Exact single-report allowlist. Shared by browser worker and offline tests. */
function stable(value) {
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stable(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
const DEFAULT_REPORT={page:'https://jdsz.jd.com/szweb/view/tradeAnalysis/tradeSummary.html',endpoint:'https://szgateway.jd.com/api/lowcode/tradeSummary/summary/getSummary.ajax'};
function registeredReport(contract){
  return [DEFAULT_REPORT,
    {page:'https://jdsz.jd.com/szweb/view/product/productDetail.html',endpoint:'https://szgateway.jd.com/api/lowcode/productDetail/table/productTable.ajax'},
    {page:'https://jdsz.jd.com/szweb/view/view-source/view-flow.html',endpoint:'https://szgateway.jd.com/api/lowcode/flowSource/sourceTable/table.ajax'}
  ].some(known=>known.page===contract?.page && known.endpoint===contract?.endpoint);
}
function allowedJob(job, expected, contract=DEFAULT_REPORT) {
  try {
    return registeredReport(contract) && job.launch === contract.page
      && job.url === contract.endpoint
      && job.method === 'POST' && !job.cookie && !job.account
      && stable(JSON.parse(job.body)) === stable(expected);
  } catch (_) { return false; }
}
function realtimeRequest(job,contract){
  let body;try{body=JSON.parse(job.body);}catch(_){throw new Error('实时请求体无效');}
  const since=Date.parse(job.requested_after),now=Date.now();
  if(!Number.isFinite(since) || now-since>60000 || since>now+5000)throw new Error('实时任务已过期');
  const china=new Date(since+8*3600000).toISOString().slice(0,19).replace('T',' '),day=china.slice(0,10);
  const prior=new Date(Date.parse(day+'T00:00:00Z')-86400000).toISOString().slice(0,10);
  if(new Date(now+8*3600000).toISOString().slice(0,10)!==day)throw new Error('实时任务跨日');
  const end=Date.parse(String(body.endDate).replace(' ','T')+'+08:00');
  if(!Number.isFinite(end) || end>since || since-end>5000 || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(body.endDate || ''))throw new Error('实时截止时间无效');
  const expected={...contract.template,startDate:day+' 00:00:00',endDate:body.endDate,compareStartDate:prior+' 00:00:00',compareEndDate:prior+body.endDate.slice(10)};
  if(!allowedJob(job,expected,contract))throw new Error('仅允许已登记实时范围、渠道和指标');
  return expected;
}
function reportRequest(job, template, contract=DEFAULT_REPORT) {
  let actual;
  try { actual=JSON.parse(job.body); } catch (_) { throw new Error('任务请求体不是 JSON。'); }
  const day=actual?.startDate;
  const time=typeof day==='string' && /^\d{4}-\d{2}-\d{2}$/.test(day) ? Date.parse(day+'T00:00:00Z') : NaN;
  if(!Number.isFinite(time) || new Date(time).toISOString().slice(0,10)!==day) throw new Error('任务日期无效。');
  const previous=new Date(time-86400000).toISOString().slice(0,10);
  const expected={...template,startDate:day,endDate:day,compareStartDate:previous,compareEndDate:previous};
  if(!allowedJob(job,expected,contract)) throw new Error('仅允许已验证报表、单日、前一日对比及固定渠道和指标。');
  return expected;
}
function trafficTreeRequest(job,contract){
  const scope=job.traffic_scope;
  if(!scope || Object.keys(scope).sort().join(',')!=='level,page,parents' || !Number.isInteger(scope.level) || scope.level<1 || scope.level>4 ||
    !Number.isInteger(scope.page) || scope.page<1 || scope.page>1000 || !Array.isArray(scope.parents) || scope.parents.length!==scope.level-1 ||
    scope.parents.some(id=>typeof id!=='string' || !/^[A-Za-z0-9_]{1,32}$/.test(id)))throw new Error('来源树范围无效');
  const field='jdr_sch_traffic_cha_last_field_src_rmad_sz_'+scope.level;
  const template={...contract.template,groups:[field],attributes:[field],pageIndex:scope.page};
  scope.parents.forEach((id,index)=>{template['flowSrcId'+(index+1)]=[id];});
  return reportRequest(job,template,contract);
}
function selectReportTab(tabs, tabId) {
  if (!Number.isInteger(tabId)) throw new Error('未指定当前标签页，请在商智交易概况页打开测试插件。');
  const tab = tabs.find(t => t.id === tabId);
  if (!tab) throw new Error('找不到打开插件时的标签页，请回到商智交易概况页重新打开插件。');
  let url;
  try { url = new URL(tab.url); } catch (_) {}
  if (!url || url.origin !== 'https://jdsz.jd.com' || url.pathname !== '/szweb/view/tradeAnalysis/tradeSummary.html') {
    throw new Error('当前页不是商智交易概况。请先切换到交易概况页，再打开插件。');
  }
  if (tab.discarded) throw new Error('当前商智页已休眠，请切回该页唤醒后再执行。');
  if (tab.status !== 'complete') throw new Error('当前商智页还在加载，请等页面加载完成后再执行。');
  return tab;
}
function allowedCapture(capture, pending, expected) {
  return !!pending && capture.tabId === pending.tabId && allowedJob({
    launch: 'https://jdsz.jd.com/szweb/view/tradeAnalysis/tradeSummary.html',
    url: capture.url, method: capture.method, body: capture.body
  }, expected);
}
function selectFreshEntry(entries, expected, requestedAfter, contract=DEFAULT_REPORT) {
  const since=requestedAfter ? Date.parse(requestedAfter) : -Infinity;
  if(Number.isNaN(since)) throw new Error('任务起始时间无效。');
  return entries.filter(entry=>{
    const r=entry.request || {};
    return Number(entry.response?.status)>0 && allowedJob({launch:contract.page,url:r.url,method:r.method,body:r.postData?.text || ''},expected,contract)
      && (!requestedAfter || (Number.isFinite(Date.parse(entry.startedDateTime)) && Date.parse(entry.startedDateTime)>=since));
  }).sort((a,b)=>(Date.parse(b.startedDateTime)||0)-(Date.parse(a.startedDateTime)||0))[0];
}
if (typeof module !== 'undefined') module.exports = { allowedJob, selectReportTab, allowedCapture, reportRequest, selectFreshEntry, trafficTreeRequest };
