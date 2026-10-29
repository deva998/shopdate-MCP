"""Public basic workflow CLI, alongside (not replacing) existing commands."""
import argparse
import json
import sys
from .runner import run


def main(platform,argv):
    if argv==['catalog']:
        from .catalog import catalog
        print(json.dumps(catalog(platform),ensure_ascii=False));return 0
    parser=argparse.ArgumentParser(prog=f'shopdate-cli {platform} workflow',
        description='只读基础概况日报/周报。固定校验和计算；经营判断由助手完成。')
    parser.add_argument('task',choices=['daily','weekly','ad-review'])
    parser.add_argument('--date',required=True,help='北京时间完整历史日')
    parser.add_argument('--store',required=True,help='精确store_key，非店铺昵称')
    parser.add_argument('--evidence',help='重放本工具已核验的证据文件，不访问平台')
    parser.add_argument('--output-root',help='报告保存目录')
    parser.add_argument('--legacy-dir',help='仅广告复盘：显式导入已有快照目录，保留旧身份及分页缺口')
    parser.add_argument('--resume',help='基础日报周报：复用已核验日期，补取目标窗口缺少日期')
    parser.add_argument('--refresh',action='store_true',help='忽略复用日期，重新取得完整窗口')
    parser.add_argument('--category-evidence',help='广告新取数：显式复用官方商品类目证据，保留原观察时间')
    parser.add_argument('--category-limit',type=int,default=20,help='广告每批新增官方商品类目查询数，0至100')
    args=parser.parse_args(argv)
    try:
        if args.task=='ad-review':
            if platform!='symc':raise ValueError('京东广告暂缓接入，不能运行ad-review。')
            from .ad_runner import run_ads
            result=run_ads(args.store,args.date,args.evidence,args.legacy_dir,args.output_root,
                resume_path=args.resume,category_evidence_path=args.category_evidence,
                category_limit=args.category_limit,refresh=args.refresh)
        else:
            if args.legacy_dir:raise ValueError('--legacy-dir仅适用于ad-review。')
            if args.category_evidence:raise ValueError('--category-evidence仅适用于ad-review。')
            result=run(platform,args.store,args.date,args.task,args.evidence,args.output_root,
                       resume_path=args.resume,refresh=args.refresh)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr)
        return 1
