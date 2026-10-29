"""Read the operator and MCP guide from one on-disk Markdown source."""
from pathlib import Path
import re

DOCUMENT = Path(__file__).resolve().parents[3] / 'references' / 'jd-analysis-guide.md'
ALIASES = {
    '实时': '实时交易概况', '今日销售': '实时交易概况',
    '退货归因': '订单与退货归因', '订单分析': '订单与退货归因',
    '单品诊断': '商品诊断与当前库存', '用户模块': '用户与会员分析',
    '行业数据': '行业大盘与热销榜',
}


def guide(topic='', *, document=None):
    from .data_scope import policy, interfaces
    path = Path(document) if document is not None else DOCUMENT
    text = path.read_text(encoding='utf-8')
    sections = {}
    for part in re.split(r'(?m)^## ', text)[1:]:
        title, _, body = part.partition('\n')
        sections[title.strip()] = '## ' + part.strip()
    common = sections.pop('通用规则')
    rows = []
    for name, content in sections.items():
        status = re.search(r'(?m)^状态：([a-z_]+)\s*$', content)
        if status is None:
            raise ValueError('指南专题缺少状态：' + name)
        rows.append({'topic': name, 'status': status.group(1),
                     'missing_sources': re.split(r'(?m)^### 剩余缺口\s*\n', content)[-1].strip().split('\n\n')[0:1]})
    result = {'platform': 'jd', 'guide_version': '2026-10-27',
              'document_path': str(path.resolve()), 'modules': rows,
              'data_scope': policy(), 'data_interfaces': interfaces(),
              'instructions': common, 'content': common}
    if not topic:
        return result
    if topic in ('完整指南', '全部', 'all'):
        result.update(topic='完整指南', content=text)
        return result
    name = ALIASES.get(topic, topic)
    matches = [name] if name in sections else [key for key in sections if name in key]
    if len(matches) != 1:
        raise ValueError('京东分析主题不存在或不唯一：' + topic + '。可用：' + '、'.join(sections))
    name = matches[0]
    result.update(topic=name, modules=[row for row in rows if row['topic'] == name],
                  content=common + '\n\n' + sections[name])
    return result
