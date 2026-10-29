"""Public portable launcher; JD and Alibaba tb packages stay process-isolated."""
import json
import os
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parent


def main():
    if sys.version_info<(3,11):
        raise SystemExit('Python 3.11+ is required')
    if len(sys.argv)<2 or sys.argv[1] not in ('jd','symc'):
        print('Usage: shopdate.py <jd|symc> <command> [args]\nMCP: shopdate.py <jd|symc> mcp')
        return 0 if len(sys.argv)<2 or sys.argv[1] in ('-h','--help') else 2
    sys.dont_write_bytecode=True
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ.setdefault('PYTHONUTF8','1')
    os.environ.setdefault('PYTHONIOENCODING','utf-8')
    os.environ.setdefault('TB_STATE_ROOT',str(ROOT/'.local/state'))
    os.environ['SYCM_MODE']='extension'
    os.environ['ALIMAMA_MODE']='extension'
    info=json.loads((ROOT/'components/jd/bridge-config.json').read_text(encoding='utf-8'))
    for prefix in ('JD','JD_STORES','SYCM','ALIMAMA','TB_ACCOUNT','TB_STORES'):
        os.environ[prefix+'_ONLY_EXTENSION_IDS']=info['extension_id']
    source=ROOT/'components/jd'
    sys.path.insert(0,str(source))
    sys.argv[0]=str(source/'shopdate_cli.py')
    runpy.run_path(sys.argv[0],run_name='__main__')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
