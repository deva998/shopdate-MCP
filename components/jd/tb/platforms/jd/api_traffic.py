"""Registered APP source queries; only the already verified levels and parent."""
import hashlib,json,time
from .api_client import APIClient,capture_api
from . import reports,overview


def collect(day,store,level='2',*,client=None):
    if level not in ('1','2'):raise ValueError('来源层级未验证')
    if client is None:
        with APIClient({'platform':'jd','store_key':store}) as active:return collect(day,store,level,client=active)
    started=time.monotonic();key='traffic-level'+level
    result=capture_api(key,day,store,client=client)
    # The dictionary describes current official labels, not historical daily
    # metrics. Reuse it only within this exact client/store session, retaining
    # the original fetch time and hash instead of downloading it fourteen times.
    cached=getattr(client,'_source_dictionary_cache',None)
    identity=result.get('identity') or {}
    reusable=isinstance(cached,dict) and cached.get('store')==store and cached.get('identity_anchor')==identity.get('identity_anchor') and isinstance(cached.get('text'),str) and hashlib.sha256(cached['text'].encode()).hexdigest()==cached.get('response_sha256')
    if not reusable:
        payload,proof=client.request('source-dictionary',day)
        actual=proof['identity'];raw=client.last_response_text
        if actual.get('platform')!='jd' or actual.get('store_key')!=store or actual.get('identity_anchor')!=identity.get('identity_anchor') or not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('来源字典身份或原文证据不符')
        cached={'store':store,'text':raw,'identity_anchor':actual['identity_anchor'],
          'source':'registered-api','request_started_at':proof['request_started_at'],'response_sha256':proof['response_sha256']}
        client._source_dictionary_cache=cached
    result['source_dictionary']={k:v for k,v in cached.items() if k!='store'}
    result['timings']['with_dictionary_ms']=round((time.monotonic()-started)*1000)
    request=overview.make_request(reports.contracts()[key]['template'],day)
    return reports.save(result,request,key)
