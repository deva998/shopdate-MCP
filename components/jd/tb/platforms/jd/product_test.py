"""Fixed official-tag cohort, seven calendar days, source-validated exports."""
from collections import Counter
from datetime import date,datetime,timedelta,timezone
import hashlib,json,math,statistics,time,uuid
from pathlib import Path
from decimal import Decimal
from .api_client import ROOT
from .product_exports import load_export,number

FIELDS={'uv':'商品访客数','cart':'加购客户数','buyers':'成交客户数','amount':'成交金额'}


def load_export_cached(path,day,store,*,cache_dir=None):
    """Reuse parsed XLSX only when source, parser and store/date are identical."""
    from . import product_exports
    path=Path(path)
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    identity={'path':str(path.resolve()),'sha256':source_hash,'date':day,'store':store,
              'parser':hashlib.sha256(Path(product_exports.__file__).read_bytes()).hexdigest()}
    digest=lambda x:hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    cache_dir=Path(cache_dir) if cache_dir is not None else ROOT/'.runtime'/'parsed-product-exports'
    target=cache_dir/(digest(identity)+'.json')
    try:
        cached=json.loads(target.read_text(encoding='utf-8'))
        if cached['identity']==identity and digest(cached['parsed'])==cached['parsed_sha256']:
            return cached['parsed']
    except (OSError,ValueError,KeyError,TypeError):pass
    parsed=load_export(path,day,'spu',store)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source_hash:raise ValueError('解析期间源文件发生变化')
    try:
        cache_dir.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        temporary.write_text(json.dumps({'identity':identity,'parsed':parsed,'parsed_sha256':digest(parsed)},ensure_ascii=False,allow_nan=False),encoding='utf-8')
        temporary.replace(target)
    except OSError:
        # Cache availability must not change the validated business result.
        if 'temporary' in locals():
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
    return parsed

