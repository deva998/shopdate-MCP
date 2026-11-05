/* JD identity has its own local queue. Neither data scheduler can occupy it. */
let jdIdentityLoopRunning=false;
const jdIdentityState={running:false,lastError:'',lastJob:null};
async function jdIdentityHandle(job){
 const page='https://jdsz.jd.com/szweb/view/index/home.html';
 if(job.transport!=='jd-identity' || job.store_request?.platform!=='jd' || Object.keys(job.store_request).length!==1 || job.launch!==page || job.url!==page || job.account || job.cookie || job.body || job.operation)throw new Error('京东身份通道拒绝非身份只读任务');
 return {id:job.id,stores:await listCurrentStores('jd')};
}
async function jdIdentityBackgroundLoop(){
 if(jdIdentityLoopRunning)return;
 jdIdentityLoopRunning=true;
 const base='http://127.0.0.1:47923',headers={'X-Dmp-Bridge':chrome.runtime.id};
 try{
  let connected=false;
  for(;;){
   try{
    if(!connected){
     const hello=await fetch(base+'/hello?v='+chrome.runtime.getManifest().version,{headers,signal:AbortSignal.timeout(1500)});
     if(!hello.ok || (await hello.json()).app!=='jd-stores-cli')throw new Error('京东身份服务尚未就绪');
     connected=true;
    }
    const response=await fetch(base+'/next?wait=2&transport=jd-identity&v='+chrome.runtime.getManifest().version,{headers,signal:AbortSignal.timeout(4000)});
    if(response.status===204)continue;
    if(!response.ok)throw new Error('京东身份任务领取失败：'+response.status);
    const job=await response.json();jdIdentityState.running=true;jdIdentityState.lastJob=job.id;
    let out;
    try{out=await jdIdentityHandle(job);jdIdentityState.lastError='';}
    catch(error){out={id:job.id,error:String(error.message || error)};jdIdentityState.lastError=out.error;}
    const delivered=await fetch(base+'/result',{method:'POST',headers:{...headers,'Content-Type':'text/plain'},body:JSON.stringify(out),signal:AbortSignal.timeout(5000)});
    jdIdentityState.running=false;
    if(!delivered.ok)throw new Error('京东身份回传失败：'+delivered.status);
   }catch(error){
    connected=false;jdIdentityState.running=false;jdIdentityState.lastError=String(error.message || error);
    if(!(await chrome.tabs.query({url:'https://jdsz.jd.com/*'})).length)break;
    await sleep(1000);
   }
  }
 }finally{jdIdentityState.running=false;jdIdentityLoopRunning=false;}
}
