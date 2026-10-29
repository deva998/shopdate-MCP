"""Audit a release tree and its SHA256 inventory without reading any browser data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

FORBIDDEN={'.runtime','.venv','.local','__pycache__','.git','.pytest_cache',
           'node_modules','browser-profile','downloads','outputs','data','state','logs'}
PATTERNS={
    'personal_path':re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[^\s"\'<>]+|/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'credential_value':re.compile(r'''(?i)["']?(?:cookie2|authorization|access_token|refresh_token|client_secret)["']?\s*[:=]\s*["'](?!["'])([A-Za-z0-9_./+\-=]{20,})["']'''),
}
TEXT_SUFFIXES={'.py','.js','.json','.html','.md','.txt','.ps1','.sh','.toml','.yml','.yaml','.example'}


def files(root):
    root=Path(root)
    # A clone's root Git metadata is never release content; nested repos remain errors.
    return sorted((p for p in root.rglob('*') if p.is_file()
                   and p.relative_to(root).parts[0]!='.git'),key=lambda p:p.as_posix())


def audit(root):
    root=Path(root)
    findings=[]
    for path in files(root):
        rel=path.relative_to(root)
        if path.is_symlink() or any(x in FORBIDDEN for x in rel.parts) or path.suffix in ('.pyc','.bak','.pem','.log'):
            findings.append({'path':rel.as_posix(),'rule':'forbidden_path'})
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in ('LICENSE','.gitignore','AGENTS.md'):
            try:
                text=path.read_text(encoding='utf-8-sig')
            except UnicodeDecodeError:
                findings.append({'path':rel.as_posix(),'rule':'invalid_utf8'});continue
            for name, regex in PATTERNS.items():
                if regex.search(text):
                    findings.append({'path':rel.as_posix(),'rule':name})
    return findings


def inventory(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files(root) if p.name!='SHA256SUMS.json'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--write-manifest',action='store_true')
    args=parser.parse_args()
    findings=audit(args.root)
    if findings:
        print(json.dumps({'status':'failed','findings':findings},ensure_ascii=False,indent=2));return 1
    current=inventory(args.root)
    manifest=args.root/'SHA256SUMS.json'
    if args.write_manifest:
        manifest.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    elif not manifest.is_file() or json.loads(manifest.read_text(encoding='utf-8'))!=current:
        print('SHA256 inventory mismatch or missing; verify the pristine extracted release.');return 1
    print(json.dumps({'status':'passed','files':len(current),'privacy_findings':0}));return 0


if __name__=='__main__':
    sys.dont_write_bytecode=True
    raise SystemExit(main())
