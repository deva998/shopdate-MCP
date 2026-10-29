"""Merge only shopdate MCP entries; preserve unrelated JSON text and back up."""
import argparse
import json
from pathlib import Path
import re
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]


def _span(text,key):
    decoder=json.JSONDecoder();p=text.index('{')+1
    while True:
        while text[p].isspace():p+=1
        if text[p]=='}':raise KeyError(key)
        name,p=decoder.raw_decode(text,p)
        while text[p].isspace():p+=1
        if text[p]!=':':raise ValueError('invalid JSON property')
        p+=1
        while text[p].isspace():p+=1
        start=p;value,p=decoder.raw_decode(text,p)
        if name==key:return start,p
        while text[p].isspace():p+=1
        if text[p]==',':p+=1
        elif text[p]=='}':raise KeyError(key)


def _insert(text,properties):
    end=text.rfind('}')
    nonempty=bool(text[text.index('{')+1:end].strip())
    if '\n' not in text:
        extra=','.join(json.dumps(k,ensure_ascii=False)+':'+json.dumps(v,ensure_ascii=False,separators=(',',':')) for k,v in properties.items())
        return text[:end]+(',' if nonempty else '')+extra+text[end:]
    newline='\r\n' if '\r\n' in text else '\n'
    closing=re.search(r'\n([ \t]*)$',text[:end])
    closing_indent=closing.group(1) if closing else ''
    first=re.search(r'\n([ \t]+)"',text)
    indent=first.group(1) if first else closing_indent+'  '
    unit=indent[len(closing_indent):] or '  '
    blocks=[]
    for key,value in properties.items():
        fragment=json.dumps(key,ensure_ascii=False)+': '+json.dumps(value,ensure_ascii=False,indent=unit)
        blocks.append(newline.join(indent+line for line in fragment.splitlines()))
    return text[:end].rstrip()+(',' if nonempty else '')+newline+(','+newline).join(blocks)+newline+closing_indent+text[end:]


def merge_text(original,servers):
    bom='\ufeff' if original.startswith('\ufeff') else ''
    text=original[len(bom):]
    obj=json.loads(text)
    if not isinstance(obj,dict):raise ValueError('MCP configuration must be a JSON object')
    if 'mcpServers' in obj and 'servers' in obj:raise ValueError('ambiguous MCP schema; select the correct client configuration file')
    schema='servers' if 'servers' in obj else 'mcpServers'
    existing=obj.get(schema,{})
    if not isinstance(existing,dict):raise ValueError('MCP server map must be an object')
    additions={}
    for key,value in servers.items():
        if key in existing and existing[key]!=value:raise ValueError('Existing configuration conflicts: '+key+'; no file changed')
        if key not in existing:additions[key]=value
    if not additions:return original
    if schema in obj:
        start,end=_span(text,schema)
        updated=text[:start]+_insert(text[start:end],additions)+text[end:]
    else:updated=_insert(text,{schema:additions})
    verified=json.loads(updated)
    expected={**obj,schema:{**existing,**additions}}
    if verified!=expected:raise ValueError('merge verification failed')
    return bom+updated


def register(target,servers,backup_dir):
    target=Path(target);backup_dir=Path(backup_dir)
    if target.is_symlink():raise ValueError('Refusing a symlink configuration target')
    before=target.read_bytes() if target.exists() else None
    original=before.decode('utf-8') if before is not None else '{}\n'
    updated=merge_text(original,servers).encode('utf-8')
    if before==updated:return {'changed':False,'backup':None,'target':str(target)}
    backup=None
    if before is not None:
        backup_dir.mkdir(parents=True,exist_ok=True)
        backup=backup_dir/(target.name+'.'+uuid.uuid4().hex+'.bak')
        with backup.open('xb') as f:f.write(before)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as f:f.write(updated)
        current=target.read_bytes() if target.exists() else None
        if current!=before:raise ValueError('Configuration changed concurrently; no replacement performed')
        temporary.replace(target)
    finally:
        if temporary.exists():temporary.unlink()
    return {'changed':True,'backup':str(backup) if backup else None,'target':str(target)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',choices=('workbuddy','claude-code','trae'),required=True)
    destination=parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--project',type=Path)
    destination.add_argument('--config-file',type=Path,help='Actual JSON file identified by this client, not a guessed path')
    args=parser.parse_args()
    try:
        python=ROOT/'.venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
        if not python.is_file():raise ValueError('Run the package installer first')
        sys.path.insert(0,str(ROOT))
        from installer import generate_configs
        configs=generate_configs(ROOT,python,sys.platform)
        if args.client=='workbuddy':
            servers={}
            for route in ('jd','symc'):
                servers.update(json.loads(configs[f'workbuddy/shopdate-{route}/mcp.json'])['mcpServers'])
        else:
            name='claude-code/.mcp.json' if args.client=='claude-code' else 'trae/mcp.json'
            servers=json.loads(configs[name])['mcpServers']
        if args.project:
            project=args.project.resolve()
            if not project.is_dir():raise ValueError('Project directory does not exist')
            target=project/('.trae/mcp.json' if args.client=='trae' else '.mcp.json')
        else:target=args.config_file.resolve()
        result=register(target,servers,ROOT/'.local/client-backups')
        print(json.dumps(result,ensure_ascii=False))
        print('Registration is not tool-call verification. Complete client trust/login when requested.')
        return 0
    except (ValueError,OSError) as error:
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
