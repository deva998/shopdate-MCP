/* Native official export only: no API replay, cookies or download permissions. */
function jdExportAction(input){
  try{
  const actionId=input.store+'|'+input.day+'|'+input.requested_after;
  const product='/szweb/view/product/productDetail.html',center='/szweb/view/reports-center/download-center.html';
  if(location.origin!=='https://jdsz.jd.com' || ![product,center].includes(location.pathname))throw new Error('未登记的导出页面');
  const anchors=[...new Set([...document.querySelectorAll('a[href]')].map(a=>a.href.split(/[?#]/)[0]).filter(h=>/^https:\/\/mall\.jd\.com\/index-\d+\.html$/.test(h)))];
  if(anchors.length!==1 || anchors[0]!=='https://mall.jd.com/index-'+String(input.store).replace('jd:mall:','')+'.html')throw new Error('导出店铺身份不符');
  const visible=e=>!e.getClientRects || e.getClientRects().length>0;
  const buttons=root=>[...root.querySelectorAll('button')].filter(visible);
  const one=(root,text)=>{const nodes=buttons(root).filter(b=>b.innerText.trim()===text);if(nodes.length!==1)throw new Error('未找到唯一导出控件：'+text);return nodes[0];};
  if(input.step==='open' || input.step==='confirm'){
    if(location.pathname!==product)throw new Error('当前不是商品导出页');
    const text=document.body.innerText;
    if(!text.includes('当前： '+input.day) && !new RegExp('当前[：:]\\s*'+input.day).test(text))throw new Error('导出日期未匹配');
    const tabs=[...document.querySelectorAll('[role="tab"]')].filter(e=>e.getAttribute('aria-selected')==='true');
    if(tabs.length!==1 || tabs[0].textContent.trim()!==input.dimension.toUpperCase())throw new Error('导出SPU/SKU维度不符');
    if(input.step==='open'){one(document,'下载数据').click();return {opened:true};}
    if(globalThis.__shopdataJDExportSubmitted===actionId)return {submitted:true};
    const dialogs=[...document.querySelectorAll('[role="dialog"]')].filter(visible).filter(e=>e.innerText.includes('下载数据'));
    if(dialogs.length!==1)throw new Error('导出窗口未就绪');
    const dialog=dialogs[0];
    for(const label of ['汇总下载','不包含对比时间']){
      const labels=[...dialog.querySelectorAll('label')].filter(e=>e.textContent.trim()===label);
      if(labels.length!==1)throw new Error('导出范围控件未匹配：'+label);
      const radio=labels[0].querySelector('input[type="radio"]');
      if(!radio)throw new Error('导出单选控件未就绪');
      if(!radio.checked){radio.click();return {ready:false,selected:label};}
    }
    const confirm=one(dialog,'确定');
    globalThis.__shopdataJDExportSubmitted=actionId;confirm.click();return {submitted:true};
  }
  if(location.pathname!==center)throw new Error('当前不是下载中心');
  const slot='__shopdataJDExportDownload',downloadId=input.store+'|'+input.day+'|'+input.requested_after;
  if(input.step==='clear-download'){
    if(globalThis[slot]?.id===downloadId)globalThis[slot].clear();return {cleared:true};
  }
  if(input.step==='read-download'){
    const state=globalThis[slot];
    if(!state || state.id!==downloadId)throw new Error('文件回调监听已过期');
    return state.url?{url:state.url,native_opened:state.native_opened}:{pending:true};
  }
  if(input.step==='refresh'){one(document,'刷新').click();return {refreshed:true};}
  const entries=[...document.querySelectorAll('tr')].map(row=>({row,cells:[...row.querySelectorAll('td')]}));
  const signature=cells=>cells.length>=3?cells[0].innerText.trim()+'|'+cells[2].innerText.trim():null;
  if(input.step==='snapshot'){
    if(!document.body.innerText.includes('下载列表') || !document.body.innerText.includes('创建时间'))throw new Error('下载中心列表尚未就绪');
    return {entries:entries.map(({cells})=>signature(cells)).filter(Boolean)};
  }
  if(input.step!=='download')throw new Error('未知导出操作');
  const issued=Date.parse(input.requested_after);
  if(!Number.isFinite(issued) || Date.now()-issued>150000)throw new Error('导出任务已过期');
  const prefix=String(input.store).replace('jd:mall:','')+'_商品明细_离线_不包括对比时间_汇总下载_'+input.day+'_'+input.day;
  const matches=entries.filter(({cells})=>{
    if(cells.length<4 || cells[0].innerText.trim()!==prefix)return false;
    if((input.baseline || []).includes(signature(cells)))return false;
    const created=Date.parse(cells[2].innerText.trim().replace(' ','T')+'+08:00');
    return Number.isFinite(created) && created>=Date.parse(input.created_after || input.requested_after) && created<=Date.now()+2000;
  });
  if(matches.length>1)throw new Error('本次出现多个匹配导出任务，停止避免串文件');
  if(!matches.length || matches[0].cells[3].innerText.trim()!=='已生成')return {ready:false,prefix};
  if(globalThis[slot])throw new Error('已有文件回调监听任务');
  const originalOpen=globalThis.open;let timer;
  const state={id:downloadId,url:null,native_opened:false};
  const observedOpen=function(raw){
    let selected=null;
    if(!state.url){try{const url=new URL(raw,location.origin);if(url.protocol==='https:' && !url.username && !url.password && (/([.]|^)jd[.]com$/.test(url.hostname) || url.hostname==='storage.360buyimg.com') && url.pathname.toLowerCase().endsWith('.xlsx'))selected=url.href;}catch(_){}}
    const opened=originalOpen.apply(this,arguments);
    if(selected && !state.url){state.url=selected;state.native_opened=!!opened;}
    return opened;
  };
  state.clear=()=>{clearTimeout(timer);if(globalThis.open===observedOpen)globalThis.open=originalOpen;if(globalThis[slot]===state)delete globalThis[slot];};
  globalThis[slot]=state;globalThis.open=observedOpen;timer=setTimeout(state.clear,12000);
  one(matches[0].row,'下载').click();
  return {ready:true,download_started:true,prefix,created_at:matches[0].cells[2].innerText.trim()};
  }catch(error){return {action_error:String(error.message || error)};}
}
async function runJDExportJob(job,options={}){
  if(!['products-spu','products-sku'].includes(job.report_key) || job.operation!=='official-export')throw new Error('未登记的官方导出任务');
  const queried=await runJDNativeJob(job,{...options,keepCreatedTab:true}),productTab=queried.identity.tab_id;
  const input={store:job.expected_store.store_key,day:JSON.parse(job.body).startDate,dimension:job.report_key.slice(9),requested_after:job.requested_after};
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  try{
  async function act(tabId,step){
    let timer;
    try{
      const value=await Promise.race([chrome.scripting.executeScript({target:{tabId},world:'MAIN',injectImmediately:true,func:jdExportAction,args:[{...input,step}]}),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('导出页面执行超时')),5000);})]);
      if(!value?.length || !value[0].result)throw new Error('导出页面没有返回结果：'+step);
      if(value[0].result.action_error)throw new Error('导出'+step+'：'+value[0].result.action_error);
      return value[0].result;
    }finally{clearTimeout(timer);}
  }
  const centerUrl='https://jdsz.jd.com/szweb/view/reports-center/download-center.html';
  let center=(await chrome.tabs.query({url:centerUrl+'*'})).find(t=>t.url?.split(/[?#]/)[0]===centerUrl);
  if(!center)center=await chrome.tabs.create({url:centerUrl,active:false});
  let baseline=null;const readyStarted=Date.now();
  while(Date.now()-readyStarted<12000){
    try{
      const current=await chrome.tabs.get(center.id);
      if(current.url?.split(/[?#]/)[0]!==centerUrl){await delay(300);continue;}
      await act(center.id,'refresh');await delay(500);
      baseline=(await act(center.id,'snapshot')).entries;break;
    }catch(error){
      if(!/导出页面|店铺身份|当前不是|没有返回结果|未就绪|控件|No frame|Cannot access|frame.*removed|No document/i.test(String(error.message || error)))throw error;
      await delay(300);
    }
  }
  if(!baseline)throw new Error('下载中心导航或店铺身份未就绪');
  input.baseline=baseline;
  await act(productTab,'open');await delay(300);
  const boundary=Math.ceil(Date.now()/1000)*1000;
  input.created_after=new Date(boundary).toISOString();
  await delay(Math.max(0,boundary-Date.now()));
  if(Date.now()-Date.parse(job.requested_after)>125000)throw new Error('导出任务已过期，未提交下载');
  let submitted=false;const modalStarted=Date.now();
  while(Date.now()-modalStarted<5000){
    try{const result=await act(productTab,'confirm');if(result.submitted){submitted=true;break;}}
    catch(error){if(!/导出窗口未就绪/.test(String(error.message || error)))throw error;}
    await delay(200);
  }
  if(!submitted)throw new Error('未能确认官方导出范围');
  const start=Date.now();let last='';
  while(Date.now()-start<90000){
    if(Date.now()-Date.parse(job.requested_after)>145000)throw new Error('导出任务已过期，未下载旧任务');
    try{
      const value=await act(center.id,'download');
      if(value.download_started){
        try{
          let file;
          const waiting=Date.now();
          while(Date.now()-waiting<10000){file=await act(center.id,'read-download');if(file.url)break;await delay(100);}
          if(!file?.url)throw new Error('未收到页面原生文件链接；未发起其他请求');
          const url=new URL(file.url);
          if(url.protocol!=='https:' || url.username || url.password || !(/(^|\.)jd\.com$/.test(url.hostname) || url.hostname==='storage.360buyimg.com') || !url.pathname.toLowerCase().endsWith('.xlsx'))throw new Error('未登记的官方XLSX文件地址：'+url.hostname);
          if(!file.native_opened)await chrome.tabs.create({url:url.href,active:false});
          return {...value,download_clicked:true,download_host:url.hostname,download_clicked_at:new Date().toISOString(),identity:queried.identity,source:'official-page-download',transport:'background-native',query_actions:queried.query_actions};
        }finally{await act(center.id,'clear-download');}
      }
      await act(center.id,'refresh');
    }catch(error){last=String(error.message || error);if(!/店铺身份|未找到唯一导出控件/.test(last))throw error;}
    await delay(1000);
  }
  throw new Error('本次官方导出未生成或下载中心未就绪：'+last);
  }finally{if(queried.temporary_tab)try{await chrome.tabs.remove(queried.temporary_tab);}catch(_){}}
}
if(typeof module!=='undefined')module.exports={jdExportAction,runJDExportJob};
