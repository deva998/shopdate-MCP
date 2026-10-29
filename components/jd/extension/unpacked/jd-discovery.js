const SAMPLE_BASE='http://127.0.0.1:47923';
const SAMPLE_HEADERS={'X-Dmp-Bridge':chrome.runtime.id};
const log=document.getElementById('log');
let captureSession=null;
function inspectPage(){return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('当前报表身份读取超时')),4000);
  chrome.devtools.inspectedWindow.eval(
  `({page:location.origin+location.pathname,timeOrigin:typeof performance==='undefined'?null:performance.timeOrigin,shops:[...document.querySelectorAll('a[href]')].filter(a=>/^https:\\/\\/mall\\.jd\\.com\\/index-\\d+\\.html(?:[?#].*)?$/.test(a.href)).map(a=>({url:a.href.split(/[?#]/)[0],name:(a.innerText||'').trim()}))})`,
  (result,error)=>{clearTimeout(timer);error?.isError || error?.isException?reject(new Error('无法读取当前报表页')):resolve(result);}
);});}
async function contentOf(entry){return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('响应正文读取超时')),8000);
  entry.getContent((text,encoding)=>{
    clearTimeout(timer);
    try {
      if(encoding==='base64')text=new TextDecoder().decode(Uint8Array.from(atob(text),c=>c.charCodeAt(0)));
      if(text.length>2000000)throw new Error('样本过大，请只查询第一页');
      resolve(JSON.parse(text));
    }catch(error){reject(error);}
  });
});}
document.getElementById('collect').addEventListener('click',async()=>{
  const button=document.getElementById('collect');button.disabled=true;
  let job;
  try {
    if(captureSession){job=captureSession.job;}else{
      const response=await fetch(SAMPLE_BASE+'/next?wait=0&v='+chrome.runtime.getManifest().version,{headers:SAMPLE_HEADERS,signal:AbortSignal.timeout(4000)});
      if(response.status!==200)throw new Error('接收器没有待处理任务，请先启动本机样本接收器');
      job=await response.json();
    }
    const before=await inspectPage();
    if(job.operation!=='discover' || !SAMPLE_PAGES.includes(before.page) || job.expected_page!==before.page)throw new Error('当前报表与任务不符，未导出');
    const shops=[...new Map(before.shops.filter(s=>s.name).map(s=>[s.url,s])).values()];
    if(shops.length!==1)throw new Error('当前店铺身份不唯一');
    if(job.expected_store && shops[0].url!==job.expected_store)throw new Error('当前店铺与指定任务不符，未导出');
    if(!Number.isFinite(before.timeOrigin))throw new Error('无法确定当前页面实例，未采样');
    if(!captureSession){
      captureSession={job,page:before.page,shop:shops[0].url,timeOrigin:before.timeOrigin,startedAfter:Date.now()};
      button.textContent='读取本次查询样本';log.textContent='采样边界已建立。请保持当前店铺和页面，不刷新页面；切换报表日期触发查询，再回来点击「读取本次查询样本」。';return;
    }
    if(captureSession.page!==before.page||captureSession.shop!==shops[0].url||captureSession.timeOrigin!==before.timeOrigin||Date.now()-captureSession.startedAfter>120000)throw new Error('页面、店铺或采样时限变化，请重新开始');
    const har=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Network样本读取超时，请确认已点开Network')),5000);
      chrome.devtools.network.getHAR(result=>{clearTimeout(timer);resolve(result);});
    });
    const selected=selectNativeSamples(har.entries || [],captureSession.startedAfter);
    if(!selected.length)throw new Error('没有JSON报表样本；请先点Network，再切日期触发查询');
    const samples=[];
    for(const entry of selected){
      let requestBody=null;
      if(entry.request.postData?.text){try{requestBody=JSON.parse(entry.request.postData.text);}catch(_){continue;}}
      const target=new URL(entry.request.url);
      const original=await contentOf(entry);
      samples.push({url:target.origin+target.pathname,method:entry.request.method,
        query:redactSample(Object.fromEntries(target.searchParams),false),request_body:redactSample(requestBody,false),
        timestamp:entry.startedDateTime,status:entry.response.status,
        response_metadata:{original_body_data_length:Array.isArray(original?.body?.data)?original.body.data.length:null,
          response_array_limit:10},response:redactSample(original)});
    }
    const after=await inspectPage();
    const current=[...new Set(after.shops.filter(s=>s.name).map(s=>s.url))];
    if(after.page!==before.page || after.timeOrigin!==before.timeOrigin || current.length!==1 || current[0]!==shops[0].url)throw new Error('采样期间页面或店铺变化，未导出');
    const result=await fetch(SAMPLE_BASE+'/result',{method:'POST',headers:{...SAMPLE_HEADERS,'Content-Type':'text/plain'},
      body:JSON.stringify({id:job.id,page:before.page,shop:shops[0],samples,source:'native-page-har-discovery',sample_only:true,capture_boundary:{started_after:captureSession.startedAfter,time_origin:before.timeOrigin,identity_binding:'current_page_before_after_only'}}),signal:AbortSignal.timeout(5000)});
    if(!result.ok)throw new Error('本机未接收样本');
    log.textContent=`已保存 ${samples.length} 个接口样本。请求/响应数组最多保留10项，供字段映射验证，不代表完整数据采集。`;
    captureSession=null;button.textContent='开始本次采样';
  }catch(error){
    captureSession=null;button.textContent='开始本次采样';
    log.textContent=String(error);
    if(job)try{await fetch(SAMPLE_BASE+'/result',{method:'POST',headers:{...SAMPLE_HEADERS,'Content-Type':'text/plain'},body:JSON.stringify({id:job.id,error:String(error)})});}catch(_){}
  }finally{button.disabled=false;}
});
