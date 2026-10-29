"""Chinese presentation of verified JD trade-summary fields; no network calls."""
import copy
from datetime import date, timedelta
import math

METRICS = [
    ('成交金额', 'jdr_sch_trade_deal_ord_ord_amt_sz_trade_deal_snapshot', '元'),
    ('成交商品件数', 'jdr_sch_trade_deal_ord_sku_qtty_sz_trade_deal_snapshot', '件'),
    ('成交客户数', 'jdr_sch_user_deal_ord_user_cnt_sz_user_deal_snapshot', '人'),
    ('成交单量', 'jdr_sch_trade_deal_ord_ord_qtty_sz_trade_deal_snapshot', '单'),
    ('店铺成交转化率', 'fo_jdr_sch_shop_deal_rate', '%'),
    ('客单价', 'fo_jdr_sch_trade_deal_ord_amt_user_sz_trade_deal_snapshot', '元'),
    ('店铺浏览量', 'jdr_sch_traffic_enter_shop__browse_page_qtty_shop_last_src', '次'),
    ('店铺访客数', 'jdr_sch_traffic_enter_shop__browse_page_cnt_shop_last_src', '人'),
    ('店铺平均停留时长', 'fo_jdr_sch_traffic_enter_shop__browse_page_avg_duration_shop_last_src', '原页面单位'),
    ('加购客户数', 'jdr_sch_sku_add_cart_sku_user_qtty_product_user_cart_add_minus_sz_bsg_shoppingcart@increase', '人'),
    ('退款金额', 'fo_jdr_sch_trade_cancel_refund_ord_amt', '元'),
    ('发货前-退款金额', 'jdr_sch_trade_cancel_ord_ord_amt_sz_trade_deal_cancel_snapshot@cancel_in_flag', '元'),
    ('未收货-退款金额', 'jdr_sch_trade_cancel_ord_ord_amt_sz_trade_deal_cancel_snapshot@cancel_out_flag', '元'),
    ('已收货-退款金额', 'jdr_eco_csas_refund_sku_amt_eco_afs_sz@received_only_refund', '元'),
    ('已收货-退货退款金额', 'jdr_eco_csas_refund_sku_amt_eco_afs_sz@received_return_refund', '元'),
]


def make_request(template, day):
    selected = date.fromisoformat(day)
    if selected.isoformat() != day:
        raise ValueError('日期格式应为 YYYY-MM-DD。')
    result = copy.deepcopy(template)
    previous = (selected - timedelta(days=1)).isoformat()
    result.update(startDate=day, endDate=day, compareStartDate=previous, compareEndDate=previous)
    return result


