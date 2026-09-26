#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
from __future__ import annotations
import argparse
from pathlib import Path
import sys

def main():
    parser=argparse.ArgumentParser(description='EVILKEY Manager')
    parser.add_argument('--preview',action='store_true',help="Interface Preview without USB")
    parser.add_argument('--demo',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--elevate',action='store_true',help="FIDO HID direct communication permissions")
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--self-test-report',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:
        from evilkey_manager.worker import main as worker_main
        return worker_main()
    if sys.platform=='win32':
        import ctypes
        try:ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError,OSError):
            try:ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError,OSError):pass
        if args.elevate and not ctypes.windll.shell32.IsUserAnAdmin():
            import subprocess
            command=([sys.executable]+sys.argv[1:]) if getattr(sys,'frozen',False) else [str(Path(__file__).resolve())]+sys.argv[1:]
            if getattr(sys,'frozen',False):command=command[1:]
            result=ctypes.windll.shell32.ShellExecuteW(None,'runas',sys.executable,subprocess.list2cmdline(command),str(Path(sys.executable).parent),1)
            return 0 if result>32 else 1
    if args.self_test_report:
        from evilkey_manager.health import run_packaging_check
        return run_packaging_check(args.self_test_report.resolve())
    from evilkey_manager.gui import launch
    launch(demo=args.preview or args.demo)
    return 0

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
