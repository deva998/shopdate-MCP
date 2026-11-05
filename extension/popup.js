// 命令行打招呼时报的名字 -> 平台（显示「正在服务」哪个工具）
const TOOLS = [
  ["stores-cli", "店铺身份识别", "京东商智与生意参谋"],
  ["sycm-cli", "生意参谋", "店铺经营数据"],
  ["alimama-cli", "万相台", "广告报表、在投计划（只读）"],
  ["qianniu-cli", "千牛", "评价、商品、物流"],
  ["dmp-cli", "达摩盘", "人群资产、画像"],
  ["alibaba-cli", "1688", "订单统计"],
  ["alisycm-cli", "1688", "生意参谋"],
  ["voc-cli", "taobao-voc", "竞品评价、问大家（买家账号）"],
];

document.getElementById('version').textContent='v'+chrome.runtime.getManifest().version;
chrome.runtime.sendMessage({ type: "status" }, (st) => {
  const el = document.getElementById("s");
  if (chrome.runtime.lastError || !st) { el.textContent = "后台未响应，请在扩展程序页重新加载本插件。"; return; }
  const name = (TOOLS.find((t) => t[0] === st.app) || [st.app, st.app])[1];
  el.textContent = st.connected
    ? `任务连接：${name}（已处理 ${st.jobs} 个请求）`
    : '任务：待命。账号登录状态见各账号右侧圆点。';
});

// ---- 账号切换 ----
const LOGIN_URL = { taobao: "https://login.taobao.com/", "1688": "https://login.1688.com/" };
const accMsg = (text) => { document.getElementById("msg").textContent = text || ""; };
const askBg = (msg) => new Promise((ok) => {
  const timer=setTimeout(()=>ok({error:'后台响应超时，请重新加载扩展后再试。'}),msg.op==='check' ? 60000 : 8000);
  chrome.runtime.sendMessage({ type: "account", ...msg }, result=>{
    clearTimeout(timer);
    const error=chrome.runtime.lastError;
    ok(error ? {error:error.message} : result);
  });
});

const JD_PAGE='https://jdsz.jd.com/szweb/view/tradeAnalysis/tradeSummary.html';
async function openJD(tabId){
  if(tabId){try{await chrome.tabs.update(tabId,{active:true});return;}catch(_){} }
  await chrome.tabs.create({url:JD_PAGE});
}
let jdRequest=0;
function askJD(op,extra={}){
  return new Promise(resolve=>{
    const timer=setTimeout(()=>resolve({error:'京东账号状态读取超时，稍后重试。'}),15000);
    chrome.runtime.sendMessage({type:'jd-account',op,...extra},result=>{
      clearTimeout(timer);const error=chrome.runtime.lastError;
      resolve(error?{error:error.message}:result);
    });
  });
}
async function renderJD(force=false){
  const request=++jdRequest;
  const box=document.getElementById('jd-stores');
  let cached=[];
  try{const data=await chrome.storage.local.get(['jdPopupAccounts','jdLastStores']);cached=data.jdPopupAccounts || (data.jdLastStores || []).map(x=>({...x,active:true}));}catch(_){}
  if(request!==jdRequest)return;
  function draw(accounts,status){
    box.textContent='';
    for(const account of accounts){
      const row=document.createElement('div');row.className='row';
      const state=status?.uid?accountState(status,account.uid):{state:status?.state || 'checking',label:status?.state==='offline'?'未登录':status?.state==='unknown'?'待确认':'核验中',detail:status?.detail};
      const current=status?.uid?status.uid===account.uid:account.active;
      const name=document.createElement('span');name.className=current?'n cur':'n';name.textContent=account.name;name.title=account.store_key || account.nick || '';
      row.append(name);
      if(status?.uid && status.uid!==account.uid && account.uid)row.append(button('切换',async()=>{
        const result=await askJD('use',{name:account.name});
        if(result.error){accMsg(result.error);return;}
        accMsg('已切换京东账号，正在打开商智核验店铺。');await openJD();await renderJD(true);
      }));
      const remove=button('删除',async()=>{
        if(!confirm(`删除存下的「${account.name}」？浏览器里现在的登录不受影响。`))return;
        const result=await askJD('remove',{name:account.name});
        if(result.error){accMsg(result.error);return;}
        accMsg('已删除本机账号存档，当前登录不受影响。');await renderJD();
      });
      remove.disabled=!account.uid;
      row.append(remove,statusDot(state));
      box.append(row);
    }
    if(!accounts.length){const empty=document.createElement('small');empty.textContent='暂无已保存的京东账号';box.append(empty);}
    const addRow=document.createElement('div');addRow.className='row';
    const add=button('添加账号',async()=>{
      add.disabled=true;accMsg('正在保存当前账号…');
      try{const result=await askJD('fresh');if(result.error){accMsg(result.error);return;}
        await chrome.tabs.create({url:result.ok.loginUrl});window.close();
      }finally{add.disabled=false;}
    });
    addRow.append(add);box.append(addRow);
  }
  draw(cached,{state:'checking',detail:'正在核验当前账号，账号名称与状态分开显示'});
  const result=await askJD('list',{force});
  if(request!==jdRequest)return;
  if(result?.ok){
    const accounts=result.ok.accounts || [];
    draw(accounts,result.ok.status);
    await chrome.storage.local.set({jdPopupAccounts:accounts.map(({name,uid,active,store_key,tab_id})=>({name,uid,active,store_key,tab_id}))});
  }else draw(cached,{state:'unknown',detail:result?.error || '暂时无法确认账号状态'});
}