def derive_zero_evidence(parsed):
    """Keep raw nulls intact. Derive only with exact nonnegative total conservation.

    Count bounds: visitors <= views; cart customers <= positive cart pieces;
    buying customers <= sold pieces. Reject inference if known rows violate bounds.
    No rule applies to products absent from the export.
    """
    raw={identifier:item['export_fields'] for identifier,item in parsed['items'].items()}
    controlled={};parents=('商品浏览量','加购商品件数（正向）','成交商品件数','成交金额')
    for field in parents:
        values=[number(item.get(field)) for item in raw.values()]
        control=number(parsed['summary']['export_fields'].get(field))
        if parsed.get('export_limit_reached') or control is None or control<0 or any(v is not None and v<0 for v in values):continue
        if field!='成交金额' and not float(control).is_integer():continue
        known=sum((Decimal(str(v)) for v in values if v is not None),Decimal(0));target=Decimal(str(control))
        arithmetic=None
        if field=='成交金额':
            monetary=[v for v in values if v is not None]
            cents=[Decimal(str(v)).quantize(Decimal('.01')) for v in monetary]
            errors=[abs(Decimal(str(v))-c) for v,c in zip(monetary,cents)]
            # Each detail must already be a cent amount up to representation
            # error. The aggregate can accumulate more than two of its own
            # ULPs: gamma_n bounds n nonnegative binary64 additions.
            if any(error>Decimal(str(math.ulp(float(v))))*2 for v,error in zip(monetary,errors)):continue
            known=sum(cents,Decimal(0));rounded=target.quantize(Decimal('.01'))
            nu=Decimal(len(monetary))*(Decimal(2)**-53)
            if nu>=1:continue
            arithmetic=(nu/(1-nu))*sum((abs(c) for c in cents),Decimal(0))+sum(errors,Decimal(0))+Decimal(str(math.ulp(float(control))))*2
            if arithmetic>=Decimal('.005') or abs(target-rounded)>arithmetic:continue
            target=rounded
        elif any(v is not None and float(v).is_integer() is False for v in values):continue
        if known==target:
            controlled[field]={'rule':'nonnegative_exact_total_conservation','field':field,'known_sum':str(known),'official_total':str(target),'unresolved_total':'0','precision':'integer_counts' if field!='成交金额' else 'cent_details_and_bounded_binary64_sum'}
            if arithmetic is not None:controlled[field].update(control_arithmetic_error_bound=str(arithmetic),official_raw_total=str(control),summed_known_rows=len(monetary))
    records={i:{k:number(item.get(field)) for k,field in FIELDS.items()} for i,item in raw.items()};proofs={}
    if '成交金额' in controlled:
        for identifier,record in records.items():
            if record['amount'] is None:
                record['amount']=0;proofs.setdefault(identifier,{})['amount']=controlled['成交金额']
    bound_consistency={}
    for metric,parent in [('uv','商品浏览量'),('cart','加购商品件数（正向）'),('buyers','成交商品件数')]:
        if parent not in controlled:continue
        consistent=True
        for identifier,item in raw.items():
            child=number(item.get(FIELDS[metric]));value=number(item.get(parent));value=0 if value is None else value
            if child is not None and (child<0 or child>value):
                consistent=False;records[identifier].setdefault('_quality_issues',[]).append(FIELDS[metric]+' > '+parent)
            if metric=='buyers' and value==0 and records[identifier]['amount'] is not None and records[identifier]['amount']>0:
                consistent=False;records[identifier].setdefault('_quality_issues',[]).append('positive_amount_without_sold_pieces')
        bound_consistency[parent]=consistent
        if not consistent:continue
        for identifier,item in raw.items():
            value=number(item.get(parent))
            if records[identifier][metric] is None and value in (None,0):
                records[identifier][metric]=0
                proofs.setdefault(identifier,{})[metric]={'rule':'zero_from_nonnegative_count_bound','bound':FIELDS[metric]+' <= '+parent,'parent_evidence':controlled[parent]}
    # Gross product revenue requires a sold piece; no sub-cent rounding is used.
    # Never apply this to refunds, costs, profit, or an absent product row.
    sold='成交商品件数'
    if sold in controlled and bound_consistency.get(sold):
        consistent=all(records[i]['amount'] is None or (records[i]['amount']>=0 and not (records[i]['amount']>0 and number(item.get(sold)) in (None,0))) for i,item in raw.items())
        known=[r['amount'] for r in records.values() if r['amount'] is not None]
        monetary_control=number(parsed['summary']['export_fields'].get('成交金额'))
        if monetary_control is None:consistent=False
        else:
            residual=Decimal(str(monetary_control))-sum((Decimal(str(v)) for v in known),Decimal(0))
            float_error=sum((Decimal(str(math.ulp(float(v))))*2 for v in [*known,monetary_control]),Decimal(0))
            # Official totals and per-product amounts can both be accumulated
            # binary64 values. Bound the aggregate arithmetic without rounding
            # any detail, or erasing a genuine sub-cent residual.
            nu=Decimal(len(known))*(Decimal(2)**-53)
            if nu>=1:consistent=False
            else:float_error+=(nu/(1-nu))*sum((abs(Decimal(str(v))) for v in known),Decimal(0))
            if float_error>=Decimal('.005'):consistent=False
            unknown_positive_pieces=any(records[i]['amount'] is None and (number(item.get(sold)) or 0)>0 for i,item in raw.items())
            if residual < -float_error or (residual>float_error and not unknown_positive_pieces):consistent=False
        if consistent:
            for identifier,item in raw.items():
                if records[identifier]['amount'] is None and number(item.get(sold)) in (None,0):
                    records[identifier]['amount']=0
                    proofs.setdefault(identifier,{})['amount']={'rule':'zero_gross_amount_from_zero_sold_pieces','scope':'product_gross_deal_amount_only','parent_evidence':controlled[sold],
                        'money_control_residual':str(residual),'money_control_arithmetic_bound':str(float_error)}
    return records,proofs

