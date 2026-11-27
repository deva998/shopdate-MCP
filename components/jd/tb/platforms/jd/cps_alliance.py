"""CPS native card/trend schema; never substitutes APP attribution metrics."""
from datetime import date, timedelta
import calendar
import math
import re

TITLES = ('付款订单金额', '付款订单行量', '付款用户数', '计佣佣金', '预估佣金')
PREFIX = '/datamix/sz/geajax/gep/api/alliance/'


def contracts():
    result = {}
    for compare in ('hb', 'tb'):
        template = {'dateType': 'day', 'startDate': '$DAY', 'endDate': '$DAY',
                    'queryTime': '$DAY', 'radioLabel': '天', 'compareType': compare}
        for kind, endpoint in (('overview', 'card'), ('index', 'index')):
            result['cps-' + kind + '-' + compare] = {
                'method': 'GET', 'origin': 'https://szgateway.jd.com',
                'path': PREFIX + endpoint + '.ajax',
                'page': 'https://jdsz.jd.com/szweb/view/market/alliance-summary-temp.html',
                'template': template.copy(), 'scope': 'historical_day_query',
                'schema': 'cps_' + kind, 'min_extension': '0.9.67',
                'cps_periods': ['day', 'week', 'month', 'custom'],
                'source': 'MCP cps-inner-scripts 20261123T110538-dc9728b1; H, U, J, trend startDate -6 days',
            }
    return result


def build_params(report, day, *, period='day', start_date=None):
    end = date.fromisoformat(day)
    if end.isoformat() != day or period not in ('day', 'week', 'month', 'custom'):
        raise ValueError('CPS周期或日期格式无效。')
    if start_date is not None and period != 'custom':
        raise ValueError('CPS起日仅用于自定义区间。')
    start = end
    query = day
    label = '天'
    if period == 'week':
        if end.weekday() != 6:
            raise ValueError('CPS周查询的date必须为完整周的周日。')
        start = end - timedelta(days=6)
        iso_year, week, _ = end.isocalendar()
        query, label = f'{iso_year}-{week}', '周'
    elif period == 'month':
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            raise ValueError('CPS月查询的date必须为完整月的月末。')
        start = end.replace(day=1)
        query, label = f'{end.year}-{end.month}', '月'
    elif period == 'custom':
        if not isinstance(start_date, str):
            raise ValueError('CPS自定义区间必须指定start-date。')
        start = date.fromisoformat(start_date)
        if start.isoformat() != start_date or not 1 <= (end-start).days+1 <= 30:
            raise ValueError('CPS自定义区间须为有效日期，含首末日1至30天。')
        query, label = start_date, str((end-start).days+1)
    if start < date(2021, 10, 1):
        raise ValueError('CPS查询早于官方页面提供的2021-10-01。')
    return {'dateType': period, 'startDate': start.isoformat(), 'endDate': day,
            'queryTime': query, 'radioLabel': label, 'compareType': report.rsplit('-', 1)[-1]}