def numeric(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def data_quality(metrics):
    by_field={m['field']:m for m in metrics}
    core=[by_field.get(field,{}) for _,field,_ in METRICS[:8]]
    missing=[name for (name,_,_),m in zip(METRICS[:8],core) if numeric(m.get('value')) is None]
    status='empty' if len(missing)==8 else 'partial' if any(numeric(m.get('value')) is None for m in metrics) else 'ok'
    return {'data_status':status,'missing_core_metrics':missing,
            'analysis_ready':not missing and all(numeric(m.get('previous')) is not None for m in core),
            'availability_note':'核心指标不可用；不能将接口成功或退款零值当作销售报表完成，需核对官方报表可用日期。' if status=='empty' else
              '部分指标缺失；只分析有证据的指标，缺失不补零。' if status=='partial' else '当前指标可用；对比完整性另见analysis_ready。'}


def summarize(payload, request, source='unknown', request_timestamp=None):
    header = payload.get('header') if isinstance(payload, dict) else None
    if not isinstance(header, dict) or header.get('code') != 0 or payload.get('errors'):
        raise ValueError('接口业务状态失败：' + str(header))
    rows = (payload.get('body') or {}).get('data')
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError('交易概况应返回一行汇总数据。')
    metrics = []
    for name, field, unit in METRICS:
        value = numeric(rows[0].get(field))
        previous = numeric(rows[0].get(field + '##compareValue'))
        change = numeric(rows[0].get(field + '##compare'))
        metrics.append(dict(name=name, field=field, unit=unit, value=value, previous=previous,
                            relative_change=change, change_source='接口 ##compare',
                            change_pp=round((value - previous) * 100, 8) if unit == '%' and value is not None and previous is not None else None))
    if not any(m['value'] is not None for m in metrics):
        raise ValueError('所有已映射指标均缺失，停止生成分析。')
    return dict(date=request['startDate'], compare_date=request['compareStartDate'], channel='全部',
                compare_type='前一日环比', shop='请在商智页面人工确认当前店铺', source=source,
                request_timestamp=request_timestamp, metrics=metrics, **data_quality(metrics),
                missing_metrics=[m['name'] for m in metrics if m['value'] is None],
                definitions='成交金额沿用京东页面口径，不改称支付金额或净销售额；转化率沿用接口原值；相对变化采用接口值，百分点差单独计算。')


def formatted(value, unit):
    if value is None:
        return '缺失'
    if unit == '%':
        return f'{value * 100:.2f}%'
    return f'{value:,.0f}' if unit in ('件', '人', '单', '次') else f'{value:,.2f}'


def markdown(report):
    quality=data_quality(report['metrics'])
    lines = ['# 京东商智 · 店铺交易概况', '',
             f"统计日期：{report['date']}；对比日期：{report['compare_date']}；渠道：全部；前一日环比。",
             f"店铺：{report['shop']}。", '',f"数据状态：{quality['data_status']}。{quality['availability_note']}", '',
             '| 指标 | 当日 | 前一日 | 相对变化 |', '|---|---:|---:|---:|']
    for metric in report['metrics']:
        label = metric['name'] + (f"（{metric['unit']}）" if metric['unit'] != '%' else '')
        change = '缺失/接口未提供' if metric['relative_change'] is None else f"{metric['relative_change'] * 100:+.2f}%"
        lines.append(f"| {label} | {formatted(metric['value'], metric['unit'])} | {formatted(metric['previous'], metric['unit'])} | {change} |")
    if quality['data_status']=='empty':
        return '\n'.join(lines+['','## 数据观察','','核心指标不可用，暂停销售、转化及退款变化结论；未提供经营动作。',
          '保留指定统计日期，不自动替换成其他日期；请核对平台最新可用完整日报。',
          f"响应来源：{report['source']}；请求发生时间：{report['request_timestamp'] or '未提供'}。请求时间不同于报表统计日期。",''])
    lines += ['', '## 数据观察', '']
    by_name = {m['name']: m for m in report['metrics']}
    for name in ('成交金额', '店铺访客数', '店铺成交转化率', '客单价'):
        metric = by_name[name]
        if metric['value'] is None:
            lines.append(f'- {name}缺失，无法判断变化。')
        elif metric['relative_change'] is not None:
            direction = '上升' if metric['relative_change'] > 0 else '下降' if metric['relative_change'] < 0 else '持平'
            text = f"- {name}较前一日{direction}，接口相对变化为 {metric['relative_change'] * 100:+.2f}%。"
            if metric['change_pp'] is not None:
                text += f"转化率绝对变化为 {metric['change_pp']:+.2f} 个百分点。"
            lines.append(text)
        else:
            lines.append(f'- {name}当日为 {formatted(metric["value"], metric["unit"])}；接口未提供变化率，不推测环比。')
    lines += ['', '## 后续核查建议', '',
              '- 按渠道查看访客和转化率，再定位变化集中在哪些渠道。当前汇总表不能证明变化原因。',
              '- 查看商品成交客户数、成交金额和客单价，核对是否存在商品结构变化；需补充对应报表后验证。', '',
              '## 口径与来源', '', report['definitions'],
              '店铺平均停留时长的单位尚未独立核实，保留原页面单位。退款金额及拆分保持京东页面名称，可能涉及跨期事件，不能直接推算同期成交队列退货率或净销售额。缺失值不按 0 处理；不据此推断利润或营销归因。',
              f"响应来源：{report['source']}；请求发生时间：{report['request_timestamp'] or '未提供'}。请求时间不同于报表统计日期。", '']
    return '\n'.join(lines)
