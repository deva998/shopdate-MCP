"""User-confirmed acquisition scope; exclusions are not missing data."""


def policy():
    return {
        'confirmed_on':'2026-10-25',
        'non_app_sources':{'status':'out_of_scope','reason':'用户确认官方未提供非APP来源明细，不接入、不列为缺口；APP来源明细与六终端概况分别保留。'},
        'inventory':{'mode':'current_sku','historical_required':False,'reason':'商品分析读取现有京东SKU库存及颜色尺码，标明采集时间；不要求历史库存，不把当前总库存冒充可售库存。'},
        'orders':{'mode':'on_demand','automatic_full_fetch':False,
                  'full_day_acceptance':['店铺与指定下单日一致','官方总数稳定','至少完整读取至末页','唯一订单编号数=官方总数','missing_orders=0'],
                  'reason':'需要订单级或全日订单分析时才发起order-list --all-pages；日检周报只复核已有证据。'},
        'advertising':{'status':'deferred','reason':'用户暂缓京东广告花费及归因接入，不作为当前范围待补接口。'},
        'customer_service':{'status':'deferred','reason':'用户暂缓客服数据接入，不读取会话正文。'},
    }


def interfaces():
    return [
        {'domain':'marketing-market-extensions','status':'partial_verified','commands':['business-modules','business-analysis'],
         'scope':'本批149个固定只读查询已登记并通过真实响应、身份、原文与结构校验，证据覆盖2026-10-26至2026-10-28（各报告按实际日期记录）。0.9.37新增20项已验：竞争概况列表/趋势/流失/商品榜10项，品牌卡分组、评价有礼活动表和搭售商品10项。礼金当前列表32页314条已核验；搭售商品达到1000行上限，不称全量。竞品画像受官方小人群门槛抑制，流失下钻仅验空结构，缺失指标不补零。六组模块仍为部分覆盖，未宣称全部子选项和筛选完成。',
         'remaining_gaps':['评价有礼活动商品弹窗暂无有效活动样本；部分促销活动下钻、其他筛选和更深流量来源尚未完成；搭售1000行及其他列表容量不等于全量；竞品非空画像/流失结构待有效样本；数字人页面仅见介绍；个人卡号/交易流水不属聚合统计范围。']},
        {'domain':'product-category-analysis','status':'partial','commands':['category-analysis','category-trend'],
         'scope':'本店行业/店铺类目离线单日汇总、嵌套子类目及两类趋势已在线核验；趋势实际范围按TIME披露。',
         'remaining_gaps':['今日实时类目未接入。']},
        {'domain':'users','status':'partial_implementation','commands':['user-modules','user-overview','user-detail','user-analysis'],
         'scope':'用户概况、访客分析、用户洞察、新老客与Plus概况及未购/关注/品牌会员特征的默认只读统计已通过真实MCP核验；真实趋势窗口与当前快照分开披露。',
         'remaining_gaps':['15个用户子模块有在线证据；综合权益SKU单日1441组、周/自定义8578组、9月12269组已全量并有末页证据，周亲密度四档及会员细分跨周期已核验。剩余非默认筛选未穷举，会员行业本店排名不等于全店行业榜Top10。购物车依用户指令暂标no_data，不重试。详见user-modules和验收清单。']},
        {'domain':'industry','status':'implemented','coverage':'official_disclosure_limited','commands':['industry-options','industry-overview','industry-products','industry-shops'],
         'scope':'官方筛选选项、历史单日大盘、热销商品及店铺榜；按类目、POP/全部及终端查询，保留区间值。',
         'remaining_gaps':['自动参数封装仅核验单日热销；返回榜单不代表全行业全部商品，不能把区间中点作为精确成交。']},
        {'domain':'overview','status':'implemented','commands':['shop-overview','shop-realtime'],'scope':'官方交易概况；历史完整日与今日快照分开。'},
        {'domain':'products','status':'implemented','commands':['product-full','product-items'],'scope':'官方有数据SKU/SPU导出；product-items仍限1000条，完整取数用product-full；官方空指标保留。'},
        {'domain':'new-products','status':'implemented','coverage':'partial_metadata','commands':['new-products-sku','new-products-spu'],'scope':'官方ABC打标队列已接入。','remaining_gaps':['首次上架日期、收藏字段尚无已核验取数来源，不等于官方必然提供。']},
        {'domain':'app-traffic','status':'implemented','commands':['traffic-tree','traffic-sources'],'scope':'APP四层来源有数据分支及分页；字典、日期、空值逐项核验。'},
        {'domain':'terminal-overview','status':'implemented','coverage':'daily_only','commands':['traffic-channels'],'scope':'六终端单日概况已接入。','remaining_gaps':['周区间去重访客/成交客户原生区间来源未核验，不能跨日相加代替。']},
        {'domain':'orders','status':'implemented','coverage':'partial_fields','commands':['order-list','order-review'],'scope':'按需全日分页与唯一编号覆盖已实现。','remaining_gaps':['买家实付、完整父兄弟单关系及拆单金额口径未齐；下单日全量不等于付款日队列完整。']},
        {'domain':'current-sku-inventory','status':'implemented','commands':['inventory-sku','product-diagnosis'],'scope':'当前SKU库存与官方颜色尺码关联；限指定商品或所选候选，缺失数量不补零。'},
        {'domain':'after-sales','status':'implemented','coverage':'partial_cohort','commands':['after-sales-list','refund-review','refund-enrich','refund-cohort'],'scope':'退款事件、服务单、原因及已核验导出可读取。','remaining_gaps':['完整付款批次分母、全部父兄弟单、部分退款金额及逐单关系仍需核验。']},
        {'domain':'product-reviews','status':'not_implemented','commands':[],'scope':'商品评价，不是客服会话。','remaining_gaps':['当前未登记独立商品评价取数入口。']},
        {'domain':'non-app-traffic',**policy()['non_app_sources'],'commands':[]},
        {'domain':'advertising',**policy()['advertising'],'commands':[]},
        {'domain':'customer-service',**policy()['customer_service'],'commands':[]},
    ]
