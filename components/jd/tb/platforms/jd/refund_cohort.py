"""Evidence gaps for payment-day cohorts. No inferred denominator or return rate."""
from datetime import date,datetime,timedelta
from .refund_enrichment import timestamp,CHINA

def required_days(payment_day):
    start=date.fromisoformat(payment_day)
    if start.isoformat()!=payment_day:raise ValueError('付款队列日期无效')
    return [(start+timedelta(days=i)).isoformat() for i in range(31)]

def relationships(index):
    families={};unknown=set();missing=set();empty=set()
    def root(identifier,trail):
        if identifier in trail:raise ValueError('官方父子订单关系存在循环，停止家族合并')
        row=index.get(identifier)
        if row is None:missing.add(identifier);return None
        if 'parent_relation_status' not in row:unknown.add(identifier);return None
        parent=row.get('parent_order_id')
        if parent is None:empty.add(identifier);return identifier
        if not isinstance(parent,str) or not parent.isdigit() or parent.startswith('0'):raise ValueError('父订单编号无效')
        return root(parent,trail|{identifier})
    for identifier in index:
        value=root(identifier,set())
        if value is not None:families[identifier]=value
    return {'observed_order_records':len(index),'observed_families':len(set(families.values())),
        'known_parent_edges':sum(bool(r.get('parent_order_id')) for r in index.values()),
        'unknown_parent_field_orders':len(unknown),'missing_parent_orders':len(missing),
        'reported_empty_parent_orders':len(empty),'relations_complete':bool(index) and not unknown and not missing,
        'all_family_members_verified':False,'family_by_order':families,
        'policy':'仅按官方parentId连接；缺字段不推为根单，未证明所有兄弟单完整，不汇总父子单金额。'}

def observation_coverage(payment_day,by_day,as_of):
    dates=required_days(payment_day);now=timestamp(as_of)
    # The latest possible payment in a whole day reaches 30 days next midnight.
    mature_at=timestamp(dates[-1]+'T00:00:00')+timedelta(days=1)
    missing=[d for d in dates if d not in by_day]
    partial=[d for d in dates if d in by_day and not by_day[d].get('whole_day_complete')]
    return {'days':30,'required_application_dates':dates,'complete_dates':[d for d in dates if d in by_day and by_day[d].get('whole_day_complete')],
        'missing_dates':missing,'partial_dates':partial,'whole_payment_day_calendar_mature':now>=mature_at,
        'complete':now>=mature_at and not missing and not partial,
        'interval_policy':'per-order [payment_confirmed_at, payment_confirmed_at + 30 elapsed days); daily partitions include the payment day and day+30'}

def assess(payment_day,index,by_day,as_of):
    graph=relationships(index);coverage=observation_coverage(payment_day,by_day,as_of)
    return {'payment_day':payment_day,'as_of':as_of,'status':'partial','payment_cohort_complete':False,
        'payment_denominator':None,'cohort_return_rate':None,'order_relationships':graph,'observation':coverage,
        'blockers':['尚未取得并核验完整付款日队列分母；已关联售后原订单不是分母。',
            '官方父单关系与全部兄弟单覆盖仍需核验。']+(['观察期服务单逐日证据未齐。'] if not coverage['complete'] else [])}

def saved_context(payment_day,store):
    from .refund_enrichment import load_cases,saved_order_index,saved_lookup_index
    index,_,errors=saved_order_index(store);cached,_,cache_errors=saved_lookup_index(store)
    # Enrichment rows may add relationships that legacy full-order projections lack.
    for identifier,row in cached.items():
        prior=index.get(identifier)
        if prior and prior.get('payment_confirmed_at') and row.get('payment_confirmed_at') and timestamp(prior['payment_confirmed_at'])!=timestamp(row['payment_confirmed_at']):raise ValueError('原付款时间冲突，停止队列核验')
        if not prior or row.get('parent_relation_status'):
            merged={**(prior or {}),**row}
            if prior and prior.get('payment_confirmed_at') and not row.get('payment_confirmed_at'):merged['payment_confirmed_at']=prior['payment_confirmed_at']
            index[identifier]=merged
    from .after_sales_export import saved_exports,observed_outcomes,window_summary
    by_day,export_services,export_proofs,export_errors=saved_exports(payment_day,store);rejected=[]
    for day in required_days(payment_day):
        if day in by_day:continue
        try:
            by_day[day],_=load_cases(day,store)
            export_services.extend(by_day[day]['orders'])
        except (OSError,ValueError,KeyError,TypeError) as exc:rejected.append({'date':day,'error':str(exc)})
    result=assess(payment_day,index,by_day,datetime.now(CHINA).isoformat())
    result.update(platform='jd',store_key=store,date=payment_day,module='付款队列与30天售后证据',
        acquisition='saved_evidence_replay_only',errors=errors+cache_errors+export_errors,rejected_service_dates=rejected,
        service_export_proofs=export_proofs,
        observed_payment_day_sample=observed_outcomes(payment_day,index,export_services,result['as_of']))
    result['observed_payment_day_sample']['service_window_complete']=result['observation']['complete']
    result['service_window_summary']=window_summary(export_services,result['observation']['complete'])
    # Index is all saved order records, not a selected payment-day denominator.
    result['order_relationships'].pop('family_by_order',None)
    result['order_relationships']['scope']='all_saved_verified_order_records_not_payment_day_cohort'
    return result

def collect(payment_day,store,*,export_evidence=None):
    import json,re
    from .api_client import ROOT
    if not re.fullmatch(r'jd:mall:\d+',store):raise ValueError('必须指定京东店铺')
    if export_evidence:
        from .after_sales_export import import_evidence
        import_evidence(export_evidence,store)
    result=saved_context(payment_day,store)
    folder=ROOT/'data/jd'/store.replace(':','_')/payment_day/'refund-cohort'/datetime.now(CHINA).strftime('%Y%m%dT%H%M%S%f%z')
    folder.mkdir(parents=True,exist_ok=False)
    result['report_path']=str(folder/'report.json')
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result
