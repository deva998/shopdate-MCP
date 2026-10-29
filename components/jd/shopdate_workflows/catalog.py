"""Scope catalog: implementation is separate from per-run data completeness."""


def catalog(platform):
    if platform not in ('jd','symc'):raise ValueError('平台必须为jd或symc。')
    native={
      'products':['product-full','product-diagnosis','product-test'] if platform=='jd' else ['item-360','item-detail','item-list'],
      'inventory':['inventory-sku','product-diagnosis'] if platform=='jd' else ['item-sku-list --live'],
      'refunds':['refund-review','refund-cohort','order-list'] if platform=='jd' else ['refund-all-list','refund-item-list','refund-origin-analysis'],
      'sources':['traffic-tree','traffic-channels'] if platform=='jd' else ['item-flow-source'],
      'customer_service':[] if platform=='jd' else ['sale-cs-list','reception-list','inquiry-loss-list']}
    rows=[{'id':task,'scope':'in_scope','implementation':'shared_workflow',
        'verification':'see_acceptance_receipts','commands':['workflow '+task],
        'data_coverage':'checked_per_run_not_implied_by_implementation'} for task in ('daily','weekly')]
    if platform=='jd':
        rows.extend([
            {'id':'product_category_analysis','scope':'in_scope','implementation':'registered_native_queries',
             'verification':'live_industry_and_shop_summary_and_trends_verified;realtime_not_integrated','commands':['category-analysis','category-trend']},
            {'id':'users','scope':'in_scope','implementation':'partial_registered_native_queries',
             'verification':'overview_visitors_insight_newold_plus_pots_fans_member_features_default_reads_live_verified;remaining_see_user_modules',
             'commands':['user-modules','user-overview','user-detail','user-analysis'],'execution':'assistant_on_demand'}])
    for key,commands in native.items():
        rows.append({'id':key,'scope':'deferred' if key=='customer_service' and platform=='jd' else 'in_scope',
            'implementation':'existing_native_script' if commands else 'not_integrated',
            'verification':'native_command_and_date_specific_evidence_required',
            'commands':commands,'semantics':'current_sku_only' if key=='inventory' else 'platform_native',
            'execution':'assistant_on_demand'})
    rows.append({'id':'advertising','scope':'deferred' if platform=='jd' else 'in_scope',
        'implementation':'not_integrated' if platform=='jd' else 'shared_workflow',
        'verification':'not_applicable' if platform=='jd' else 'fresh_replay_resume_receipts_required',
        'commands':[] if platform=='jd' else ['workflow ad-review']})
    if platform=='jd':rows.append({'id':'non_app_sources','scope':'out_of_scope','implementation':'not_required',
        'verification':'official_detail_not_available','commands':[]})
    rows.append({'id':'industry','scope':'in_scope','implementation':'registered_native_queries' if platform=='jd' else 'not_integrated',
        'verification':'live_options_overview_product_shop_reads_passed' if platform=='jd' else 'blocked_by_browser_site_policy',
        'commands':['industry-options','industry-overview','industry-products','industry-shops'] if platform=='jd' else [],
        'offline_contracts':None if platform=='jd' else 'shopdate_workflows/tmall-industry-contracts.json',
        'offline_contract_status':None if platform=='jd' else 'local_source_candidates; enums_method_response_not_live_verified',
        'semantics':'official_intervals_retained; returned_rank_scope_not_all_market',
        'note':'只接行业大盘、商品榜、店铺榜；天猫市场页面受浏览器安全策略拦截，尚未接入，不用本店类目销售替代。'})
    return {'platform':platform,'modules':rows,
        'principle':'固定取数校验公式由脚本执行；原因判断和建议由助手完成；专门模块保留原接口按需下钻。',
        'excluded_features':['腾讯飞书取数填数','定时任务','自动预算调整'],
        'status_note':'此目录不宣称所有数据域完整，需查看具体任务质量与验收证据。'}
