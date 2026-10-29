"""Explicit migration of saved ad-review files; never certifies legacy identity."""
import hashlib
import json
from pathlib import Path
from .ad_review import money
from .metrics import window


def import_snapshot(directory,store,day):
    window('symc',store,day,'daily')
    directory=Path(directory).resolve()
    files={}
    def load(name):
        path=directory/name;raw=path.read_bytes()
        files[name]={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}
        return json.loads(raw.decode('utf-8'))
    base=load('verified-analysis.json')
    progress=load('official-category-progress.json')
    lookup=load('official-sales-category-lookup.json')
    scenes=load('scenes-realtime-window15.json')
    if any(record.get('date')!=day for record in (base,progress,scenes)):
        raise ValueError('旧快照日期与请求不符。')
    if progress.get('checked')!=progress.get('totalItems') or len(progress['records'])!=progress['totalItems']:
        raise ValueError('类目查询进度尚未完整记录，不能视为已完成映射查询。')
    roots={r['path']:str(cid) for cid,r in lookup.items() if '>' not in r['path']}
    categories=[]
    for cid,row in lookup.items():
        names=row['path'].split('>')
        if len(names)>2 or names[0] not in roots or row['top']!=names[0]:
            raise ValueError('旧快照类目结构不受此迁移适配器支持。')
        path=[str(cid)] if len(names)==1 else [roots[names[0]],str(cid)]
        categories.append({'id':str(cid),'path':path,'names':names,'sales':row.get('sales')})
    raw_items={str(r['promotionId']):r for r in base['items']}
    if len(raw_items)!=len(base['items']):
        raise ValueError('旧广告明细有重复商品，拒绝自动去重。')
    def convert(row,identifier,name):
        return {'id':str(identifier),'name':name,'spend':row.get('charge'),
            'attributed_sales':row.get('alipayInshopAmt'),'clicks':row.get('click'),
            'conversions':row.get('alipayInshopNum'),'impressions':row.get('adPv')}
    items=[]
    catalog_ids={r['id'] for r in categories}
    for record in progress['records']:
        raw=raw_items.get(str(record['itemId']))
        if raw is None or money(raw.get('charge'))!=money(record.get('charge')):
            raise ValueError('类目匹配记录与广告商品花费不一致。')
        category_id=str(record['officialCateId']) if record.get('officialCateId') is not None else None
        category=lookup.get(category_id)
        if category and record.get('officialPath') and category['path']!=record['officialPath']:
            raise ValueError('两份官方类目证据路径冲突。')
        # An official item class may be absent from the day's sales report.
        # Preserve its official ID/path for spend allocation, without inventing sales.
        official_path=record.get('officialPath','').split('>') if record.get('officialPath') else []
        if record.get('matched') and category_id not in catalog_ids and len(official_path)==2 and official_path[0] in roots:
            categories.append({'id':category_id,'path':[roots[official_path[0]],category_id],
                'names':official_path,'sales':None,'sales_observed':False})
            catalog_ids.add(category_id)
        item=convert(raw,record['itemId'],raw.get('promotionName',str(record['itemId'])))
        item['category_id']=category_id if record.get('matched') else None
        item['official_path']=record.get('officialPath','').split('>') if record.get('officialPath') else []
        item['category_root_id']=roots.get(item['official_path'][0]) if item['official_path'] and record.get('matched') else None
        item['category_mapping_source']=record.get('source')
        items.append(item)
    coverage=base['itemCoverage']
    return {'platform':'symc','store_key':store,'date':day,
        'identity_status':'legacy_declared','identity_verified':False,
        'attribution':{'window_days':scenes['window'],'mode':'realtime' if scenes['realtime'] else 'settled',
            'maturity':'immature_snapshot','conversion_definition':'alipayInshopNum/click'},
        'controls':{'spend':base['adSpend'],'store_sales':base['storeSales']},
        'item_coverage':{'expected_rows':coverage['expectedRows'],'retrieved_rows':coverage['retrievedRows'],
            'scope':'positive_spend_items','note':coverage.get('note')},
        'channels':[convert(row,row['scene'],row['scene']) for row in base['scenes']],
        'items':items,'categories':categories,
        'provenance':{'type':'legacy_snapshot','files':files,'account_label':base.get('account'),
            'store_binding':'declared_for_replay_not_retroactively_verified',
            'category_observed_at':progress.get('catalogCheckedAt'),
            'note':'类目为查询时官方归属，不证明历史日归属未变化。'}}
