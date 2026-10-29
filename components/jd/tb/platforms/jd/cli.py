import argparse
import hashlib
import json
import sys
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ...core.bridge import BridgeServer
from ...core.stores import discover,choose_store,verify_identity
from .platform import JD
from . import overview,reports

ROOT=Path(__file__).resolve().parents[3]
TOPICS=['标准全景报表','日体检','周复盘','测款专项','退货归因','广告 ROI','客服质检']


def capabilities():
    from .data_scope import policy,interfaces
    missing={
      '标准全景报表':['指定日期的已登记数据域若缺原始证据需按next_call补采；商品缺失指标和可比覆盖逐项保留，不以采集命令已实现冒充每日报表已齐'],
      '日体检':['同口径净成交定义、完整售后与付款队列、商品评价尚未齐；订单明细按需读取，未抓全日不等于接口未接入'],
      '周复盘':['原生区间去重UV/成交客户数、完整售后与付款队列、净成交口径及商品评价仍有缺口'],
      '测款专项':['product-test已实现官方打标SPU固定队列七日同窗、相对四分位及四类判定；仍缺首次上架年龄与收藏；分指标判定，金额缺失不阻断转化分析，缺失指标不补零'],
      '退货归因':['refund-review核验退款事件趋势及申请日原因；refund-cohort可重放已核验官方范围导出，区分31日服务申请覆盖与付款分母。完整付款队列、父/兄弟单及部分退款金额仍需核验；观察窗完整不等于真实退货率可算，业务状态仍partial'],
      '广告 ROI':[],
      '客服质检':[]}
    return {'platform':'jd','commands':['doctor','accounts','panorama','refund-review','refund-cohort','refund-enrich','after-sales-list','order-list','order-review','product-diagnosis','inventory-sku','shop-overview','shop-realtime','daily-check','weekly-review','product-items','product-full','traffic-sources','traffic-tree','traffic-channels','new-products-sku','new-products-spu','new-products-review','product-test','product-compare-files','capabilities','category-analysis','category-trend','user-overview','user-detail','user-modules','user-analysis','business-modules','business-analysis'],
      'additional_reports':'product-full默认登记接口导出下载并核对概况。daily-check整合两日SPU与APP来源，严格校验后可复用文件；weekly-review整合14日SPU、概况和APP来源，默认立即返回任务编号，按返回的next_call查询，不重复启动。product-items仍限1000条；官方有数据商品不等于所有在架商品，空值不补0。',
      'modules':[{'topic':t,'status':'partial' if i<5 else 'deferred','missing_sources':missing[t],**({'reason':'用户暂缓接入，不作为当前范围缺口'} if i>=5 else {})} for i,t in enumerate(TOPICS)],
      'data_scope':policy(),'data_interfaces':interfaces(),
      'transport':'registered-api (native fallback explicit)','transport_acceptance':'overview_spu_exports_named_partial_app_daily_and_weekly_verified','account_switching':'MCP仅选择当前已登录店铺；0.8.4扩展弹窗已实现本机账号存档/添加/切换，真实浏览器切换尚待验收'}


