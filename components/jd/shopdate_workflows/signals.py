"""Observed movements and suggested reads; never business causes or actions."""
from .metrics import numeric


def build_signals(report):
    platform=report['platform'];metrics=report.get('metrics',[])
    amount='payAmt' if platform=='symc' else 'jdr_sch_trade_deal_ord_ord_amt_sz_trade_deal_snapshot'
    targets=[m for m in metrics if m['field']==amount]
    targets += [m for m in metrics if m['field'] in ('rfdSucAmt','fo_jdr_sch_trade_cancel_refund_ord_amt') and (numeric(m.get('relative_change')) or 0)>0]
    signals=[];requests=[]
    for metric in targets:
        value,previous,change=(numeric(metric.get(k)) for k in ('value','previous','relative_change'))
        if value is None or previous is None or change in (None,0):continue
        signals.append({'field':metric['field'],'direction':'上升' if change>0 else '下降',
            'observation':metric['name']+'与上一可比窗口存在变化，仅为观测，不证明原因。',
            'evidence':{'value':value,'previous':previous,'relative_change':change},
            'threshold':'无预设显著性阈值；是否异常由助手结合业务判断'})
        refund=metric['field']!=amount
        commands=(['refund-item-list','refund-all-list'] if refund else ['item-list','item-flow-source']) if platform=='symc' else (['refund-review','refund-cohort'] if refund else ['product-full','traffic-tree'])
        requests.append({'purpose':'核查退款事件及付款队列，避免同期分母混用' if refund else '查商品与来源变化集中位置',
            'platform':platform,'date':report['date'],'store_key':report['store_key'],
            'commands':commands,'execution':'assistant_on_demand',
            'instructions':'先查看commands参数；需要商品或付款队列范围时再选择，不自动全量取数。',
            'trigger_field':metric['field']})
    return signals,requests
