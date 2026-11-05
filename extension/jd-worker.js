/* JD scheduler independent of the original Taobao bridge loop. No API replay. */
async function runJDNativeJob(job,options={}) {
  const contracts=await (await fetch(chrome.runtime.getURL('report-contracts.json'))).json();
  const contract=contracts[job.report_key];
  if(!contract || job.transport!=='background-native')throw new Error('未登记的京东后台任务');
  const expected=reportRequest(job,contract.template,contract);
  if(job.expected_store?.platform!=='jd' || !/^jd:mall:\d+$/.test(job.expected_store.store_key) || !Number.isFinite(Date.parse(job.requested_after)))throw new Error('后台取数必须指定店铺和任务时间');
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  async function execute(tabId,func,args){
    let timer;
    try{
      const result=await Promise.race([chrome.scripting.executeScript({target:{tabId},world:'MAIN',injectImmediately:true,func,args}),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('报表页面执行超时：'+func.name)),5000);})]);
      if(!result?.length || result[0].result===undefined)throw new Error('报表页面未返回结果：'+func.name);
      return result[0].result;
    }finally{clearTimeout(timer);}
  }
  let tab,createdTab=null,diagnostics=[],wrongIdentity=false;
  for(let pass=0;pass<2 && !tab;pass++){
    const discoveryStarted=Date.now();
    do{
      const tabs=await chrome.tabs.query({url:contract.page+'*'});
      const matching=tabs.filter(item=>item.url?.split(/[?#]/)[0]===contract.page);
      if(!matching.length && pass===0)break;
      diagnostics=[];
      const candidates=await Promise.all(matching.map(async candidate=>{
        if(candidate.discarded){diagnostics.push('标签'+candidate.id+'已休眠');return null;}
        try{
          const actual=await execute(candidate.id,readJDIdentity,[new URL(contract.page).pathname]);
          if(sameStore(job.expected_store,actual))return candidate;
          if(actual?.store_key)wrongIdentity=true;
          diagnostics.push('标签'+candidate.id+'：'+(actual?.store_key?'店铺不符':'身份DOM尚未就绪'));return null;
        }catch(error){diagnostics.push('标签'+candidate.id+'：'+String(error.message || error));return null;}
      }));
      tab=candidates.filter(Boolean).sort((a,b)=>Number(!!b.active)-Number(!!a.active) || a.id-b.id)[0];
      if(tab)break;
      await delay(400);
    }while(Date.now()-discoveryStarted<12000);
    if(!tab && pass===0 && !wrongIdentity){createdTab=await chrome.tabs.create({url:contract.page,active:false});}
    else if(!tab)break;
  }
  if(!tab){if(createdTab)await chrome.tabs.remove(createdTab.id);throw new Error('无法核验指定店铺报表页：'+contract.page+'；'+diagnostics.join('；'));}
  const input={id:job.id,page:contract.page,endpoint:contract.endpoint,expected,store:job.expected_store.store_key,requested_after:job.requested_after,timeout_ms:125000};
  const actions=[],started=Date.now();
  async function step(name){
    const value=await execute(tab.id,nativeQueryAction,[{key:job.report_key,expected,step:name,store:job.expected_store.store_key}]);
    actions.push(name);return value;
  }
  const settle=()=>delay(options.settleMs ?? 500);
  let installed=false,handedOff=false;
  try{
    await execute(tab.id,jdNativeObserver,[{...input,op:'install'}]);installed=true;
    await step('inspect');await step('dimension');await settle();
    if(!(await step('dimension-ready')).ready)throw new Error('商品维度未切换成功');
    await step('alternate');await settle();
    if(job.is_yesterday)await step('yesterday');
    else {await step('calendar');await settle();await step('date-cell');}
    await settle();await step('compare');
    let displayed;
    for(let attempt=0;attempt<8;attempt++){
      displayed=await step('date-ready');if(displayed.ready)break;await settle();
    }
    if(!displayed?.ready)throw new Error('网页日期未切换成功：当前'+(displayed?.current || '未知')+'，对比'+(displayed?.previous || '未知')+'；要求'+expected.startDate+'，未等待旧日期响应');
    if(job.report_key==='traffic-level2'){
      await settle();await step('sources');await settle();
      if((await step('source-count')).count<=2){await step('sources');await settle();}
    }
    while(Date.now()-started<120000){
      const response=await execute(tab.id,jdNativeObserver,[{...input,op:'read'}]);
      if(response.error)throw new Error(response.error);
      if(response.result){
        const dictionary=job.report_key.startsWith('traffic-')?await execute(tab.id,readJDDimensionCapture,[]):null;
        const after=await execute(tab.id,readJDIdentity,[new URL(contract.page).pathname]);
        if(!sameStore(job.expected_store,after) || !sameStore(job.expected_store,response.result.identity))throw new Error('取数期间店铺变化');
        handedOff=true;
        return {...response.result,source_dictionary:dictionary,temporary_tab:createdTab?.id || null,identity:{...after,tab_id:tab.id},query_actions:actions,transport:'background-native'};
      }
      await delay(300);
    }
    throw new Error('120秒内未捕获匹配的网页原生响应；未读取旧记录');
  }finally{
    if(installed)try{await execute(tab.id,jdNativeObserver,[{...input,op:'clear'}]);}catch(_){}
    if(createdTab && (!options.keepCreatedTab || !handedOff))try{await chrome.tabs.remove(createdTab.id);}catch(_){}
  }
}

let jdLoopRunning=false;
const jdState={running:false,lastError:'',lastJob:null};
async function jdBackgroundLoop(){
  if(jdLoopRunning)return;
  jdLoopRunning=true;
  const base='http://127.0.0.1:47922',headers={'X-Dmp-Bridge':chrome.runtime.id};
  try{
    let connected=false;
    for(;;){
      try{
      if(!connected){
        const hello=await fetch(base+'/hello?v='+chrome.runtime.getManifest().version,{headers,signal:AbortSignal.timeout(1500)});
        if(!hello.ok || (await hello.json()).app!=='jd-cli')throw new Error('京东本机服务尚未就绪');
        connected=true;
      }
      const response=await fetch(base+'/next?wait=2&transport=background-native&v='+chrome.runtime.getManifest().version,{headers,signal:AbortSignal.timeout(4000)});
      // Empty is not disconnected. Inactive page timers may only tick every
      // thirty seconds; keep this worker alive to receive the next MCP job.
      if(response.status===204)continue;
      if(!response.ok)throw new Error('京东任务领取失败：'+response.status);
      const job=await response.json();jdState.running=true;jdState.lastJob=job.id;jdState.lastError='';
      let out;
      try{out=await (['api-probe','registered-api'].includes(job.operation)?runJDApiProbeJob(job):job.operation==='official-export'?runJDExportJob(job):runJDNativeJob(job));}catch(error){out={error:String(error.message || error)};jdState.lastError=out.error;}
      const delivered=await fetch(base+'/result',{method:'POST',headers:{...headers,'Content-Type':'text/plain'},body:JSON.stringify({id:job.id,...out}),signal:AbortSignal.timeout(5000)});
      jdState.running=false;
      if(!delivered.ok)throw new Error('京东结果回传失败：'+delivered.status);
      }catch(error){
        connected=false;jdState.running=false;jdState.lastError=String(error.message || error);
        // A command's subprocess disappears on completion. Discover its
        // replacement directly; never re-execute an already submitted job.
        const tabs=await chrome.tabs.query({url:'https://jdsz.jd.com/*'});
        if(!tabs.length)break;
        await sleep(1000);
      }
    }
  }catch(error){jdState.lastError=String(error.message || error);}
  finally{jdState.running=false;jdLoopRunning=false;}
}
