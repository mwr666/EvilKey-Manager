# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .widgets import BG, WHITE, INK, MUTED, RED, S, F, Label, Button, Card
from .models import UserError

class FormDialog(tk.Toplevel):
    """Modal input form. PIN fields are cleared, never placed in logs or filenames."""
    def __init__(self,parent,title,description,fields,button="Confirm",validator=None):
        super().__init__(parent);self.withdraw();self.title(title);self.transient(parent)
        self.configure(bg=BG);self.resizable(False,False);self.result=None;self.inputs={};self.validator=validator
        card=Card(self);card.pack(fill='both',expand=True,padx=S(16),pady=S(16));body=card.body
        Label(body,title,23,True).pack(anchor='w')
        Label(body,description,14,color=MUTED,wraplength=S(490)).pack(fill='x',pady=(S(12),S(15)))
        first=None
        for key,label,secret,default in fields:
            Label(body,label,14,bold=True).pack(anchor='w',pady=(S(12),S(6)))
            var=tk.StringVar(value=default);entry=ttk.Entry(body,textvariable=var,width=45,show='●' if secret else '')
            entry.pack(fill='x');self.inputs[key]=(var,entry,secret)
            if first is None:first=entry
        self.error=tk.StringVar();Label(body,textvariable=self.error,size=13,color=RED,wraplength=S(490)).pack(fill='x',pady=S(10))
        actions=tk.Frame(body,bg=WHITE);actions.pack(fill='x',pady=(S(5),0))
        Button(actions,"Cancel",self.reject).pack(side='left')
        Button(actions,button,self.accept,kind='danger' if "Delete" in button or 'reset' in button.lower() else 'primary').pack(side='right')
        self.bind('<Escape>',lambda _:self.reject());self.protocol('WM_DELETE_WINDOW',self.reject)
        # No Return binding on destructive dialogs: typing the confirmation phrase
        # cannot accidentally activate the destructive button.
        self.update_idletasks();w=self.winfo_reqwidth();h=self.winfo_reqheight()
        x=max(0,min(parent.winfo_rootx()+(parent.winfo_width()-w)//2,self.winfo_screenwidth()-w))
        y=max(0,min(parent.winfo_rooty()+(parent.winfo_height()-h)//2,self.winfo_screenheight()-h))
        self.geometry(f'+{x}+{y}');self.deiconify();self.grab_set()
        if first:first.focus_set()
        parent.wait_window(self)
    def accept(self):
        values={k:v.get() for k,(v,_,_) in self.inputs.items()}
        try:
            if self.validator:self.validator(values)
        except (UserError,ValueError) as e:self.error.set(str(e));values.clear();return
        self.result=values;self._clear();self.destroy()
    def reject(self):self._clear();self.destroy()
    def _clear(self):
        for v,e,secret in self.inputs.values():
            if secret:v.set('');e.delete(0,'end')
