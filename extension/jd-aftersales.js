/* Read-only official after-sale list. No audit, receipt, refund or close actions. */
const JD_AFS_PAGE='https://shop.jd.com/jdm/trade/after-sale/independent-after-sale/list?tabCode=all';
const JD_AFS_APIS=['dsm.seller.afs.bff.serviceOrderQueryDsmService.page','dsm.seller.afs.serviceOrderQueryDsmService.page'];
function afterSalesInput(job){
 if(job.operation!=='registered-api'||job.probe_key!=='after-sales-list'||job.launch!==JD_AFS_PAGE||job.expected_store?.platform!=='jd'||!/^jd:mall:\d+$/.test(job.expected_store.store_key||'')||!/^\d{4}-\d\d-\d\d$/.test(job.afs_date||'')||!Number.isInteger(job.afs_page)||job.afs_page<1||job.afs_page>2000||!Number.isFinite(Date.parse(job.requested_after)))throw new Error('售后请求超出登记范围');
 if(job.afs_page_size!=null&&![10,100].includes(job.afs_page_size))throw new Error('售后每页数量超出登记范围');
 return {date:job.afs_date,page:job.afs_page,page_size:job.afs_page_size||10,requested_after:job.requested_after};
}
async function afterSalesNativeRead(input){
 const XHR=XMLHttpRequest,open=XHR.prototype.open,send=XHR.prototype.send,meta=new WeakMap();let timer,wrappedOpen,wrappedSend,resolve,reject,started=false;
 const diagnostic={xhr_sends:0,target_requests:0,parse_errors:0,last:null};
 const response=new Promise((a,b)=>{resolve=a;reject=b;});response.catch(()=>{});
 const apis=['dsm.seller.afs.bff.serviceOrderQueryDsmService.page','dsm.seller.afs.serviceOrderQueryDsmService.page'];
 // Verified official list payload uses whole-second end-of-day precision.
 const begin=Date.parse(input.date+'T00:00:00+08:00'),end=begin+86400000-1000,pageSize=input.page_size||10;
 const scalar=(obj,keys)=>Object.fromEntries(keys.filter(k=>obj?.[k]!=null&&['string','number','boolean'].includes(typeof obj[k])).map(k=>[k,obj[k]]));
 try{
  if(location.origin!=='https://shop.jd.com'||location.pathname!=='/jdm/trade/after-sale/independent-after-sale/list')throw new Error('售后执行页面不符');
  wrappedOpen=function(method,url,...rest){meta.set(this,{method,url});return open.call(this,method,url,...rest);};
  wrappedSend=function(body){
   diagnostic.xhr_sends++;
   try{
    const m=meta.get(this),url=new URL(m?.url,location.href);
    if(m?.method?.toUpperCase()==='POST'&&url.origin==='https://sff.jd.com'&&url.pathname==='/api'&&url.searchParams.get('appId')==='BHPQ4MHJBUOQZKTFTRNS'&&apis.includes(url.searchParams.get('api'))){
     diagnostic.target_requests++;let d;try{d=JSON.parse(body).request?.data;}catch(_){diagnostic.parse_errors++;return send.call(this,body);}
     const range=d?.applyTimeRange;
     const empty=v=>v==null||v===''||v===false||v===0||Array.isArray(v)&&v.every(empty)||typeof v==='object'&&Object.values(v).every(empty);
     const expectedKeys=['applyTime','applyTimeRange','tabCode','pageIndex','pageSize'];
     const safeNumber=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
     diagnostic.last={begin:safeNumber(range?.dateBegin),end:safeNumber(range?.dateEnd),page:safeNumber(d?.pageIndex),pageSize:safeNumber(d?.pageSize),tab_all:d?.tabCode==='all',nonempty_keys:Object.entries(d||{}).filter(([k,v])=>!expectedKeys.includes(k)&&!empty(v)).map(([k])=>k.replace(/[^a-zA-Z0-9_]/g,'').slice(0,60)).slice(0,20)};
     if(range?.dateBegin===begin&&range?.dateEnd===end&&d.pageIndex===input.page&&d.pageSize===pageSize&&d.tabCode==='all'&&Object.entries(d).every(([k,v])=>expectedKeys.includes(k)||empty(v))){
      started=true;const at=new Date().toISOString(),api=url.searchParams.get('api');
      this.addEventListener('loadend',async()=>{
       try{
        if(this.status!==200)throw new Error('售后HTTP状态：'+this.status);
        const raw=this.responseText;if(raw.length>8*1024*1024)throw new Error('售后响应超过上限');const value=JSON.parse(raw),data=value.data;
        if(value.code===605)throw new Error('官方安全验证605：停止，不自动重试');
        const total=data?.totalNum,validTotal=(typeof total==='number'||typeof total==='string'&&/^(0|[1-9]\d*)$/.test(total))&&Number.isSafeInteger(Number(total))&&Number(total)>=0;
        if(value.code!==200||!Array.isArray(data?.content)||data.content.length>pageSize||!validTotal)throw new Error('售后列表结构待核验：code='+value.code+'；data字段='+Object.keys(data||{}).join(','));
        const allowed={serviceOrderBaseFacetDTO:['afsApplyTime','afsEndTime','afsCompleteTime','afsType','afsTypeName','afsServiceType','afsServiceTypeName'],orderFacetDTO:['orderId','orderCreateTime','orderPayTime','payTime'],serviceOrderStatusFacetDTO:['afsServiceStatus','afsServiceStatusName','status','statusName','stepName'],refundFacetDTO:['applyRefundAmount','refundAmount','refundStatus','refundStatusName','refundTime'],mainWareFacetDTO:['skuId','wareId','wareName','skuName','wareNum','num','warePrice','price','itemNum']};
        const content=data.content.map(row=>{
         const out=scalar(row,['afsServiceId','reverseId','reverseType','orderId','customerExpectation','customerExpectationName']);
         if(['afsServiceId','reverseId','orderId'].some(k=>typeof out[k]==='number'&&!Number.isSafeInteger(out[k])))throw new Error('售后编号超过安全整数');
         for(const [key,keys] of Object.entries(allowed))out[key]=scalar(row[key],keys);
         out.wareFacetDTOList=(row.wareFacetDTOList||[]).map(x=>scalar(x,allowed.mainWareFacetDTO));
         const reasons=row.customerApplyFacetDTO?.applyReasonFacetDTO?.afsReasons??row.applyReasonFacetDTO?.afsReasons;
         out.applyReasonFacetDTO={afsReasons:Array.isArray(reasons)?reasons.filter(x=>typeof x==='string'):typeof reasons==='string'&&reasons.trim()?[reasons]:null};
         out.schema=Object.fromEntries(Object.keys(allowed).map(k=>[k,Object.keys(row[k]||{})]));return out;
        });
        const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))).map(x=>x.toString(16).padStart(2,'0')).join('');
        resolve({status:200,text:JSON.stringify({projection:'jd-afs-business-v1',code:200,data:{totalNum:Number(data.totalNum),content},query:{date:input.date,dateBegin:range.dateBegin,dateEnd:range.dateEnd,page:input.page,pageSize,time_basis:'application_day',tab:'all',api}}),request_started_at:at,received_at:new Date().toISOString(),raw_response_sha256:digest,request_mode:'official-ui-observer-business-projection'});
       }catch(error){reject(error);}
      },{once:true});
     }
    }
   }catch(_){}
   return send.call(this,body);
  };
  XHR.prototype.open=wrappedOpen;XHR.prototype.send=wrappedSend;
  timer=setTimeout(()=>{const d=diagnostic.last;reject(new Error('未收到目标申请日期、全部状态和指定页的售后原生响应；xhr_sends='+diagnostic.xhr_sends+'；target_requests='+diagnostic.target_requests+'；parse_errors='+diagnostic.parse_errors+(d?'；begin='+d.begin+'；end='+d.end+'；page='+d.page+'；pageSize='+d.pageSize+'；tab_all='+d.tab_all+'；nonempty_keys='+d.nonempty_keys.join(','):'')));},22000);
  if(input.page===1){
   const dates=[...document.querySelectorAll('input.jd-range-input')].filter(e=>e.getClientRects().length);
   if(dates.length!==2)throw new Error('售后申请日期控件不唯一');
   for(let i=0;i<2;i++){
    dates[i].focus();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(dates[i],input.date);
    dates[i].dispatchEvent(new Event('input',{bubbles:true}));dates[i].dispatchEvent(new Event('change',{bubbles:true}));dates[i].dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));dates[i].blur();await new Promise(r=>setTimeout(r,200));
   }
   // Text parsing uses YYYY-MM-DD and loses the configured end-of-day time.
   // The official range panel's pick handler applies defaultTime[0/1].
   // Typed dates only position the calendar; commit through its native cells.
   dates[0].click();
   const visiblePanels=()=>[...document.querySelectorAll('.jd-date-range-picker')].filter(e=>e.getClientRects().length&&e.closest('[role="dialog"]')?.getAttribute('aria-hidden')!=='true');
   let panels=visiblePanels(),ready=Date.now()+2000;
   while(!panels.length&&Date.now()<ready){await new Promise(r=>setTimeout(r,50));panels=visiblePanels();}
   if(panels.length!==1)throw new Error('售后申请日期日历未就绪或不唯一');
   for(let pick=0;pick<2;pick++){
    const cells=[...panels[0].querySelectorAll('[aria-label="'+input.date+'"]')].filter(e=>e.getClientRects().length&&e.getAttribute('aria-disabled')!=='true'&&!e.closest('td')?.classList.contains('disabled'));
    if(cells.length!==1)throw new Error('售后目标日期不可选或不唯一');
    cells[0].click();await new Promise(r=>setTimeout(r,150));
    panels=visiblePanels();if(!panels.length)break;
   }
   if(visiblePanels().length)throw new Error('售后申请日期范围未通过原生日历提交');
   const size=document.querySelector('.jd-pagination__sizes');
   if(!size)throw new Error('售后每页条数控件缺失');
   if(!size.textContent.replace(/\s/g,'').includes(pageSize+'条/页')){
    const combo=size.querySelector('[role="combobox"]');if(!combo)throw new Error('售后每页条数下拉框缺失');combo.click();
    let option;const until=Date.now()+2000;
    do{const list=document.getElementById(combo.getAttribute('aria-controls'));option=[...(list?.querySelectorAll('[role="option"]')||[])].find(e=>e.textContent.replace(/\s/g,'')===pageSize+'条/页');if(option)break;await new Promise(r=>setTimeout(r,50));}while(Date.now()<until);
    if(!option)throw new Error('售后官方每页'+pageSize+'条选项不可用');option.click();await new Promise(r=>setTimeout(r,200));
   }
   if(!started){const q=[...document.querySelectorAll('button')].filter(e=>e.textContent.trim()==='查询'&&e.getClientRects().length);if(q.length!==1)throw new Error('售后查询按钮不唯一');q[0].click();}
  }else{
   const current=document.querySelector('.jd-pagination [aria-current="true"]'),next=document.querySelector('.jd-pagination .btn-next');
   if(Number(current?.textContent.trim())!==input.page-1||!next||next.disabled)throw new Error('售后分页未按顺序，不跳页');next.click();
  }
  return await response;
 }catch(error){return {error:'售后只读查询失败：'+String(error.message||error)};}
 finally{clearTimeout(timer);if(XHR.prototype.open===wrappedOpen)XHR.prototype.open=open;if(XHR.prototype.send===wrappedSend)XHR.prototype.send=send;}
}
async function runJDAfterSalesJob(job){
 const input=afterSalesInput(job),created=[],deadline=Date.now()+50000;
 async function execute(id,func,args=[],ms=6000){if(Date.now()>=deadline)throw new Error('售后后台任务总预算用尽');ms=Math.min(ms,deadline-Date.now());let timer;try{const r=await Promise.race([chrome.scripting.executeScript({target:{tabId:id},world:'MAIN',injectImmediately:true,func,args}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('售后页面执行超时：'+func.name)),ms);})]);if(!r?.[0]?.result||r[0].result.error)throw new Error(r?.[0]?.result?.error||'售后页面没有返回');return r[0].result;}finally{clearTimeout(timer);}}
 try{
  let info=(await chrome.tabs.query({url:JD_ORDER_SHOP_PAGE+'*'})).find(t=>!t.discarded&&t.status==='complete');
  if(!info){info=await chrome.tabs.create({url:JD_ORDER_SHOP_PAGE,active:false});created.push(info.id);}
  let merchant;for(let i=0;i<30&&Date.now()<deadline;i++){try{merchant=await execute(info.id,readJDOrderMerchant);break;}catch(_){await new Promise(r=>setTimeout(r,200));}}
  if(merchant?.store_key!==job.expected_store.store_key)throw new Error('售后店铺与官方商家映射不符');
  const tab=(await chrome.tabs.query({url:JD_AFS_PAGE.split('?')[0]+'*'})).filter(t=>!t.discarded&&t.status==='complete').sort((a,b)=>Number(!!b.active)-Number(!!a.active))[0];
  if(!tab)throw new Error('请打开已登录的官方自主售后页');
  const result=await execute(tab.id,afterSalesNativeRead,[input],27000),after=await execute(info.id,readJDOrderMerchant);
  if(after.store_key!==merchant.store_key||after.merchant_id!==merchant.merchant_id)throw new Error('售后读取期间店铺改变');
  return {...result,identity:{...after,merchant_identity_kind:merchant.kind,merchant_identity_anchor:JD_ORDER_SHOP_PAGE},source:'registered-api',transport:'registered-api',execution_page:tab.url};
 }finally{for(const id of created)try{await chrome.tabs.remove(id);}catch(_){}}
}
if(typeof module!=='undefined')module.exports={afterSalesInput,afterSalesNativeRead,runJDAfterSalesJob};
