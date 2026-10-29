"""Evidence-bound SKU cohort comparison; traffic semantics remain unverified."""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,math
from .new_products import ROOT,parse_page

AMOUNT='jdr_sch_trade_deal_ord_sku_amt_szweb_trade_newproduct_flag'

def amount(row):
    value=row.get('metrics',{}).get(AMOUNT)
    return round(value,2) if type(value) in (int,float) and math.isfinite(value) and value>=0 else None

def compare(current,previous):
    if any(r.get('platform')!='jd' or r.get('dimension')!='sku' or r.get('complete') is not True for r in (current,previous)):raise ValueError('新品对照只接受完整SKU报告')
    if current['store_key']!=previous['store_key'] or date.fromisoformat(current['date'])-date.fromisoformat(previous['date'])!=timedelta(days=1):raise ValueError('新品店铺或相邻日期不符')
    def index(report):
        rows=report['rows'];result={r['id']:r for r in rows}
        if len(result)!=len(rows):raise ValueError('SKU存在多标签组，不支持直接合计')
        return result
    now,old=index(current),index(previous);common=set(now)&set(old)
    changed=sorted(i for i in common if now[i]['flags']!=old[i]['flags'])
    stable=sorted(common-set(changed))
    def total(values):
        values=list(values)
        return round(math.fsum(values),2) if all(v is not None for v in values) else None
    def summary(rows):
        rows=list(rows);values=[amount(r) for r in rows]
        return {'products':len(rows),'amount':total(values),'sold_products':sum(v>0 for v in values) if all(v is not None for v in values) else None,'missing_amount_products':[r['id'] for r in rows if amount(r) is None]}
    a,b=summary(now.values()),summary(old.values())
    stable_now=total(amount(now[i]) for i in stable);stable_old=total(amount(old[i]) for i in stable)
    delta=round(stable_now-stable_old,2) if stable_now is not None and stable_old is not None else None
    rankings=[{'id':i,'current_amount':amount(now[i]),'previous_amount':amount(old[i]),'delta':round(amount(now[i])-amount(old[i]),2)} for i in stable if amount(now[i]) is not None and amount(old[i]) is not None]
    valid=a['amount'] is not None and b['amount'] is not None
    return {'platform':'jd','store_key':current['store_key'],'date':current['date'],'compare_date':previous['date'],'status':'ok' if valid else 'partial','workflow_status':'partial','analysis_scope':'official_tagged_sku_amount_comparison','current':a,'previous':b,
        'amount_delta':round(a['amount']-b['amount'],2) if valid else None,'amount_relative_change':a['amount']/b['amount']-1 if valid and b['amount'] else None,
        'stable_cohort':{'products':len(stable),'current_amount':stable_now,'previous_amount':stable_old,'amount_delta':delta},
        'entered_ids':sorted(set(now)-set(old)),'exited_ids':sorted(set(old)-set(now)),'flag_changed_ids':changed,
        'risers':sorted((r for r in rankings if r['delta']>0),key=lambda r:(-r['delta'],r['id']))[:10],
        'fallers':sorted((r for r in rankings if r['delta']<0),key=lambda r:(r['delta'],r['id']))[:10],
        'excluded_metrics':['traffic_conversion','active_visitor_products','active_cart_products','first_listing_age'],
        'notes':['每天新品集合可能变化；当日集合金额变化不等于固定新品队列成长','进入/退出仅表示在两日官方打标集合中出现/消失，不代表首次上架或下架','同标签可比商品排名仅描述成交金额变化，不证明原因','访客/加购明细与页面汇总口径尚未对齐，暂不推导转化率或流量归因','没有首次上架日期及同观察窗趋势，测款专项仍未完整实现']}