def analyze(days,cohort,series):
    if len(days)!=7 or days!=[(date.fromisoformat(days[0])+timedelta(days=i)).isoformat() for i in range(7)]:raise ValueError('测款必须使用七个连续完整日')
    if not cohort or len(set(cohort))!=len(cohort):raise ValueError('固定队列为空或商品编号重复')
    rows=[]
    for identifier in sorted(cohort):
        daily=[series.get(d,{}).get(identifier) for d in days]
        identity=next((x for x in reversed(daily) if x and x.get('name')),{})
        row={'name':identity.get('name'),'item_num':identity.get('item_num'),'spu_id':identifier,'known_days':sum(x is not None for x in daily),'missing':[], 'daily':[{'date':d,'metrics':v} for d,v in zip(days,daily)]}
        for field in FIELDS:
            values=[x.get(field) if x else None for x in daily]
            valid=[type(v) in (int,float) and math.isfinite(v) and v>=0 for v in values]
            row[field]=round(math.fsum(values),2) if all(valid) else None
            if not all(valid):row['missing'].append(field)
        if any(x and x.get('_quality_issues') for x in daily):row['missing'].append('source_counter_contradiction')
        uv=row['uv'];row['cart_rate']=row['cart']/uv if uv and row['cart'] is not None else None
        row['pay_rate']=row['buyers']/uv if uv and row['buyers'] is not None else None
        row['uv_value']=row['amount']/uv if uv and row['amount'] is not None else None
        if any(row[f] is not None and not 0<=row[f]<=1 for f in ('cart_rate','pay_rate')):row['missing'].append('rate_scope_inconsistent')
        rows.append(row)
    eligible=[r for r in rows if not r['missing'] and r['uv']>0]
    blockers={'source_counter_contradiction','rate_scope_inconsistent'}
    comparable=[r for r in rows if not blockers.intersection(r['missing']) and r['uv'] is not None and r['uv']>0 and r['pay_rate'] is not None]
    comparable_ids={r['spu_id'] for r in comparable}
    benchmarks={}
    for field in ('uv','cart_rate','pay_rate'):
        values=[r[field] for r in comparable if r[field] is not None]
        if len(values)>=4:
            q=statistics.quantiles(values,n=4,method='inclusive')
            benchmarks[field]={'count':len(values),'p25':q[0],'median':statistics.median(values),'p75':q[2],'min':min(values),'max':max(values)}
    for row in rows:
        label='数据不足';reason='观察窗记录或指标缺失，不能补零判定'
        if row['spu_id'] in comparable_ids:
            if not all(f in benchmarks for f in ('uv','pay_rate')):reason='转化可比样本不足4款，不计算四分位判定'
            elif row['uv']<benchmarks['uv']['p25']:reason='观察窗访客人次处于队列下四分位，仅作相对样本提醒'
            elif row['cart_rate'] is not None and 'cart_rate' in benchmarks and benchmarks['cart_rate']['p75']>benchmarks['cart_rate']['p25'] and benchmarks['pay_rate']['p75']>benchmarks['pay_rate']['p25'] and row['cart_rate']>=benchmarks['cart_rate']['p75'] and row['pay_rate']<=benchmarks['pay_rate']['p25'] and row['cart']>0:
                label='意向高待转化';reason='队列内加购率处于上四分位、成交率处于下四分位；不证明款式或承接原因'
            elif benchmarks['pay_rate']['p75']>benchmarks['pay_rate']['p25'] and benchmarks['uv']['max']>benchmarks['uv']['min'] and row['pay_rate']>0 and row['pay_rate']>=benchmarks['pay_rate']['p75'] and row['uv']<=benchmarks['uv']['median']:
                label='候选加流量';reason='队列内成交率处于上四分位、访客人次不高于中位数；先小范围补充流量验证稳定性'
            elif row['buyers']>0:label='已有成交，继续观察';reason='观察窗有成交客户，继续观察流量与转化稳定性'
            else:reason='没有形成足够的成交或相对意向信号'
        if not blockers.intersection(row['missing']) and row['uv']==0:reason='已证明观察窗无访客，缺少评价款式的流量样本'
        if row['missing'] and label!='数据不足':reason+='；部分指标缺失，仅按已知指标判断'
        row.update(label=label,reason=reason)
    labels=Counter(r['label'] for r in rows)
    actions=[]
    if labels['意向高待转化']:actions.append('对意向高待转化候选逐项核查价格、尺码、详情页与库存，先验证再改动')
    if labels['候选加流量']:actions.append('对候选款小范围补充流量，跟踪新增访客、加购及成交客户，验证转化是否稳定；不直接作大规模放量结论')
    if not actions and labels['已有成交，继续观察']:actions.append('对已有成交商品持续观察流量与转化，金额未知单独标注，不据此否定已知表现')
    if not actions:actions=['先补齐缺失指标并核对官方空值含义；本次不输出加流量或改款建议','取得首次上架日期后，再建立同上架年龄队列，保留本次固定日历窗作参考']
    coverage={'complete':{f:sum(r[f] is not None for r in rows) for f in FIELDS},'missing':{f:sum(r[f] is None for r in rows) for f in FIELDS}}
    return {'coverage':coverage,'status':'partial' if len(eligible)<len(rows) else 'ok','workflow_status':'implemented_with_data_limits','cohort_size':len(rows),'complete_metric_products':len(eligible),'conversion_comparable_products':len(comparable),'days':days,
        'cohort_definition':'end_date_official_tagged_spu_fixed_snapshot','observation_window':'seven_calendar_days_not_listing_age','benchmarks':benchmarks,'labels':dict(Counter(r['label'] for r in rows)),'items':rows,
        'notes':['固定统计日官方打标SPU集合，七个日历日同窗；没有首次上架日期，不是同上架年龄队列','访客及客户按日相加为人次；成交率及加购率为按日汇总近似，不是周去重率','分位基线使用访客及成交客户完整、无口径矛盾的商品；加购基线再排除加购缺失商品；各指标样本数见基线','金额缺失不阻断转化判断，加购缺失不阻断成交转化判断；所有缺失单独标注，UV价值在金额未知时保持缺失','原始空值不改动；仅有逐单元格依据的推导零值另留证据；其余未知不补零','缺失日或未出现的商品行不补零；低访客只作样本不足提醒，不评价款式好坏','分位规则只反映本队列相对位置，不是行业阈值或统计显著性证明；候选需小范围验证转化稳定性','收藏及首次上架日期尚未接入；本次仅分析流量、加购和成交表现'],
        'actions':actions}

