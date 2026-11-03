// Public source discovery for shopdate_symc MCP. Text only, never eval/import.
function sycmPublicAssetAllowed(raw) {
  if (typeof raw !== 'string' || raw.includes('%') || raw.includes('..')) return false;
  try {
    const u = new URL(raw);
    return u.protocol === 'https:' && u.host === 'g.alicdn.com' && !u.username && !u.password && !u.search && !u.hash
      && /^\/dt\/(?:sycm-[A-Za-z0-9_-]+|ops-flow)\/[A-Za-z0-9_./-]+\.js$/.test(u.pathname);
  } catch (_) { return false; }
}
async function sycmFetchPublicAsset(job) {
  if (!sycmPublicAssetAllowed(job.url) || job.method && job.method !== 'GET' || job.body || job.cookie)
    return {id:job.id,error:'Public discovery only allows registered SYCM static JavaScript GET'};
  try {
    const response = await fetch(job.url, {method:'GET',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(45000)});
    const length=Number(response.headers.get('content-length') || 0);
    if(length>10000000)return {id:job.id,error:'Public asset exceeds size limit'};
    const text=await response.text();
    if(text.length>5000000)return {id:job.id,error:'Public asset exceeds size limit'};
    return {id:job.id,status:response.status,text};
  } catch(e) { return {id:job.id,error:'Public source read failed: '+String(e.message || e)}; }
}
