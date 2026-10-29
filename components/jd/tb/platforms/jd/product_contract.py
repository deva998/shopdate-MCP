"""Observed SKU/SPU product-table contracts, discovery parser only; no network."""
from datetime import date,timedelta
from .overview import numeric

ENDPOINT='https://szgateway.jd.com/api/lowcode/productDetail/table/productTable.ajax'
AMOUNT='jdr_sch_trade_deal_ord_ord_amt_sz_trade_deal_snapshot'
QUANTITY='jdr_sch_trade_deal_ord_sku_qtty_sz_trade_deal_snapshot'
RATE='fo_jdr_sch_industry_deal_rate'
VISITORS='jdr_sch_traffic_brow_sku__page_cnt_traffic_plat_item_di_sz_bsg'
FIELDS=[('成交金额',AMOUNT,'元'),('成交商品件数',QUANTITY,'件'),
        ('商品成交转化率',RATE,'fraction'),('商品访客数',VISITORS,'人')]


def parse_sample(sample, *, sample_only=True):
    if sample.get('url')!=ENDPOINT or sample.get('method')!='POST' or sample.get('status')!=200:
        raise ValueError('不是成功的原生商品明细响应')
    request=sample.get('request_body') or {}
    dimension=request.get('proType')
    if dimension not in ('sku','spu'):raise ValueError('商品维度未验证')
    id_field=dimension+'_id'
    selected=date.fromisoformat(request.get('startDate',''))
    day=selected.isoformat();previous=(selected-timedelta(days=1)).isoformat()
    expected={'proType':dimension,'realtime':False,'dateType':'day','interval':'DAY','startDate':day,
        'endDate':day,'compareStartDate':previous,'compareEndDate':previous,'compareType':'hb',
        'channel':'all','onlyAttention':False}
    if any(type(request.get(key)) is not type(value) or request.get(key)!=value for key,value in expected.items()):
        raise ValueError('当前只验证SKU/SPU、单日、全部渠道、前一日对比；不猜测其他参数合同')
    payload=sample.get('response') or {}
    if payload.get('header',{}).get('code')!=0 or payload.get('errors'):
        raise ValueError('商品接口业务状态失败')
    body=payload.get('body') or {};rows=body.get('data')
    if not isinstance(rows,list) or not rows:raise ValueError('商品响应缺少数据数组')
    items=[];summary=None;seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('商品记录结构异常')
        metrics={name:{'field':field,'unit':unit,'value':numeric(row.get(field)),
           'previous':numeric(row.get(field+'##compareValue')),
           'relative_change':numeric(row.get(field+'##compare'))} for name,field,unit in FIELDS}
        item={id_field:row.get(id_field),'name':row.get('name'),'item_num':row.get('item_num'),'metrics':metrics}
        if row.get('$summary') is True or row.get(id_field)=='合计':
            if summary is not None:raise ValueError('多条合计行，待核查')
            summary=item;continue
        if not isinstance(item[id_field],str) or not item[id_field].isdigit():raise ValueError('商品编号缺失或无效')
        if item[id_field] in seen:raise ValueError('商品编号重复，拒绝重复计数')
        seen.add(item[id_field]);items.append(item)
    return {'date':day,'compare_date':previous,'dimension':dimension,'channel':'all',
       'coverage':'sample_only' if sample_only else 'returned_rows_only','complete':None,'reported_size':body.get('size'),
       'original_body_data_length':(sample.get('response_metadata') or {}).get('original_body_data_length'),
       'captured_rows':len(rows),'captured_item_rows':len(items),'summary':summary,'items':items,
       'missing_metrics':[name for name,field,_ in FIELDS if not any(numeric(r.get(field)) is not None for r in rows)],
       'notes':(['样本响应数组已截取，不能认为是完整商品列表或完整排名'] if sample_only else ['已读取接口返回的全部记录，但返回上限及全店覆盖尚未确认'])+[
         '合计行不计入商品行数，不累加商品UV作为全店去重人数',
         'fo_jdr_sch_industry_deal_rate映射为页面商品成交转化率，不能按字段名解释为同行转化率',
         '分页/返回上限与全店覆盖仍待核实；SPU/SKU编号分开保留']}