def load_day(day,store,*,root=ROOT):
    candidates=[]
    for folderday in (day,(date.fromisoformat(day)+timedelta(days=1)).isoformat()):
        candidates+=sorted((root/'data/jd'/store.replace(':','_')/folderday/'products-spu-api').glob('*/products-spu-exports/report.json'),reverse=True)
    errors=[]
    for path in candidates:
        try:
            report=json.loads(path.read_text(encoding='utf-8'));side='current' if report.get('date')==day else 'previous'
            if report.get('store',{}).get('store_key')!=store or report.get('dimension')!='spu' or not report.get('transaction_totals_reconciled'):raise ValueError('导出配对报告身份或完整性不符')
            if report.get('date' if side=='current' else 'compare_date')!=day:raise ValueError('导出配对日期不符')
            source=report['sources'][side];control=report['sources']['overview']
            if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()!=source['sha256'] or hashlib.sha256(Path(control['path']).read_bytes()).hexdigest()!=control['sha256']:raise ValueError('导出或概况文件哈希不符')
            overview=json.loads(Path(control['path']).read_text(encoding='utf-8'))
            if overview.get('store',{}).get('store_key')!=store or overview.get('date' if side=='current' else 'compare_date')!=day:raise ValueError('独立概况身份或日期不符')
            parsed=load_export_cached(source['path'],day,store);metrics={m['name']:m for m in overview['metrics']}
            slot='value' if side=='current' else 'previous'
            for field,tolerance in [('成交金额',.01),('成交商品件数',0)]:
                expected=metrics.get(field,{}).get(slot);actual=parsed['summary']['metrics'][field]
                if expected is None or actual is None or abs(expected-actual)>tolerance:raise ValueError('导出与独立概况不符')
            records,zero_evidence=derive_zero_evidence(parsed)
            for identifier,record in records.items():
                record.update(name=parsed['items'][identifier]['name'],item_num=parsed['items'][identifier]['item_num'])
            return records,{'date':day,'export':source,'control':control,'acquisition':'saved_official_export_revalidated','transaction_totals_reconciled':True,'derived_zero_evidence':zero_evidence}
        except (ValueError,KeyError,OSError) as error:errors.append(str(error))
    raise ValueError('缺少可验证商品导出：'+day+'；'+('；'.join(errors[-2:]) or '先运行product-full --dimension spu'))

