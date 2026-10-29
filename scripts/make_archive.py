"""Verify and archive a pristine tree. Run before installing into this folder."""
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile
from verify_release import files

ROOT=Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/verify_release.py')],check=True)
    target=ROOT.parent/(ROOT.name+'.zip')
    if target.exists():
        raise SystemExit('Archive already exists; choose a new output directory before rebuilding.')
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in files(ROOT):
            name=ROOT.name+'/'+p.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(name,date_time=(2026,10,29,0,0,0))
            info.create_system=3
            info.external_attr=(0o100755 if p.suffix=='.sh' else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,p.read_bytes())
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='ascii')
    print(target.name+' '+digest)


if __name__=='__main__':
    raise SystemExit(main())
