# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
from importlib import metadata
from pathlib import Path
import shutil
import sys
out=Path(__file__).resolve().parents[1]/'manager'/'licenses'
out.mkdir(exist_ok=True)
shutil.copy2(Path(__file__).resolve().parents[1]/'manager'/'LICENSE.md', out/'EvilKey-Manager-LICENSE.txt')
for name in ('fido2','cryptography','cffi','pycparser','pyinstaller'):
    dist=metadata.distribution(name)
    for item in dist.files or []:
        if any(part.lower().startswith(('license','copying','notice')) for part in item.parts):
            source=Path(dist.locate_file(item))
            if source.is_file() and source.stat().st_size < 500_000:
                target=out/(name+'-'+str(item).replace('/','_').replace('\\','_')+'.txt')
                target.write_text(source.read_text(encoding='utf-8',errors='replace'),encoding='utf-8')
for filename in ('LICENSE.txt','LICENSE'):
    p=Path(sys.base_prefix)/filename
    if p.is_file():shutil.copy2(p,out/'Python-LICENSE.txt');break
# Tcl and Tk licenses in the standard Windows CPython distribution.
for p in (Path(sys.base_prefix)/'tcl').glob('*/license.terms'):
    shutil.copy2(p,out/(p.parent.name+'-license.txt'))
