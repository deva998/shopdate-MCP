"""Start the package venv over inherited stdio; bootstrap needs only Python."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('route',choices=('jd','symc'))
    args=parser.parse_args()
    python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():
        parser.error('Run the package installer first: .venv Python is missing')
    return subprocess.call([str(python),'-B',str(ROOT/'shopdate.py'),args.route,'mcp'])


if __name__=='__main__':raise SystemExit(main())
