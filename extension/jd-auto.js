/* Local task polling only. Never calls JD endpoints or browser query controls. */
function startAutoReceiver({isEnabled,isBusy,poll,schedule=setTimeout,cancel=clearTimeout}) {
  let stopped=false,timer;
  async function tick() {
    if(stopped)return;
    try {if(isEnabled() && !isBusy()) await poll();} catch (_) { /* Server absent: keep idle. */ }
    finally {if(!stopped) timer=schedule(tick,1000);}
  }
  timer=schedule(tick,1000);
  return ()=>{stopped=true;cancel(timer);};
}
if(typeof module!=='undefined')module.exports={startAutoReceiver};