def load_cohort(day,store,*,root=ROOT):
    from .new_product_review import load_verified
    for path in sorted((root/'data/jd'/store.replace(':','_')/day/'new-products-spu').glob('*/report.json'),reverse=True):
        try:
            report=load_verified(path,day,store,dimension='spu')
            return sorted({r['id'] for r in report['rows']}),str(path)
        except (ValueError,KeyError,OSError):continue
    raise ValueError('缺少完整官方打标SPU队列，先运行new-products-spu')

def compare_windows(current,previous):
    before={r['spu_id']:r for r in previous['items']};pairs=[]
    blockers={'source_counter_contradiction','rate_scope_inconsistent'}
    for row in current['items']:
        prior=before.get(row['spu_id'])
        if prior and not blockers.intersection(row['missing']) and not blockers.intersection(prior['missing']):pairs.append((row,prior))
    metrics={}
    for field in FIELDS:
        matched=[(a,b) for a,b in pairs if a[field] is not None and b[field] is not None]
        now=math.fsum(a[field] for a,b in matched) if matched else None
        old=math.fsum(b[field] for a,b in matched) if matched else None
        metrics[field]={'products':len(matched),'current':now,'previous':old,'relative_change':(now-old)/old if old else None}
    rates={}
    for rate,field in [('conversion','buyers'),('cart_rate','cart')]:
        matched=[(a,b) for a,b in pairs if all(x[f] is not None for x in (a,b) for f in ('uv',field))]
        def value(index):
            uv=math.fsum(pair[index]['uv'] for pair in matched)
            return math.fsum(pair[index][field] for pair in matched)/uv if uv else None
        now,old=value(0),value(1)
        rates[rate]={'products':len(matched),'current':now,'previous':old,'percentage_points':(now-old)*100 if now is not None and old is not None else None}
    declining=sorted(({'spu_id':a['spu_id'],'name':a.get('name'),'item_num':a.get('item_num'),'current_buyers':a['buyers'],'previous_buyers':b['buyers'],'delta':a['buyers']-b['buyers']} for a,b in pairs if a['buyers'] is not None and b['buyers'] is not None and a['buyers']<b['buyers']),key=lambda x:x['delta'])[:5]
    return {'cohort':'end_date_fixed_official_tagged_spu','current_days':current['days'],'previous_days':previous['days'],'metrics':metrics,**rates,'declining_buyers':declining,'causal_limit':'指标变化只支持现象定位，不能据此证明价格、尺码、库存或页面是原因；金额仅代表两期金额完整的同一子集'}