def capture(request, operation, expected=None,report_key='overview',bridge=None):
    owns_bridge=bridge is None
    if owns_bridge:bridge=BridgeServer(JD)
    issued=datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    yesterday=(datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat()
    contract=reports.contracts()[report_key]
    job={'url':contract['endpoint'],'launch':contract['page'],'report_key':report_key,
      'method':'POST','body':json.dumps(request,ensure_ascii=False),'operation':operation}
    if expected:job['expected_store']=expected
    if operation!='identify':
        job.update(requested_after=issued,capture_timeout_ms=120000,
          transport='background-native',auto_query=True,is_yesterday=request['startDate']==yesterday)
    start=time.perf_counter()
    started=False
    try:
        if owns_bridge:
            bridge.start()
            started=True
        result=bridge.submit(job,150 if operation!='identify' else 20)
    finally:
        if owns_bridge:
            if started:bridge.stop()
            else:bridge.server_close()
    if result.get('error'):raise ValueError(result['error'])
    identity=result.get('identity')
    if not isinstance(identity,dict) or not identity.get('store_key'):raise ValueError('响应缺少实际店铺身份，停止。')
    if expected:verify_identity(expected,identity)
    if operation!='identify':
        if result.get('status')!=200:raise ValueError(f"HTTP {result.get('status')}，未生成报告。")
        try:timestamp=datetime.fromisoformat(result['request_timestamp'].replace('Z','+00:00'))
        except (KeyError,TypeError,ValueError):raise ValueError('缺少有效的新请求时间。') from None
        if timestamp<datetime.fromisoformat(issued):raise ValueError('拒绝把旧响应作为新取数。')
        if (timestamp-datetime.fromisoformat(issued)).total_seconds()>150:raise ValueError('任务已过期，可能经历睡眠或暂停；请重新发起取数，不保存迟到结果。')
        if result.get('source')!='native-page-response' or result.get('transport')!='background-native':raise ValueError('响应来源或取数通道与后台任务不符。')
        try:verified=datetime.fromisoformat(result['identity_verified_at'].replace('Z','+00:00'))
        except (KeyError,TypeError,ValueError):raise ValueError('缺少身份核验时间，停止。') from None
        if verified<datetime.fromisoformat(issued) or timestamp<verified:raise ValueError('响应早于本次店铺身份核验，停止。')
    result['timings']={'capture_ms':round((time.perf_counter()-start)*1000),'browser_capture_ms':result.get('capture_ms')}
    result['requested_after']=issued
    return result


def save_overview(result,request):
    identity=result['identity'];day=request['startDate']
    report=overview.summarize(json.loads(result['text']),request,result['source'],result['request_timestamp'])
    report.update(platform='jd',store=identity,shop=identity['name'],timings=result['timings'],requested_after=result['requested_after'],
      transport=result.get('transport'),identity_verified_at=result.get('identity_verified_at'),query_actions=result.get('query_actions',[]),bridge_client_version=result.get('bridge_client_version'))
    folder=ROOT/'data'/'jd'/identity['store_key'].replace(':','_')/day
    folder.mkdir(parents=True,exist_ok=True)
    raw=result['text'].encode('utf-8')
    report['response_sha256']=hashlib.sha256(raw).hexdigest()
    report['report_path']=str(folder/'report.json')
    (folder/'response.json').write_bytes(raw)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'report.md').write_text(overview.markdown(report),encoding='utf-8')
    compact={'status':report['data_status'],**overview.data_quality(report['metrics']),'identity':identity,'report_path':report['report_path'],'date':day,
      'compare_date':request['compareStartDate'],'timings':result['timings'],'metrics':report['metrics'],'missing_metrics':report['missing_metrics']}
    return report,compact


