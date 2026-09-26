#!/usr/bin/env python3
"""Read-only PC dependency check. No enumeration/opening of security keys."""
import sys,platform,importlib.metadata
import tkinter
from evilkey_manager.backend import load_api
api=load_api()
for name in ('fido2','cryptography'):
    print(name,importlib.metadata.version(name))
print('Python:',platform.python_version(),platform.machine())
print('Tcl/Tk:',tkinter.TkVersion)
print('Operating system:',platform.system())
print('ENVIRONMENT_OK; USB was not opened')
