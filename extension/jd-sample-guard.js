const SAMPLE_PAGES=[
  'https://jdsz.jd.com/szweb/view/product/productDetail.html',
  'https://jdsz.jd.com/szweb/view/flow/flow-summary.html',
  'https://jdsz.jd.com/szweb/view/view-source/view-flow.html',
  'https://jdsz.jd.com/szweb/view/customer/member-overview-temp.html',
  'https://jdsz.jd.com/szweb/view/user/member-benefits-temp.html',
  'https://jdsz.jd.com/szweb/view/venders/activity-lists-temp.html'
];
function sampleCandidate(entry){
  try {
    const url=new URL(entry.request.url);
    return url.origin==='https://szgateway.jd.com' && (url.pathname.startsWith('/api/lowcode/') || /^\/szpaas\/lowcode\/szajax\/(?:index\/)?query\/[A-Za-z0-9_-]{1,80}\.ajax$/.test(url.pathname)) &&
      ['GET','POST'].includes(entry.request.method) && entry.response.status===200 &&
      /json/i.test(entry.response.content?.mimeType || '');
  }catch(_){return false;}
}
function redactSample(value,limitArrays=true){
  if(Array.isArray(value))return (limitArrays?value.slice(0,10):value).map(item=>redactSample(item,limitArrays));
  if(value && typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[
    key, /cookie|authorization|csrf|token|password|secret|signature|session|(^|_)pin$/i.test(key)?'[redacted]':redactSample(item,limitArrays)
  ]));
  if(typeof value==='string' && /^[\[{]/.test(value.trim())){try{return redactSample(JSON.parse(value),limitArrays);}catch(_){}}
  return value;
}
function selectNativeSamples(entries,startedAfter){
  if(!Number.isFinite(startedAfter)||startedAfter<=0)throw new Error('缺少本次采样边界');
  const selected=new Map();
  for(const entry of entries.filter(sampleCandidate).filter(e=>Number.isFinite(Date.parse(e.startedDateTime))&&Date.parse(e.startedDateTime)>=startedAfter).sort((a,b)=>Date.parse(b.startedDateTime)-Date.parse(a.startedDateTime))){
    const key=entry.request.url+'|'+(entry.request.postData?.text||'');if(!selected.has(key))selected.set(key,entry);
  }
  return [...selected.values()].slice(0,25);
}
if(typeof module!=='undefined')module.exports={sampleCandidate,redactSample,SAMPLE_PAGES,selectNativeSamples};
