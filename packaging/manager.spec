# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
from pathlib import Path
import os
ROOT = Path(SPECPATH).parent
worker = ROOT / 'build' / 'worker' / 'EvilKeyUsb'
if not (worker / 'EvilKeyUsb.exe').is_file():
    raise RuntimeError('Build the USB communication module first.')
# A console helper inside the single-file GUI preserves anonymous pipe IPC.
# No PIN is written to a command line, an environment variable or a disk file.
datas = [(str(ROOT / 'manager' / 'assets'), 'assets'),
         (str(ROOT / 'manager' / 'licenses'), 'licenses')]
for path in worker.rglob('*'):
    if path.is_file():
        datas.append((str(path), str(Path('bin') / path.relative_to(worker).parent)))
analysis = Analysis(
    [str(ROOT / 'manager' / 'run_manager.py')],
    pathex=[str(ROOT / 'manager')], datas=datas,
    hiddenimports=['tkinter', 'tkinter.ttk', 'evilkey_manager.demo'],
    excludes=['fido2', 'cryptography', '_cffi_backend', 'PIL', 'numpy', 'matplotlib', 'pytest'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
options = dict(name='EvilKeyManager', debug=False, strip=False, upx=False,
               console=False, uac_admin=True, uac_uiaccess=False,
               icon=str(ROOT / 'manager' / 'assets' / 'evilkey.ico'),
               version=str(ROOT / 'packaging' / 'version_info.txt'))
if os.environ.get('EVILKEY_ONE_FOLDER') == '1':
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, **options)
    collection = COLLECT(exe, analysis.binaries, analysis.datas,
                         strip=False, upx=False, name='EvilKeyManager')
else:
    exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [], **options)
