# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""English desktop interface. The UI never implements its own CTAP protocol."""
from __future__ import annotations
from dataclasses import asdict, replace
from datetime import datetime
import json
import math
import time
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from . import __version__
from .controller import Actions
from .backend import MUTATIONS
from .models import DisplaySettings, UserError, display_text
from .jobs import JobRunner
from .project import DEFAULTS, BOOL_FIELDS, HEX_FIELDS, find_firmware_source
from .loot import (VARIABLE_MODE, REFLECTION_MODE, INDEXED_MODE, read_loot,
                   read_loot_index, decode_rows, describe, export_csv)
from .widgets import (BG, WHITE, INK, MUTED, BORDER, NAVY, TEAL, PALE, RED, INPUT_BG, SURFACE_ALT, ACCENT_SOFT,
                      S, F, setup, rounded, icon, mix, Icon, IconBadge, Logo, AnimatedLogo, Label, Card, Button,
                      Toggle, Slider, PercentEntry, ScrollPage)

NAMES={'scan':'Search for devices','info':'Read device','ping':'Check connection',
 'metadata':'Credential storage usage','credentials':'Credential list','display_read':'Read display settings',
 'display_write':'Save display settings','drive_read':'Read Manager Drive mode','drive_write':'Manager Drive write protection','set_pin':'Set PIN','change_pin':'Change PIN',
 'always_uv':'User verification','pin_policy':'PIN policy','resident_keys':'Credential storage',
 'makecred_uv':'Registration verification','delete_credential':'Delete credential',
 'rename_credential':'Edit description','enterprise':'Enterprise Attestation','reset':'Reset device'}


