"""Replay an explicitly witnessed official export; retain business columns only.

The witness is a local acquisition record, not an independent signed JD certificate.
Source files remain in Downloads; no buyer columns are copied into evidence reports.
"""
from collections import Counter
from datetime import date,datetime,timedelta
from decimal import Decimal,InvalidOperation
from pathlib import Path
import hashlib,io,json,re,zipfile
import xml.etree.ElementTree as ET
from .after_sales import PAGE
from .refund_enrichment import CHINA,timestamp

NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
HEADERS=('服务单号','订单号','售后申请时间','客户期望','售后状态','一级申请原因','二级申请原因','商品编号','商品名称','商品数量','退款金额')

def _days(begin,end):
    first=date.fromisoformat(begin);last=date.fromisoformat(end)
    if first.isoformat()!=begin or last.isoformat()!=end or not 0<=(last-first).days<=92:raise ValueError('官方售后导出范围无效')
    return [(first+timedelta(days=n)).isoformat() for n in range((last-first).days+1)]

def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[1-9]\d{0,19}',value):raise ValueError('导出业务编号无效')
    return value

def _number(value):
    if value in ('','-','—',None):return None
    try:n=Decimal(value)
    except (InvalidOperation,TypeError):raise ValueError('导出金额或数量格式无效') from None
    if not n.is_finite() or n<0:raise ValueError('导出金额或数量无效')
    return str(n)

def parse_workbook(raw,begin,end,official_total):
    dates=_days(begin,end)
    if type(official_total) is not int or not 0<=official_total<=500000:raise ValueError('官方导出总数无效')
    if not raw.startswith(b'PK'):raise ValueError('工作簿不可读或已加密，不尝试解密')
    rows=[];seen=set();by={d:0 for d in dates};money_missing=0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(i.file_size for i in z.infolist())>300_000_000:raise ValueError('工作簿超过登记大小')
        sheets=[n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)]
        if sheets!=['xl/worksheets/sheet1.xml']:raise ValueError('导出分卷/工作表结构未核验')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _,el in ET.iterparse(f,events=['end']):
                    if el.tag==NS+'si':strings.append(''.join(el.itertext()));el.clear()
        headers=None;ix={}
        with z.open(sheets[0]) as f:
            for _,el in ET.iterparse(f,events=['end']):
                if el.tag!=NS+'row':continue
                values={}
                for c in el.findall(NS+'c'):
                    ref=c.get('r','');col=re.sub(r'\d','',ref)
                    if c.find(NS+'f') is not None:raise ValueError('导出含公式，不接受未核验计算值')
                    if c.get('t')=='inlineStr':v=''.join(c.find(NS+'is').itertext())
                    else:
                        v=c.findtext(NS+'v','')
                        if c.get('t')=='s':v=strings[int(v)]
                    values[col]=v
                if headers is None:
                    if '服务单号' not in values.values():el.clear();continue
                    headers=list(values.values())
                    if any(headers.count(h)!=1 for h in HEADERS):raise ValueError('官方售后导出表头缺失或重复')
                    ix={v:k for k,v in values.items() if v in HEADERS};el.clear();continue
                if not any(values.values()):el.clear();continue
                # Values outside this whitelist are deliberately neither inspected nor persisted.
                get=lambda k:values.get(ix[k],'')
                sid=_id(get('服务单号'));oid=_id(get('订单号'))
                skus=[_id(s.strip()) for s in re.split('[，,]',get('商品编号'))]
                if len(set(skus))!=len(skus):raise ValueError('同一服务单的商品编号重复，需核验件数结构')
                if sid in seen:raise ValueError('服务单重复，不能推定全范围完整')
                applied=timestamp(get('售后申请时间'));day=applied.date().isoformat()
                if day not in by:raise ValueError('服务单申请时刻超出官方导出范围')
                qty=_number(get('商品数量'));amount=_number(get('退款金额'))
                if qty is None or Decimal(qty)!=int(Decimal(qty)):raise ValueError('商品件数未核验')
                seen.add(sid);by[day]+=1;money_missing+=amount is None
                rows.append({'service_id':sid,'order_id':oid,'application_time_raw':applied.isoformat(),
                    'service_type_raw':get('客户期望'),'status_fields':{'afsServiceStatusName':get('售后状态')},
                    'refund_fields':{'refundAmount':amount,'amount_basis':'official_export_退款金额_status_snapshot'},
                    'reasons':[get(h) for h in ('一级申请原因','二级申请原因') if get(h)],
                    'reason_levels':{'level_1':get('一级申请原因') or None,'level_2':get('二级申请原因') or None},
                    'items':[{'wareId':sku} for sku in skus],
                    'service_item_quantity_raw':int(Decimal(qty)),
                    'item_description_raw':get('商品名称'),
                    'item_quantity_basis':'export_service_total_not_allocated_to_skus'})
                el.clear()
                if len(rows)>official_total:raise ValueError('导出行数超过官方列表总数')
        if headers is None or len(rows)!=official_total:raise ValueError('导出唯一服务单数与官方列表总数不一致')
    return {'range_complete':True,'range_start':begin,'range_end':end,'official_total':official_total,
        'unique_service_count':len(rows),'unique_order_count':len({r['order_id'] for r in rows}),
        'refund_amount_missing_services':money_missing,'orders':rows,
        'by_day':{d:{'whole_day_complete':True,'unique_service_count':n,'source':'official_native_export'} for d,n in by.items()},
        'limitations':['官方导出与相同全部状态/申请范围列表总数一致；零条日期由整个范围全量文件支持。',
        '退款金额为导出快照字段，未将完成状态推为退款成功，空值不补零。',
        '导出无付款时间、父单编号及全部兄弟单证明；不构成完整付款分母。']}

