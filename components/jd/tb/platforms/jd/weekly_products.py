"""Fourteen independently reconciled daily SPU exports; no missing-value imputation."""
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import json,sys
from .business_structure import identity,ranking,change
from .api_products import ROOT,write_json
from .overview import numeric

def compare_pairs(pairs,controls,day,store):
    days=[(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(13,-1,-1)]
    if len(pairs)!=7 or len(controls)!=14 or sorted(row['date'] for row in controls)!=days:raise ValueError('商品周比较必须十四日且不重复')
    by_date={row['date']:row for row in controls};indexes={};raw_indexes={};names={};sources=[]
    extra_names={'成交商品件数':'units','商品成交转化率':'conversion'}
    extra={name:{} for name in extra_names};extra_raw={name:{} for name in extra_names}
    for pair in pairs:
        selected=pair['date'];identity(pair,selected,store)
        prior=(date.fromisoformat(selected)-timedelta(days=1)).isoformat()
        if selected not in days[1::2] or prior!=pair.get('compare_date') or pair.get('dimension')!='spu' or pair.get('channel')!='all' or pair.get('coverage')!='exported_active_products' or pair.get('transaction_totals_reconciled') is not True or pair.get('export_limit_reached'):
            raise ValueError('商品周比较维度、日期或完整核对不符')
        for selected_day,side,slot in [(selected,'current','value'),(prior,'previous','previous')]:
            if selected_day in indexes:raise ValueError('商品日期重复')
            control=by_date[selected_day];identity(control,selected_day,store)
            metrics={item['name']:item for item in control['metrics']}
            for name,tolerance in [('成交金额',Decimal('.01')),('成交商品件数',Decimal(0))]:
                value=metrics.get(name,{}).get('value');total=pair.get('reconciliation',{}).get(side,{}).get(name,{}).get('summary')
                if value is None or total is None or abs(Decimal(str(total))-Decimal(str(value)))>tolerance:raise ValueError('商品日合计与本轮概况不符：'+selected_day+' '+name)
            records={};raw_indexes[selected_day]=set()
            for name in extra_names:extra[name][selected_day]={};extra_raw[name][selected_day]=set()
            for item in pair['items']:
                if item.get('membership')==('previous_only' if side=='current' else 'current_only'):continue
                identifier=item['spu_id']
                if identifier in records:raise ValueError('商品编号重复')
                records[identifier]=numeric(item['metrics'].get('成交金额',{}).get(slot));names[identifier]=item.get('name')
                if records[identifier] is not None and 'amount' not in pair.get('derived_zero_evidence',{}).get(side,{}).get(identifier,{}):raw_indexes[selected_day].add(identifier)
                for name,field in extra_names.items():
                    value=numeric(item['metrics'].get(name,{}).get(slot));extra[name][selected_day][identifier]=value
                    if value is not None and field not in pair.get('derived_zero_evidence',{}).get(side,{}).get(identifier,{}):extra_raw[name][selected_day].add(identifier)
            indexes[selected_day]=records
        sources.append({'date':selected,'report_path':pair.get('report_path'),'acquisition_path':pair.get('acquisition_path'),'files':pair.get('sources')})
    if sorted(indexes)!=days:raise ValueError('商品日期不完整')
    rows=[]
    for identifier,name in names.items():
        values=[indexes[selected].get(identifier) for selected in days]
        previous=sum(values[:7]) if all(v is not None for v in values[:7]) else None
        current=sum(values[7:]) if all(v is not None for v in values[7:]) else None
        row=change(identifier,name,current,previous)
        row['known_days']=sum(v is not None for v in values);rows.append(row)
    comparable=sum(r['delta'] is not None for r in rows)
    coverage={'成交金额':{'union_products':len(rows),'comparable_products':comparable,
        'current_known_products':sum(r['value'] is not None for r in rows),
        'previous_known_products':sum(r['previous'] is not None for r in rows)}}
    import math
    money=[r for r in rows if r['delta'] is not None]
    raw_count=sum(all(r['id'] in raw_indexes[d] for d in days) for r in money)
    coverage['成交金额'].update(raw_comparable_products=raw_count,derived_comparable_products=len(money)-raw_count)
    coverage['成交金额']['active_comparable_products']=sum(r['value']!=0 or r['previous']!=0 for r in money)
    for side,slot,window in [('current','value',days[7:]),('previous','previous',days[:7])]:
        amount=math.fsum(r[slot] for r in money)
        total=math.fsum(next(m['value'] for m in by_date[d]['metrics'] if m['name']=='成交金额') for d in window)
        coverage['成交金额'][side+'_comparable_amount']=amount
        coverage['成交金额'][side+'_official_amount']=total
        coverage['成交金额'][side+'_amount_share']=amount/total if total else None
    for name in extra_names:
        known=lambda identifier,window:all(extra[name][d].get(identifier) is not None for d in window)
        ids=[i for i in names if known(i,days)]
        raw_count=sum(all(i in extra_raw[name][d] for d in days) for i in ids)
        coverage[name]={'union_products':len(rows),'comparable_products':len(ids),
            'current_known_products':sum(known(i,days[7:]) for i in names),'previous_known_products':sum(known(i,days[:7]) for i in names),
            'raw_comparable_products':raw_count,'derived_comparable_products':len(ids)-raw_count,
            'definition':'连续十四日日率均已知的商品范围；不平均日率为周转化率，不把人次当周去重人数' if name=='商品成交转化率' else '十四日件数均已知的商品范围'}
    return {**ranking(rows),'status':'ok','metric':'成交金额','unit':'元','dimension':'spu','period':'seven_vs_seven','dates':days,
      'comparable_coverage':coverage,
      'derived_zero_cells':sum(len(fields) for pair in pairs for side in pair.get('derived_zero_evidence',{}).values() for fields in side.values()),
      'current_items':len(set().union(*(set(indexes[selected]) for selected in days[7:]))),
      'previous_items':len(set().union(*(set(indexes[selected]) for selected in days[:7]))),
      'daily_controls_reconciled':True,'sources':sources,'items':rows,
      'limitation':'十四日官方有数据SPU，逐日金额/件数均与本轮概况核对；按七日金额加总比较。仅十四日金额完整的SPU可排名，缺失或单边出现不补0、不认定新品；不是全店变化的完整分摊，不加总商品UV作为店铺去重人数。'}

def collect(day,store,controls,*,client):
    from .api_products import collect as pair_collect
    from .daily import validate_window
    validate_window(controls,day,store,14)
    pairs=[];reused=[]
    for offset in range(12,-1,-2):
        selected=(date.fromisoformat(day)-timedelta(days=offset)).isoformat()
        print('周商品结构：'+selected+' 与前一日',file=sys.stderr,flush=True)
        saved=pair_collect(selected,store,'spu',client=client,reuse_verified=True)
        pair=json.loads(Path(saved['report_path']).read_text(encoding='utf-8'))
        pair.update(report_path=saved['report_path'],acquisition_path=saved['acquisition_path']);pairs.append(pair)
        reused+=saved.get('reused_dates',[])
    report=compare_pairs(pairs,controls,day,store)
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'products-spu-weekly'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report.update(report_path=str(folder/'report.json'),reused_dates=sorted(reused),new_export_dates=[selected for selected in report['dates'] if selected not in reused])
    write_json(folder/'report.json',report)
    return {key:value for key,value in report.items() if key!='items'}
