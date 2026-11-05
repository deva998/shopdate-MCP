// DOM identity only. Mall links are page identity anchors, not JD API shopId.
function readJDIdentity(requiredPath='/szweb/view/tradeAnalysis/tradeSummary.html') {
  if(!['/szweb/view/index/home.html','/szweb/view/tradeAnalysis/tradeSummary.html','/szweb/view/product/productDetail.html','/szweb/view/view-source/view-flow.html','/szweb/view/product/mark-new-product-temp.html','/szweb/view/flow/flow-summary.html'].includes(requiredPath))return null;
  if(location.origin!=='https://jdsz.jd.com' || location.pathname!==requiredPath)return null;
  const links=[...document.querySelectorAll('a[href]')].map(a=>({url:a.href,name:(a.innerText || a.textContent || '').trim()}))
    .filter(a=>/^https:\/\/mall\.jd\.com\/index-\d+\.html(?:[?#].*)?$/.test(a.url) && a.name);
  const distinct=[...new Map(links.map(a=>[a.url.split(/[?#]/)[0],a])).values()];
  if(distinct.length!==1)return null;
  const one=distinct[0],match=/index-(\d+)\.html/.exec(one.url);
  return {platform:'jd',store_key:'jd:mall:'+match[1],name:one.name,identity_kind:'page_mall_link',identity_anchor:one.url.split(/[?#]/)[0]};
}

function sameStore(expected,actual){
  return !!actual && expected?.platform===actual.platform && expected?.store_key===actual.store_key;
}
if(typeof module!=='undefined')module.exports={readJDIdentity,sameStore};