def main(argv):
    if argv and argv[0] in ('business-modules','business-analysis'):
        from .business_stats import main as business_main
        return business_main(argv)
    if argv and argv[0] in ('category-analysis','category-trend','user-overview','user-detail','user-modules','user-analysis'):
        from .shop_insights import main as insights_main
        return insights_main(argv)
    if argv and argv[0] in ('industry-options','industry-overview','industry-products','industry-shops'):
        from .industry import main as industry_main
        return industry_main(argv)
    help_details={
      'refund-cohort':'--date为付款日。重放完整付款分母、31个申请日分区和父子单缺口；--service-export-evidence可显式导入已核对官方任务、店铺、范围、列表总数和文件哈希的本机售后导出。后续重放约秒级，无需重载插件。不自动抓取或解密；观察窗完整仍不等于付款分母完整，缺证据不计算退货率。',
      'refund-enrich':'对本店本日已验收完整售后单关联原订单，先重放已保存订单和已成功查询批次，仅按缺口每批最多50个订单编号补查。返回后台任务及next_call；--job-id查状态。付款后30天按实际时刻分成熟/未成熟，仍缺完整付款日分母与整个观察窗售后，不计算真实退货率。需数据桥0.9.15，补存官方parentId并跟进已知父单；旧投影缺关系需补查，无新增权限。',
      'order-review':'只重放指定日已保存订单证据，不自动抓全日；分开显示编号完整性、金额缺失、父拆单和时间口径。',
      'product-diagnosis':'--product-id指定商品；后台精确关联官方SKU销售、颜色尺码和15分钟内当前总库存。不归因历史缺货，不聚合组转化率。',
      'refund-review':'复核指定日止十四日已保存概况原文、同店身份和相邻日期口径，返回七日对前七日退款事件趋势和官方阶段拆分；另重放该申请日已保存全量服务单证据并单列原因、商品关联和状态快照。不自动补新数据，不把一个申请日当七日退款事件归因，不计算真实成交队列退货率。',
      'after-sales-list':'按申请日及全部状态顺序读取；单页10条，--all-pages用官方100条/页返回后台任务，--job-id查询已有任务。只保留服务单、商品、原因、金额、状态及时间，排除买家信息。整日完整性看whole_day_complete、官方总数和唯一服务单数；归因仍受原付款队列及观察期缺失限制。需数据桥0.9.13；2026-10-23实测18页1782张，缺失0、重复0、原因覆盖1782张。',
      'inventory-sku':'指定--product-id和--store，--date为商品归属的已核验导出日期（默认昨天）。读取当前SKU总库存快照，仅skuStatusList=[4]；不是历史/可售库存。需统一数据桥0.9.6；使用独立后台临时页，准备超时限次恢复，不需手动切前台；长期恢复以实际验收记录为准。日检、周报自动补取本次最多10件所选商品；测款纳入最多60件候选，均逐件核验15分钟时效，过期保留缺口。自动补取所选商品的缺失/过期/不完整快照，失败停止并保留partial；候选总数和未选择数另列，不冒充全店库存。',
      'order-list':'订单级分析按需抓取全量；日检周报不隐式启动。近180日内历史下单日，--date指定日期，--page从1顺序读取（50条/页）。--all-pages立即返回后台任务编号，按next_call查询结果；无需重复启动。需数据桥0.9.5；固定使用官方50条分页，请求起始间隔至少2秒。遇605安全验证立即停止，不自动重试。原生页面取数期间保持订单页前台、电脑不休眠；后台页面暂停可能执行超时。0.9.5整日唯一订单覆盖已实测。全量先完整遍历，再按订单编号合并，缺单自动补读；官方总数每页必须一致，唯一编号数等于官方总数且至少一轮到末页才complete=true。最多三轮、30分钟，仍缺单则partial，返回missing_orders/collection_stop；任务结束不等于数据完整。只含订单业务字段，商家应收不等于买家实付，含父/拆单记录；状态为采集期间快照。部分覆盖不可计算全日付款/取消率。',
      'shop-realtime':'北京时间今天00:00至任务发起时的实时交易概况；须指定--store。当前值单独保存，不覆盖历史日报；data_as_of未知时不把请求时间冒充平台更新时间，不与昨日全天比较。',
      'panorama':'指定店铺和日期的已保存证据全景核查：概况、SPU、APP四层来源、六终端概况及新品SKU/SPU。逐域返回成功、部分指标、空表、缺失、无效、未接入和补数命令；只重新验证现存原文，不触发新采集，不借用其他日期。',
      'new-products-sku':'官方打标新品SKU全量取数；指定--date及--store。默认返回后台任务编号，按next_call查询；不以首次出现代替上架日期。',
      'new-products-spu':'官方打标新品SPU全量取数；保留ABC标签分组，并另报唯一商品数。默认后台取数。',
      'new-products-review':'读取并重新验证当日及前一日已保存新品SKU分页证据，输出集合变化、同标签商品金额涨跌及中文报告；缺少日期数据则报错。',
      'product-test':'固定目标日官方打标SPU队列；默认返回后台任务及next_call，按同一任务查询，不重复启动。默认七日测款，--weeks 2完成前后两周同队列对照；任务绑定周数。复用源文件哈希和解析代码均未变化的Excel解析缓存，自动补齐最多10件所选候选当前库存并明确未选择数量。缺数据先取new-products-spu及product-full。不是同上架年龄队列；按可用指标分别判定，以商品名称、货号与SPU定位；候选不等于直接放量，整体仍partial。',
      'traffic-channels':'按官方六种终端读取单日流量概况；不是非APP来源明细。严格保留空值，全部不从终端求和。',
      'traffic-tree':'APP末次场域来源四层有数据分支完整分页，按官方字典命名；非APP来源不在接入范围，不列为缺口。默认返回后台任务编号。'}
    selected=argv[0] if argv else ''
    ap=argparse.ArgumentParser(prog='tb jd',epilog=help_details.get(selected,'新品：new-products-sku/spu取数；new-products-review两日对照；product-test七日同窗测款。来源：traffic-tree仅APP。'))
    ap.add_argument('command',choices=['doctor','accounts','panorama','refund-review','refund-cohort','refund-enrich','after-sales-list','order-list','order-review','product-diagnosis','inventory-sku','shop-overview','shop-realtime','daily-check','weekly-review','product-items','product-full','traffic-sources','traffic-tree','traffic-channels','new-products-sku','new-products-spu','new-products-review','product-test','product-compare-files','capabilities','industry-options','industry-overview','industry-products','industry-shops','category-analysis','category-trend','user-overview','user-detail','user-modules','user-analysis','business-modules','business-analysis'])
    ap.add_argument('--date')
    ap.add_argument('--page',type=int,default=1,help='order-list每页50条、after-sales-list每页10条；必须顺序读取，不把单页当整日全量')
    ap.add_argument('--all-pages',action='store_true',help='order-list或after-sales-list：后台核验整日分页，返回任务编号，不阻塞MCP等待')
    ap.add_argument('--product-id',help='inventory-sku/product-diagnosis：指定已核验店铺导出中的商品编码；date为归属证据日期，库存始终为当前快照')
    ap.add_argument('--weeks',type=int,choices=[1,2],default=1,help='仅product-test：1为七日测款，2为固定新品队列两周对照')
    ap.add_argument('--store',default='')
    ap.add_argument('--dimension',choices=['sku','spu'],default='sku')
    ap.add_argument('--source-level',choices=['1','2'],default='2')
    ap.add_argument('--current-file')
    ap.add_argument('--previous-file')
    ap.add_argument('--service-export-evidence',help='仅refund-cohort：显式导入已核对官方任务/店铺/范围/列表总数/文件哈希的售后导出凭据；不补付款分母')
    ap.add_argument('--downloads-dir')
    ap.add_argument('--background',action='store_true',help='长任务立即返回本机任务编号，避免超过MCP客户端等待上限')
    ap.add_argument('--job-id',help='只查询已有后台任务，不重新取数')
    ap.add_argument('--foreground',action='store_true',help='仅终端诊断：同步等待长任务；MCP默认返回后台任务编号')
    ap.add_argument('--transport',choices=['native','api'],default='api',help='概况、流量、完整商品及经营分析默认登记接口；native为旧页面诊断流程')
    args=ap.parse_args(argv)
    if args.service_export_evidence and args.command!='refund-cohort':raise ValueError('--service-export-evidence仅支持refund-cohort')
    if args.all_pages and (args.command not in ('order-list','after-sales-list') or args.page!=1):raise ValueError('--all-pages仅支持order-list或after-sales-list并从第1页开始')
    if args.page!=1 and args.command not in ('order-list','after-sales-list'):raise ValueError('--page仅支持order-list或after-sales-list')
    if args.product_id and args.command not in ('inventory-sku','product-diagnosis'):raise ValueError('--product-id仅支持inventory-sku或product-diagnosis')
    if args.command=='product-diagnosis' and not args.product_id:raise ValueError('SKU诊断必须指定--product-id')
    if args.weeks!=1 and args.command!='product-test':raise ValueError('--weeks仅支持product-test')
    if args.command=='capabilities':print(json.dumps(capabilities(),ensure_ascii=False,indent=2));return 0
    if args.command=='accounts':print(json.dumps({'stores':discover('jd')},ensure_ascii=False,indent=2));return 0
    if args.command=='doctor':
        identities=discover('jd');identity=choose_store(identities,'jd',args.store)
        print(json.dumps({'connected':True,'identity':identity,'probe':'identity_ok','data_probe':'not_run',
          'note':'已识别当前登录页面身份；无需交易概况页或F12。不代表所有数据接口或七个工作流已通过验收。',
          'bridge_timings':getattr(identities,'bridge_timings',None),'discovery':getattr(identities,'discovery',None),'capabilities':capabilities()},ensure_ascii=False,indent=2));return 0
    yesterday=(datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat()
    if args.command=='shop-realtime':
        from .realtime import collect,now_china
        if args.date and args.date!=now_china().date().isoformat():raise ValueError('实时概况只支持北京时间今天')
        if args.transport!='api' or args.background or args.job_id or args.foreground:raise ValueError('实时概况只支持登记接口即时查询')
        print(json.dumps(collect(args.store),ensure_ascii=False,allow_nan=False));return 0
    day=args.date or yesterday
    if day>yesterday:raise ValueError('只支持昨天或更早的完整日。')
    if args.foreground and (args.command not in ('daily-check','weekly-review','traffic-tree','new-products-sku','new-products-spu','order-list','after-sales-list','refund-enrich','product-diagnosis','product-test') or args.background or args.job_id):raise ValueError('同步报告不能与后台或任务状态选项并用')
    if args.background or args.job_id or (args.all_pages and not args.foreground) or (args.command in ('daily-check','weekly-review','traffic-tree','new-products-sku','new-products-spu','refund-enrich','product-diagnosis','product-test') and args.transport=='api' and not args.foreground):
        if args.command not in ('daily-check','weekly-review','traffic-tree','new-products-sku','new-products-spu','order-list','after-sales-list','refund-enrich','product-diagnosis','product-test') or args.transport!='api' or (args.background and args.job_id) or (args.command in ('order-list','after-sales-list') and args.page!=1):raise ValueError('后台/任务状态只支持登记报告；全量列表从第1页开始，后台与任务编号不能并用')
        from .report_jobs import start,status
        kwargs={} if args.command=='weekly-review' else {'command':args.command}
        if args.command=='product-diagnosis':kwargs['product_id']=args.product_id
        if args.command=='product-test':kwargs['weeks']=args.weeks
        output=status(args.job_id,day,args.store,**kwargs) if args.job_id else start(day,args.store,**kwargs)
        print(json.dumps(output,ensure_ascii=False,separators=(',',':'),allow_nan=False));return 0
    if args.command=='order-review':
        from .order_review import collect
        print(json.dumps(collect(day,args.store,args.current_file),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='refund-review':
        from .refund_review import collect
        print(json.dumps(collect(day,args.store),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='refund-cohort':
        from .refund_cohort import collect
        extra={'export_evidence':args.service_export_evidence} if args.service_export_evidence else {}
        print(json.dumps(collect(day,args.store,**extra),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='refund-enrich':
        from .refund_enrichment import collect
        print(json.dumps(collect(day,args.store),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='after-sales-list':
        from .after_sales import collect,collect_all
        print(json.dumps(collect_all(day,args.store) if args.all_pages else collect(day,args.store,args.page),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='product-diagnosis':
        from .product_diagnosis import collect
        print(json.dumps(collect(day,args.store,args.product_id),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='order-list':
        from .orders import collect
        if args.transport!='api':raise ValueError('订单仅支持登记的原生SDK只读接口')
        print(json.dumps(collect(day,args.store,args.page,all_pages=args.all_pages),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='inventory-sku':
        from .inventory import collect
        if not args.product_id:raise ValueError('库存查询必须指定--product-id')
        print(json.dumps(collect(args.product_id,args.store,day),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='panorama':
        from .panorama import collect
        print(json.dumps(collect(day,args.store),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='product-test':
        from .product_test import collect
        print(json.dumps(collect(day,args.store,weeks=args.weeks),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='new-products-review':
        from .new_product_review import collect
        print(json.dumps(collect(day,args.store,args.current_file,args.previous_file),ensure_ascii=False,allow_nan=False));return 0
    if args.command.startswith('new-products-'):
        if args.transport!='api':raise ValueError('新品只支持登记接口')
        from .new_products import collect
        print(json.dumps(collect(day,args.store,args.command.rsplit('-',1)[1]),ensure_ascii=False,allow_nan=False));return 0
    if args.command=='traffic-channels':
        if args.transport!='api':raise ValueError('终端概况只支持登记接口')
        from .traffic_channels import collect
        print(json.dumps(collect(day,args.store),ensure_ascii=False,separators=(',',':'),allow_nan=False));return 0
    if args.command=='traffic-tree':
        if args.transport!='api':raise ValueError('来源树只支持登记接口')
        from .traffic_tree import collect
        print(json.dumps(collect(day,args.store),ensure_ascii=False,separators=(',',':'),allow_nan=False));return 0
    if args.command=='product-full':
        if args.transport=='api':
            from .api_products import collect
            result=collect(day,args.store,args.dimension)
        else:
            from .product_downloads import collect
            result=collect(day,args.store,args.dimension,args.downloads_dir)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return 0
    if args.command in ('daily-check','weekly-review'):
        if args.command=='daily-check':from .daily import collect
        else:from .weekly import collect
        if not args.store.startswith('jd:mall:') or not args.store.removeprefix('jd:mall:').isdigit():raise ValueError('经营分析必须指定精确店铺编号')
        from .business_structure import tool_summary
        print(json.dumps(tool_summary(collect(day,args.store,transport=args.transport)),ensure_ascii=False,separators=(',',':'),allow_nan=False));return 0
    if args.command=='traffic-sources' and args.transport=='api':
        from .api_traffic import collect
        print(json.dumps(collect(day,args.store,args.source_level),ensure_ascii=False,indent=2,allow_nan=False));return 0
    if args.command=='product-compare-files':
        from .product_exports import save_comparison
        if not args.store.startswith('jd:mall:') or not args.store.removeprefix('jd:mall:').isdigit():raise ValueError('本地导出核验必须指定精确店铺编号')
        if not args.current_file or not args.previous_file:raise ValueError('必须提供两天官方不含对比的导出文件')
        control=ROOT/'data/jd'/args.store.replace(':','_')/day/'report.json'
        print(json.dumps(save_comparison(args.current_file,args.previous_file,control,day,args.dimension,args.store),ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    report_key='products-'+args.dimension if args.command=='product-items' else 'traffic-level'+args.source_level if args.command=='traffic-sources' else 'overview'
    template=reports.contracts()[report_key]['template']
    request=overview.make_request(template,day)
    expected=None
    if args.store.startswith('jd:mall:'):
        if not args.store[len('jd:mall:'):].isdigit():raise ValueError('无效的店铺标识。')
        expected={'platform':'jd','store_key':args.store}
    elif args.store:
        expected=choose_store(discover('jd'),'jd',args.store)
    elif args.command!='doctor':
        raise ValueError('取数必须指定 --store；先运行 stores list --platform jd。')
    if report_key!='overview':
        print(f"目标报表：{reports.contracts()[report_key]['page']}；统一后台将恢复 {day} 的查询条件并校验原生新响应，无需F12。",file=sys.stderr,flush=True)
    if report_key=='overview' and args.transport=='api':
        from .api_client import capture_api
        result=capture_api('overview',day,expected['store_key'])
    else:result=capture(request,'identify' if args.command=='doctor' else 'overview',expected,report_key)
    identity=result['identity']
    if args.command=='doctor':
        print(json.dumps({'connected':True,'identity':identity,'note':'身份连通通过；不代表所有报表及七个模块都可用。','capabilities':capabilities()},ensure_ascii=False,indent=2));return 0
    if report_key!='overview':
        if report_key.startswith('traffic-') and not (result.get('source_dictionary') or {}).get('text'):
            from .api_client import attach_source_dictionary
            try:result=attach_source_dictionary(result,day)
            except (ValueError,RuntimeError) as error:
                result['source_dictionary']={'capture_status':'registered_api_unavailable','error':str(error)}
                print('来源字典未获取，指标保留、名称保持未知：'+str(error),file=sys.stderr,flush=True)
        print(json.dumps(reports.save(result,request,report_key),ensure_ascii=False,indent=2,allow_nan=False));return 0
    _,compact=save_overview(result,request)
    print(json.dumps(compact,ensure_ascii=False,indent=2))
    return 0


