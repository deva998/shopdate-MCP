"""Deterministic ad views. Attribution and shop sales retain separate meanings."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from .metrics import numeric,ratio,window,VERSION

MONEY=('spend','attributed_sales')
COUNTS=('clicks','conversions','impressions')


def money(value):
    value=numeric(value)
    return Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP) if value is not None else None


def total(rows,field):
    values=[money(r.get(field)) if field in MONEY or field=='sales' else numeric(r.get(field)) for r in rows]
    return float(sum(values)) if all(v is not None for v in values) else None


def unique(rows,label):
    identifiers=[r.get('id') for r in rows]
    if any(not isinstance(i,str) or not i for i in identifiers) or len(set(identifiers))!=len(identifiers):
        raise ValueError(label+'必须使用唯一字符串ID，不能重复或丢失精度。')


def summary(rows):
    result={field:total(rows,field) for field in (*MONEY,*COUNTS)}
    result.update(roi=ratio(result['attributed_sales'],result['spend']),
        ctr=ratio(result['clicks'],result['impressions']),
        cvr=ratio(result['conversions'],result['clicks']))
    return result


def reconciled(value,control):
    return value is not None and control is not None and abs(money(value)-money(control))<=Decimal('.01')


def analyze_ads(payload,store,day):
    window('symc',store,day,'daily')
    if payload.get('platform')!='symc' or payload.get('store_key')!=store or payload.get('date')!=day:
        raise ValueError('广告证据平台、店铺或日期不符。')
    attribution=payload.get('attribution',{})
    if type(attribution.get('window_days')) is not int or attribution['window_days']<=0 or not attribution.get('mode') or not attribution.get('maturity'):
        raise ValueError('必须声明归因窗口、模式和快照成熟度。')
    if attribution.get('conversion_definition')!='alipayInshopNum/click':
        raise ValueError('归因转化口径必须明确为alipayInshopNum/click。')
    items,channels,categories=(payload.get(key,[]) for key in ('items','channels','categories'))
    plans=payload.get('plans',[])
    unique(plans,'计划')
    for rows,label in [(items,'商品'),(channels,'渠道'),(categories,'类目')]:
        unique(rows,label)
    if not items or not channels:
        raise ValueError('缺少广告商品或渠道证据。')
    catalog={r['id']:r for r in categories}
    for row in categories:
        path,names=row.get('path'),row.get('names')
        if not isinstance(path,list) or not path or len(path)!=len(names or []) or path[-1]!=row['id'] or len(set(path))!=len(path):
            raise ValueError('官方类目路径无效。')
        for index,identifier in enumerate(path):
            parent=catalog.get(identifier)
            if not parent or parent['path']!=path[:index+1] or parent['names']!=names[:index+1]:
                raise ValueError('官方类目路径存在冲突或缺少父级证据。')
    controls=payload.get('controls',{})
    spend=money(controls.get('spend'));sales=money(controls.get('store_sales'))
    spend=float(spend) if spend is not None else None
    sales=float(sales) if sales is not None else None
    coverage=payload.get('item_coverage',{})
    expected,retrieved=coverage.get('expected_rows'),coverage.get('retrieved_rows')
    complete=(type(expected) is int and type(retrieved) is int and expected==retrieved and
              len(items)==retrieved and coverage.get('scope')=='all_items' and
              coverage.get('complete',True) is True and not coverage.get('duplicate_ids'))
    item_total,channel_total=summary(items),summary(channels)
    groups=defaultdict(list);unmatched=[];root_only=[]
    for row in items:
        category=catalog.get(row.get('category_id'))
        if category:
            groups[category['path'][0]].append(row)
        elif row.get('category_root_id') in catalog and row.get('category_id') and row.get('official_path') and row.get('category_mapping_source')=='/cc/item/price/info.json':
            root=catalog[row['category_root_id']]
            if len(root['path'])!=1 or row['official_path'][0]!=root['names'][0]:
                raise ValueError('商品官方路径与根类目证据冲突。')
            # Full official name path + official leaf ID are retained on item.
            # Allocate spend to known official root; do not invent missing ancestor IDs.
            groups[root['id']].append(row);root_only.append(row)
        else:
            unmatched.append(row)
    roots=[r for r in categories if len(r['path'])==1]
    sales_catalog=[r for r in categories if r.get('sales_observed',True)]
    sales_roots=[r for r in sales_catalog if len(r['path'])==1]
    parent_ids={identifier for r in sales_catalog for identifier in r['path'][:-1]}
    leaves=[r for r in sales_catalog if r['id'] not in parent_ids]
    output_categories=[]
    def attach(identifier,name,group,category=None):
        result={'id':identifier,'name':name,**summary(group),'item_count':len(group),
            'sales':category.get('sales') if category else None}
        result['spend_sob']=ratio(result['spend'],spend)
        result['sales_sob']=ratio(numeric(result['sales']),sales)
        result['ad_spend_rate']=ratio(result['spend'],numeric(result['sales']))
        if not group and not complete:
            for field in ('spend','spend_sob','ad_spend_rate','attributed_sales','clicks','conversions','impressions','roi','ctr','cvr'):
                result[field]=None
        return result
    for root in roots:
        output_categories.append(attach(root['id'],root['names'][0],groups[root['id']],root))
    if unmatched:
        output_categories.append(attach('__unmatched__','官方类目未匹配',unmatched))
    missing={field:sum(numeric(r.get(field)) is None for r in items) for field in (*MONEY,*COUNTS)}
    quality={'identity_status':payload.get('identity_status','unknown'),
        'identity_verified':payload.get('identity_verified') is True and payload.get('identity_status')=='verified',
        'all_rows_complete':complete,'expected_rows':expected,'retrieved_rows':retrieved,
        'item_rows_used':len(items),'item_scope':coverage.get('scope','unknown'),
        'item_spend_reconciled':reconciled(item_total['spend'],spend),
        'channel_spend_reconciled':reconciled(channel_total['spend'],spend),
        'item_spend_difference':float(money(item_total['spend'])-money(spend)) if item_total['spend'] is not None and spend is not None else None,
        'unmatched_items':len(unmatched),'unmatched_spend':total(unmatched,'spend'),
        'root_only_mapping_items':len(root_only),
        'missing_item_fields':{k:v for k,v in missing.items() if v},
        'missing_channel_fields':{field:sum(numeric(r.get(field)) is None for r in channels) for field in (*MONEY,*COUNTS) if any(numeric(r.get(field)) is None for r in channels)},
        'ad_categories_without_sales_rows':sorted({r['category_id'] for r in items if r.get('category_id') and (r['category_id'] not in catalog or not catalog[r['category_id']].get('sales_observed',True))}),
        'root_sales_sum':total(sales_roots,'sales'),'leaf_sales_sum':total(leaves,'sales')}
    quality['root_sales_reconciled']=reconciled(quality['root_sales_sum'],sales)
    quality['leaf_sales_reconciled']=reconciled(quality['leaf_sales_sum'],sales)
    branches=[]
    for parent in sales_catalog:
        children=[r for r in sales_catalog if len(r['path'])==len(parent['path'])+1 and r['path'][:-1]==parent['path']]
        if children:
            child_sum=total(children,'sales')
            branches.append({'id':parent['id'],'parent_sales':parent.get('sales'),
                'children_sales_sum':child_sum,'reconciled':reconciled(child_sum,numeric(parent.get('sales')))})
    quality['branch_sales_reconciliation']=branches
    quality['all_branch_sales_reconciled']=all(r['reconciled'] for r in branches)
    plan_total=summary(plans)
    quality['plan_spend_reconciled']=reconciled(plan_total['spend'],spend) if plans else None
    plan_coverage=payload.get('plan_coverage',{})
    quality['plan_rows_complete']=bool(plans and plan_coverage.get('complete') is True and
        plan_coverage.get('expected_rows')==plan_coverage.get('retrieved_rows')==len(plans))
    quality['plans_requested']='plans' in payload
    quality['plan_coverage']=plan_coverage
    quality['item_pagination_duplicates']=coverage.get('duplicate_ids',[])
    quality['missing_plan_fields']={field:sum(numeric(r.get(field)) is None for r in plans) for field in (*MONEY,*COUNTS) if any(numeric(r.get(field)) is None for r in plans)}
    good=all(quality[k] for k in ('identity_verified','all_rows_complete','item_spend_reconciled',
        'channel_spend_reconciled','root_sales_reconciled','leaf_sales_reconciled','all_branch_sales_reconciled')) and not unmatched and not quality['missing_item_fields'] and not quality['missing_channel_fields'] and not quality['ad_categories_without_sales_rows']
    if quality['plans_requested']:
        good=good and quality['plan_rows_complete'] and quality['plan_spend_reconciled'] and not quality['missing_plan_fields']
    quality['pending_category_queries']=len(payload.get('pending_category_ids',[]))
    if quality['pending_category_queries']:good=False
    return {'schema_version':VERSION,'workflow':'ad-review','platform':'symc','store_key':store,'date':day,
        'timezone':'Asia/Shanghai','status':'ok' if good else 'partial','analysis_ready':bool(good),
        'attribution':attribution,'controls':{'spend':spend,'store_sales':sales},
        'totals':item_total,'channel_totals':channel_total,
        'plans':[{'id':r['id'],'name':r.get('name') or r['id'],**summary([r]),
            'spend_sob':ratio(numeric(r.get('spend')),spend)} for r in plans],
        'plan_totals':plan_total if plans else None,
        'channels':[{'id':r['id'],'name':r.get('name') or r['id'],**summary([r]),'spend_sob':ratio(numeric(r.get('spend')),spend)} for r in channels],
        'categories':sorted(output_categories,key=lambda r:-(r['spend'] or 0)),
        'sales_details':[{'id':r['id'],'name':'>'.join(r['names']),'path':r['path'],
            'sales':r.get('sales'),'sales_sob':ratio(numeric(r.get('sales')),sales)} for r in leaves],
        'items':[{'id':r['id'],'name':r.get('name') or r['id'],'category_id':r.get('category_id'),
            'official_path':r.get('official_path'),'category_root_id':r.get('category_root_id'),**summary([r])} for r in items],
        'quality':quality,'grouping':'官方根类目汇总花费，销售保留官方叶级路径',
        'formulas':{'spend_sob':'类目或渠道花费/控制总花费','sales_sob':'类目实际销售/店铺实际销售',
            'ad_spend_rate':'同官方类目花费/实际销售','roi':'归因成交金额/花费',
            'ctr':'click/adPv','cvr':'alipayInshopNum/click，归因成交笔数口径，非去重买家转化率'},
        'limitations':['商品和渠道为不同视图，不相加。商品间接归因成交不等于该类目实际销售。',
            '总花费对平不代表分页、归因、类目或身份完整。',
            '快照可能回补，成熟度按输入声明；本报告不自动调预算或写文档。']}