def collect(day,store,*,weeks=1):
    if weeks not in (1,2):raise ValueError('测款仅支持一周或两周')
    started=time.perf_counter()
    days=[(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    cohort,path=load_cohort(day,store);series={};sources=[]
    for d in days:
        series[d],proof=load_day(d,store)
        proof['derived_zero_evidence']={i:p for i,p in proof['derived_zero_evidence'].items() if i in cohort}
        sources.append(proof)
    report=analyze(days,cohort,series);report.update(platform='jd',store_key=store,date=day,sources=sources,cohort_source=path)
    if weeks==2:
        previous_days=[(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(13,6,-1)]
        previous_series={}
        for d in previous_days:
            previous_series[d],proof=load_day(d,store)
            proof['derived_zero_evidence']={i:p for i,p in proof['derived_zero_evidence'].items() if i in cohort}
            sources.append(proof)
        report['comparison']=compare_windows(report,analyze(previous_days,cohort,previous_series))
    report['derived_zero_cells']=sum(len(p) for q in sources for p in q['derived_zero_evidence'].values())
    from .inventory import ensure_context as inventory_context
    preferred=[r['spu_id'] for r in report['items'] if r['label'] in ('候选加流量','意向高待转化')]
    report['inventory']=inventory_context(day,store,preferred,limit=60)
    report['metric_status']=report['status']
    # Listing age and favorites are still absent even if observed sales and
    # the selected inventory happen to be complete.
    report['status']='partial'
    report['elapsed_seconds']=round(time.perf_counter()-started,3)
    report['weeks']=weeks
    report['highlights']={label:[{k:r[k] for k in ('spu_id','name','item_num','uv','buyers','cart_rate','pay_rate','amount','missing')} for r in sorted((x for x in report['items'] if x['label']==label),key=lambda x:-(x['buyers'] or 0))[:5]] for label in ('候选加流量','意向高待转化')}
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'product-test'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True,exist_ok=False)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'report.md').write_text(render_markdown(report),encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('items','sources')}|{'report_path':str(folder/'report.json'),'markdown_path':str(folder/'report.md')}


def render_markdown(report):
    days=report['days']
    lines=[f'# 京东官方打标新品测款：{report["date"]}',f'店铺：{report["store_key"]}；观察窗：{days[0]} 至 {days[-1]}',f'固定队列{report["cohort_size"]}款；全部指标完整{report["complete_metric_products"]}款；访客与成交客户可比{report["conversion_comparable_products"]}款。',f'判定数量：{report["labels"]}',f'有逐单元格依据的推导零值：{report["derived_zero_cells"]}个；原始文件及空单元格保持不变。','\n## 队列内相对判定','每类最多展示10款；完整明细见同目录report.json。','|商品名称|货号|SPU|标签|访客人次|加购率近似|成交客户人次|成交率近似|成交金额|UV价值（元/访客人次）|缺失指标|','|---|---|---|---|---:|---:|---:|---:|---:|---:|---|']
    escape=lambda v:str(v if v not in (None,'') else '未提供').replace('|','\\|').replace('\n',' ').replace('\r',' ')
    for label in ('意向高待转化','候选加流量','已有成交，继续观察','数据不足'):
        selected=sorted((r for r in report['items'] if r['label']==label),key=lambda r:-(r['amount'] or 0))[:10]
        for r in selected:
            fmt=lambda v:'缺失' if v is None else f'{v:.2f}'
            pct=lambda v:'缺失' if v is None else f'{v:.2%}'
            missing='、'.join(FIELDS.get(f,f) for f in r['missing']) or '无'
            lines.append('|'+ '|'.join([escape(r.get('name')),escape(r.get('item_num')),escape(r['spu_id']),label,fmt(r['uv']),pct(r['cart_rate']),fmt(r['buyers']),pct(r['pay_rate']),fmt(r['amount']),fmt(r['uv_value']),missing])+'|')
    lines+=['\n## 最多两个验证动作',*['- '+a for a in report['actions']],'\n## 口径与未完成项',*['- '+n for n in report['notes']]]
    if 'comparison' in report:
        comparison=report['comparison']
        lines+=['\n## 固定新品队列两周对照','各指标仅使用两周该指标均完整的相同商品；各行样本可能不同。','|指标|可比商品数|本周|前周|相对变化|','|---|---:|---:|---:|---:|']
        for field,values in comparison['metrics'].items():
            lines.append('|'+FIELDS[field]+'|'+str(values['products'])+'|'+ '|'.join('缺失' if values[k] is None else (f'{values[k]:.2%}' if k=='relative_change' else f'{values[k]:.2f}') for k in ('current','previous','relative_change'))+'|')
        for key,title in [('conversion','近似成交率'),('cart_rate','近似加购率')]:
            rate=comparison[key]
            lines.append(f'- {title}（{rate["products"]}款）：本周'+('缺失' if rate['current'] is None else f'{rate["current"]:.2%}')+'，前周'+('缺失' if rate['previous'] is None else f'{rate["previous"]:.2%}'))
        lines.append(comparison['causal_limit'])
    from .inventory import markdown as inventory_markdown
    return '\n'.join(lines)+inventory_markdown(report.get('inventory'))
