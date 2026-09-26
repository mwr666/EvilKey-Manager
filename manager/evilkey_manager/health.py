# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Packaging checks: imports and local crypto only, never USB enumeration."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

def check_backend():
    from .backend import load_api
    api=load_api()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    secret=AESGCM.generate_key(bit_length=256);gcm=AESGCM(secret);nonce=os.urandom(12)
    plain=b'EvilKeyManager packaging check'
    assert gcm.decrypt(nonce,gcm.encrypt(nonce,plain,None),None)==plain
    key=ec.generate_private_key(ec.SECP256R1());sig=key.sign(plain,ec.ECDSA(hashes.SHA256()))
    key.public_key().verify(sig,plain,ec.ECDSA(hashes.SHA256()))
    assert api.cbor.decode(api.cbor.encode({1:'ok',2:bytes(32)}))=={1:'ok',2:bytes(32)}
    return {'ok':True,'fido2':importlib.metadata.version('fido2'),
            'cryptography':importlib.metadata.version('cryptography'),'usb_opened':False}

def run_packaging_check(report: Path):
    result={'schema':'evilkey-packaging-check-v1','ok':False,'usb_opened':False,
            'frozen':bool(getattr(sys,'frozen',False)),'python':sys.version.split()[0]}
    try:
        import tkinter as tk
        root=tk.Tk();root.withdraw()
        from .models import DisplaySettings
        assert DisplaySettings.decode(DisplaySettings().encode())==DisplaySettings()
        from .gui import Application
        app=Application(root,demo=False);root.update_idletasks()
        # Inspect all six real pages without invoking discovery or an HID call.
        for i in range(6):app.book.select(i);root.update_idletasks()
        app.shutdown_ui();root.destroy();result['gui_pages']=6
        if getattr(sys,'frozen',False):cmd=[str(Path(sys._MEIPASS)/'bin'/'EvilKeyUsb.exe')]
        else:cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'run_manager.py'),'--worker']
        completed=subprocess.run(cmd,input=json.dumps({'operation':'health','args':{}})+'\n',
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        messages=[json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        last=messages[-1] if messages else {}
        if completed.returncode!=0 or last.get('type')!='result' or last.get('data',{}).get('ok') is not True:
            raise RuntimeError("Checking the USB module failed.")
        result.update(ok=True,worker=last['data'])
    except Exception as e:
        result['error_type']=type(e).__name__
        result['error']="The package check has not been completed. Check the completeness of libraries and files."
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if result['ok'] else 1
