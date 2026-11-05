/* Visible DevTools panel: direct loopback delivery, no background worker messages. */
const BASE = 'http://127.0.0.1:47922';
const PAGE = 'https://jdsz.jd.com/szweb/view/tradeAnalysis/tradeSummary.html';
const ENDPOINT = 'https://szgateway.jd.com/api/lowcode/tradeSummary/summary/getSummary.ajax';
const HEADERS = { 'X-Dmp-Bridge': chrome.runtime.id };
const VERSION = chrome.runtime.getManifest().version;
const targetTabId = chrome.devtools.inspectedWindow.tabId;
const contractsPromise = fetch(chrome.runtime.getURL('report-contracts.json')).then(r => r.json());
let active = false;
let polling = false;
const statusElement = document.querySelector('#status');
const logElement = document.querySelector('#log');
document.querySelector('#info').textContent = `扩展 ${chrome.runtime.getManifest().version} 已加载；当前被检查的标签页 ID：${targetTabId}。面板无需连接隐藏后台。`;
function log(text) { logElement.textContent = (logElement.textContent + '\n' + new Date().toLocaleTimeString() + ' ' + text).trim().slice(-12000); }
function status(text) { statusElement.textContent = text; log(text); }
function buttons(disabled) { document.querySelector('#start').disabled = disabled; document.querySelector('#check').disabled = disabled; }
async function hello() {
  let response;
  try { response = await fetch(BASE + '/hello?v='+VERSION, {headers:HEADERS,signal:AbortSignal.timeout(4000)}); }
  catch (_) { throw new Error('Python 服务未启动、已退出或本机连接被拦截。请先重新运行 PowerShell 命令，再点击检查。'); }
  if (response.status===426)throw new Error('此面板版本过旧，请重新加载扩展并重开F12。');
  if (!response.ok) throw new Error(`Python 连接被拒绝（HTTP ${response.status}），请核对插件 ID。`);
  if ((await response.json()).app !== 'jd-cli') throw new Error('47922 端口不是本测试服务。');
}
async function nextTaskURL(){
  const page=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('无法读取当前报表页地址')),4000);
    chrome.devtools.inspectedWindow.eval('location.origin+location.pathname',(result,error)=>{
      clearTimeout(timer);if(error?.isError || error?.isException || typeof result!=='string')reject(new Error('报表页地址读取失败'));else resolve(result);
    });
  });
  return BASE+'/next?wait=0&v='+VERSION+'&page='+encodeURIComponent(page);
}
async function deliver(job, out) {
  const response = await fetch(BASE + '/result', {method:'POST',headers:{...HEADERS,'Content-Type':'text/plain'},
    body:JSON.stringify({id:job.id,...out}),signal:AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error(`Python 未接收结果（HTTP ${response.status}），可能已超时退出。`);
}
async function panelIdentity(page=PAGE){
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('无法识别当前店铺，请等待商智页面加载完成。')),5000);
    const path=JSON.stringify(new URL(page).pathname);
    const expression='(()=>({identity:('+readJDIdentity.toString()+')('+path+'),page:location.origin+location.pathname,mallLinks:[...document.querySelectorAll("a[href]")].filter(a=>/^https:\\/\\/mall\\.jd\\.com\\/index-\\d+\\.html(?:[?#].*)?$/.test(a.href)).length}))()';
    chrome.devtools.inspectedWindow.eval(expression,(result,error)=>{
      clearTimeout(timer);
      if(error?.isError || error?.isException)reject(new Error(`店铺识别执行失败；标签页 ${targetTabId}；${error.value || error.description || 'Chrome 未提供详情'}`));
      else if(!result?.identity?.store_key)reject(new Error(`当前商智页面没有可验证的店铺身份；标签页 ${targetTabId}；实际页面 ${result?.page || '未知'}；要求页面 ${page}；商城身份链接 ${result?.mallLinks ?? '未知'} 个。停止。`));
      else resolve({...result.identity,tab_id:targetTabId});
    });
  });
}
async function restoreQuery(job,expected){
  const actions=[];
  async function step(name){
    const input={key:job.report_key,expected,step:name,store:job.expected_store.store_key};
    const result=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('网页查询控件响应超时：'+name)),4000);
      chrome.devtools.inspectedWindow.eval('('+nativeQueryAction.toString()+')('+JSON.stringify(input)+')',(result,error)=>{
        clearTimeout(timer);if(error?.isError || error?.isException)reject(new Error(error.value || error.description || '网页操作失败：'+name));else resolve(result);
      });
    });actions.push(name);return result;
  }
  const settle=()=>new Promise(resolve=>setTimeout(resolve,500));
  await step('inspect');await step('dimension');await settle();
  if(!(await step('dimension-ready')).ready)throw new Error('商品维度未切换成功');
  // An alternate period forces a native request even when the target date is already selected.
  await step('alternate');await settle();
  if(job.is_yesterday)await step('yesterday');
  else {await step('calendar');await settle();await step('date-cell');}
  await settle();await step('compare');
  if(job.report_key==='traffic-level2'){
    await settle();await step('sources');await settle();
    if((await step('source-count')).count<=2){await step('sources');await settle();}
  }
  return actions;
}
async function runProbe(prefetched=null) {
  if (active || polling) return;
  active = true; buttons(true);
  let job, resultSent = false;
  try {
    const contracts = await contractsPromise;
    status('步骤 1/4：检查 Python 连接……');
    if(prefetched) job=prefetched;
    else {
      await hello();
      const response=await fetch(await nextTaskURL(),{headers:HEADERS,signal:AbortSignal.timeout(4000)});
      if(response.status!==200) throw new Error('Python 没有待执行任务，请先启动服务。');
      job=await response.json();
    }
    const contract=contracts[job.report_key || 'overview'];
    if(!contract)throw new Error('报表合同未登记，请更新插件。');
    const expected = reportRequest(job, contract.template,contract);
    const identity=await panelIdentity(contract.page);
    if(job.expected_store && !sameStore(job.expected_store,identity))throw new Error('当前店铺与指定店铺不符，未执行取数。');
    const identityVerifiedAt=new Date().toISOString();
    if(job.operation==='identify'){
      await deliver(job,{status:200,text:JSON.stringify(identity),identity});resultSent=true;
      status('已回传当前京东店铺身份：'+identity.name);return;
    }
    document.querySelector('#query').textContent = `本次任务：${job.report_key || 'overview'}；${expected.startDate} 对比 ${expected.compareStartDate}；渠道 ${expected.channel}。请确认当前页面店铺。`;
    log(`只接收 ${expected.startDate}，对比 ${expected.compareStartDate} 的报表请求。`);
    status('步骤 2/4：读取当前 Network 已记录的请求……');
    const captureStart=Date.now();let queryActions=[];
    if(job.auto_query){
      if(!job.requested_after || !job.expected_store)throw new Error('自动查询必须绑定店铺和新请求时间');
      status('正在通过原生网页控件恢复日期和维度……');
      queryActions=await restoreQuery(job,expected);
      log('已恢复网页查询条件；继续校验新响应参数，不使用旧记录。');
    } else if(job.refresh_page){
      if(!job.requested_after)throw new Error('自动刷新必须要求本次新响应。');
      const info=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('无法确认当前报表页，未刷新。')),4000);
        chrome.devtools.inspectedWindow.eval('({page:location.origin+location.pathname})',(result,error)=>{
          clearTimeout(timer);
          if(error?.isError || error?.isException || result?.page!==contract.page)reject(new Error('当前页不是本次任务报表，未刷新。'));
          else resolve(result);
        });
      });
      chrome.devtools.inspectedWindow.reload({ignoreCache:false});
      log('已通过 Chrome 原生刷新报表页一次，等待昨天的新响应。');
    }
    const timeout=job.requested_after ? Math.min(120000,Math.max(10,Number(job.capture_timeout_ms)||60000)) : 0;
    let selected,entries=[],candidates=[],waitingLogged=false;
    do {
      const har=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('Chrome getHAR 在 5 秒内未返回。')),5000);
        chrome.devtools.network.getHAR(result=>{clearTimeout(timer);resolve(result);});
      });
      entries=har?.entries || [];
      candidates=entries.filter(entry=>entry.request?.url===contract.endpoint && entry.request.method==='POST');
      const currentIdentity=await panelIdentity(contract.page);
      if(!sameStore(identity,currentIdentity))throw new Error('等待期间页面或店铺发生变化，停止本次任务。');
      selected=selectFreshEntry(entries,expected,identityVerifiedAt,contract);
      if(selected)break;
      if(timeout && Date.now()-captureStart<timeout){
        if(!waitingLogged){status('等待本次新请求：请切换网页日期到目标日期；旧记录不会回传。');waitingLogged=true;}
        await new Promise(resolve=>setTimeout(resolve,500));
      }
    } while(timeout && Date.now()-captureStart<timeout);
    log(`Network 共 ${entries.length} 条；交易概况 POST ${candidates.length} 条。`);
    if(!selected){
      for(const entry of candidates.slice(-3)){
        let details='请求体缺失或不是 JSON';
        try {const actual=JSON.parse(entry.request.postData?.text || '');details='参数不同：'+Object.keys(expected).filter(k=>stable(actual[k])!==stable(expected[k])).join('、')+'；日期 '+actual.startDate+'；请求时间 '+entry.startedDateTime;}catch(_){}
        log('未接收：'+details);
      }
      throw new Error(`Network 共 ${entries.length} 条，交易概况 ${candidates.length} 条；`+(job.requested_after?'没有找到任务开始后的匹配新响应，请切换日期后重新发起任务。':candidates.length?'参数不匹配，请查看上方差异。':'未找到报表请求，请切换网页日期。'));
    }
    log('选中已有请求，时间：'+(selected.startedDateTime || 'Chrome 未提供')+'；本次不会重新查询京东。');
    status('步骤 3/4：读取所选请求的响应正文……');
    const out=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Chrome 在 8 秒内未返回响应正文。请检查该请求的 Response 是否可见。')),8000);
      if(typeof selected.getContent!=='function'){clearTimeout(timer);reject(new Error('Chrome getHAR 返回的请求缺少 getContent 方法。'));return;}
      selected.getContent((content,encoding)=>{
        clearTimeout(timer);
        try {
          if(encoding==='base64') content=new TextDecoder().decode(Uint8Array.from(atob(content),c=>c.charCodeAt(0)));
          if(typeof content!=='string' || !content.length) throw new Error('Chrome 未提供响应正文；请检查 Network 中该请求的 Response。');
          resolve({status:selected.response.status,text:content,source:'native-page-har-buffer',request_timestamp:selected.startedDateTime || null,capture_ms:Date.now()-captureStart});
        } catch(error){reject(error);}
      });
    });
    status('步骤 4/4：已读取响应，回传 Python……');
    const after=await panelIdentity(contract.page);
    if(!sameStore(identity,after))throw new Error('取数期间店铺已变化，停止回传。');
    out.identity=after;out.query_actions=queryActions;out.identity_verified_at=identityVerifiedAt;
    await deliver(job,out); resultSent=true;
    status(`已回传原网页响应 HTTP ${out.status}。请看 PowerShell 的业务状态与样本核对结果。`);
  } catch (error) {
    if (job && !resultSent) {
      try { await deliver(job,{error:String(error)}); } catch (_) { log('错误信息未能回传：Python 可能已经退出。'); }
    }
    status('未完成：'+String(error));
  } finally { active=false; buttons(false); }
}
document.querySelector('#check').addEventListener('click',async()=>{
  if(active)return;
  try {await hello();status('Python 已连接。开启自动接收后等待任务；历史日期请在任务启动后切换日期，产生本次新请求。');}
  catch(error){status(String(error));}
});
document.querySelector('#start').addEventListener('click',()=>runProbe());
let stopAuto=null;
document.querySelector('#auto').addEventListener('change',()=>{
  if(stopAuto){stopAuto();stopAuto=null;}
  if(!document.querySelector('#auto').checked){status('自动接收已关闭，可手动读取。');return;}
  status('自动接收已开启：等待 AI 启动本机任务。请只在当前店铺的一个面板开启。');
  stopAuto=startAutoReceiver({isEnabled:()=>document.querySelector('#auto').checked,isBusy:()=>active || polling,poll:async()=>{
    polling=true;
    try {
      await hello();
      if(!document.querySelector('#auto').checked)return;
      const response=await fetch(await nextTaskURL(),{headers:HEADERS,signal:AbortSignal.timeout(4000)});
      if(response.status!==200)return;
      const job=await response.json();polling=false;
      await runProbe(job);
    } finally {polling=false;}
  }});
});
status('面板已就绪。开启自动接收后启动 AI 任务；昨天会正常刷新，历史日期需在任务开始后切换日期产生新请求。');
