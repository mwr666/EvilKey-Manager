# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Nonblocking GUI process supervisor with cooperative cancel + hard deadline."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
from threading import Thread
import time
from typing import Callable
from .backend import MUTATIONS
from .models import UserError

class JobRunner:
    def __init__(self,entrypoint: Path,on_progress: Callable,on_done: Callable):
        self.entrypoint=entrypoint;self.on_progress=on_progress;self.on_done=on_done
        self.process=None;self.messages=queue.Queue();self.pending=None
        self.cancel_at=None;self.started=0.0;self.operation="";self.timed_out=False
        self.limit=30;self.serial=0;self.reader_eof=False
    @property
    def busy(self):return self.process is not None
    def start(self,operation: str,args: dict):
        if self.busy:raise UserError("Another operation is in progress. The new request was not queued.")
        payload=json.dumps({"operation":operation,"args":args},ensure_ascii=True)+'\n'
        if len(payload)>65536:raise UserError("The demand is too big.")
        if getattr(sys, "frozen", False):
            worker = Path(sys._MEIPASS) / "bin" / "EvilKeyUsb.exe"
            if not worker.is_file():
                raise UserError("The USB communication module is missing. Download the complete application again.")
            cmd = [str(worker)]
        else:
            cmd = [sys.executable, str(self.entrypoint), "--worker"]
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        self.process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',bufsize=1,creationflags=flags)
        self.serial+=1;serial=self.serial;process=self.process
        self.reader_eof=False;self.operation=operation;self.pending=None;self.cancel_at=None;self.started=time.monotonic();self.timed_out=False
        self.limit=240 if operation in {'credentials','metadata','display_read','display_write','always_uv','pin_policy','enterprise','delete_credential','rename_credential','resident_keys','makecred_uv'} else 50 if operation=='reset' else 30
        def reader():
            try:
                for line in process.stdout:
                    if len(line)>2_000_000:break
                    try:msg=json.loads(line)
                    except (ValueError,TypeError):continue
                    if isinstance(msg,dict) and msg.get('type') in {'result','progress','error'}:
                        self.messages.put((serial,msg))
            finally:self.messages.put((serial,{'type':'eof'}))
        Thread(target=reader,daemon=True).start()
        try:self.process.stdin.write(payload);self.process.stdin.flush()
        except (BrokenPipeError,OSError):self.pending={'type':'error','error':{'message':"The USB process failed to start.",'connection_lost':True}}
        payload=""
    def cancel(self):
        if not self.busy or self.cancel_at is not None:return
        self.cancel_at=time.monotonic()
        try:self.process.stdin.write('cancel\n');self.process.stdin.flush()
        except (OSError,ValueError):pass
        self.on_progress("A cancellation request has been sent. Waiting for completion...")
    def pump(self):
        while True:
            try:serial,msg=self.messages.get_nowait()
            except queue.Empty:break
            if serial!=self.serial or not self.busy:continue
            if msg['type']=='progress':self.on_progress(str(msg.get('text',''))[:1000])
            elif msg['type'] in ('result','error'):self.pending=msg
            elif msg['type']=='eof':self.reader_eof=True
        if not self.busy:return
        now=time.monotonic()
        if now-self.started>self.limit and self.cancel_at is None:
            self.timed_out=True;self.cancel()
        if self.cancel_at is not None and now-self.cancel_at>3 and self.process.poll() is None:
            self.process.kill()  # only this isolated USB worker, no unrelated process
        if self.process.poll() is not None:
            # Reader may be one scheduler tick behind process exit. Drain once
            # more on the next pump before declaring a missing response.
            if not self.reader_eof:return
            process=self.process;self.process=None
            try:process.stdin.close();process.stdout.close()
            except (OSError,ValueError):pass
            process.wait()
            result=self.pending
            if result is None:
                message=("The operation timed out." if self.timed_out else "The operation was interrupted.")
                if self.operation in MUTATIONS:message+=" A write may already have been applied. Read device state before another change."
                result={'type':'error','error':{'message':message,'connection_lost':True}}
            result['cancel_requested']=self.cancel_at is not None
            self.pending=None
            self.on_done(self.operation,result)
