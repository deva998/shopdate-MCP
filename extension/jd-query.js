/* Serialized into the inspected page. Only operates observed, read-only UI controls. */
function nativeQueryAction({key,expected,step,store}) {
  const paths={overview:'/szweb/view/tradeAnalysis/tradeSummary.html',
    'products-sku':'/szweb/view/product/productDetail.html','products-spu':'/szweb/view/product/productDetail.html',
    'traffic-level1':'/szweb/view/view-source/view-flow.html','traffic-level2':'/szweb/view/view-source/view-flow.html'};
  if(!paths[key] || location.origin!=='https://jdsz.jd.com' || location.pathname!==paths[key])throw new Error('不是任务要求的报表页');
  const anchors=[...new Set([...document.querySelectorAll('a[href]')].filter(a=>/^https:\/\/mall\.jd\.com\/index-\d+\.html(?:[?#].*)?$/.test(a.href) && (a.innerText || a.textContent || '').trim()).map(a=>a.href.split(/[?#]/)[0]))];
  if(anchors.length!==1 || anchors[0]!=='https://mall.jd.com/index-'+String(store).replace('jd:mall:','')+'.html')throw new Error('操作前店铺身份不符');
  if(!expected || !/^\d{4}-\d{2}-\d{2}$/.test(expected.startDate) || expected.endDate!==expected.startDate || expected.compareType!=='hb')throw new Error('仅支持已登记单日环比任务');
  const visible=e=>e.getClientRects().length>0;
  const select=selector=>[...document.querySelectorAll(selector)].filter(visible);
  function one(selector){const nodes=select(selector);if(nodes.length!==1)throw new Error('查询控件缺失或不唯一：'+selector);return nodes[0];}
  function click(selector){const node=one(selector);node.click();return {clicked:true};}
  const dateSelector=value=>'[data-component-name="ComboDatePicker"][data-event-content="当前时间_'+value+'"]';
  const selected=node=>node.classList.contains('jmt-combo-date-picker-list-tag-select');
  if(step==='inspect'){
    const channelRows=select('.jmt--form-item-main').filter(row=>row.querySelector('label')?.textContent.trim()==='渠道');
    const channel=channelRows.length===1?channelRows[0].querySelector('.jmt-selector')?.getAttribute('value'):null;
    if(channel!==expected.channel)throw new Error('渠道未确认或不匹配，停止自动查询：'+channel);
    if(select('input[type="text"],input:not([type]),textarea').some(e=>e.value?.trim()))throw new Error('存在商品ID、SPU或关键词筛选，请先清空后重试');
    if(select('input[type="checkbox"]').some(e=>e.checked && e.closest('label')?.textContent.includes('仅看关注')))throw new Error('仅看关注商品已开启');
    return {channel};
  }
  if(step==='dimension'){
    if(!key.startsWith('products-'))return {ready:true};
    const dimension=key==='products-spu'?'SPU':'SKU';
    const node=one('[role="tab"][data-event-content="'+dimension+'"]');
    if(node.getAttribute('aria-selected')==='true')return {ready:true};
    node.click();return {clicked:true};
  }
  if(step==='dimension-ready')return {ready:!key.startsWith('products-') || one('[role="tab"][data-event-content="'+(key==='products-spu'?'SPU':'SKU')+'"]').getAttribute('aria-selected')==='true'};
  if(step==='alternate'){
    const node=one(dateSelector('近7天'));
    return click(dateSelector(selected(node)?'近30天':'近7天'));
  }
  if(step==='yesterday')return click(dateSelector('昨天'));
  if(step==='calendar'){
    // ComboDatePicker defaults to trigger="hover". Clicking applies its default
    // day; entering the selector opens the live calendar and its change handler.
    one(dateSelector('天')).dispatchEvent(new MouseEvent('mouseover',{bubbles:true,cancelable:true}));
    return {hovered:true};
  }
  if(step==='date-cell')return click('[role="gridcell"][data-event-content="当前时间天_'+expected.startDate+'"]');
  if(step==='date-ready'){
    const text=document.body.innerText;
    const current=/当前[：:]\s*(\d{4}-\d{2}-\d{2})/.exec(text)?.[1];
    const previous=/对比[：:]\s*(\d{4}-\d{2}-\d{2})/.exec(text)?.[1];
    return {ready:current===expected.startDate && previous===expected.compareStartDate,current,previous};
  }
  if(step==='compare'){
    const node=one('[data-component-name="ComboDatePicker"][data-event-content="对比时间_天_环比"]');
    if(selected(node))return {ready:true};node.click();return {clicked:true};
  }
  if(step==='source-count')return {count:select('tr').filter(row=>row.querySelector('.source-name')).length};
  if(step==='sources'){
    if(key!=='traffic-level2' || JSON.stringify(expected.flowSrcId1)!=='["2"]')throw new Error('未登记的流量父来源');
    const rows=select('tr').filter(row=>row.querySelector('.source-name')?.textContent.trim()==='站内场域');
    if(rows.length!==1)throw new Error('未找到唯一站内场域来源行');
    const button=rows[0].querySelector('.jmt-table-tree-icon-expand-button');
    if(!button)throw new Error('流量展开按钮未就绪');button.click();return {clicked:true};
  }
  throw new Error('未登记的网页操作：'+step);
}
if(typeof module!=='undefined')module.exports={nativeQueryAction};
