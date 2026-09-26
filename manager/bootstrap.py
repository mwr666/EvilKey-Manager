#!/usr/bin/env python3
"""Create a fresh, local GUI environment. Does not communicate with USB."""
from pathlib import Path
import os,subprocess,sys,venv
ROOT=Path(__file__).resolve().parent

def main():
    if sys.version_info<(3,10):raise SystemExit('Python 3.10+ is required. Install Python with Tcl/Tk support.')
    try:import tkinter
    except ImportError:raise SystemExit('Python lacks tkinter. Install the Tcl/Tk component of Python. No changes made to USB.')
    env=ROOT/'.venv-manager';exe=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if env.exists():
        if not exe.is_file() or exe.stat().st_size==0:
            raise SystemExit('The existing .venv-manager is incomplete. Rename that environment folder before running install again. The firmware folder must NOT be deleted.')
        try:subprocess.run([str(exe),'-c','import sys,tkinter; assert sys.version_info >= (3,10)'],check=True)
        except (OSError,subprocess.CalledProcessError):raise SystemExit('Existing environment cannot start. Rename .venv-manager and run install again.')
    else:venv.EnvBuilder(with_pip=True).create(env)
    subprocess.run([str(exe),'-m','pip','install','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],check=True)
    subprocess.run([str(exe),str(ROOT/'check_environment.py')],check=True)
    print('Installed. Run start_admin.cmd for USB configuration or demo.cmd for a GUI demonstration.')
if __name__=='__main__':
    try:main()
    except (OSError,subprocess.CalledProcessError) as exc:raise SystemExit('Installation failed. Check Python/network/permissions. No device operation was performed.\n'+str(exc))
