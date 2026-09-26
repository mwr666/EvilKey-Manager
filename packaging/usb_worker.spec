# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata
ROOT = Path(SPECPATH).parent
analysis = Analysis(
    [str(ROOT / 'manager' / 'usb_entry.py')],
    pathex=[str(ROOT / 'manager')],
    datas=copy_metadata('fido2') + copy_metadata('cryptography'),
    hiddenimports=['fido2.hid.windows', 'cryptography.hazmat.bindings._rust'],
    excludes=['tkinter', 'PIL', 'numpy', 'matplotlib', 'pytest'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name='EvilKeyUsb', debug=False, strip=False, upx=False,
          console=True, uac_admin=False)
collection = COLLECT(exe, analysis.binaries, analysis.datas,
                     strip=False, upx=False, name='EvilKeyUsb')
