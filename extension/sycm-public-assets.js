// Public source discovery for shopdate_symc MCP. Text only, never eval/import.
function sycmPublicAssetAllowed(raw) {
  if (typeof raw !== 'string' || raw.includes('%') || raw.includes('..')) return false;
  try {
    const u = new URL(raw);
    return u.protocol === 'https:' && u.host === 'g.alicdn.com' && !u.username && !u.password && !u.search && !u.hash
      && (/^\/dt\/(?:sycm-[A-Za-z0-9_-]+|ops-flow|op-fa|op-live|op-sales|op-cc|op-service|op-cp|op-market|oneness-page)\/[A-Za-z0-9_./-]+\.js$/.test(u.pathname)
          || /^\/dt\/ops-bda\/1\.0\.15\/js\/trade\/(?:overview|constitute)\/app\.js$/.test(u.pathname)
          || /^\/qbi\/qbi\/[0-9.]+\/[A-Za-z0-9_./~-]+\.js$/.test(u.pathname)
          || u.pathname === '/dt/ops-base/1.0.11/js/ops-base.js'
          || /^\/aligenius\/customer-service-performance\/[0-9.]+\/[A-Za-z0-9_./-]+\.js$/.test(u.pathname));
  } catch (_) { return false; }
}
async function sycmFetchPublicAsset(job) {
  if (!sycmPublicAssetAllowed(job.url) || job.method && job.method !== 'GET' || job.body || job.cookie)
    return {id:job.id,error:'Public discovery only allows registered SYCM static JavaScript GET'};
  const range=job.byte_range;
  if(range && (!Array.isArray(range)||range.length!==2||!range.every(Number.isSafeInteger)||range[0]<0||range[1]<range[0]||range[1]-range[0]+1>1048576))
    return {id:job.id,error:'Public source range must be at most one MiB'};
  try {
    const response = await fetch(job.url, {method:'GET',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(45000),...(range?{headers:{Range:`bytes=${range[0]}-${range[1]}`}}:{})});
    const contentRange=response.headers.get('content-range')||'';
    if(range){
      const match=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(contentRange);
      if(response.status!==206||!match||Number(match[1])!==range[0]||Number(match[2])>range[1]){
        await response.body?.cancel();return {id:job.id,error:'Server did not honor the bounded public source range'};
      }
    }
    const length=Number(response.headers.get('content-length') || 0);
    if(length>10000000)return {id:job.id,error:'Public asset exceeds size limit'};
    const text=await response.text();
    if(text.length>5000000)return {id:job.id,error:'Public asset exceeds size limit'};
    return {id:job.id,status:response.status,text,...(range?{content_range:contentRange}: {})};
  } catch(e) { return {id:job.id,error:'Public source read failed: '+String(e.message || e)}; }
}
