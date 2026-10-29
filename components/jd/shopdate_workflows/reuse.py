"""Explicit, identity-bounded overview reuse; no automatic cache search."""
from copy import deepcopy
from datetime import date


def prepare_reuse(payload,platform,store,dates,refresh=False):
    if payload.get('platform')!=platform or payload.get('store_key')!=store:
        raise ValueError('续跑证据平台或店铺不符。')
    if not dates or sorted(set(dates))!=dates:
        raise ValueError('目标窗口日期必须连续、唯一且升序。')
    if refresh:
        return {'rows':[],'sources':[],'reused_dates':[],'pending_dates':list(dates)}
    rows=payload.get('rows',[]);sources=payload.get('sources',[])
    row_dates=[r.get('date') for r in rows];source_dates=[r.get('date') for r in sources]
    if len(set(row_dates))!=len(row_dates) or len(set(source_dates))!=len(source_dates):
        raise ValueError('续跑证据存在重复日期，禁止自动覆盖。')
    command='shop-overview' if platform=='jd' else 'home-table'
    by_source={s['date']:s for s in sources}
    for row in rows:
        day=row['date']
        if date.fromisoformat(day).isoformat()!=day or row.get('platform')!=platform or row.get('store_key')!=store:
            raise ValueError('续跑日期、平台或店铺不一致。')
        if day not in by_source or by_source[day].get('command')!=command:
            raise ValueError('续跑来源不是同口径店铺日概况。')
    verified=set(row_dates) if payload.get('identity_verified') is True else set(payload.get('verified_dates',[]))
    if not verified or not verified.issubset(set(row_dates)):
        raise ValueError('检查点未保存可核验的日期身份，禁止复用。')
    selected=sorted(set(dates)&verified)
    by_row={r['date']:r for r in rows}
    return {'rows':[deepcopy(by_row[d]) for d in selected],
            'sources':[deepcopy(by_source[d]) for d in selected],
            'reused_dates':selected,'pending_dates':[d for d in dates if d not in selected]}
