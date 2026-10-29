// JD credentials use the same local-only vault as Taobao, never MCP responses.
let jdStatusCache=null;
let jdStatusPending=null;
function invalidateJDStatus(){jdStatusCache=null;}
async function reloadJDReports(){
  const tabs=await chrome.tabs.query({url:'https://jdsz.jd.com/szweb/view/*'});
  await Promise.allSettled(tabs.filter(t=>!t.discarded).map(t=>chrome.tabs.reload(t.id)));
}

async function currentJDLoginStatus(force=false){
  const cookies=await scopeCookies('jd'),me=whoIs('jd',cookies);
  const signature=cookies.filter(c=>['pin','pt_pin','thor','pt_key'].includes(c.name)).map(c=>[c.domain,c.name,c.value].join('|')).sort().join(';');
  if(!me.uid)return {state:cookies.length?'unknown':'offline',uid:'',stores:[],checked_at:new Date().toISOString(),detail:cookies.length?'无法确认当前京东账号，请打开商智页面核验':'未登录'};
  if(!force && jdStatusCache?.signature===signature && Date.now()-jdStatusCache.at<30000){
    const tabIds=new Set((await chrome.tabs.query({url:'https://jdsz.jd.com/szweb/view/*'})).filter(t=>!t.discarded && t.status!=='loading').map(t=>t.id));
    if(jdStatusCache.status.stores.every(s=>s.identity_source==='owned_background_recovery' || tabIds.has(s.tab_id)))return jdStatusCache.status;
  }
  if(jdStatusPending?.signature===signature)return jdStatusPending.promise;
  const promise=(async()=>{
    const stores=await fastJDStores();
    const after=whoIs('jd',await scopeCookies('jd'));
    if(after.uid!==me.uid)return {state:'unknown',uid:after.uid,stores:[],detail:'检查期间账号发生变化',checked_at:new Date().toISOString()};
    const status={state:stores.length?'online':'unknown',uid:me.uid,stores,source:'current_page_identity',checked_at:new Date().toISOString(),detail:stores.length?'已识别当前商智登录页面；接口权限在取数时校验':'请打开已登录的商智页面；未识别不等于登录失效'};
    // A transient failed read must not suppress recovery on the next check.
    jdStatusCache=stores.length?{signature,status,at:Date.now()}:null;return status;
  })();
  jdStatusPending={signature,promise};
  try{return await promise;}finally{if(jdStatusPending?.promise===promise)jdStatusPending=null;}
}

async function jdAccountList(force=false){
  const status=await currentJDLoginStatus(force);
  let {jdHiddenUids=[]}=await chrome.storage.local.get('jdHiddenUids');
  if(status.state==='online' && status.uid && !jdHiddenUids.includes(status.uid)){
    const store=status.stores[0],name=store.name.replace(/\s+/g,' ').trim();
    const v=await loadVault(),cookies=await scopeCookies('jd');
    // Reject an identity/cookie race instead of binding a shop to another login.
    if(whoIs('jd',cookies).uid===status.uid){
      let key=Object.keys(v.accounts.jd).find(n=>v.accounts.jd[n].uid===status.uid) || name;
      for(let i=2;v.accounts.jd[key] && v.accounts.jd[key].uid!==status.uid;i++)key=name+'（'+i+'）';
      v.accounts.jd[key]={uid:status.uid,nick:name,cookies,savedAt:Date.now(),store_key:store.store_key,tab_id:store.tab_id};
      v.activeAccount.jd=key;await saveVault(v);
      await chrome.storage.local.set({jdLastStores:[{name,store_key:store.store_key,tab_id:store.tab_id,observed_at:store.observed_at}]});
    }
  }
  const v=await loadVault();
  return {accounts:Object.entries(v.accounts.jd).filter(([,a])=>!jdHiddenUids.includes(a.uid)).map(([name,a])=>({...summary('jd',name,a,v.activeAccount.jd),store_key:a.store_key,tab_id:a.tab_id})),status};
}

async function jdAccountRemove(name){
  const v=await loadVault(),record=v.accounts.jd[name];
  if(!record)throw new Error('没有存过这个京东账号');
  await accountRemove('jd',name);
  const {jdHiddenUids=[],jdLastStores=[]}=await chrome.storage.local.get(['jdHiddenUids','jdLastStores']);
  await chrome.storage.local.set({jdHiddenUids:[...new Set([...jdHiddenUids,record.uid])],jdLastStores:jdLastStores.filter(s=>s.store_key!==record.store_key)});
  return {removed:true};
}

async function jdAccountFresh(){
  const cookies=await scopeCookies('jd'),me=whoIs('jd',cookies);
  if(cookies.length && !me.uid)throw new Error('未能确认当前京东账号，未更改登录。请先打开商智页面并确认账号。');
  // Explicit Add re-enables saving this account before storing a new login.
  await chrome.storage.local.set({jdHiddenUids:[]});
  await jdAccountList(true);
  const result=await accountFresh('jd');invalidateJDStatus();
  await chrome.storage.local.set({jdLastStores:[],jdPopupAccounts:[]});
  await reloadJDReports();return result;
}

async function jdAccountUse(name){
  const result=await accountUse('jd',name);invalidateJDStatus();
  await chrome.storage.local.set({jdLastStores:[],jdPopupAccounts:[]});
  await reloadJDReports();return result;
}

async function handleJDAccount(msg){
  if(msg.op==='list')return jdAccountList(!!msg.force);
  if(msg.op==='remove')return jdAccountRemove(msg.name);
  if(msg.op==='fresh')return jdAccountFresh();
  if(msg.op==='use')return jdAccountUse(msg.name);
  throw new Error('未知京东账号操作');
}