function button(text, onClick) {
  const b = document.createElement("button");
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

let checking = false;
const loginStates={};
const loginPending=new Set();
function statusDot(status) {
  const d = document.createElement("span");
  d.className = "st " + (status.state==='online'?'on':'');
  d.title = status.detail || status.label;
  d.setAttribute('aria-label',status.label);
  const group=document.createElement('span');group.className='row';
  const label=document.createElement('small');label.textContent=status.label;
  group.append(d,label);return group;
}
function loadLoginState(scope,force=false){
  if(loginPending.has(scope))return;
  loginPending.add(scope);
  chrome.runtime.sendMessage({type:'login-status',scope,force},result=>{
    const error=chrome.runtime.lastError;
    loginStates[scope]=error || result?.error || !result?.status ? {state:'unknown',uid:null,detail:error?.message || result?.error || '后台没有返回状态'} : result.status;
    loginPending.delete(scope);
    renderAccounts().catch(e=>accMsg(String(e)));
  });
}

async function renderAccounts() {
  const res = await askBg({ op: "list" });
  const box = document.getElementById("accounts");
  box.textContent = "";
  if (!res || res.error) { accMsg(res ? res.error : "后台没有响应"); return; }
  // 淘宝在前（JS 会把「1688」这种数字键排到最前）
  for (const [scope, cur] of Object.entries(res.ok.current).sort(([a], [b]) => (a === "taobao" ? -1 : b === "taobao" ? 1 : 0))) {
    const sec = document.createElement("div");
    sec.className = "acc";
    const h = document.createElement("h2");
    h.textContent = `${cur.label}账号`;
    sec.append(h);
    if(!loginStates[scope])loadLoginState(scope);
    const saved = cur.loggedIn && res.ok.scopes[scope].some((a) => a.uid === cur.uid);
    if (!saved) {   // 存过的账号用绿色名字表示「现在用的是它」；没存过或没登录才单独写一行
      const now = document.createElement("div");now.className='row';
      const label=document.createElement('span');label.className='n';
      label.textContent=cur.loggedIn ? `当前账号：${cur.nick || cur.uid}（未保存）` : '当前没有登录账号';
      const status=accountState(loginStates[scope],cur.uid);
      if(status.state==='online')label.classList.add('cur');
      now.append(label,statusDot(status));
      sec.append(now);
    }
    for (const a of res.ok.scopes[scope]) {
      const row = document.createElement("div");
      row.className = "row";
      const n = document.createElement("span");
      const state=accountState(loginStates[scope],a.uid);
      n.className = "n" + (state.state==='online' ? " cur" : "");
      n.textContent = a.name;
      n.title = a.nick;
      row.append(n);
      if (state.state==='offline' && a.active && state.detail) {
        const w = document.createElement("small");
        w.className = "bad";
        w.textContent = state.detail.split("（")[0];
        row.append(w);
      }
      if (state.state==='offline' && a.active) row.append(button("重新登录", async () => {
        // 掉线的账号：把现在的登录先存好、从浏览器里收起来，再打开登录页；登录的还是这个号，插件会自动把它的存档换成新的登录
        const r = await askBg({ op: "fresh", scope });
        if (r && r.error) { accMsg(r.error); return; }
        chrome.tabs.create({ url: r.ok.loginUrl });
        window.close();
      }));
      else if (!a.active) row.append(button("切换", async () => {
        accMsg("正在切换…");
        const r = await askBg({ op: "use", scope, name: a.name });
        accMsg(r && r.error ? r.error : `已换成「${a.name}」，刷新后台页面后生效。`);
        delete loginStates[scope];renderAccounts();
      }));
      row.append(button("删除", async () => {
        if (!confirm(`删除存下的「${a.name}」？浏览器里现在的登录不受影响。`)) return;
        const r = await askBg({ op: "remove", scope, name: a.name });
        accMsg(r && r.error ? r.error : "");
        renderAccounts();
      }));
      row.append(statusDot(state));
      sec.append(row);
    }
    if (cur.loggedIn) {
      // 加新账号不要点网页上的「退出」：那会让存下的这个账号失效。这里只把它从浏览器里收起来，再去登录新的
      const row = document.createElement("div");
      row.className = "row";
      row.append(button("登录新账号", async () => {
        const r = await askBg({ op: "fresh", scope });
        if (r && r.error) { accMsg(r.error); return; }
        chrome.tabs.create({ url: r.ok.loginUrl });
        window.close();
      }));
      sec.append(row);
    } else {
      const row = document.createElement("div");
      row.className = "row";
      row.append(button("去登录", () => { chrome.tabs.create({ url: LOGIN_URL[scope] }); window.close(); }));
      sec.append(row);
    }
    if (cur.loggedIn && !saved) {
      const row = document.createElement("div");
      row.className = "row";
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = `给现在这个账号起个名字，如「主店」`;
      row.append(input, button("保存", async () => {
        const r = await askBg({ op: "save", scope, name: input.value });
        accMsg(r && r.error ? r.error : `已保存为「${r.ok.name}」。`);
        renderAccounts();
      }));
      sec.append(row);
    }
    box.append(sec);
  }
}

async function checkAccounts() {
  if(checking)return;
  const control=document.getElementById('accounts-check');
  control.disabled=true;
  checking = true;
  try {
    await renderAccounts();
    for(const scope of ['taobao','1688']){delete loginStates[scope];loadLoginState(scope,true);}
    await renderJD(true);
  } finally {
    checking = false;
    control.disabled=false;
    await renderAccounts();
  }
}
document.getElementById('accounts-check').addEventListener('click',()=>checkAccounts().catch(e=>accMsg(String(e))));
renderAccounts().catch(e=>accMsg(String(e)));
renderJD().catch(e=>accMsg(String(e)));