def load_verified(path,day,store,dimension="sku"):
    path=Path(path);r=json.loads(path.read_text(encoding='utf-8'))
    if r.get('store_key')!=store or r.get('date')!=day or r.get('dimension')!=dimension or r.get('complete') is not True:raise ValueError('报告店铺、日期、维度或完整性不符')
    rows=[];expected=None
    if not r.get('requests'):raise ValueError('缺少原始分页证据')
    for page,q in enumerate(r['requests'],1):
        if q.get('identity',{}).get('store_key')!=store or q.get('identity',{}).get('platform')!='jd' or q.get('date')!=day or q.get('case')!='new-products' or q.get('source')!='registered-api':raise ValueError('分页证据身份不符')
        body=q.get('request_body') or {};params=body.get('commonParam') or {}
        if params.get('page')!=page or any(params.get(k)!=day for k in ('date','startDate','endDate')) or dimension+'_id' not in body.get('groupList',[]):raise ValueError('分页请求范围不符')
        raw=Path(q['response_path']).read_text(encoding='utf-8')
        if hashlib.sha256(raw.encode()).hexdigest()!=q.get('response_sha256'):raise ValueError('分页正文哈希不符')
        batch,total=parse_page(json.loads(raw),dimension)
        if expected is None:expected=total
        if expected!=total:raise ValueError('分页总数变化')
        rows.extend(batch)
    if rows!=r.get('rows') or len(rows)!=expected or len({(x['id'],*x['flags'].values()) for x in rows})!=len(rows):raise ValueError('保存报告与完整分页不一致')
    return r

def collect(day,store,current_file=None,previous_file=None):
    prior=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
    def find(d,specified):
        if specified:return Path(specified)
        candidates=sorted((ROOT/'data/jd'/store.replace(':','_')/d/'new-products-sku').glob('*/report.json'),reverse=True)
        for path in candidates:
            try:load_verified(path,d,store);return path
            except (ValueError,KeyError,OSError):continue
        raise ValueError('缺少可验证的完整新品SKU数据：'+d+'；先运行new-products-sku')
    current_path=find(day,current_file);previous_path=find(prior,previous_file)
    r=compare(load_verified(current_path,day,store),load_verified(previous_path,prior,store))
    r['sources']={'current':str(current_path),'previous':str(previous_path),'acquisition':'saved_verified_registered_api_pages'}
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'new-products-review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True,exist_ok=False)
    (folder/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    lines=[f'# 京东官方打标新品对照：{day}',f'店铺：{store}；对比日期：{prior}',f"当日新品集合：{r['current']['products']}个SKU，成交金额{r['current']['amount']}元；前日集合{r['previous']['products']}个SKU，成交金额{r['previous']['amount']}元。",f"同标签可比集合：{r['stable_cohort']['products']}个SKU，成交金额变化{r['stable_cohort']['amount_delta']}元。",f"进入集合{len(r['entered_ids'])}个，退出集合{len(r['exited_ids'])}个，标签变化{len(r['flag_changed_ids'])}个。",'\n## 金额变化排名（仅同标签可比商品）','|SKU|当日金额|前日金额|变化|','|---|---:|---:|---:|']
    lines += [f"|{x['id']}|{x['current_amount']}|{x['previous_amount']}|{x['delta']:.2f}|" for x in r['risers']+r['fallers']]
    lines += ['\n## 核查建议','- 优先检查下滑榜商品的库存、价格和活动变更；本报告不把它们认定为已证实原因。','- 对新进入集合的商品继续跟踪同一批SKU；退出集合的商品另查标签与在售状态。','- 完成汇总口径核对后，再分析流量和加购转化。','\n## 口径与限制']+['- '+n for n in r['notes']]
    (folder/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return {k:v for k,v in r.items() if k not in ('entered_ids','exited_ids','flag_changed_ids')}|{'entered_products':len(r['entered_ids']),'exited_products':len(r['exited_ids']),'flag_changed_products':len(r['flag_changed_ids']),'report_path':str(folder/'report.json'),'markdown_path':str(folder/'report.md')}
