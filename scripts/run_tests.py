"""Run tests without opening USB. Each GUI case gets its own Tcl interpreter process."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

def cases(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from cases(case)
        else:
            yield case.id()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--gui-only', action='store_true')
    parser.add_argument('--start', type=int, default=0, help='First GUI case, for split CI runs')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--report', type=Path, default=ROOT / 'build' / 'test-results.json')
    args = parser.parse_args()
    results = []
    if not args.gui_only:
        core = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_manager.py', '-v'], cwd=ROOT)
        if core.returncode:
            return core.returncode
        loot = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_loot', '-v'], cwd=ROOT)
        if loot.returncode:
            return loot.returncode
        flash = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_flash_arduino', '-v'], cwd=ROOT)
        if flash.returncode:
            return flash.returncode
    sys.path.insert(0, str(ROOT / 'tests'))
    ids = list(cases(unittest.defaultTestLoader.loadTestsFromName('test_gui')))
    ids = ids[args.start:args.start + args.limit] if args.limit else ids[args.start:]
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT / 'tests')
    for name in ids:
        print(name, flush=True)
        try:
            process = subprocess.run([sys.executable, '-m', 'unittest', name, '-v'], cwd=ROOT,
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=40, text=True, encoding='utf-8', errors='replace')
            print(process.stdout, flush=True)
            results.append({'test': name, 'ok': process.returncode == 0, 'output': process.stdout})
        except subprocess.TimeoutExpired:
            results.append({'test': name, 'ok': False, 'output': 'Test timeout: 40 seconds.'})
            print('TIMEOUT', flush=True)
    report = {'schema': 'evilkey-manager-tests-v1', 'ok': all(r['ok'] for r in results),
              'gui_tests': len(results), 'usb_opened': False, 'results': results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"GUI: {sum(r['ok'] for r in results)}/{len(results)} PASS")
    return 0 if report['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