# EvilKey port builds use 0xMMmmppbb in CTAP GetInfo.firmwareVersion.
# Small legacy values (for example upstream 0x0800) are deliberately not
# presented as this port's semantic version.
def firmware_version_label(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0xFFFF or value > 0xFFFFFFFF:
        return None
    major=(value >> 24) & 0xFF
    minor=(value >> 16) & 0xFF
    patch=(value >> 8) & 0xFF
    build=value & 0xFF
    label=f"{major}.{minor}.{patch}"
    return f"{label}+{build}" if build else label

class NavButton(Button):
    def __init__(self,*args,**kw):self.selected=False;super().__init__(*args,**kw)
    def draw(self):
        if not self.winfo_exists():return
        self.delete('all');w=self.winfo_width();h=self.winfo_height()
        disabled=self._state=='disabled'
        bg=ACCENT_SOFT if self.selected else '#171A1D' if self.hover else WHITE
        fg=INK if self.selected or self.hover else MUTED
        outline='#315149' if self.selected else TEAL if self.focused else BORDER
        if disabled:fg='#65666B';outline=BORDER
        yoff=S(1) if self.pressed else 0
        rounded(self,S(1),S(1)+yoff,w-S(2),h-S(2)-yoff,S(11),fill=bg,outline=outline)
        if self.selected:
            self.create_line(S(14),h-S(3),w-S(14),h-S(3),fill=TEAL,width=S(2),capstyle='round')
        icon(self,self.name,S(17),(h-S(20))/2+yoff,S(20),TEAL if self.selected else fg)
        self.create_text(S(46),h/2+yoff,anchor='w',text=self._text,font=F(14,'bold' if self.selected else 'normal'),fill=fg)

class Book:
    def __init__(self,app,parent):self.app=app;self.parent=parent;self.frames=[];self.tabs=[];self.index=0
    def select(self,index=None):
        if index is None:return self.index
        index=int(index)
        for i,f in enumerate(self.frames):
            f.pack_forget();self.tabs[i].selected=(i==index);self.tabs[i].draw()
        self.frames[index].pack(fill='both',expand=True);self.index=index;self.app.active_page=index
        self.app.root.after_idle(self.app.reflow)
    def add(self,title,symbol):
        i=len(self.frames)
        btn=NavButton(self.app.nav,title,lambda:self.select(i),name=symbol,width=166,height=46)
        btn.grid(row=0,column=i,sticky='nsew',padx=S(3),pady=S(3));self.app.nav.columnconfigure(i,weight=1,uniform='tabs')
        f=tk.Frame(self.parent,bg=BG);scroll=ScrollPage(f);footer=tk.Frame(f,bg=BG)
        footer.pack(side='bottom',fill='x',pady=(S(10),0));scroll.pack(fill='both',expand=True)
        self.frames.append(f);self.tabs.append(btn);return scroll,footer

class ScreenPreview(tk.Canvas):
    def __init__(self,parent):
        super().__init__(parent,bg=WHITE,height=S(260),highlightthickness=0)
        self.settings=DisplaySettings();self.bind('<Configure>',lambda _:self.draw())
    def update_settings(self,s):self.settings=s;self.draw()
    def draw(self):
        if not self.winfo_exists():return
        self.delete('all');w=max(self.winfo_width(),S(300));s=self.settings;col=w/3
        captions=["Active",'Dimmed','Off']
        times=["Ready",f'After {s.dim_seconds} s' if s.dim_seconds else "Disabled",f'+ {s.off_seconds} s' if s.off_seconds and s.dim_seconds else "Disabled"]
        accent=f'#{s.accent_rgb:06X}'
        for i in range(3):
            cx=(i+.5)*col
            self.create_text(cx,S(23),text=captions[i],font=F(13,'bold'),fill=INK)
            self.create_text(cx,S(45),text=times[i],font=F(12),fill=MUTED)
            dw=min(S(106),col-S(30));dh=S(153);x=cx-dw/2;y=S(74)
            rounded(self,x+S(3),y+S(5),dw,dh,S(19),fill='#000000',outline='')
            rounded(self,x,y,dw,dh,S(17),fill='#181A1D',outline='#34373B')
            rounded(self,x+S(5),y+S(5),dw-S(10),dh-S(10),S(13),fill='#000000',outline='')
            if i<2:
                c=accent if i==0 else '#33403D'
                icon(self,'lock',cx-S(17),y+S(37),S(34),c,2)
                self.create_text(cx,y+S(94),text='EVILKEY',font=F(11,'bold'),fill=c)
                self.create_line(cx-S(12),y+dh-S(15),cx+S(12),y+dh-S(15),fill=c,width=S(3),capstyle='round')
            if i<2:icon(self,'arrow',(i+1)*col-S(9),y+dh/2,S(18),MUTED)

class Application(Actions):
    def __init__(self,root:tk.Tk,demo=False):
        self.root=root;self.demo=demo;self.devices=[];self.device=None;self.info=None
        self.credentials=[];self.display_record=None;self.drive_record=None;self.closed=False;self.active_page=0
        self.action_buttons=[];self.screen_vars={};self.project_vars={};self.public_log=[]
        self.percent_entries=[];self._input_states=[];self._inputs_locked=False;self.loaded_form=None;self._filling=False;self._layout_after=None
        self._status_pulse=0.0;self._status_pulse_after=None;self._status_pulse_started=time.perf_counter()
        self._logo_after=None;self._logo_phase=0;self._logo_started=time.perf_counter()
        self._firmware_label='—';self._count_value='—'
        self.loot_data=b'';self.loot_rows=[];self.loot_source=None;self.loot_index=None
        self.firmware=find_firmware_source()
        setup(root);root.title('EVILKEY Manager');root.configure(bg=BG)
        if os.name=='nt':
            ico=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets'/'evilkey.ico'
            if ico.is_file():
                try:root.iconbitmap(str(ico))
                except tk.TclError:pass
        sw,sh=root.winfo_screenwidth(),root.winfo_screenheight()
        w=min(S(1440),sw-S(40));h=min(S(960),sh-S(75))
        root.geometry(f'{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}')
        root.minsize(min(S(1050),sw-S(40)),min(S(690),sh-S(75)))
        self.owner=tk.BooleanVar(value=False);self.owner.trace_add('write',lambda *_:self.refresh_enabled())
        self.auth=tk.StringVar(value='PIN on device');self.protocol=tk.StringVar(value='Auto (prefer 2)')
        self.device_label=tk.StringVar(value="Select USB Key");self.usb_label=tk.StringVar(value='—')
        self.status=tk.StringVar(value="Connect the device and select Search USB.")
        self.connection=tk.StringVar(value="Demo mode · no device connected" if demo else "Device not connected")
        self.summary=tk.StringVar(value="Read the device to view its settings.")
        self.pin_status=tk.StringVar(value="Read the key first.")
        self.screen_status=tk.StringVar(value="Read display settings from the device.")
        self.drive_status=tk.StringVar(value="Read Manager Drive mode.")
        self.drive_read_only=tk.BooleanVar(value=False)
        self.drive_loaded=None
        self.count=tk.StringVar(value="The list has not been read.")
        self.build()
        if demo:
            from .demo import DemoRunner
            self.runner=DemoRunner(root,self.progress,self.done)
        else:self.runner=JobRunner(Path(__file__).resolve().parents[1]/'run_manager.py',self.progress,self.done)
        self.refresh_enabled();root.protocol('WM_DELETE_WINDOW',self.close)
        self._pump_handle=root.after(60,self.pump)
        self._scan_handle=root.after(200,lambda:self.submit('scan')) if demo else None
        root.bind('<Destroy>',self.destroyed,add='+')
        root.bind_all('<MouseWheel>',self.wheel,add='+');root.bind_all('<Button-4>',self.wheel,add='+');root.bind_all('<Button-5>',self.wheel,add='+')
        root.bind('<Control-s>',lambda _:self.save_shortcut())
        root.bind('<F5>',lambda _:self.request_info())
        self.book.select(0)
        self._logo_after=root.after(24,self.animate_logo)

    def animate_logo(self):
        self._logo_after=None
        if self.closed:return
        if self.root.winfo_ismapped():
            phase=int((time.perf_counter()-self._logo_started)/0.024)%256
            if phase!=self._logo_phase:
                self._logo_phase=phase
                if self.logo_overview.winfo_ismapped():self.logo_overview.show_frame(phase)
        self._logo_after=self.root.after(24,self.animate_logo)

    def build(self):
        # Compact product header: logo, product name and one calm connection indicator.
        header=tk.Frame(self.root,bg=NAVY,height=S(78));header.pack(fill='x');header.pack_propagate(False)
        brand=tk.Frame(header,bg=NAVY);brand.pack(side='left',fill='y',padx=(S(24),S(8)))
        self.logo_header=Logo(brand,'evilkey_logo_header.png',bg=NAVY)
        self.logo_header.pack(side='left',padx=(0,S(12)),pady=S(7))
        titles=tk.Frame(brand,bg=NAVY);titles.pack(side='left',fill='y',pady=S(13))
        Label(titles,'EVILKEY Manager',24,True,INK,NAVY).pack(anchor='w')
        Label(titles,"Safe key management in one place.",12,False,MUTED,NAVY).pack(anchor='w',pady=(S(2),0))

        statuspill=tk.Canvas(header,width=S(232),height=S(42),bg=NAVY,highlightthickness=0)
        statuspill.pack(side='right',padx=(S(8),S(24)),pady=S(18))
        self.dot=tk.Canvas(header,width=1,height=1,bg=NAVY,highlightthickness=0);self.dot.place_forget()
        self._statuspill=statuspill
        self._statuspill.bind('<Configure>',lambda _:self._render_connection_pill())

        # System-style connection panel. Authentication lives in the same surface,
        # reducing vertical fragmentation without changing any control semantics.
        top_wrap=tk.Frame(self.root,bg=BG);top_wrap.pack(fill='x',padx=S(24),pady=(S(16),S(10)))
        top_card=Card(top_wrap,padding=18);top_card.pack(fill='x')
        top=top_card.body
        top.columnconfigure(0,weight=5)
        top.columnconfigure(1,weight=1)
        top.columnconfigure(4,weight=2)
        for c,label in [(0,"Device"),(1,'USB'),(4,"Protocol mode")]:
            Label(top,label,11,bold=True,color=MUTED,bg=WHITE).grid(row=0,column=c,sticky='w',pady=(0,S(6)))
        self.device_combo=ttk.Combobox(top,textvariable=self.device_label,state='readonly',width=31)
        self.device_combo.grid(row=1,column=0,sticky='ew',padx=(0,S(16)));self.device_combo.bind('<<ComboboxSelected>>',self.selected_device)
        self.usb_field=ttk.Entry(top,textvariable=self.usb_label,state='readonly',width=11,justify='center');self.usb_field.grid(row=1,column=1,padx=(0,S(16)),sticky='ew')
        self.scan_btn=Button(top,'Search USB',self.request_scan,name='search',width=162);self.scan_btn.grid(row=1,column=2,padx=(0,S(10)))
        self.info_btn=Button(top,"Read device",self.request_info,kind='primary',name='usb',width=176);self.info_btn.grid(row=1,column=3,padx=(0,S(16)))
        self.proto_combo=ttk.Combobox(top,textvariable=self.protocol,values=['Auto (prefer 2)',"Protocol 1","Protocol 2"],state='readonly',width=17);self.proto_combo.grid(row=1,column=4)
        sep=tk.Frame(top,bg=BORDER,height=1);sep.grid(row=2,column=0,columnspan=5,sticky='ew',pady=(S(16),S(13)))
        authbar=tk.Frame(top,bg=WHITE);authbar.grid(row=3,column=0,columnspan=5,sticky='ew')
        self.owner_box=Toggle(authbar,self.owner,"I authorize managing this device",width=470);self.owner_box.pack(side='left')
        self.auth_combo=ttk.Combobox(authbar,textvariable=self.auth,values=['PIN on device','PIN on computer'],state='readonly',width=20);self.auth_combo.pack(side='right');self.auth_combo.bind('<<ComboboxSelected>>',lambda _:self.refresh_enabled())
        Label(authbar,'Operation confirmation',12,color=MUTED,bg=WHITE).pack(side='right',padx=S(12))

        # Segmented navigation.
        self.nav=tk.Frame(self.root,bg=BG);self.nav.pack(fill='x',padx=S(24),pady=(0,S(12)))
        nav_back=tk.Canvas(self.nav,bg=BG,highlightthickness=0,height=S(52));nav_back.place(x=0,y=0,relwidth=1,relheight=1)
        nav_back.bind('<Configure>',lambda e:(nav_back.delete('all'),rounded(nav_back,S(1),S(1),e.width-S(2),e.height-S(2),S(14),fill=WHITE,outline=BORDER)))

        stack=tk.Frame(self.root,bg=BG);stack.pack(fill='both',expand=True,padx=S(24))

        # Bottom status remains visible but visually quiet.
        statusbar=tk.Frame(self.root,bg=BG,height=S(48));statusbar.pack(side='bottom',fill='x',padx=S(24),pady=(S(8),S(12)))
        status_card=Card(statusbar,padding=11);status_card.pack(fill='x')
        sb=status_card.body
        self.progressbar=ttk.Progressbar(sb,mode='indeterminate',length=S(112));self.progressbar.pack(side='left',padx=(0,S(14)))
        self.cancel_btn=Button(sb,"Cancel",self.cancel,name='close',height=34);self.cancel_btn.pack(side='right')
        lab=Label(sb,textvariable=self.status,size=12,color=MUTED,bg=WHITE,wraplength=S(960));lab.pack(side='left',fill='x',expand=True);lab.bind('<Configure>',lambda e:lab.configure(wraplength=max(S(200),e.width-S(8))))

        self.book=Book(self,stack);self.scrolls=[];self.pages=[];self.footers=[]
        for title,symbol in [("Overview",'home'),('PIN & policies','lock'),("Credentials",'card'),("Display",'monitor'),('Firmware','chip'),("USB Tool data",'file'),("Service",'tool')]:
            sc,ft=self.book.add(title,symbol);self.scrolls.append(sc);self.pages.append(sc.body);self.footers.append(ft)
        self.build_overview();self.build_security();self.build_credentials();self.build_display();self.build_project();self.build_loot();self.build_service()
        self._render_connection_pill();self._schedule_status_pulse()

    def _connection_is_live(self):
        return bool(self.info) and not self.demo

    def _render_connection_pill(self):
        if not hasattr(self,'_statuspill') or not self._statuspill.winfo_exists():return
        c=self._statuspill;c.delete('all')
        w=max(S(210),c.winfo_width() or S(210));h=max(S(40),c.winfo_height() or S(40))
        connected=self._connection_is_live()
        fill=ACCENT_SOFT if connected else WHITE
        border='#315149' if connected else BORDER
        dot=TEAL if connected else MUTED
        text="Device connected" if connected else "No active connection"
        rounded(c,S(1),S(1),w-S(2),h-S(2),S(18),fill=fill,outline=border)
        cx=S(21);cy=h/2
        if connected:
            pulse=max(0.0,min(1.0,float(self._status_pulse)))
            rr=S(8.0+3.0*pulse)
            ring=mix('#315149',TEAL,0.45*(1.0-pulse))
            c.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,outline=ring,width=1)
        radius=S(5)
        c.create_oval(cx-radius,cy-radius,cx+radius,cy+radius,fill=dot,outline='')
        c.create_text(S(40),h/2,anchor='w',text=text,font=F(12,'normal'),fill=INK if connected else MUTED)
        if connected:icon(c,'check',w-S(31),h/2-S(9),S(17),TEAL)

    def _schedule_status_pulse(self):
        if self.closed:return
        connected=self._connection_is_live()
        if connected:
            elapsed=time.perf_counter()-self._status_pulse_started
            self._status_pulse=(1.0-math.cos((elapsed%2.4)/2.4*math.tau))*0.5
            delay=40
        else:
            self._status_pulse=0.0;delay=250
        self._render_connection_pill()
        try:self._status_pulse_after=self.root.after(delay,self._schedule_status_pulse)
        except tk.TclError:self._status_pulse_after=None

    def action(self,parent,text,command,condition=lambda:True,kind='secondary',name=None,side='left'):
        b=Button(parent,text,command,kind=kind,name=name);b.pack(side=side,padx=(0,S(10)),pady=S(3));self.action_buttons.append((b,condition));return b
    def body_card(self,page,title,subtitle='',symbol=None):
        c=Card(page);c.pack(fill='x',pady=(0,S(12)));c.title(title,subtitle,symbol);return c.body
    def note(self,parent,text,color=MUTED):
        l=Label(parent,text,13,color=color);l.pack(fill='x',pady=(S(6),S(7)));l.bind('<Configure>',lambda e:l.configure(wraplength=max(S(160),e.width-S(8))));return l
    def row(self,parent):
        r=tk.Frame(parent,bg=WHITE);r.pack(fill='x',pady=S(5));return r

    def build_overview(self):
        page=self.pages[0]
        hero=Card(page,padding=22);hero.pack(fill='x',pady=(0,S(12)))
        b=hero.body
        top=tk.Frame(b,bg=WHITE);top.pack(fill='x')
        text_col=tk.Frame(top,bg=WHITE);text_col.pack(side='left',fill='both',expand=True)
        head=tk.Frame(text_col,bg=WHITE);head.pack(fill='x')
        self.logo_overview=AnimatedLogo(head,bg=WHITE)
        self.logo_overview.pack(side='left',padx=(0,S(16)))
        copy=tk.Frame(head,bg=WHITE);copy.pack(side='left',fill='x',expand=True,pady=(S(15),0))
        Label(copy,"Your EVILKEY",22,True).pack(anchor='w')
        Label(copy,textvariable=self.connection,size=13,color=TEAL,bg=WHITE).pack(anchor='w',pady=(S(4),0))
        summary=Label(text_col,textvariable=self.summary,size=14,color=MUTED,bg=WHITE,wraplength=S(760))
        summary.pack(fill='x',pady=(S(16),S(2)))
        summary.bind('<Configure>',lambda e:summary.configure(wraplength=max(S(400),e.width-S(8))))
        self.note(text_col,"Changing settings requires PIN confirmation. Reading device information does not modify stored data.")
        stats=tk.Frame(page,bg=BG);stats.pack(fill='x',pady=(0,S(12)));self.stats={}
        for i,(key,title,symbol) in enumerate([('firmware','Firmware version','chip'),('pin','PIN protection','lock'),('creds',"Credentials",'card')]):
            stats.columnconfigure(i,weight=1,uniform='stats');c=Card(stats,padding=18);c.grid(row=0,column=i,sticky='nsew',padx=(0,S(10) if i<2 else 0))
            head=tk.Frame(c.body,bg=WHITE);head.pack(fill='x')
            IconBadge(head,symbol,38).pack(side='left',padx=(0,S(11)))
            Label(head,title,12,True,MUTED).pack(side='left')
            v=tk.StringVar(value='—');self.stats[key]=v
            Label(c.body,textvariable=v,size=27,bold=True).pack(anchor='w',pady=(S(14),S(3)))

        b=self.body_card(page,"Device Information","Supported features and current status read directly from the key.",'usb')
        self.capabilities=ttk.Treeview(b,columns=('field','value'),show='headings',height=5,selectmode='none')
        self.capabilities.heading('field',text='Feature');self.capabilities.heading('value',text='Status')
        self.capabilities.column('field',width=S(370));self.capabilities.column('value',width=S(600));self.capabilities.pack(fill='x',pady=(S(8),0))
        f=self.footers[0];self.action(f,"Check Connection",lambda:self.submit('ping'),lambda:bool(self.info),name='refresh');self.action(f,"Save Information",self.save_report,lambda:bool(self.info),name='export')

    def build_security(self):
        page=self.pages[1];b=self.body_card(page,"PIN and access rules","Manage the PIN code and the login confirmation method.",'lock')
        Label(b,textvariable=self.pin_status,size=15,wraplength=S(1100)).pack(fill='x',pady=(0,S(14)))
        row=self.row(b);self.action(row,'Set PIN',lambda:self.pin_dialog(False),lambda:self.owned() and self.opts().get('clientPin') is False,kind='primary',name='lock');self.action(row,"Change PIN",lambda:self.pin_dialog(True),lambda:self.owned() and self.opts().get('clientPin') is True,name='edit')
        self.note(b,"The PIN consists of digits 0–9. The setting and change of the PIN are performed in the protected form on the computer.")
        b=self.body_card(page,"User Verification")
        self.always=tk.BooleanVar();Toggle(b,self.always,"Require verification on each login",width=600).pack(anchor='w')
        r=self.row(b);self.action(r,"Save verification requirement",self.always_apply,lambda:self.has_auth() and self.opts().get('authnrCfg') and 'alwaysUv' in self.opts())
        b=self.body_card(page,'PIN policy')
        r=self.row(b);Label(r,'Minimum digits',15).pack(side='left',padx=(0,S(20)));self.minimum=tk.StringVar(value='4');ttk.Spinbox(r,from_=4,to=63,textvariable=self.minimum,width=6).pack(side='left')
        self.force=tk.BooleanVar();Toggle(r,self.force,"Force PIN change",width=280).pack(side='left',padx=S(22))
        self.note(b,"Relying parties allowed to read the minimum PIN length — one domain per line:")
        self.rp_text=tk.Text(b,height=3,font=F(14),bg=INPUT_BG,fg=INK,insertbackground=INK,relief='flat',highlightthickness=1,highlightbackground=BORDER,highlightcolor=TEAL,padx=S(12),pady=S(10));self.rp_text.pack(fill='x')
        self.note(b,"This is not a sign-in allowlist. Saving replaces the entire list; an empty field clears it. This command cannot lower the minimum PIN length.")
        r=self.row(b);self.action(r,"Save PIN rules",self.policy_apply,lambda:self.has_auth() and self.opts().get('setMinPINLength') and self.opts().get('authnrCfg'))
        b=self.body_card(page,"Credential storage")
        self.rk_enabled=tk.BooleanVar(value=True);self.mcuv_allowed=tk.BooleanVar(value=False)
        Toggle(b,self.rk_enabled,"Store credentials on device",width=550).pack(anchor='w')
        r=self.row(b);self.action(r,"Save credential setting",lambda:self.vendor_apply('resident_keys'),lambda:self.has_auth() and 0x00052b41f53590d3 in (self.info or {}).get('vendor_commands',[]))
        Toggle(b,self.mcuv_allowed,"Allow registration without verification when the service does not require it",width=830).pack(anchor='w',pady=(S(16),0))
        self.note(b,"The second option reduces protection during registration. Physical confirmation remains required.")
        r=self.row(b);self.action(r,"Save registration policy",lambda:self.vendor_apply('makecred_uv'),lambda:self.has_auth() and 0x000377913e17951f in (self.info or {}).get('vendor_commands',[]))

    def build_credentials(self):
        page=self.pages[2];b=self.body_card(page,"Credentials","Discoverable credentials stored on this device.",'card')
        r=self.row(b);self.action(r,"Read list",lambda:self.submit('credentials'),lambda:self.has_auth() and self.opts().get('credMgmt'),kind='primary',name='refresh');self.action(r,"Check capacity",lambda:self.submit('metadata'),lambda:self.has_auth() and self.opts().get('credMgmt'))
        Label(b,textvariable=self.count,size=14,color=MUTED).pack(fill='x',pady=S(12))
        self.filter=tk.StringVar();self.filter.trace_add('write',lambda *_:self.filter_credentials())
        r=self.row(b);Icon(r,'search',22,MUTED).pack(side='left',padx=(0,S(10)));entry=ttk.Entry(r,textvariable=self.filter);entry.pack(side='left',fill='x',expand=True)
        self.note(b,"Filter by service, user or description.")
        tbl=tk.Frame(b,bg=WHITE);tbl.pack(fill='both',expand=True)
        self.credential_table=ttk.Treeview(tbl,columns=('rp','name','display','id'),show='headings',height=7,selectmode='browse')
        for key,title,width in [('rp',"Service",250),('name',"User",210),('display','Display name',280),('id','Identifier',180)]:self.credential_table.heading(key,text=title);self.credential_table.column(key,width=S(width),minwidth=S(80))
        sb=ttk.Scrollbar(tbl,command=self.credential_table.yview);self.credential_table.configure(yscrollcommand=sb.set);self.credential_table.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y');self.credential_table.bind('<<TreeviewSelect>>',lambda _:self.refresh_enabled())
        self.note(b,"This list excludes credentials whose IDs are stored only by the service. Editing a display name here does not change the account on the website.")
        f=self.footers[2];self.action(f,"Edit description",self.rename_credential,lambda:self.has_auth() and bool(self.selected_credential()),name='edit');self.action(f,"Delete credential",self.delete_credential,lambda:self.has_auth() and bool(self.selected_credential()),kind='danger',name='trash')

    def build_display(self):
        page=self.pages[3]
        self.display_grid=tk.Frame(page,bg=BG);self.display_grid.pack(fill='x')
        self.display_left=Card(self.display_grid);self.display_right=Card(self.display_grid)
        self.display_grid.columnconfigure(0,weight=3,uniform='display');self.display_grid.columnconfigure(1,weight=2,uniform='display')
        self.display_left.grid(row=0,column=0,sticky='nsew',padx=(0,S(14)))
        self.display_right.grid(row=0,column=1,sticky='new')
        self._display_wide=True
        b=self.display_left.body;b.columnconfigure(0,weight=1)
        self.display_left.title("Display and sleep","Adjust brightness and screen timing.",'monitor')
        header=self.row(b);self.action(header,"Read Settings",lambda:self.request_display_read(),lambda:self.has_auth() and self.opts().get('authnrCfg'),name='refresh')
        self.screen_badge=Label(b,textvariable=self.screen_status,size=13,color=MUTED);self.screen_badge.pack(fill='x',pady=(S(2),S(8)))
        form=tk.Frame(b,bg=WHITE);form.pack(fill='x');form.columnconfigure(2,weight=1);form.columnconfigure(3,minsize=S(92))
        fields=[('brightness',"Screen brightness",'sun',8,255,'%'),('dim_brightness',"Dimmed brightness",'sun',1,32,'%'),('dim_seconds',"Dim after inactivity",'clock',0,3600,'s'),('off_seconds',"Turn off after dimming",'clock',0,3600,'s'),('presence_seconds',"Confirmation timeout",'clock',1,120,'s'),('uv_seconds','PIN entry timeout','clock',15,120,'s')]
        defaults=DisplaySettings()
        for i,(key,text,symbol,low,high,unit) in enumerate(fields):
            v=tk.StringVar(value=str(getattr(defaults,key)));self.screen_vars[key]=v
            Label(form,text,14).grid(row=i,column=0,sticky='w',padx=(0,S(15)),pady=S(6))
            Icon(form,symbol,21,MUTED).grid(row=i,column=1,padx=(0,S(16)))
            Slider(form,v,low,high,steps=[0,5,10,15,30,45,60,90,120,180,300,600,900,1800,3600] if key in ('dim_seconds','off_seconds') else None).grid(row=i,column=2,sticky='ew',padx=(0,S(14)))
            if unit=='%':entry=PercentEntry(form,v,low,high);self.percent_entries.append(entry);entry.display.trace_add('write',lambda *_:self.form_changed())
            else:entry=ttk.Spinbox(form,from_=low,to=high,textvariable=v,width=8,justify='right')
            entry.grid(row=i,column=3,sticky='ew');Label(form,unit,13,color=MUTED).grid(row=i,column=4,padx=(S(8),0),sticky='w')
        self.screen_vars['accent_rgb']=tk.StringVar(value='#4DE3C1')
        Label(form,'Accent color',14).grid(row=6,column=0,sticky='w',pady=S(14));Icon(form,'palette',22,MUTED).grid(row=6,column=1,padx=(0,S(16)))
        colorrow=tk.Frame(form,bg=WHITE);colorrow.grid(row=6,column=2,columnspan=3,sticky='w')
        self.color_chip=tk.Canvas(colorrow,width=S(30),height=S(30),highlightthickness=1,highlightbackground=BORDER,bg='#4DE3C1');self.color_chip.pack(side='left',padx=(0,S(10)));self.color_chip.bind('<Button-1>',lambda _:self.pick_color())
        ttk.Entry(colorrow,textvariable=self.screen_vars['accent_rgb'],width=10).pack(side='left');Button(colorrow,"Select",self.pick_color,width=96,height=38).pack(side='left',padx=S(10))
        self.screen_vars['animation']=tk.BooleanVar(value=True);Toggle(b,self.screen_vars['animation'],'Animate while processing',width=530).pack(anchor='w',pady=(S(10),S(7)))
        r=self.row(b);Icon(r,'check',22,TEAL).pack(side='left',padx=(0,S(10)));Label(r,"Touch awakens the screen — always active",14).pack(side='left')
        self.note(b,'0 s = never. Minimum automatic dim and screen-off delay: 5 s.')
        rb=self.display_right.body;self.display_right.title("Screen Preview",name='eye')
        self.preview=ScreenPreview(rb);self.preview.pack(fill='x',pady=(S(5),S(16)))
        helpbox=tk.Frame(rb,bg=PALE,padx=S(18),pady=S(18));helpbox.pack(fill='x')
        Label(helpbox,"How does it work?",16,True,INK,PALE).pack(anchor='w')
        self.preview_text=tk.StringVar();self.help_label=Label(helpbox,textvariable=self.preview_text,size=14,color=INK,bg=PALE,wraplength=S(410));self.help_label.pack(fill='x',pady=(S(10),0));self.help_label.bind('<Configure>',lambda e:self.help_label.configure(wraplength=max(S(200),e.width-S(8))))
        self.note(rb,"The first touch wakes the screen without activating a button or entering a PIN digit.")
        self.display_grid.bind('<Configure>',lambda _:self.schedule_reflow())
        for v in self.screen_vars.values():v.trace_add('write',lambda *_:self.form_changed())
        md=self.body_card(page,'Manager Drive / microSD',"Write mode for the microSD card exposed over USB Mass Storage.",'usb')
        self.note(md,"The microSD card is available for reading and writing by default. After placing the needed files on it, you can enable write protection. The change requires PIN confirmation.")
        Toggle(md,self.drive_read_only,'Read only — block USB host writes to microSD',width=760).pack(anchor='w',pady=(S(4),S(8)))
        self.drive_read_only.trace_add('write',lambda *_:self.drive_changed())
        Label(md,textvariable=self.drive_status,size=13,color=MUTED).pack(fill='x',pady=(S(2),S(8)))
        mr=self.row(md)
        self.action(mr,"Read Mode",lambda:self.submit('drive_read'),lambda:self.has_auth() and self.opts().get('authnrCfg'),name='refresh')
        self.action(mr,"Save microSD mode",self.drive_write,lambda:self.has_auth() and bool(self.drive_record) and self.drive_record.get('storage_ok') and self.drive_dirty(),kind='primary',name='save')
        self.note(md,"Firmware enforces write protection immediately. Windows may update the read-only indicator only after reconnection or toggling Manager Drive on the device.")
        f=self.footers[3]
        self.save_btn=self.action(f,"Save Changes",self.display_write,lambda:self.has_auth() and bool(self.display_record) and self.display_record.get('storage_ok') and self.display_dirty(),kind='primary',name='save')
        self.action(f,"Restore defaults",self.restore_defaults,lambda:self.display_record is not None,name='refresh')
        self.action(f,"Export Settings",self.export_display,lambda:self.display_record is not None,name='export')
        self.action(f,"Import Settings",self.import_display,lambda:self.display_record is not None,name='import')
        self.update_preview()

    def build_project(self):
        page=self.pages[4];b=self.body_card(page,'Firmware configuration',"Choose device features and export an Arduino project for building.",'chip')
        self.note(b,"Export creates a separate Arduino project. Changes take effect after you build and flash it. Brightness and screen timing can be changed directly on the Display tab. Air Mouse is included in the firmware and configured on the key. Exit Air Mouse to reconnect Manager in FIDO mode.")
        r=self.row(b);self.action(r,"Load configuration",self.import_header,name='import');self.action(r,'Export project',self.export_source,kind='primary',name='export')
        labels={
            'FIDO_V1_USB_PROFILE':"USB Key Profile",
            'FIDO_V1_CUSTOM_VID':'Vendor ID (VID)',
            'FIDO_V1_CUSTOM_PID':'Product ID (PID)',
            'FIDO_V1_CUSTOM_PRODUCT':"Device name shown by the OS",
            'FIDO_V1_CUSTOM_MANUFACTURER':'USB manufacturer name',
            'FIDO_V1_CUSTOM_BCD_DEVICE':"USB device version",
            'FIDO_V1_MANAGEMENT_SERIAL':"Management serial number",
            'FIDO_V1_MANAGER_DRIVE':"Manager Drive support",
            'FIDO_V1_MANAGER_DRIVE_DEFAULT':"Enable Manager Drive at startup",
            'FIDO_V1_MANAGER_DRIVE_READ_ONLY_DEFAULT':"Default write protection",
            'FIDO_V1_MANAGER_DRIVE_SD_HZ':"MicroSD card speed (Hz)",
            'FIDO_V1_MANAGER_DRIVE_VID':'Manager Drive vendor ID (VID)',
            'FIDO_V1_MANAGER_DRIVE_PID':'Manager Drive product ID (PID)',
            'FIDO_V1_MANAGER_DRIVE_PRODUCT':'Manager Drive name shown by the OS',
            'FIDO_V1_MANAGER_DRIVE_MANUFACTURER':'Manager Drive USB manufacturer',
            'FIDO_V1_MANAGER_DRIVE_BCD_DEVICE':'Manager Drive USB version',
            'FIDO_V1_USB_TOOL':"USB Tool Support",
            'FIDO_V1_USB_TOOL_DEFAULT':"Enable USB Tool on startup",
            'FIDO_V1_USB_TOOL_VARIABLE_EXFIL':"Capture script variable values",
            'FIDO_V1_USB_TOOL_KEYSTROKE_REFLECTION':"Receive feedback from the computer",
            'FIDO_V1_USB_TOOL_LAYOUT_DEFAULT':"Built-in keyboard layout",
            'FIDO_V1_USB_TOOL_LANGUAGE_DEFAULT':"Default Script Language Code",
            'FIDO_V1_USB_TOOL_SD_HZ':"MicroSD card speed (Hz)",
            'FIDO_V1_USB_TOOL_MAX_PAYLOAD':'Maximum script size (B)',
            'FIDO_V1_USB_TOOL_VID':'USB Tool vendor ID (VID)',
            'FIDO_V1_USB_TOOL_PID':'USB Tool product ID (PID)',
            'FIDO_V1_USB_TOOL_PRODUCT':'USB Tool name shown by the OS',
            'FIDO_V1_USB_TOOL_MANUFACTURER':'USB Tool manufacturer name',
            'FIDO_V1_USB_TOOL_BCD_DEVICE':'USB Tool device version',
            'FIDO_V1_DISPLAY':"AMOLED Screen",
            'FIDO_V1_TOUCH_CONFIRM':'Touchscreen confirmation',
            'FIDO_V1_LOCAL_UV':"PIN on the key screen",
            'FIDO_V1_BOOT_CONFIRM_FALLBACK':'BOOT button confirmation fallback',
            'FIDO_V1_BRIGHTNESS':"Screen brightness (8–255)",
            'FIDO_V1_DIM_BRIGHTNESS':"Brightness after dimming (1-32)",
            'FIDO_V1_DIM_AFTER_SECONDS':"Dimmer after idle (s)",
            'FIDO_V1_OFF_AFTER_DIM_SECONDS':'Turn off after dimming (s)',
            'FIDO_V1_PRESENCE_TIMEOUT_SECONDS':"Confirmation time (s)",
            'FIDO_V1_UV_TIMEOUT_SECONDS':'PIN entry timeout (s)',
            'FIDO_V1_GUI_ACCENT_RGB':'Accent color (RGB)',
            'FIDO_V1_GUI_ANIMATION':'Processing animation',
        }
        identity=['FIDO_V1_USB_PROFILE','FIDO_V1_CUSTOM_VID','FIDO_V1_CUSTOM_PID','FIDO_V1_CUSTOM_PRODUCT','FIDO_V1_CUSTOM_MANUFACTURER','FIDO_V1_CUSTOM_BCD_DEVICE','FIDO_V1_MANAGEMENT_SERIAL']
        manager_drive=['FIDO_V1_MANAGER_DRIVE','FIDO_V1_MANAGER_DRIVE_DEFAULT','FIDO_V1_MANAGER_DRIVE_READ_ONLY_DEFAULT','FIDO_V1_MANAGER_DRIVE_SD_HZ','FIDO_V1_MANAGER_DRIVE_VID','FIDO_V1_MANAGER_DRIVE_PID','FIDO_V1_MANAGER_DRIVE_PRODUCT','FIDO_V1_MANAGER_DRIVE_MANUFACTURER','FIDO_V1_MANAGER_DRIVE_BCD_DEVICE']
        usb_tool=['FIDO_V1_USB_TOOL','FIDO_V1_USB_TOOL_DEFAULT','FIDO_V1_USB_TOOL_VARIABLE_EXFIL','FIDO_V1_USB_TOOL_KEYSTROKE_REFLECTION','FIDO_V1_USB_TOOL_LAYOUT_DEFAULT','FIDO_V1_USB_TOOL_LANGUAGE_DEFAULT','FIDO_V1_USB_TOOL_SD_HZ','FIDO_V1_USB_TOOL_MAX_PAYLOAD','FIDO_V1_USB_TOOL_VID','FIDO_V1_USB_TOOL_PID','FIDO_V1_USB_TOOL_PRODUCT','FIDO_V1_USB_TOOL_MANUFACTURER','FIDO_V1_USB_TOOL_BCD_DEVICE']
        screen=[k for k in DEFAULTS if k not in identity and k not in manager_drive and k not in usb_tool]
        self.project_choices={
            'FIDO_V1_USB_PROFILE':{0:'Local profile',1:"FIDO compatibility",2:'EvilKey'},
            'FIDO_V1_USB_TOOL_LAYOUT_DEFAULT':{0:'English (US)',1:'Polish (PL)',2:'German (DE)',3:'French (FR)',4:"Spanish (ES)"},
        }
        groups=[
            ("USB identity",'Device name and identifiers shown to the computer.',identity),
            ('Manager Drive',"Expose the microSD card as USB storage.",manager_drive),
            ('USB Tool', 'USB keyboard, scripts, and data capture on microSD.',usb_tool),
            ("Display and confirmation","Initial display and confirmation settings.",screen),
        ]
        for title,description,keys in groups:
            b=self.body_card(page,title,description);b.columnconfigure(1,weight=1)
            form=tk.Frame(b,bg=WHITE);form.pack(fill='x');form.columnconfigure(1,weight=1)
            for i,k in enumerate(keys):
                value=DEFAULTS[k]
                shown=self.project_choices[k][value] if k in self.project_choices else f'0x{value:X}' if k in HEX_FIELDS else str(value)
                v=tk.BooleanVar(value=bool(value)) if k in BOOL_FIELDS else tk.StringVar(value=shown)
                self.project_vars[k]=v
                l=Label(form,labels[k],14,wraplength=S(430));l.grid(row=i,column=0,sticky='w',pady=S(8),padx=(0,S(30)))
                if k in BOOL_FIELDS:control=Toggle(form,v,width=160)
                elif k in self.project_choices:control=ttk.Combobox(form,values=list(self.project_choices[k].values()),state='readonly',textvariable=v,width=34)
                else:control=ttk.Entry(form,textvariable=v,width=36)
                control.grid(row=i,column=1,sticky='w')
        b=self.body_card(page,'Before flashing');self.note(b,"Settings already stored on the device take precedence over project defaults. Switching Manager Drive or USB Tool restarts USB. Custom VID/PID values must match the intended USB identity and do not imply certification.")

    def build_loot(self):
        page=self.pages[5]
        b=self.body_card(page,"USB Tool data","Open data from the microSD card and export it as CSV.",'file')
        self.loot_mode=tk.StringVar(value='Automatic with index file (.idx)')
        self.loot_summary=tk.StringVar(value='No file loaded.')
        r=self.row(b)
        ttk.Combobox(r,textvariable=self.loot_mode,state='readonly',width=42,values=['Automatic with index file (.idx)',"Variable values — 16-bit numbers","Return data — bytes"]).pack(side='left',padx=(0,S(12)))
        self.action(r,"Open data file",self.open_loot,name='import')
        self.action(r,'Export CSV',self.export_loot,lambda:bool(self.loot_rows),name='export')
        self.loot_mode.trace_add('write',lambda *_:self.refresh_loot())
        Label(b,textvariable=self.loot_summary,size=13,color=MUTED,wraplength=S(1050)).pack(fill='x',pady=(S(12),S(8)))
        frame=tk.Frame(b,bg=WHITE);frame.pack(fill='both',expand=True)
        self.loot_table=ttk.Treeview(frame,columns=('index','segment','format','offset','hex','value','ascii'),show='headings',height=11,selectmode='browse')
        for key,title,width in [('index','#',70),('segment','Segment',85),('format','Format',150),('offset','Offset',100),('hex','Bytes',130),('value',"Value",150),('ascii','ASCII',80)]:
            self.loot_table.heading(key,text=title);self.loot_table.column(key,width=S(width),minwidth=S(65),anchor='center')
        sb=ttk.Scrollbar(frame,command=self.loot_table.yview);self.loot_table.configure(yscrollcommand=sb.set)
        self.loot_table.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y')
        self.note(b,"A matching .idx file identifies data formats automatically. Manager checks file size and SHA-256. Without an index, choose the format manually. The table shows up to 4,096 records; CSV export includes the full file.")

    def _loot_mode_id(self):
        if self.loot_mode.get().startswith('Automatic'):return INDEXED_MODE
        return VARIABLE_MODE if self.loot_mode.get().startswith("Variable values") else REFLECTION_MODE

    def open_loot(self):
        path=filedialog.askopenfilename(parent=self.root,title="Open USB Tool data",filetypes=[("USB Tool data",'*.bin'),('All files','*.*')])
        if not path:return
        try:
            source=Path(path);data=read_loot(source);index=read_loot_index(source,data)
            self.loot_source=source;self.loot_data=data;self.loot_index=index
            if index is not None:self.loot_mode.set('Automatic with index file (.idx)')
            elif self._loot_mode_id()==INDEXED_MODE:self.loot_mode.set("Variable values — 16-bit numbers")
            else:self.refresh_loot()
        except (OSError,UserError) as e:messagebox.showerror("Data from USB Tool",str(e),parent=self.root)

    def refresh_loot(self):
        if not hasattr(self,'loot_table') or self.loot_source is None:return
        try:self.loot_rows=decode_rows(self.loot_data,self._loot_mode_id(),self.loot_index)
        except UserError as e:self.loot_rows=[];self.loot_summary.set(str(e))
        else:self.loot_summary.set(f'{self.loot_source.name} · {describe(self.loot_data,self._loot_mode_id(),self.loot_index)}')
        self.loot_table.delete(*self.loot_table.get_children())
        for row in self.loot_rows[:4096]:self.loot_table.insert('', 'end', values=(row['index'],row['segment'],row['format'],row['offset'],row['hex'],row['value'],row['ascii']))
        self.refresh_enabled()

    def export_loot(self):
        if not self.loot_rows:return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.csv',initialfile='loot.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        try:export_csv(Path(path),self.loot_rows,self._loot_mode_id())
        except OSError as e:messagebox.showerror("Data from USB Tool",str(e),parent=self.root)

    def build_service(self):
        page=self.pages[6];b=self.body_card(page,"Service","Application information and operations requiring special attention.",'tool')
        Label(b,f'EVILKEY Manager  {__version__}',20,True).pack(anchor='w');self.note(b,"USB key configuration. The application works locally, without an account and without cloud service.")
        r=self.row(b);self.action(r,'Licenses',self.show_licenses,name='info')
        b=self.body_card(page,"Key Reset");self.note(b,"Reset permanently removes the PIN and all FIDO credentials. Before performing, make sure you have a different way of logging into each associated account.")
        r=self.row(b);self.action(r,"Reset FIDO…",self.reset_dialog,lambda:self.owned(),kind='danger',name='trash')
        b=self.body_card(page,'Enterprise Attestation');self.note(b,"Enterprise Attestation can disclose an organizational device identifier. Enable it only if the device supports this feature.")
        r=self.row(b);self.action(r,"Enable Enterprise Attestation…",self.enterprise,lambda:self.has_auth() and 'ep' in self.opts() and self.opts().get('authnrCfg'))
        b=self.body_card(page,'Recent operations');self.log_box=tk.Text(b,height=5,font=F(13),bg=INPUT_BG,fg=MUTED,insertbackground=INK,relief='flat',highlightthickness=1,highlightbackground=BORDER,state='disabled',wrap='word',padx=S(10),pady=S(10));self.log_box.pack(fill='x')

    def reflow(self):
        if not self.root.winfo_exists():return
        if not self.display_grid.winfo_ismapped():return
        wide=self.display_grid.winfo_width()>=S(1190)
        if getattr(self,'_display_wide',None) is wide:return
        self._display_wide=wide
        self.display_left.grid_forget();self.display_right.grid_forget()
        self.display_grid.columnconfigure(0,weight=3 if wide else 1,uniform='display' if wide else '')
        self.display_grid.columnconfigure(1,weight=2 if wide else 0,uniform='display' if wide else '')
        self.display_left.grid(row=0,column=0,sticky='nsew',padx=(0,S(14) if wide else 0))
        self.display_right.grid(row=0 if wide else 1,column=1 if wide else 0,sticky='new',pady=(0 if wide else S(14),0))
    def schedule_reflow(self):
        if self._layout_after:
            try:self.root.after_cancel(self._layout_after)
            except tk.TclError:pass
        self._layout_after=self.root.after(80,self.reflow)
    def wheel(self,e):
        if not hasattr(self,'book'):return
        if e.widget.winfo_class() in ('Text','Treeview','TCombobox','TSpinbox','TEntry'):return
        sc=self.scrolls[self.book.index];w=e.widget
        while w is not None and w is not sc:w=getattr(w,'master',None)
        if w is not sc:return
        step=-1 if getattr(e,'num',0)==4 else 1 if getattr(e,'num',0)==5 else (-1 if e.delta>0 else 1)
        if sc.body.winfo_height()>sc.canvas.winfo_height():sc.canvas.yview_scroll(step*3,'units')
    def refresh_enabled(self):
        if not hasattr(self,'runner'):return
        busy=self.runner.busy
        self.lock_form_inputs(busy)
        for b,cond in self.action_buttons:
            try:enabled=not busy and bool(cond())
            except (AttributeError,KeyError,ValueError,tk.TclError,TypeError):enabled=False
            b.configure(state='normal' if enabled else 'disabled')
        self.scan_btn.configure(state='disabled' if busy else 'normal');self.info_btn.configure(state='normal' if not busy and self.device else 'disabled')
        self.device_combo.configure(state='disabled' if busy else 'readonly');self.owner_box.configure(state='normal' if not busy and self.info else 'disabled')
        self.auth_combo.configure(state='disabled' if busy else 'readonly');self.proto_combo.configure(state='disabled' if busy else 'readonly');self.cancel_btn.configure(state='normal' if busy else 'disabled')
    def lock_form_inputs(self,busy):
        if busy==self._inputs_locked:return
        self._inputs_locked=busy
        if busy:
            self._input_states=[]
            def walk(parent):
                for w in parent.winfo_children():
                    if isinstance(w,(ttk.Entry,ttk.Spinbox,ttk.Combobox,Toggle,Slider)):
                        if isinstance(w,(Toggle,Slider)):
                            previous='normal' if w.enabled else 'disabled'
                        else:previous=str(w.cget('state'))
                        self._input_states.append((w,previous));w.configure(state='disabled')
                    elif isinstance(w,tk.Text) and w is self.rp_text:
                        self._input_states.append((w,str(w.cget('state'))));w.configure(state='disabled')
                    walk(w)
            for p in self.pages:walk(p)
        else:
            for w,state in self._input_states:
                if w.winfo_exists():w.configure(state=state)
            self._input_states=[]

    def progress(self,text):
        text=display_text(text,600)
        if self.demo:text="Demo mode · no device connected. "+text.replace("Operation on sample data.",'')
        self.status.set(text)
    def log(self,text):
        self.public_log=(self.public_log+[datetime.now().strftime('%H:%M:%S')+'   '+text])[-60:]
        self.log_box.configure(state='normal');self.log_box.delete('1.0','end');self.log_box.insert('1.0','\n'.join(self.public_log));self.log_box.configure(state='disabled')
    def log_operation(self,op,result):self.log(NAMES.get(op,'Operation')+' — '+result.lower())
    def show_error(self,exc):
        text=str(exc) if isinstance(exc,(UserError,ValueError)) else "The operation failed. Check the file and access permissions."
        self.progress(text);messagebox.showerror('EVILKEY Manager',text,parent=self.root)
    def update_connection(self):
        if self.demo:text="Demo mode · no device connected"
        elif self.info:text="Device connected"
        elif self.device:text="Device selected"
        else:text="Device not connected"
        self.connection.set(text);self._render_connection_pill()
        self.usb_label.set(f"{self.device['vid']:04X}:{self.device['pid']:04X}" if self.device else '—')
    def invalidate(self):
        self._firmware_label='—'
        self.info=None;self.owner.set(False);self.display_record=None;self.loaded_form=None;self.credentials=[]
        self.summary.set("Read the device to view its settings.");self.pin_status.set("Read the device first.");self.screen_status.set("Read display settings from the device.");self.count.set("The list has not been read.")
        for v in self.stats.values():v.set('—')
        self.capabilities.delete(*self.capabilities.get_children());self.filter_credentials();self.refresh_enabled();self.update_connection()
    def discard_prompt(self):
        return not (self.display_dirty() or self.drive_dirty()) or messagebox.askyesno("Unsaved settings","Discard unsaved Display or Manager Drive changes?",parent=self.root)
    def selected_device(self,event=None):
        if self.runner.busy:return
        index=self.device_combo.current()
        if not self.discard_prompt():
            if self.device in self.devices:self.device_combo.current(self.devices.index(self.device))
            return
        self.device=self.devices[index] if 0<=index<len(self.devices) else None;self.invalidate();self.progress("Device selected. Read its settings.")
    def request_scan(self):
        if not self.runner.busy and self.discard_prompt():self.submit('scan')
    def request_info(self):
        if self.device and not self.runner.busy and self.discard_prompt():self.submit('info')
    def request_display_read(self):
        if not self.runner.busy and self.discard_prompt():self.submit('display_read')
    def fill_info(self,data):
        previous=self.info;self.info=data
        if not previous or previous.get('identity')!=data.get('identity'):self.owner.set(False)
        self.display_record=None;self.loaded_form=None;self.screen_status.set("Read display settings from the device.")
        self.drive_record=None;self.drive_loaded=None;self.drive_status.set("Read Manager Drive mode.")
        opts=data['options'];self.rk_enabled.set(bool(opts.get('rk')));self.mcuv_allowed.set(bool(opts.get('makeCredUvNotRqd')));self.always.set(bool(opts.get('alwaysUv')));self.minimum.set(str(data.get('min_pin_length',4)))
        if opts.get('uv') is not True:self.auth.set('PIN on computer')
        self.stats['pin'].set('Set' if opts.get('clientPin') else 'Not set')
        reported=firmware_version_label(data.get('firmware_reported'))
        if reported:self._firmware_label=reported
        self.stats['firmware'].set(self._firmware_label)
        retry=lambda v:'—' if v is None else str(v)
        self.pin_status.set(f"PIN: {'set' if opts.get('clientPin') else 'not set'}   ·   Minimum: {data.get('min_pin_length',4)} digits   ·   PIN attempts: {retry(data.get('pin_retries'))}   ·   On-device attempts: {retry(data.get('uv_retries'))}")
        if data.get('force_pin_change'):self.pin_status.set(self.pin_status.get()+'\nA PIN change is required.')
        if data.get('power_cycle'):self.pin_status.set(self.pin_status.get()+"\nFully power off the device before trying again.")
        self.summary.set(f"USB  {self.device['vid']:04X}:{self.device['pid']:04X}    ·    Confirmation: {'on-device PIN' if opts.get('uv') else 'computer PIN'}")
        self.capabilities.delete(*self.capabilities.get_children())
        rows=[('On-device verification',opts.get('uv')),("Credential management",opts.get('credMgmt')),("Verification on every sign-in",opts.get('alwaysUv')),("Discoverable credentials",opts.get('rk')),('PIN policy changes',opts.get('setMinPINLength'))]
        for k,v in rows:self.capabilities.insert('','end',values=(k,"Enabled" if v else "Disabled" if v is False else "Unavailable"))
        self.update_connection();self.refresh_enabled()
    def done(self,op,result):
        self.progressbar.stop()
        if result.get('type')=='error':
            error=result.get('error',{});self.display_record=None;self.loaded_form=None;self.screen_status.set("Read settings again.");self.drive_record=None;self.drive_loaded=None;self.drive_status.set('Read Manager Drive mode again.')
            if op in MUTATIONS:self.credentials=[];self.filter_credentials()
            if error.get('connection_lost'):self.invalidate()
            text=display_text(error.get('message',"The operation failed."),1400);self.progress(text);self.log_operation(op,"Stopped")
            if not self.closed:messagebox.showerror('Operation stopped',text,parent=self.root)
        else:
            data=result.get('data',{})
            if op=='scan':
                self.devices=data;self.device=None;self.invalidate()
                self.device_combo['values']=[f"{display_text(d['product'],55) or 'FIDO device'}  ·  {d['vid']:04X}:{d['pid']:04X}  ·  {i+1}" for i,d in enumerate(data)]
                self.device_label.set("Select USB Key" if data else "Key not found")
                if len(data)==1:self.device_combo.current(0);self.selected_device()
                self.progress(f'Found {len(data)} devices. Select one and read its information.')
            elif op=='info':self.fill_info(data);self.progress("Device read. To make changes, authorize management of this device.")
            elif op=='ping':self.progress("Connection is working.")
            elif op in ('metadata','credentials'):
                self.count.set(f"Stored: {data['existing']}    ·    Estimated remaining slots: {data['remaining_estimate']}");self.stats['creds'].set(str(data['existing']))
                if op=='credentials':self.credentials=data['credentials'];self.filter_credentials()
                self.progress("Reading complete.")
            elif op in ('display_read','display_write'):
                self.display_record=data;self.fill_display(DisplaySettings.from_dict(data['settings']));self.loaded_form=self.form_values()
                fw=display_text(data.get('firmware',''),30).split(' ')[0].removesuffix('-dev');self._firmware_label=fw or '—';self.stats['firmware'].set(self._firmware_label)
                self.screen_status.set("Settings saved to device" if op=='display_write' else "Settings read from device")
                if not data.get('storage_ok'):self.screen_status.set("Could not save settings. Check device storage.")
                self.progress("Settings saved and verified." if op=='display_write' else "Display settings read.")
            elif op in ('drive_read','drive_write'):
                self.drive_record=data;self.drive_read_only.set(bool(data['settings']['read_only']));self.drive_loaded=bool(data['settings']['read_only'])
                mode='read only' if self.drive_loaded else 'read and write'
                active='ON' if data.get('enabled') else 'OFF'
                self.drive_status.set(f'Manager Drive {active} · microSD: {mode}')
                if not data.get('compiled'):self.drive_status.set("Firmware has no compiled Manager Drive support.")
                elif not data.get('storage_ok'):self.drive_status.set("Could not save Manager Drive settings. Check device storage.")
                self.progress("microSD write protection saved." if op=='drive_write' else "Manager Drive mode read.")
            elif op=='reset':self.invalidate();self.progress("PIN and FIDO credentials removed. Read the key again.")
            else:
                self.display_record=None;self.loaded_form=None;self.screen_status.set("Read settings again.")
                if op in ('delete_credential','rename_credential'):self.credentials=[];self.filter_credentials();self.count.set("Change confirmed. Read the list again.")
                if op in ('set_pin','change_pin','pin_policy','always_uv','enterprise','resident_keys','makecred_uv'):
                    self.info=None;self.owner.set(False);self.pin_status.set("Change confirmed. Read the device again.");self.update_connection()
                self.progress("The setting was already current." if data.get('unchanged') else "Change confirmed. Read current device status.")
            self.log_operation(op,"Finished")
            if result.get('cancel_requested') and op in MUTATIONS:self.progress("The change was confirmed despite the cancellation request. Read key status.")
        self.refresh_enabled()
    def drive_dirty(self):
        return self.drive_loaded is not None and bool(self.drive_read_only.get())!=bool(self.drive_loaded)
    def drive_changed(self):
        if self.drive_record:
            mode='Unsaved change: read only' if self.drive_read_only.get() else 'Unsaved change: read and write'
            self.drive_status.set(mode if self.drive_dirty() else ('Manager Drive ON' if self.drive_record.get('enabled') else 'Manager Drive OFF'))
        self.refresh_enabled()

    def form_values(self):
        return {k:v.get() for k,v in self.screen_vars.items()}
    def display_dirty(self):
        if self.loaded_form is None:return False
        if self.form_values()!=self.loaded_form:return True
        for e in self.percent_entries:
            try:
                if abs(float(e.display.get().replace(',','.'))-int(e.raw.get())*100/255)>0.006:return True
            except (ValueError,tk.TclError):return True
        return False
    def form_changed(self):
        if not self._filling:
            self.update_preview()
            if self.display_record:self.screen_status.set('Unsaved changes' if self.display_dirty() else "Settings match the device")
            self.refresh_enabled()
    def update_preview(self):
        if not hasattr(self,'preview'):return
        try:
            args={k:(v.get() if k=='animation' else int(v.get().lstrip('#'),16) if k=='accent_rgb' else int(v.get())) for k,v in self.screen_vars.items()}
            s=DisplaySettings(**args).validate()
        except (ValueError,tk.TclError,UserError):return
        self.preview.update_settings(s);self.color_chip.configure(bg=f'#{s.accent_rgb:06X}')
        if not s.dim_seconds:text="Automatic dimming and screen off are disabled."
        elif not s.off_seconds:text=f'The screen dims after {s.dim_seconds} s of inactivity. Automatic screen off is disabled.'
        else:text=f'The screen dims after {s.dim_seconds} s of inactivity and turns off {s.off_seconds} s later ({s.dim_seconds+s.off_seconds} s total).'
        self.preview_text.set(text+"\n\nTouching the dimmed or off screen restores full brightness.")
    def fill_display(self,s):
        self._filling=True
        try:
            for k,v in self.screen_vars.items():x=getattr(s,k);v.set(f'#{x:06X}' if k=='accent_rgb' else x if k=='animation' else str(x))
        finally:self._filling=False
        self.form_changed()
    def get_display(self):
        for e in self.percent_entries:e.commit()
        return super().get_display()
    def restore_defaults(self):
        if not self.display_record:return
        self.fill_display(replace(DisplaySettings(),revision=self.display_record['settings']['revision']));self.progress("Defaults loaded into the form. Select Save changes to apply them to the device.")
    def save_shortcut(self):
        if self.active_page==3 and not self.runner.busy and self.has_auth() and self.display_record and self.display_dirty():self.display_write()
    def shutdown_ui(self):
        self.closed=True
        try:self.progressbar.stop()
        except tk.TclError:pass
        # Cancel only application-owned timers.  Child widgets own their short
        # microanimation timers and Tk removes those with the widgets; deleting
        # every Tcl `after` command here can double-delete widget callbacks.
        for name in ('_pump_handle','_scan_handle','_layout_after','_status_pulse_after','_logo_after'):
            handle=getattr(self,name,None)
            if handle:
                try:self.root.after_cancel(handle)
                except tk.TclError:pass
                setattr(self,name,None)

    def destroyed(self,event):
        if event.widget is self.root:self.shutdown_ui()

    def close(self):
        if self.runner.busy:
            if not messagebox.askyesno('Operation in progress',"Cancel the operation and close the application? A change may already have been written and cannot be undone here.",parent=self.root):return
            self.closed=True;self.runner.cancel()
        elif self.discard_prompt():self.shutdown_ui();self.root.destroy()
    def show_licenses(self):
        top=tk.Toplevel(self.root);top.title('Licenses');top.configure(bg=BG);top.geometry(f'{S(720)}x{S(520)}');top.transient(self.root)
        text=tk.Text(top,wrap='word',font=F(13),bg=INPUT_BG,fg=INK,insertbackground=INK,padx=S(20),pady=S(20),relief='flat',highlightthickness=1,highlightbackground=BORDER);text.pack(fill='both',expand=True,padx=S(12),pady=S(12))
        base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'licenses'
        content='EVILKEY Manager '+__version__+"\n\nManager application: EvilKey Manager License 1.0.\nDevice firmware: GNU AGPL version 3 and applicable third-party terms.\n\n"
        if base.is_dir():
            for p in sorted(base.glob('*.txt')):content+='\n'+p.name+'\n'+'─'*40+'\n'+p.read_text(encoding='utf-8',errors='replace')+'\n'
        else:content+="Full licensing information is supplied with the Manager package."
        text.insert('1.0',content);text.configure(state='disabled');Button(top,'Close',top.destroy).pack(pady=(0,S(12)))

def launch(demo=False):
    root=tk.Tk();app=Application(root,demo=demo)
    def callback_error(kind,value,tb):
        # Do not stringify unexpected exceptions or local variables: they can
        # contain PIN values while a dialog callback is executing.
        messagebox.showerror('EVILKEY Manager',"An interface error occurred. Close the application and restart it.",parent=root)
    root.report_callback_exception=callback_error
    root.mainloop()
