"""Local setup and MCP configuration export. Never edits an Agent's settings."""
import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import uuid
import venv
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
CLIENTS = ('all', 'codex', 'claude-code', 'claude-desktop', 'cursor', 'trae', 'workbuddy', 'doubao', 'generic')


def source_roots(root):
    root = Path(root).resolve()
    return {name: root/'components'/name for name in ('jd', 'ali')}


def generate_configs(root, python, platform=None):
    root, python = Path(root).resolve(), Path(python).resolve()
    extension = json.loads((ROOT/'components/jd/bridge-config.json').read_text(encoding='utf-8'))['extension_id']
    env = {'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'TB_STATE_ROOT': str(root/'.local/state'),
           'SYCM_MODE': 'extension', 'ALIMAMA_MODE': 'extension'}
    env.update({prefix+'_ONLY_EXTENSION_IDS':extension for prefix in
                ('JD','JD_STORES','SYCM','ALIMAMA','TB_ACCOUNT','TB_STORES')})
    servers = {f'shopdate-{route}':{'command':str(python),
                'args':[str(root/'shopdate.py'),route,'mcp'], 'env':dict(env)} for route in ('jd','symc')}
    dump = lambda obj: json.dumps(obj, ensure_ascii=False, indent=2)+'\n'
    configs = {name+'/mcp.json':dump({'mcpServers':servers}) for name in
               ('generic','claude-desktop','cursor','doubao')}
    configs['claude-code/.mcp.json'] = dump({'mcpServers':servers})
    trae = copy.deepcopy(servers)
    for server in trae.values():
        server['env'].update(START_MCP_TIMEOUT_MS='120000', RUN_MCP_TIMEOUT_MS='600000')
        if ' ' in server['command']:
            # TRAE documents a no-space command requirement. Keep paths in args.
            host_platform=platform or sys.platform
            base_python=Path(getattr(sys,'_base_executable',sys.executable))
            if host_platform==sys.platform and base_python.is_file() and ' ' not in str(base_python):
                server['command']=str(base_python)
                prefix=[]
            elif host_platform=='win32':
                server['command']='py'
                prefix=['-3-64']
            else:
                server['command']='python3'
                prefix=[]
            server['args']=prefix+[str(root/'scripts/launch_venv_mcp.py'),server['args'][-2]]
    configs['trae/mcp.json'] = dump({'mcpServers':trae})
    for key, value in servers.items():
        configs[f'workbuddy/{key}/mcp.json'] = dump({'mcpServers':{key:{'type':'stdio',**value}}})
    lines=[]
    for key, value in servers.items():
        lines += [f'[mcp_servers.{key}]', 'command = '+json.dumps(value['command'],ensure_ascii=False),
                  'args = '+json.dumps(value['args'],ensure_ascii=False),
                  'startup_timeout_sec = 120', 'tool_timeout_sec = 600',
                  f'[mcp_servers.{key}.env]']
        lines += [k+' = '+json.dumps(v,ensure_ascii=False) for k,v in value['env'].items()]
        lines += ['']
    configs['codex/config.toml']='\n'.join(lines)+'\n'
    return configs


def export_configs(root, python, platform=None, client='all'):
    if client not in CLIENTS:
        raise ValueError('unsupported client')
    root=Path(root).resolve()
    folder=root/'.local/mcp-configs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    configs=generate_configs(root,python,platform)
    for name, text in configs.items():
        if client!='all' and name.split('/')[0]!=client:
            continue
        path=folder/name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='\n') as output:
            output.write(text)
    (folder/'README.txt').write_text(
        'Merge only these shopdate entries into the selected client; never replace unrelated settings.\n'
        'WorkBuddy: add JD and Alibaba separately as local stdio connectors.\n'
        'Doubao: conditional template only; requires local STDIO support in your version.\n'
        'Paths describe this installation. After moving it, rerun the installer with --config-only.\n',encoding='utf-8')
    return folder


def validate_options(*, offline, wheelhouse, index_url=None):
    if offline and not wheelhouse:
        raise ValueError('--offline requires --wheelhouse with local dependency wheels')
    if wheelhouse and not Path(wheelhouse).is_dir():
        raise ValueError('wheelhouse directory does not exist')
    if index_url:
        parsed=urlsplit(index_url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('--index-url requires an HTTPS URL without embedded credentials, query or fragment')
        if offline:
            raise ValueError('--index-url cannot be combined with --offline')


def pip_command(python, requirements, *, offline=False, wheelhouse=None, index_url=None):
    cmd=[python,'-m','pip','install','--disable-pip-version-check','-r',requirements]
    if offline:
        cmd += ['--no-index']
    if wheelhouse:
        cmd += ['--find-links',Path(wheelhouse).resolve()]
    if index_url:
        cmd += ['--index-url',index_url]
    return cmd


def validate_runtime(version, pointer_bits):
    if tuple(version[:2]) < (3,11):
        raise ValueError('Python 3.11 or newer is required')
    if pointer_bits != 64:
        raise ValueError('64-bit Python is required; 32-bit dependency wheels are not supported')


def pip_environment(offline, inherited=None):
    env=dict(os.environ if inherited is None else inherited)
    # Mode is an explicit installer choice; do not inherit a contradictory flag.
    # Proxy, index URL and certificate settings are preserved.
    env.update(PIP_NO_INDEX='1' if offline else '0',
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    return env


def run(argv, *, env=None):
    env={**os.environ, 'PYTHONUTF8':'1', 'PYTHONIOENCODING':'utf-8'} if env is None else env
    subprocess.run([str(x) for x in argv],check=True,cwd=ROOT,env=env)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',choices=CLIENTS,default='all')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--wheelhouse',type=Path)
    parser.add_argument('--config-only',action='store_true')
    parser.add_argument('--index-url',help='Optional HTTPS Python package index; online installation only')
    args=parser.parse_args(argv)
    try:
        validate_runtime(sys.version_info,struct.calcsize('P')*8)
        validate_options(offline=args.offline,wheelhouse=args.wheelhouse,index_url=args.index_url)
        for name, path in source_roots(ROOT).items():
            if not (path/'tb/cli.py').is_file():
                raise ValueError('missing bundled source: '+name)
        python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if args.config_only:
            if not python.is_file():
                raise ValueError('install dependencies first; .venv Python is missing')
        else:
            if not python.is_file():
                venv.EnvBuilder(with_pip=True).create(ROOT/'.venv')
            cmd=pip_command(python,ROOT/'requirements.txt',offline=args.offline,
                            wheelhouse=args.wheelhouse,index_url=args.index_url)
            print('Dependency mode: '+('offline (local wheelhouse)' if args.offline else 'online (pip index enabled)'),flush=True)
            run(cmd,env=pip_environment(args.offline))
        # This checks registration only. It never reads store/account/browser data.
        for route in ('jd','symc'):
            run([python,ROOT/'shopdate.py',route,'mcp','--check'])
        folder=export_configs(ROOT,python,sys.platform,args.client)
        print('MCP_CONFIG_EXPORT='+str(folder),flush=True)
        print('CHROME_EXTENSION='+str(ROOT/'components/jd/extension/unpacked'),flush=True)
        print('No Agent settings changed. See README.md for manual merge and Chrome loading.')
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Setup failed: '+str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
