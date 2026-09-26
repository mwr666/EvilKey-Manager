# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Isolated USB worker. stdin/stdout are PRIVATE anonymous parent-child pipes.
No PIN in process arguments, URLs, environment variables, files or log events.
"""
from __future__ import annotations
import json
import os
import sys
from threading import Event, Lock, Thread
from .backend import AUTH_JOBS, MUTATIONS, error_public, execute
from .models import UserError


def main() -> int:
    lock=Lock();event=Event();request={};operation=""
    def send(kind,**fields):
        with lock:
            sys.stdout.write(json.dumps({"type":kind,**fields},ensure_ascii=True)+"\n");sys.stdout.flush()
    try:
        raw=bytearray()
        while len(raw)<65537:
            byte=os.read(sys.stdin.fileno(),1)
            if not byte:break
            raw.extend(byte)
            if byte==b'\n':break
        line=raw.decode('utf-8');raw.clear()
        if not line.endswith('\n') or len(line)>65536:raise UserError("Invalid application request.")
        request=json.loads(line);line=""
        if not isinstance(request,dict) or set(request)!={"operation","args"} or not isinstance(request["args"],dict) or not isinstance(request["operation"],str):
            raise UserError("Invalid application request.")
        operation=request["operation"]
        def read_control():
            try:
                pending=b''
                while not event.is_set():
                    chunk=os.read(sys.stdin.fileno(),64)
                    if not chunk:return
                    pending=(pending+chunk)[-256:]
                    if b'cancel\n' in pending:event.set();return
            except (OSError,ValueError):return
        Thread(target=read_control,daemon=True).start()
        if operation == "health":
            if request["args"]:
                raise UserError("Invalid parameters for checking the application.")
            from .health import check_backend
            result = check_backend()
        else:
            result=execute(operation,request["args"],event,lambda text:send("progress",text=text))
        send("result",data=result)
        return 0
    except BaseException as exc:
        send("error",error=error_public(exc,operation in MUTATIONS))
        return 1
    finally:
        # Python immutable strings cannot be guaranteed zeroized. The isolated
        # process exits after each job; no authentication session is cached.
        
        if isinstance(request,dict):request.clear()
        event.set()
