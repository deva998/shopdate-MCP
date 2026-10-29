"""Evidence-bounded source/product rankings for existing JD workflows."""
from datetime import date,timedelta
from pathlib import Path
import json,time
from .overview import numeric

def identity(report,day,store):
    if report.get('platform')!='jd' or report.get('store',{}).get('store_key')!=store or report.get('date')!=day:
        raise ValueError('结构数据平台、店铺或日期不符')

def ranking(rows):
    known=[row for row in rows if row['delta'] is not None]
    return {'decliners':sorted((row for row in known if row['delta']<0),key=lambda row:row['delta'])[:5],
      'gainers':sorted((row for row in known if row['delta']>0),key=lambda row:row['delta'],reverse=True)[:5],
      'unranked_ids':[row['id'] for row in rows if row['delta'] is None],'ranked_records':len(known)}

def change(identifier,name,value,previous,metrics=None):
    value=numeric(value);previous=numeric(previous)
    return {'id':identifier,'name':name,'value':value,'previous':previous,
      'delta':value-previous if value is not None and previous is not None else None,
      'relative_change':value/previous-1 if value is not None and previous not in (None,0) else None,'metrics':metrics or {}}

def traffic_changes(reports,day,store):
    count=len(reports)
    if count not in (1,14):raise ValueError('来源结构需要单日或完整十四日')
    days=[(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(count-1,-1,-1)]
    ordered=sorted(reports,key=lambda row:row['date'])
    if [row['date'] for row in ordered]!=days:raise ValueError('来源日期不连续或重复')
    for row,selected in zip(ordered,days):
        identity(row,selected,store)
        if row.get('compare_date')!=(date.fromisoformat(selected)-timedelta(days=1)).isoformat():raise ValueError('来源对比日期不符')
        if row.get('channel')!='app' or row.get('parent_ids')!=['2'] or row.get('group')!='jdr_sch_traffic_cha_last_field_src_rmad_sz_2' or row.get('complete_for_request') is not True:
            raise ValueError('来源结构范围或完整性不符')
    indexes=[{item['source_id']:item for item in row['rows']} for row in ordered]
    identifiers=list(dict.fromkeys(key for index in indexes for key in index));rows=[]
    for identifier in identifiers:
        entries=[index.get(identifier) for index in indexes]
        latest=next(entry for entry in reversed(entries) if entry)
        if count==1:
            metric=latest['metrics'].get('引入成交金额',{})
            value,previous=metric.get('value'),metric.get('previous')
        else:
            values=[numeric((entry or {}).get('metrics',{}).get('引入成交金额',{}).get('value')) for entry in entries]
            previous=sum(values[:7]) if all(v is not None for v in values[:7]) else None
            value=sum(values[7:]) if all(v is not None for v in values[7:]) else None
        rows.append(change(identifier,latest.get('name'),value,previous,latest['metrics'] if count==1 else None))
    return {**ranking(rows),'status':'ok','metric':'引入成交金额','unit':'元','channel':'app','parent_ids':['2'],
      'period':'day' if count==1 else 'seven_vs_seven','dates':days,'records':len(rows),
      'sources':[{'date':row['date'],'report_path':row.get('report_path'),'response_sha256':row.get('response_sha256')} for row in ordered],
      'limitation':'仅APP站内场域二级来源；按引入成交金额变化排名，不证明全店归因；未出现或缺失记录不补0；不累加来源UV。周比较为逐日引入金额加总，不是原生区间归因报表。'}

def product_changes(report,day,store):
    identity(report,day,store)
    if report.get('compare_date')!=(date.fromisoformat(day)-timedelta(days=1)).isoformat() or report.get('dimension')!='spu' or report.get('transaction_totals_reconciled') is not True or report.get('coverage')!='exported_active_products':
        raise ValueError('商品结构日期、维度或合计核对不符')
    rows=[]
    for item in report['items']:
        metric=item['metrics'].get('成交金额',{})
        row=change(item['spu_id'],item.get('name'),metric.get('value'),metric.get('previous'),item['metrics'])
        row['membership']=item['membership'];rows.append(row)
    return {**ranking(rows),'status':'ok','metric':'成交金额','unit':'元','dimension':'spu','date':day,'compare_date':report['compare_date'],
      'current_items':report.get('current_items'),'previous_items':report.get('previous_items'),'report_path':report.get('report_path'),
      'sources':report.get('sources'),'comparable_coverage':report.get('comparable_coverage',{}),
      'derived_zero_cells':sum(len(fields) for side in report.get('derived_zero_evidence',{}).values() for fields in side.values()),
      'limitation':'官方有数据SPU；仅两日金额已知或有严格推导证据才计算变化，原始空值不改；单边缺行不等于新品或零销售。排名只解释可比商品的金额变化，不证明原因。'}

def saved_terminals(day,store,*,weekly=False,root=None):
    from .api_client import ROOT
    from .panorama import latest,load_terminals
    root=Path(root) if root is not None else ROOT
    next_call={'platform':'jd','store':store,'command':'traffic-channels','args':['--date',day]}
    metadata={'date':day,'acquisition':'saved_evidence_revalidated',
        'period':'target_day_snapshot_not_weekly' if weekly else 'day'}
    try:
        path=latest(root/'data/jd'/store.replace(':','_')/day/'traffic-channels')
        result=load_terminals(path,day,store)
        if weekly:result['limitation']+=' 这是目标日快照，不是两周终端比较。'
        return {**result,**metadata}
    except FileNotFoundError:
        return {**metadata,'status':'missing','reason':'缺少目标日六终端已保存证据；未新增网络请求','next_call':next_call}
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {**metadata,'status':'invalid','error':str(error),'next_call':next_call}


def collect(day,store,*,weekly=False,overview_reports=None):
    from .api_client import APIClient
    from .api_traffic import collect as traffic
    from .api_products import collect as products
    started=time.monotonic();result={}
    with APIClient({'platform':'jd','store_key':store}) as client:
        try:
            rows=[]
            for offset in range(13 if weekly else 0,-1,-1):
                selected=(date.fromisoformat(day)-timedelta(days=offset)).isoformat()
                saved=traffic(selected,store,client=client)
                row=json.loads(Path(saved['report_path']).read_text(encoding='utf-8'));row['report_path']=saved['report_path'];rows.append(row)
            result['traffic']=traffic_changes(rows,day,store)
        except (ValueError,RuntimeError,TimeoutError,OSError) as error:result['traffic']={'status':'unavailable','error':str(error)}
        if weekly:
            from .weekly_products import collect as weekly_products
            try:result['products']=weekly_products(day,store,overview_reports or [],client=client)
            except (ValueError,RuntimeError,TimeoutError,OSError) as error:result['products']={'status':'unavailable','error':str(error)}
        else:
            try:
                saved=products(day,store,'spu',client=client,reuse_verified=True)
                row=json.loads(Path(saved['report_path']).read_text(encoding='utf-8'));row['report_path']=saved['report_path']
                result['products']=product_changes(row,day,store)
                result['products']['acquisition_path']=saved.get('acquisition_path')
                result['products']['reused_dates']=saved.get('reused_dates',[])
                result['products']['processing']=saved.get('processing',{})
            except (ValueError,RuntimeError,TimeoutError,OSError) as error:result['products']={'status':'unavailable','error':str(error)}
        from .analysis_context import collect as context_collect
        result.update(context_collect(day,store,weekly=weekly,client=client))
    result['terminals']=saved_terminals(day,store,weekly=weekly)
    from .inventory import ensure_context as inventory_context
    products=result.get('products',{})
    selected=[r['id'] for key in ('decliners','gainers') for r in products.get(key,[])]
    result['inventory']=inventory_context(day,store,selected)
    from .order_review import context as order_context
    result['orders']=order_context(day,store,weekly=weekly)
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    return result

def markdown(structure):
    if not structure:return ''
    lines=['','## 商品与来源变化（已验证范围）']
    for key,title in [('products','SPU商品'),('traffic','APP站内场域来源')]:
        result=structure.get(key,{})
        lines+=['','### '+title]
        if result.get('status')!='ok':lines.append('未取得：'+result.get('error',result.get('reason','未采集')));continue
        lines+=[result['limitation'],'','| 方向 | 编号 | 名称 | 本期金额 | 对比金额 | 变化金额 |','|---|---|---|---:|---:|---:|']
        for kind,label in [('decliners','下降'),('gainers','上升')]:
            for row in result[kind]:
                name=str(row['name'] or '名称未知').replace('|','／').replace('\n',' ')
                lines.append(f"| {label} | {row['id']} | {name} | {row['value']:,.2f} | {row['previous']:,.2f} | {row['delta']:+,.2f} |")
        lines.append('缺失金额不可排名的编号数：'+str(len(result['unranked_ids'])))
        if result.get('comparable_coverage'):
            lines+=['','| 指标 | 两期商品集合 | 可比 | 原始可比 | 含推导零值的可比 |',
                '|---|---:|---:|---:|---:|']
            for name,coverage in result['comparable_coverage'].items():
                lines.append('|'+name+'|'+'|'.join(str(coverage.get(k,'未分列')) for k in ('union_products','comparable_products','raw_comparable_products','derived_comparable_products'))+'|')
            money=result['comparable_coverage'].get('成交金额',{})
            if 'active_comparable_products' in money:
                lines.append('可比商品中，至少一期有成交金额的商品：'+str(money['active_comparable_products'])+'件。')
            for side,label in [('current','本期'),('previous','对比期')]:
                share=money.get(side+'_amount_share')
                if share is not None:lines.append(label+'可比子集成交金额占独立概况：'+f'{share:.2%}'+'；未覆盖金额不外推、不归因。')
            lines.append('可比排名仅代表相同已知子集；未覆盖记录不当作零，也不外推为全店贡献。')
        if result.get('report_path'):lines.append('商品明细证据：'+result['report_path'])
        for source in result.get('sources',[]) if isinstance(result.get('sources'),list) else []:
            lines.append('来源证据：'+str(source.get('report_path'))+'；SHA256 '+str(source.get('response_sha256')))
    terminal=structure.get('terminals')
    if terminal:
        lines+=['','### 六终端概况（目标日）']
        if terminal.get('status') not in ('ok','partial','empty'):
            lines.append('未取得：'+terminal.get('error',terminal.get('reason','未采集')))
        else:
            lines+=[terminal['limitation'],'证据：'+terminal['report_path'],'',
                '| 终端 | 状态 | 店铺访客 | 成交金额 |','|---|---|---:|---:|']
            for channel in terminal['channels']:
                values=[channel['metrics'].get(name,{}).get('value') for name in ('店铺访客数','成交金额')]
                lines.append('| '+' | '.join([channel['name'],channel['status'],*['缺失' if v is None else str(v) for v in values]])+' |')
    from .inventory import markdown as inventory_markdown
    from .analysis_context import markdown as context_markdown
    from .order_review import markdown as order_markdown
    return '\n'.join(lines)+'\n'+inventory_markdown(structure.get('inventory'))+context_markdown(structure)+order_markdown(structure.get('orders'))

def attach(report,structure):
    report['structure']=structure
    actions=[]
    for key,label in [('products','SPU'),('traffic','APP站内场域来源')]:
        section=structure.get(key,{})
        if section.get('status')!='ok':continue
        ranked=section.get('decliners',[])+section.get('gainers',[])
        if not ranked:continue
        row=max(ranked,key=lambda item:abs(item['delta']))
        actions.append({'action':f"核查{label} {row['name'] or row['id']}（{row['id']}）的{section['metric']}变化，结合活动、库存及承接记录验证原因",
          'evidence':{**row,'field':section['metric']},'limitation':section['limitation']})
    refund_actions=[item for item in report.get('actions',[]) if '退款' in item['action']]
    # Preserve a refund warning/action when present; otherwise show two observed structural leads.
    report['actions']=(actions[:1]+refund_actions[:1] if refund_actions and actions else actions or report.get('actions',[]))[:2]
    return report

def tool_summary(report):
    """Keep bounded findings visible to AI; full structured evidence stays on disk."""
    output={key:report[key] for key in ('platform','store','module','status','date','compare_date','current_period','previous_period','finding','report_path','markdown_path','collection','data_scope') if key in report}
    output['structure']={}
    if report.get('aftersales'):
        output['aftersales']={k:v for k,v in report['aftersales'].items() if k not in ('trend','sources')}
    for key,section in report.get('structure',{}).items():
        if not isinstance(section,dict):continue
        if key=='orders':
            output['structure'][key]={'status':section['status'],'limitation':section['limitation'],
              'reports':[{k:r.get(k) for k in ('date','status','order_ids_complete','observed_order_records','official_total','unknown_receivables_records','known_receivables_sum','all_record_receivables_sum','deduplicated_business_orders','time_basis','status_as_of','source_report_path')} for r in section['reports']],
              'missing_dates':[e['date'] for e in section['errors']],'next_calls':section['next_calls'][:3]}
            continue
        if key in ('source_layers','terminal_comparison'):
            compact={k:v for k,v in section.items() if k not in ('levels','sources','next_calls')}
            if 'levels' in section:
                compact['levels']=[{k:v for k,v in row.items() if k not in ('unranked_ids','decliners','gainers')}|
                  {'unranked_records':len(row['unranked_ids']),'decliners':row['decliners'][:3],'gainers':row['gainers'][:3]} for row in section['levels']]
            if section.get('next_calls'):compact['next_calls']=section['next_calls'][:3]
            output['structure'][key]=compact
            continue
        if key=='inventory':
            output['structure'][key]=section
            continue
        compact={field:section[field] for field in ('status','error','reason','metric','channel','parent_ids','period','current_items','previous_items','ranked_records','limitation','report_path','reused_dates','new_export_dates','daily_controls_reconciled','date','acquisition','next_call','processing') if field in section}
        if key=='terminals':
            compact['channels']=[{'channel':row['channel'],'name':row['name'],'status':row['status'],
                'missing_metrics':row['missing_metrics'],
                'metrics':{name:{slot:metric.get(slot) for slot in ('value','previous','relative_change')}
                    for name,metric in row['metrics'].items() if name in ('店铺访客数','成交金额','成交转化率')}} for row in section.get('channels',[])]
            output['structure'][key]=compact
            continue
        compact['unranked_records']=len(section.get('unranked_ids',[]))
        for field in ('comparable_coverage','derived_zero_cells'):
            if field in section:compact[field]=section[field]
        for direction in ('decliners','gainers'):
            compact[direction]=[{field:item.get(field) for field in ('id','name','value','previous','delta')} for item in section.get(direction,[])[:3]]
        output['structure'][key]=compact
    output['metrics']=[{key:metric.get(key) for key in ('name','unit','value','previous','relative_change','median7')} for metric in report.get('metrics',[])]
    output['actions']=[{'action':item['action'],'limitation':item.get('limitation')} for item in report.get('actions',[])]
    output['missing_sources']=report.get('missing_sources',[])
    return output
