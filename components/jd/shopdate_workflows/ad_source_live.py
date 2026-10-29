"""Platform adapter: only existing allowlisted report and category read APIs."""
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


class Provider:
    attribution_mode='historical'
    plan_order='campaignId'
    def __init__(self):
        root=(ROOT.parent/'ali').resolve()
        loaded=sys.modules.get('tb')
        if loaded is not None and Path(loaded.__file__).resolve().parent.parent!=root.resolve():raise ValueError('广告取数需独立阿里进程。')
        sys.path.insert(0,str(root));os.environ['PYTHONPATH']=str(root)
        from tb.core import transport
        from tb.platforms.alimama import cli as ali
        from tb.platforms.sycm import cli as sycm
        self.transport=transport;self.ali=ali;self.sycm=sycm;self.active=None
        self.requests=0

    def switch(self,name):
        if self.active==name:return
        self.close();self.active=name

    def close(self):
        for module in (self.ali,self.sycm):
            if module._CLIENT is not None:
                self.transport.release(module._CLIENT);module._CLIENT=None
        self.active=None

    def identity(self):
        from .source import current_symc
        module=self.ali if self.active=='alimama' else self.sycm
        server=getattr(module._CLIENT,'_bridge_server',None) if module._CLIENT is not None else None
        return current_symc(server)

    def _report(self,body,biz='universalBP'):
        self.requests+=1
        return self.ali._api_call('/report/query.json'+('?bizCode='+biz if biz!='universalBP' else ''),
            body,method='POST',cookies=self.ali.load_alimama_cookies())

    def scene(self,key,day):
        biz=self.ali.PROMO_BIZ_CODES[key][0]
        return self._report({'bizCode':biz,'byPage':False,'fromRealTime':False,
            'startTime':day,'endTime':day,'splitType':'sum','computeType':'sum','effectEqual':15,
            'sourceList':['scene','adgroup_list'],'queryDomains':[],
            'queryFieldIn':['charge','click','adPv','alipayInshopAmt','alipayInshopNum']},biz)

    def page(self,kind,day,offset):
        return self._report({'bizCode':'universalBP','fromRealTime':False,'source':'baseReport','from':'pcBaseReport',
            'byPage':True,'byPageWithoutCount':False,'totalTag':True,'needCountAccelerate':True,
            'rptType':'item_promotion' if kind=='item' else 'campaign',
            'queryDomains':['promotion' if kind=='item' else 'campaign'],
            'queryFieldIn':list(self.ali.REPORT_METRICS),'startTime':day,'endTime':day,'splitType':'day',
            'effectEqual':15,'havingList':[],'pageSize':100,'pageNo':offset//100+1,'offset':offset,
            'orderField':self.plan_order if kind=='plan' else 'charge','orderBy':'desc','unifyType':'zhai'})

    def sales(self,day):
        cookies=self.sycm.load_taobao_cookies();self.requests+=2
        return {'overview':self.sycm.fetch_home_table(day,day,cookies=cookies),
            'categories':self.sycm.fetch_preset('cate-list',start_date=day,end_date=day,page_size=100,cookies=cookies)}

    def price(self,item_id):
        from tb.platforms.sycm.item import _fetch_price
        self.requests+=1
        return _fetch_price('/cc/item/price/info.json',item_id=item_id,cookies=self.sycm.load_taobao_cookies())
