"""Extend each existing service in its own process; never edit upstream SYCM."""
from pathlib import Path
import sys
from .metrics import window

ROOT=Path(__file__).resolve().parents[1]


def install(platform):
    from tb import mcp_server as upstream
    from mcp.types import ToolAnnotations
    from mcp.server.mcpserver.exceptions import ToolError
    original=upstream.build

    def build():
        server=original()

        @server.tool(description='本平台方案B模块目录：实施方式、验收要求、排除范围；不取业务数据，不代表所有数据域完整。',
            annotations=ToolAnnotations(read_only_hint=True,destructive_hint=False,open_world_hint=False))
        async def workflow_catalog()->str:
            import json
            from .catalog import catalog
            return json.dumps(catalog(platform),ensure_ascii=False)

        @server.tool(description=(f'{platform}只读工作流。task=daily或weekly；symc另支持ad-review：无证据则新取数，evidence_path为离线重放，'
            'date为北京时间完整历史日，store必须为对应精确store_key。'
            '统一日期身份校验、七日基线/两周加权比较与JSON/Markdown证据；'
            '广告复盘固定计算渠道、官方类目、SOB、广告费率，保留分页和身份缺口。'
            '基础任务可用resume_path显式复用已核验日期；refresh=true重新取完整窗口。'
            '广告新取渠道/商品/计划和销售，按category_limit分批匹配官方类目，未完成返回next_call。'
            '基础日报不自动采集商品、来源、订单、库存明细，不代替经营原因判断。'),
            annotations=ToolAnnotations(read_only_hint=True,destructive_hint=False,open_world_hint=True))
        async def workflow(task:str,date:str,store:str,evidence_path:str='',resume_path:str='',refresh:bool=False,
                           category_evidence_path:str='',category_limit:int=20)->str:
            try:
                if task=='ad-review':
                    if platform!='symc':raise ValueError('京东广告暂缓接入，不能运行ad-review。')
                    window(platform,store,date,'daily')
                    if evidence_path and (resume_path or refresh or category_evidence_path):raise ValueError('广告重放不能与新取数参数混用。')
                    if not 0<=category_limit<=100:raise ValueError('每批类目查询数应为0至100。')
                else:
                    window(platform,store,date,task)
                    if category_evidence_path:raise ValueError('类目缓存仅适用于广告任务。')
                    if evidence_path and (resume_path or refresh):raise ValueError('证据重放不能与续跑或刷新混用。')
            except ValueError as error:
                raise ToolError(str(error)) from error
            argv=[sys.executable,str(ROOT/'shopdate_cli.py'),platform,'workflow',task,
                  '--date',date,'--store',store]
            if evidence_path:argv+=['--evidence',evidence_path]
            if resume_path:argv+=['--resume',resume_path]
            if refresh:argv+=['--refresh']
            if category_evidence_path:argv+=['--category-evidence',category_evidence_path]
            if task=='ad-review':argv+=['--category-limit',str(category_limit)]
            code,out,err=await upstream.execute(argv,timeout=480)
            return upstream.deliver('shopdate-cli '+platform+' workflow '+task,
                                    code,out,err,slug=platform+'-workflow-'+task)
        return server
    upstream.build=build
