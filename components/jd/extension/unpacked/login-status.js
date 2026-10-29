// Current-session state only. A saved account is not necessarily signed in.
const loginCache = new Map();
async function currentLoginStatus(scope, force=false) {
  if(!SCOPES[scope])throw new Error('不支持的账号平台');
  const cookies=await scopeCookies(scope);
  const me=whoIs(scope,cookies);
  const checked_at=new Date().toISOString();
  if(!me.uid)return {state:'offline',uid:'',detail:'未登录',checked_at};
  const previous=loginCache.get(scope);
  if(!force && previous?.uid===me.uid && Date.now()-Date.parse(previous.checked_at)<60000)return previous;
  const result=await probe(scope,cookies);
  // Identity may change while a network probe is running.
  const after=whoIs(scope,await scopeCookies(scope));
  if(after.uid!==me.uid)return {state:'unknown',uid:after.uid,detail:'检查期间账号发生变化，请稍后重试',checked_at};
  const status={state:result.alive===true?'online':result.alive===false?'offline':'unknown',
    uid:me.uid,detail:result.how,checked_at:new Date().toISOString(),source:'backend_login_probe'};
  loginCache.set(scope,status);
  return status;
}

function accountState(status, uid) {
  if(!status)return {state:'checking',label:'检查中'};
  if(status.state==='unknown' && !status.uid)return {state:'unknown',label:'无法确认',detail:status.detail};
  if(!uid || !status.uid || status.uid!==uid)return {state:'offline',label:'未登录'};
  return {state:status.state,label:status.state==='online'?'已登录':status.state==='offline'?'登录失效':'无法确认',detail:status.detail};
}
if(typeof module!=='undefined')module.exports={accountState};