def normalize(data, report, day, *, values=None):
    values = values or build_params(report, day)
    period = values['dateType']
    coverage = {'whole_module_complete': False, 'nulls_preserved': True,
                'scope': 'historical_day_query', 'comparison': report.rsplit('-', 1)[-1],
                'metric_scope': 'CPS联盟官方付款及佣金口径，不等同于APP引入成交金额',
                'schema_validation': 'cps_official_shape', 'business_data_verified': True,
                'period': period, 'requested_start_date': values['startDate'], 'requested_end_date': values['endDate']}
    if report.startswith('cps-index-'):
        rows = data.get('data')
        if not isinstance(rows, list):
            raise ValueError('CPS指标字典结构无效。')
        coverage.update(metadata_only=True, business_data_verified=False, returned_rows=len(rows))
        return {'data': data, 'coverage': coverage}
    cards = data.get('cards')
    if not isinstance(cards, list) or any(not isinstance(c, dict) or not isinstance(c.get('name'), str)
            or not isinstance(c.get('code'), str) or 'value' not in c or not isinstance(c.get('norms'), list) for c in cards):
        raise ValueError('CPS汇总指标结构无效。')
    if len({c['code'] for c in cards}) != len(cards) or len({c['name'] for c in cards}) != len(cards):
        raise ValueError('CPS汇总指标代码或名称重复。')
    by_name = {c['name']: c for c in cards}
    missing = [name for name in TITLES if name not in by_name]
    nulls = [c['name'] for c in cards if c['value'] in (None, '', '--', '_DATA_NO_AUTH_')]
    coverage.update(returned_rows=len(cards), missing_metrics=missing, null_metrics=nulls,
                    trend_status=data.get('trend_status'), additional_source_requests=data.get('additional_source_requests', 0),
                    data_availability='official_empty' if not cards else 'missing_values' if nulls else 'returned_values',
                    missing_comparison_metrics=[c['name'] for c in cards if not any(n.get('code') == coverage['comparison'] and type(n.get('value')) in (int,float) and math.isfinite(n['value']) for n in c['norms'] if isinstance(n,dict))],
                    note='官方type=5/6为元，type=1为数量；行量不改名为订单数。佣金定义保留desc，比较比例不额外乘除100。')
    if period != 'day':
        coverage['requested_scope_complete'] = False
    trend = data.get('trend')
    if data.get('trend_status') == 'ok':
        if not isinstance(trend, dict) or not isinstance(trend.get('categories'), list) or not isinstance(trend.get('series'), list):
            raise ValueError('CPS趋势结构无效。')
        labels = trend['categories']
        if period != 'day':
            if any(not isinstance(label, str) for label in labels) or len(set(labels)) != len(labels):
                raise ValueError('CPS跨周期趋势标签不是字符串或有重复。')
            start = date.fromisoformat(values['startDate'])
            end = date.fromisoformat(day)
            expected_dates = [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
            for label in labels:
                try:
                    parsed_label = date.fromisoformat(label)
                except ValueError:
                    raise ValueError('CPS跨周期趋势未返回已验证的每日日期格式。') from None
                if parsed_label.isoformat() != label or label < values['startDate'] or label > day:
                    raise ValueError('CPS跨周期趋势日期超出查询区间。')
            if labels != sorted(labels):
                raise ValueError('CPS跨周期趋势日期乱序。')
            for series in trend['series']:
                if not isinstance(series, dict) or not isinstance(series.get('code'),str) or not isinstance(series.get('data'), list) or len(series['data']) != len(labels):
                    raise ValueError('CPS趋势长度与日期轴不符。')
            codes = {s.get('code') for s in trend['series']}
            if len(codes) != len(trend['series']):
                raise ValueError('CPS跨周期趋势指标代码重复。')
            series_by_code = {s['code']:s for s in trend['series']}
            totals = {}
            for card in cards:
                series = series_by_code.get(card['code'])
                numbers = series['data'] if series else []
                if not numbers or type(card['value']) not in (int,float) or not math.isfinite(card['value']) or any(type(v) not in (int,float) or not math.isfinite(v) for v in numbers):
                    totals[card['code']] = {'status':'missing_valid_values'}
                    continue
                if card['name'] == '付款用户数':
                    totals[card['code']] = {'status':'not_additive_unique_users'}
                    continue
                total = math.fsum(numbers)
                totals[card['code']] = {'status':'matched' if math.isclose(total,card['value'],rel_tol=1e-10,abs_tol=1e-6) else 'mismatch',
                                        'sum_daily':total,'card_value':card['value']}
            coverage.update(returned_date_labels=len(labels), date_start=values['startDate'], date_end=day,
                            native_date_labels=labels, date_axis_status='validated_daily_interval',
                            trend_granularity='day',interval_dates_complete=labels == expected_dates,
                            totals_reconciliation=totals,
                            missing_trend_metrics=[c['name'] for c in cards if c['code'] not in codes])
            coverage['requested_scope_complete'] = (not missing and not nulls and not coverage['missing_comparison_metrics']
                and coverage['interval_dates_complete'] and not coverage['missing_trend_metrics']
                and all(t['status'] in ('matched','not_additive_unique_users') for t in totals.values()))
            return {'data': data, 'coverage': coverage}
        start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
        short_dates = {(date.fromisoformat(day) - timedelta(days=i)).strftime('%m-%d'):
                       (date.fromisoformat(day) - timedelta(days=i)).isoformat() for i in range(7)}
        dates = []
        for label in labels:
            if not isinstance(label, str):
                raise ValueError('CPS趋势日期不是字符串。')
            normalized = short_dates.get(label, '') if re.fullmatch(r'\d{2}-\d{2}', label) else label[:10]
            try:
                date.fromisoformat(normalized)
            except ValueError:
                raise ValueError('CPS趋势日期格式无效。') from None
            if normalized < start or normalized > day:
                raise ValueError('CPS趋势日期超出查询窗口。')
            dates.append(normalized)
        if dates and (dates != sorted(set(dates)) or dates[-1] != day):
            raise ValueError('CPS趋势日期重复、乱序或末日不符。')
        for series in trend['series']:
            if not isinstance(series, dict) or not isinstance(series.get('data'), list) or len(series['data']) != len(labels):
                raise ValueError('CPS趋势长度与日期轴不符。')
        codes = {s.get('code') for s in trend['series']}
        coverage.update(returned_date_labels=len(labels), date_start=start, date_end=day,
                        seven_dates_complete=len(dates) == 7,
                        missing_trend_metrics=[c['name'] for c in cards if c['code'] not in codes])
    return {'data': data, 'coverage': coverage}