def validate_evidence(p,store,sha):
    identity=p.get('identity',{})
    mall=re.fullmatch(r'jd:mall:(\d+)',store)
    name=re.sub(r'\s+','',identity.get('name') or '')
    page_name=re.sub(r'\s+','',p.get('page_store_name') or '')
    official_merchant=identity.get('merchant_identity_kind')=='official_shop_information' and re.fullmatch(r'\d+',str(identity.get('merchant_id','')))
    mall_link=bool(mall and identity.get('platform')=='jd' and identity.get('identity_anchor')=='https://mall.jd.com/index-'+mall[1]+'.html'
        and identity.get('identity_kind')=='page_mall_link' and name and page_name and name==page_name)
    if (p.get('platform')!='jd' or p.get('store_key')!=store or p.get('source')!='official_native_export'
        or p.get('page_url')!=PAGE or p.get('tab')!='all' or p.get('task_status')!='导出成功'
        or p.get('archive_sha256')!=sha or not re.fullmatch(r'\d+',p.get('task_id',''))
        or identity.get('store_key')!=store or not (official_merchant or mall_link)):raise ValueError('官方导出凭据的店铺、任务、范围或哈希不符')
    _days(p['range_start'],p['range_end'])
    created=timestamp(p['task_created_at']);observed=timestamp(p['observed_at'])
    last_day_end=timestamp(p['range_end']+'T00:00:00')+timedelta(days=1)
    if not last_day_end<=created<=observed:raise ValueError('导出任务快照早于完整观察窗结束或晚于观察时刻')
    if type(p.get('official_total')) is not int or p['official_total']<0:raise ValueError('官方列表总数缺失')

