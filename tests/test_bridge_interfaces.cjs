// Offline bridge contracts; all network responses are synthetic.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const extension=path.join(__dirname,'../components/jd/extension/unpacked');

test('native complete-week requests retain fixed metrics and reject altered scopes',()=>{
  const contracts=JSON.parse(fs.readFileSync(path.join(extension,'report-contracts.json'),'utf8'));
  const context={console,Date,JSON,DEFAULT_REPORT:contracts.overview};vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(extension,'jd-guard.js'),'utf8'),context);
  const spec=contracts.overview;
  const body={...spec.template,startDate:'2026-10-26',endDate:'2026-11-01',compareStartDate:'2025-10-27',compareEndDate:'2025-11-02',compareType:'tb',dateType:'week',interval:'DAY'};
  const job={url:spec.endpoint,launch:spec.page,method:'POST',body:JSON.stringify(body)};
  assert.equal(context.reportRequest(job,spec.template,spec).dateType,'week');
  for(const patch of [{endDate:'2026-10-31'},{compareStartDate:'2025-10-26'},{channel:'app'},{indicators:['unregistered']}])
    assert.throws(()=>context.reportRequest({...job,body:JSON.stringify({...body,...patch})},spec.template,spec));
});

test('public discovery accepts only bounded official HTTPS static resources',()=>{
  const context={URL};vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(extension,'sycm-public-assets.js'),'utf8'),context);
  assert.equal(context.sycmPublicAssetAllowed('https://g.alicdn.com/dt/ops-flow/example.js'),true);
  for(const url of ['http://g.alicdn.com/dt/ops-flow/example.js','https://example.org/file.js','https://g.alicdn.com/dt/ops-flow/../file.js','https://g.alicdn.com/dt/ops-flow/file.js?token=x','https://user:pass@g.alicdn.com/dt/ops-flow/file.js'])
    assert.equal(context.sycmPublicAssetAllowed(url),false);
});

test('discovery rejects write bodies before fetch and returns source as text',async()=>{
  const requests=[];
  const context={URL,AbortSignal,fetch:async(url,options)=>{requests.push({url,options});return {status:200,headers:{get:()=>null},text:async()=> 'window.synthetic = "text only";'};}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(extension,'sycm-public-assets.js'),'utf8'),context);
  const url='https://g.alicdn.com/dt/ops-flow/example.js';
  for(const patch of [{method:'POST'},{body:'x'},{cookie:'x'}])assert.ok((await context.sycmFetchPublicAsset({id:'example',url,...patch})).error);
  assert.equal(requests.length,0);
  const result=await context.sycmFetchPublicAsset({id:'example',url});
  assert.equal(result.text,'window.synthetic = "text only";');assert.equal(context.synthetic,undefined);
  assert.equal(requests.length,1);assert.equal(requests[0].options.credentials,'omit');assert.equal(requests[0].options.redirect,'error');
});
