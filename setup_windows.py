"""Create a project-local Python environment. Never accesses the game."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--skip-install',action='store_true',help='Only verify an existing .venv')
    args=parser.parse_args()
    if sys.platform!='win32' or sys.version_info[:2]!=(3,12) or platform.machine().lower() not in ('amd64','x86_64'):
        raise SystemExit('Use Windows 10/11 x64 and Python 3.12 x64 from python.org.')
    env=os.environ.copy()
    temp=ROOT/'.tmp';temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp),TMP=str(temp),PYTHONUTF8='1')
    os.environ.update(TEMP=str(temp),TMP=str(temp))
    python=ROOT/'.venv/Scripts/python.exe'
    if not python.exists():
        print('Creating .venv ...',flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT/'.venv')
    if not args.skip_install:
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
                        '-r',str(ROOT/'requirements.txt')],cwd=ROOT,env=env,check=True)
    subprocess.run([str(python),'-X','utf8',str(ROOT/'doctor.py')],cwd=ROOT,env=env,check=True)
    print('Setup complete. Double-click Start CW Counter.cmd.',flush=True)


if __name__=='__main__':main()
