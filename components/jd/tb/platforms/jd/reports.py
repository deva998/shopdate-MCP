"""Registered native report contracts and bounded presentation."""
import hashlib
import json
from pathlib import Path
from . import product_contract,traffic_contract

ROOT=Path(__file__).resolve().parents[3]

def contracts():
    return json.loads((ROOT/'extension/unpacked/report-contracts.json').read_text(encoding='utf-8'))

def save(result,request,key):
    payload=json.loads(result['text'])
    contract=contracts()[key]
    envelope={'url':contract['endpoint'],'method':'POST','status':result['status'],
      'request_body':request,'response':payload,
      'response_metadata':{'original_body_data_length':len(payload.get('body',{}).get('data',[]))}}
    parser=product_contract.parse_sample if key.startswith('products-') else traffic_contract.parse_sample
    report=parser(envelope,sample_only=False)
    dictionary=result.get('source_dictionary')
    if key.startswith('traffic-') and dictionary and dictionary.get('text'):
        if not dictionary.get('identity_anchor') or dictionary.get('identity_anchor')!=result['identity'].get('identity_anchor'):
            raise ValueError('来源字典店铺身份不符')
        report=traffic_contract.name_sources(report,json.loads(dictionary['text']))
        raw_dictionary=dictionary.get('text','').encode('utf-8')
        report['source_dictionary']={k:v for k,v in dictionary.items() if k!='text'}
        report['source_dictionary']['sha256']=hashlib.sha256(raw_dictionary).hexdigest()
    elif key.startswith('traffic-') and dictionary:report['source_dictionary_diagnostic']=dictionary
    report.update(platform='jd',store=result['identity'],source=result['source'],
      request_timestamp=result['request_timestamp'],requested_after=result['requested_after'],timings=result['timings'],
      bridge_client_version=result.get('bridge_client_version'),query_actions=result.get('query_actions',[]),
      identity_verified_at=result.get('identity_verified_at'),transport=result.get('transport'))
    if result.get('api_proof'):report['api_proof']=result['api_proof']
    folder=ROOT/'data/jd'/result['identity']['store_key'].replace(':','_')/request['startDate']/key
    folder.mkdir(parents=True,exist_ok=True)
    raw=result['text'].encode('utf-8')
    report['response_sha256']=hashlib.sha256(raw).hexdigest()
    (folder/'response.json').write_bytes(raw)
    if key.startswith('traffic-') and dictionary and dictionary.get('text'):(folder/'source-dictionary.json').write_bytes(raw_dictionary)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    title='商品明细' if key.startswith('products-') else '流量来源（APP）'
    lines=[f'# 京东商智 · {title}',f"日期：{report['date']}；对比：{report['compare_date']}；渠道：{report['channel']}。",
      f"店铺：{result['identity']['name'].replace(chr(10),' ')}",'','## 范围与限制',*['- '+note for note in report['notes']],
      '',f"结构化完整结果：{folder/'report.json'}",f"请求发生时间：{result['request_timestamp']}（不是报表统计日期）。"]
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    compact={k:v for k,v in report.items() if k not in ('items','rows')}
    records=report.get('items',report.get('rows',[]))
    compact.update(status='ok',report_path=str(folder/'report.json'),returned_records=len(records),preview=records[:10])
    return compact
