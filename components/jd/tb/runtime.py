"""Private identity and state namespace for the independent derivative."""
import json
import os
from pathlib import Path


def configure():
    root=Path(__file__).resolve().parent.parent
    info=json.loads((root/'bridge-config.json').read_text(encoding='utf-8'))
    for prefix in ('SYCM','TB_ACCOUNT','TB_STORES','JD','JD_STORES'):
        os.environ[prefix+'_ONLY_EXTENSION_IDS']=info['extension_id']
    os.environ.setdefault('TB_STATE_ROOT',str(root/'.runtime'))
    os.environ.setdefault('JD_BRIDGE_PORT','47922')
    os.environ.setdefault('JD_STORES_BRIDGE_PORT','47923')
