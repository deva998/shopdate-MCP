"""shopdate-cli: one public entry, two independent existing implementations."""
import json,os,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ('-h','--help'):
        print('shopdate-cli\n  jd <command>       京东商智 / 京麦\n  symc <command>     生意参谋 / 淘宝 / 天猫（阿里系）\n  jd mcp             shopdate-jd MCP\n  symc mcp           shopdate-symc MCP\n  <jd|symc> workflow <daily|weekly> --date YYYY-MM-DD --store STORE\n示例：shopdate-cli jd capabilities')
        return 0
    route=args.pop(0)
    if route not in ('jd','symc'):
        print('平台必须为 jd 或 symc',file=sys.stderr);return 2
    if args[:1]==['workflow']:
        from shopdate_workflows.cli import main as workflow_main
        return workflow_main(route,args[1:])
    root=ROOT if route=='jd' else (ROOT.parent/'ali').resolve()
    if not (root/'tb/cli.py').is_file():raise ValueError('平台源目录不可用：'+str(root))
    # Both upstream packages are called tb; each launch is a separate process.
    sys.path.insert(0,str(root));os.environ['PYTHONPATH']=str(root);os.chdir(root)
    if args[:1]==['mcp']:
        from shopdate_workflows.mcp import install
        install(route)
    from tb.cli import main as platform_main
    common={'mcp','account','stores','modules','plugin'}
    return platform_main(args if args and args[0] in common else [('jd' if route=='jd' else 'sycm'),*args])

if __name__=='__main__':sys.exit(main())
