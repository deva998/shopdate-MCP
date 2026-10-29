"""Exact-window APP hierarchy and terminal comparisons for daily/weekly reports."""
from datetime import date,timedelta
from pathlib import Path
from .overview import numeric,formatted
from .api_client import ROOT

def window(day,count):
 return [(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(count-1,-1,-1)]

def source_layers(reports,day,store):
 from .business_structure import ranking,change
 count=len(reports)
 if count not in (1,14) or sorted(r['date'] for r in reports)!=window(day,count):raise ValueError('四层来源日期缺失或重复')
 ordered=sorted(reports,key=lambda r:r['date']);indexes=[];names={}
 for r in ordered:
  if r.get('store',{}).get('platform')!='jd' or r['store'].get('store_key')!=store or r.get('channel')!='app' or not r.get('app_complete'):raise ValueError('四层来源店铺或完整性不符')
  if r.get('compare_date')!=window(r['date'],2)[0]:raise ValueError('四层来源对比日期不符')
  index={}
  for node in r['nodes']:
   key=tuple(node['path'])
   if not 1<=len(key)<=4 or node['level']!=len(key) or key in index:raise ValueError('来源路径层级或重复无效')
   index[key]=node;names[key]=node['name']
  indexes.append(index)
 levels=[]
 for level in range(1,5):
  rows=[]
  for key,name in names.items():
   if len(key)!=level:continue
   entries=[i.get(key,{}).get('metrics',{}).get('引入成交金额',{}) for i in indexes]
   if count==1:value,prior=numeric(entries[0].get('value')),numeric(entries[0].get('previous'))
   else:
    values=[numeric(e.get('value')) for e in entries]
    prior=sum(values[:7]) if all(v is not None for v in values[:7]) else None
    value=sum(values[7:]) if all(v is not None for v in values[7:]) else None
   row=change('/'.join(key),name,value,prior);row['path']=list(key);rows.append(row)
  levels.append({'level':level,'records':len(rows),**ranking(rows)})
 return {'status':'ok','channel':'app','period':'day' if count==1 else 'seven_vs_seven','dates':window(day,count),
  'levels':levels,'sources':[{'date':r['date'],'report_path':r.get('report_path')} for r in ordered],
  'limitation':'APP四层分别比较完整路径；父子层不相加，跨父同名编号不合并。周金额仅同路径每日有值才加总；缺行不补零，不证明全店归因。'}

def terminal_comparison(reports,day,store,*,weekly=False):
 count=14 if weekly else 2;days=window(day,count)
 if len(reports)!=count or sorted(r['date'] for r in reports)!=days:raise ValueError('终端比较日期缺失或重复')
 ordered=sorted(reports,key=lambda r:r['date'])
 for r in ordered:
  if r.get('store_key')!=store:raise ValueError('终端比较店铺不符')
  if [c['channel'] for c in r['channels']]!=['all','app','pc','wx','sq','m']:raise ValueError('终端范围不完整')
 indexes=[{c['channel']:c for c in r['channels']} for r in ordered];split=7 if weekly else 1;channels=[]
 def total(entries,name):
  values=[numeric(e.get('metrics',{}).get(name,{}).get('value')) for e in entries]
  return sum(values) if all(v is not None for v in values) else None
 for key in indexes[0]:
  entries=[index[key] for index in indexes];metrics={}
  periods=[]
  for group in (entries[:split],entries[split:]):
   uv=total(group,'店铺访客数');buyers=total(group,'成交客户数');product_uv=total(group,'商品访客数')
   periods.append({'成交金额':total(group,'成交金额'),'日均店铺访客数':uv/split if uv is not None else None,
    '按日汇总近似成交转化率':buyers/product_uv if buyers is not None and product_uv not in (None,0) else None})
  for name in periods[0]:
   prior,value=periods[0][name],periods[1][name]
   metrics[name]={'value':value,'previous':prior,'relative_change':value/prior-1 if value is not None and prior not in (None,0) else None}
  channels.append({'channel':key,'name':entries[-1]['name'],'metrics':metrics,'known_days':sum(e['status']!='empty' for e in entries)})
 missing=any(m[slot] is None for c in channels for m in c['metrics'].values() for slot in ('value','previous'))
 return {'status':'partial' if missing else 'ok','period':'seven_vs_seven' if weekly else 'day_vs_previous',
  'dates':days,'channels':channels,'deduplicated_week_uv_available':False,
  'sources':[{'date':r['date'],'report_path':r.get('report_path')} for r in ordered],
  'limitation':'六终端各自比较，全部为官方独立汇总，不相加终端UV。日均访客不是周去重UV；近似转化率=sum(日成交客户数)/sum(日商品访客数)，沿用该终端接口分母。官方空表不补零，缺日不计算整窗结论。'}

def collect(day,store,*,weekly=False,client=None,root=None):
 from .panorama import latest,load_traffic,load_terminals
 from . import traffic_tree,traffic_channels
 root=Path(root) if root is not None else ROOT;base=root/'data/jd'/store.replace(':','_');output={}
 fetch_blocked=False
 for key,command,days in [('source_layers','traffic-tree',window(day,14 if weekly else 1)),('terminal_comparison','traffic-channels',window(day,14 if weekly else 2))]:
  loaded=[];errors=[]
  for selected in days:
   def load():
    path=latest(base/selected/command)
    if key=='source_layers':return load_traffic(path,selected,store,root=root)
    return {**load_terminals(path,selected,store),'date':selected,'store_key':store}
   try:r=load()
   except (OSError,ValueError,KeyError,TypeError) as error:
    if client is None or fetch_blocked:errors.append({'date':selected,'error':str(error)});continue
    try:
     if key=='source_layers':captured=traffic_tree.collect(selected,store,client=client,root=root)
     else:captured=traffic_channels.collect(selected,store,client=client)
     if captured.get('errors'):
      raise ValueError('; '.join(e.get('error',str(e)) if isinstance(e,dict) else str(e) for e in captured['errors']))
     r=load()
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as failure:
     errors.append({'date':selected,'error':str(failure)})
     fetch_blocked=True;continue
   loaded.append(r)
  if errors:
   output[key]={'status':'partial' if loaded else 'missing','period':'seven_vs_seven' if weekly else 'day',
    'loaded_dates':[r['date'] for r in loaded],'errors':errors,'limitation':'日期窗不完整，不使用已取回的部分日期代替整窗比较。',
    'next_calls':[{'platform':'jd','store':store,'command':command,'args':['--date',e['date']]} for e in errors]}
  else:output[key]=source_layers(loaded,day,store) if key=='source_layers' else terminal_comparison(loaded,day,store,weekly=weekly)
 return output

def markdown(sections):
 lines=['','## APP四层与六终端比较']
 for key,title in [('source_layers','APP来源各层变化'),('terminal_comparison','六终端前后期比较')]:
  r=sections.get(key,{})
  if not r:continue
  lines+=['','### '+title,r.get('limitation','')]
  if r.get('errors'):lines+=['- '+e['date']+'：'+e['error'] for e in r['errors']];continue
  if key=='source_layers':
   for level in r['levels']:
    lines+=['','第'+str(level['level'])+'层：'+str(level['ranked_records'])+'条金额可比；未比较'+str(len(level['unranked_ids']))+'条。']
    for label,direction in [('下降','decliners'),('上升','gainers')]:
     for row in level[direction][:3]:lines.append(f"- {label}：{row['name']}（{row['id']}），变化{row['delta']:+,.2f}元。")
  else:
   lines+=['','| 终端 | 本期金额 | 前期金额 | 本期日均店铺访客 | 本期近似成交转化率 |','|---|---:|---:|---:|---:|']
   for c in r['channels']:
    m=c['metrics'];lines.append('| '+' | '.join([c['name'],formatted(m['成交金额']['value'],'元'),formatted(m['成交金额']['previous'],'元'),formatted(m['日均店铺访客数']['value'],'人'),formatted(m['按日汇总近似成交转化率']['value'],'%')])+' |')
 return '\n'.join(lines)+'\n'
