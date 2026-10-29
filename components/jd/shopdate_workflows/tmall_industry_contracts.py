"""Offline candidate contracts from installed source; no network transport."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import re

CONTRACTS=Path(__file__).with_name('tmall-industry-contracts.json')


def catalog():
    return deepcopy(json.loads(CONTRACTS.read_text(encoding='utf-8'))['candidates'])


def verify_local_sources(workspace):
    root=Path(workspace).resolve()
    allowed={'extensions/qingmu-5.6.5/js/sycmv2.js','extensions/qingmu-5.6.5/js/sycm.js'}
    for item in catalog().values():
        source=item['source'];relative=source['path']
        if relative not in allowed:raise ValueError('未登记的本地接口证据路径。')
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('本地证据不能超出工作区。')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('候选接口源码已变化，必须重新核验。')
        if item['path'] not in raw.decode('utf-8'):raise ValueError('候选接口不在对应本地源码中。')
    return True


def describe_request(kind,params,*,today=None):
    """Describe, never execute. Enum strings are supplied, not guessed defaults."""
    if kind not in ('products','shops'):raise ValueError('仅整理两种榜单候选；不能将市场供给当行业总盘。')
    contract=catalog()[kind]
    if not isinstance(params,dict) or set(params)!=set(contract['observed_parameter_names']):
        raise ValueError('候选参数必须精确匹配已观察字段；实际必填项仍需在线核验。')
    if type(params['page']) is not int or params['page']<1:raise ValueError('页码必须为正整数。')
    for field in ('dateType','dateRange','cateId','priceSeg','rankType','sellerType'):
        if not isinstance(params[field],str) or (field!='priceSeg' and not params[field]):raise ValueError('候选参数应为明确字符串。')
    if params['dateType']!='day':raise ValueError('离线契约暂限单日结构检查，其他周期未核验。')
    if not re.fullmatch(r'\d+',params['cateId']):raise ValueError('类目须提供官方数字ID，不按标题推测。')
    interval=params['dateRange'].split('|')
    if len(interval)!=2:raise ValueError('日期范围须为开始日|结束日。')
    for value in interval:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) or date.fromisoformat(value).isoformat()!=value:raise ValueError('日期无效。')
    today=today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    if interval[0]!=interval[1] or interval[1]>=today:raise ValueError('仅校验完整历史单日。')
    return {'kind':kind,'method':contract['method'],'url':'https://sycm.taobao.com'+contract['path'],
        'params':deepcopy(params),'execution':'disabled_pending_authorized_validation',
        'enum_values_verified':False,'live_verified':False,'source':contract['source'],
        'note':'仅离线描述。接口当前有效性、请求方法、枚举值、分页与响应结构均未完成真实核验。'}
