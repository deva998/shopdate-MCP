// Account identifiers may be returned; credentials remain inside the original account bridge.
// Popup needs the first responsive page, not the slowest open JD tab.
let jdIdentityRecoveryPending=null;
async function jdIdentitySession(){
  if(typeof scopeCookies!=='function' || typeof whoIs!=='function')return null;
  const cookies=await scopeCookies('jd'),me=whoIs('jd',cookies);
  if(!me.uid)return null;
  // Private comparison key only; never return cookie values in identities/logs.
  return JSON.stringify([me.uid,cookies.filter(c=>['pin','pt_pin','thor','pt_key'].includes(c.name)).map(c=>[c.domain,c.name,c.value].join('|')).sort()]);
}
// Page lifecycle stalls are not login failures. Verify the live session in one
// owned, inactive homepage; never reload/activate a user's tab or trust a vault.
async function recoverJDIdentity(session){
  if(!session)return [];
  if(jdIdentityRecoveryPending)return jdIdentityRecoveryPending.session===session?jdIdentityRecoveryPending.promise:[];
  if(!chrome.tabs.create || !chrome.tabs.get || !chrome.tabs.remove)return [];
  const promise=(async()=>{
    let owned,abandoned=false;
    const url='https://jdsz.jd.com/szweb/view/index/home.html',deadline=Date.now()+8000;
    async function bounded(operation,until=deadline){
      let timer;
      try{return await Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('后台身份复核超时')),Math.max(1,until-Date.now()));})]);}
      finally{clearTimeout(timer);}
    }
    async function cleanup(id){try{await bounded(chrome.tabs.remove(id),Date.now()+1000);}catch(_){} }
    try{
      if(await bounded(jdIdentitySession())!==session)return [];
      const creation=chrome.tabs.create({url,active:false});
      // A delayed Chrome callback may arrive after the caller's deadline.
      creation.then(tab=>{if(abandoned)void cleanup(tab.id);else owned=tab;},()=>{});
      owned=await bounded(creation);
      do{
        const tab=await bounded(chrome.tabs.get(owned.id));
        if(tab.status==='complete' && tab.url?.split(/[?#]/)[0]!==url)return [];
        if(tab.status==='complete' && tab.url?.split(/[?#]/)[0]===url){
          let timer;
          try{
            const results=await Promise.race([
              chrome.scripting.executeScript({target:{tabId:owned.id},world:'MAIN',injectImmediately:true,func:readJDIdentity,args:['/szweb/view/index/home.html']}),
              new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('后台身份复核超时')),Math.min(2000,Math.max(1,deadline-Date.now())));})]);
            const identity=results?.[0]?.result;
            if(identity?.platform==='jd' && /^jd:mall:\d+$/.test(identity.store_key || '') && identity.identity_anchor==='https://mall.jd.com/index-'+identity.store_key.split(':').at(-1)+'.html'){
              if(await bounded(jdIdentitySession())!==session)return [];
              return [{...identity,tab_id:owned.id,observed_at:new Date().toISOString(),identity_source:'owned_background_recovery'}];
            }
          }catch(_){return [];}
          finally{clearTimeout(timer);}
        }
        await new Promise(resolve=>setTimeout(resolve,100));
      }while(Date.now()<deadline);
      return [];
    }catch(_){return [];}
    finally{abandoned=true;if(owned)await cleanup(owned.id);}
  })();
  jdIdentityRecoveryPending={session,promise};
  try{return await promise;}finally{if(jdIdentityRecoveryPending?.promise===promise)jdIdentityRecoveryPending=null;}
}
async function fastJDStores(timeoutMs=4000){
  const session=await jdIdentitySession();
  const paths=['/szweb/view/index/home.html','/szweb/view/tradeAnalysis/tradeSummary.html','/szweb/view/product/productDetail.html','/szweb/view/view-source/view-flow.html','/szweb/view/product/mark-new-product-temp.html','/szweb/view/flow/flow-summary.html'];
  const tabs=await chrome.tabs.query({url:'https://jdsz.jd.com/szweb/view/*'});
  const jobs=tabs.filter(t=>!t.discarded && t.status!=='loading' && paths.includes(new URL(t.url).pathname)).map(async tab=>{
    let timer;
    try{
      const results=await Promise.race([chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',injectImmediately:true,func:readJDIdentity,args:[new URL(tab.url).pathname]}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('页面超时')),timeoutMs);})]);
      if(!results[0]?.result)throw new Error('无店铺身份');
      return {...results[0].result,tab_id:tab.id,observed_at:new Date().toISOString()};
    }finally{clearTimeout(timer);}
  });
  try{return [await Promise.any(jobs)];}catch(_){return tabs.length?recoverJDIdentity(session):[];}
}

async function listCurrentStores(platform='',timeoutMs=2500) {
  const rows=[];
  async function deadline(operation){
    let timer;
    try{return await Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('页面身份读取超时')),timeoutMs);})]);}
    finally{clearTimeout(timer);}
  }
  if(!platform || platform==='jd'){
    const session=await deadline(jdIdentitySession());
    const paths=['/szweb/view/index/home.html','/szweb/view/tradeAnalysis/tradeSummary.html','/szweb/view/product/productDetail.html','/szweb/view/view-source/view-flow.html','/szweb/view/product/mark-new-product-temp.html','/szweb/view/flow/flow-summary.html'];
    const tabs=await deadline(chrome.tabs.query({url:'https://jdsz.jd.com/szweb/view/*'}));
    const found=await Promise.all(tabs.map(async tab=>{
      try {
        const path=new URL(tab.url).pathname;
        if(!paths.includes(path) || tab.discarded || tab.status==='loading')return null;
        const results=await deadline(chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',injectImmediately:true,func:readJDIdentity,args:[path]}));
        const identity=results[0]?.result;
        return identity?{...identity,tab_id:tab.id,observed_at:new Date().toISOString()}:null;
      } catch(_){return null;}
    }));
    const identities=found.filter(Boolean);
    rows.push(...(identities.length?identities:tabs.length?await recoverJDIdentity(session):[]));
  }
  if(!platform || platform==='sycm'){
    const cookies=await scopeCookies('taobao');
    const identity=whoIs('taobao',cookies);
    if(identity.uid){
      const tabs=await chrome.tabs.query({url:'https://sycm.taobao.com/*'});
      rows.push({platform:'sycm',store_key:'sycm:account:'+identity.uid,name:identity.nick || identity.uid,
        identity_kind:'taobao_account',shop_name_verified:false,
        note:'这是淘宝账号标识；当前生意参谋店铺名称需在页面确认，不能把账号昵称当作已验证店铺名。',
        tab_ids:tabs.map(t=>t.id),observed_at:new Date().toISOString()});
    }
  }
  return [...new Map(rows.map(r=>[r.store_key,r])).values()];
}