def _json(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def import_evidence(evidence_file,store):
    from .api_client import ROOT
    p=json.loads(Path(evidence_file).read_text(encoding='utf-8'));source=Path(p['archive_path'])
    raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest();validate_evidence(p,store,sha)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files=[i for i in z.infolist() if not i.is_dir()]
        expected=timestamp(p['task_created_at']).strftime('%Y-%m-%d-%H-%M-%S')+'--'+p['task_id']+'.xlsx'
        if len(files)!=1 or files[0].flag_bits&1 or files[0].file_size>100_000_000 or files[0].filename!=expected:raise ValueError('官方导出任务文件关联或加密状态不符')
        report=parse_workbook(z.read(files[0]),p['range_start'],p['range_end'],p['official_total'])
    folder=ROOT/'data/jd'/store.replace(':','_')/p['range_start']/'after-sales-export'/p['task_id']
    folder.mkdir(parents=True,exist_ok=True)
    projection=_json(report);safe=folder/'business.json';safe.write_text(projection,encoding='utf-8')
    proof={**p,'projection_sha256':hashlib.sha256(projection.encode()).hexdigest(),'projection_path':str(safe)}
    proof_path=folder/'proof.json';proof_path.write_text(_json(proof),encoding='utf-8')
    return str(proof_path)

def saved_exports(payment_day,store):
    from .api_client import ROOT
    from .refund_cohort import required_days
    wanted=required_days(payment_day);by={};services=[];proofs=[];errors=[]
    base=(ROOT/'data/jd'/store.replace(':','_')).resolve()
    # Use a single complete official export covering the whole required range; never merge stale snapshots.
    candidates=[]
    for path in base.glob('????-??-??/after-sales-export/*/proof.json'):
        try:
            p=json.loads(path.read_text(encoding='utf-8'))
            if p['range_start']>wanted[0] or p['range_end']<wanted[-1]:continue
            sha=hashlib.sha256(Path(p['archive_path']).read_bytes()).hexdigest();validate_evidence(p,store,sha)
            projected=Path(p['projection_path']).resolve()
            if not projected.is_relative_to(base):raise ValueError('导出投影路径超出本店')
            raw=projected.read_text(encoding='utf-8')
            if hashlib.sha256(raw.encode()).hexdigest()!=p['projection_sha256']:raise ValueError('售后导出投影哈希不符')
            report=json.loads(raw)
            if not report['range_complete'] or report['unique_service_count']!=p['official_total']:raise ValueError('售后导出完整性凭据不符')
            candidates.append((timestamp(p['observed_at']),p,report,str(path)))
        except (OSError,ValueError,KeyError,TypeError) as exc:errors.append({'proof':str(path),'error':str(exc)})
    if candidates:
        _,p,r,path=max(candidates,key=lambda x:x[0]);by={d:r['by_day'][d] for d in wanted}
        services=[x for x in r['orders'] if wanted[0]<=timestamp(x['application_time_raw']).date().isoformat()<=wanted[-1]]
        proofs=[{'proof_path':path,'task_id':p['task_id'],'official_total':p['official_total'],'unique_service_count':r['unique_service_count'],
            'observed_at':p['observed_at'],'archive_sha256':p['archive_sha256'],'refund_amount_missing_services':r['refund_amount_missing_services']}]
    return by,services,proofs,errors

def observed_outcomes(payment_day,index,services,as_of):
    now=timestamp(as_of);selected={};unknown=0
    for oid,row in index.items():
        if not row.get('payment_confirmed_at'):unknown+=1;continue
        paid=timestamp(row['payment_confirmed_at'])
        if paid.date().isoformat()==payment_day and paid<=now:selected[oid]=paid
    matched=[];seen=set();before=after=0
    for row in services:
        if row['service_id'] in seen:raise ValueError('30天观察服务单重复')
        seen.add(row['service_id']);paid=selected.get(row['order_id'])
        if paid is None:continue
        applied=timestamp(row['application_time_raw'])
        if applied<paid:before+=1
        elif applied>=paid+timedelta(days=30):after+=1
        else:matched.append(row)
    return {'scope':'known_verified_orders_paid_on_selected_day_not_complete_payment_cohort',
        'sample_available':bool(selected),'sample_note':'已保存证据中的付款日订单样本，不是全队列。' if selected else '没有已核验的该付款日订单，不能据零样本得出无售后结论。',
        'known_payment_day_orders':len(selected),'in_window_service_count':len(matched),
        'in_window_unique_orders':len({r['order_id'] for r in matched}),'before_payment_services':before,'after_window_services':after,
        'known_immature_orders':sum(now<p+timedelta(days=30) for p in selected.values()),
        'payment_denominator_complete':False,'return_rate':None,
        'reason_distribution':dict(Counter(label for row in matched for label in set(row.get('reasons') or []))),
        'policy':'只计已核验付款时刻起30日内的服务申请；服务单/订单分别去重，未提供金额汇总或父子单金额合并。'}

def window_summary(services,complete):
    """Application-window causes, kept separate from payment-cohort attribution."""
    def top(values):return [{'label':k,'service_count':v} for k,v in Counter(values).most_common(10)]
    return {'time_basis':'service_application_window_not_payment_cohort','complete':complete,
        'unique_services':len({s['service_id'] for s in services}),
        'unique_orders':len({s['order_id'] for s in services}),
        'refund_amount_missing_services':sum(s.get('refund_fields',{}).get('refundAmount') is None for s in services),
        'multi_sku_services':sum(len(s.get('items',[]))>1 for s in services),
        'reason_level_1_top10':top(s['reason_levels']['level_1'] for s in services if s.get('reason_levels',{}).get('level_1')),
        'reason_level_2_top10':top(s['reason_levels']['level_2'] for s in services if s.get('reason_levels',{}).get('level_2')),
        'reason_levels_missing_services':sum(not s.get('reason_levels') for s in services),
        'policy':'一级/二级官方原因分别展示，不相加为不同服务单；申请窗原因不能解释同付款批次的真实退货率。金额空值不补零，退款状态为快照。'}
