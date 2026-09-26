# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Small native Tk controls with explicit keyboard, focus and disabled states."""
from __future__ import annotations
import math
import time
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font as tkfont
from .models import UserError

BG = '#050607'
WHITE = '#0F1113'          # primary elevated surface
INK = '#F5F5F7'
MUTED = '#98989D'
BORDER = '#2A2D31'
NAVY = '#090A0C'
TEAL = '#5EE6C5'
TEAL_DARK = '#46CDB1'
PALE = '#101B19'
RED = '#FF6B67'
SURFACE_ALT = '#15171A'
SURFACE_HOVER = '#1B1E22'
INPUT_BG = '#0B0D0F'
SHADOW = '#000000'
ACCENT_SOFT = '#10201D'
OFF = '#3A3D42'
FACTOR = 1.0
FAMILY = 'Segoe UI'

def S(n): return max(1, round(n * FACTOR))
def F(size=15, weight='normal'): return (FAMILY, -S(size), weight)

def _rgb(value):
    value=value.lstrip('#')
    return tuple(int(value[i:i+2],16) for i in (0,2,4))

def mix(a,b,t):
    """Blend two Tk colours; used for short compositor-like microanimations."""
    t=max(0.0,min(1.0,float(t))); ar=_rgb(a);br=_rgb(b)
    return '#%02X%02X%02X'%tuple(round(x+(y-x)*t) for x,y in zip(ar,br))

def ease(t):
    t=max(0.0,min(1.0,float(t)))
    return t*t*(3.0-2.0*t)

def asset_path(*parts):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return base.joinpath('assets', *parts)

def load_photo(name):
    path = asset_path(name)
    if not path.is_file():
        return None
    try:
        return tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None

class Logo(tk.Label):
    def __init__(self, parent, image_name='evilkey_logo_header.png', bg=BG):
        self.image = load_photo(image_name)
        if self.image is not None:
            super().__init__(parent, image=self.image, bg=bg, bd=0, highlightthickness=0)
        else:
            super().__init__(parent, text='EVILKEY', font=F(16, 'bold'), fg=TEAL, bg=bg)

class ImagePanel(tk.Label):
    def __init__(self, parent, image_name, bg=WHITE):
        self.image = load_photo(image_name)
        if self.image is not None:
            super().__init__(parent, image=self.image, bg=bg, bd=0, highlightthickness=0)
        else:
            super().__init__(parent, bg=bg, bd=0, highlightthickness=0)


class AnimatedLogo(tk.Label):
    """Compact Tk animation backed by the firmware logo's 256-frame sheet."""

    FRAMES = 256
    COLUMNS = 16

    def __init__(self, parent, bg=WHITE):
        self.size = 96
        self.sheet = load_photo('evilkey_logo_overview_animated.png')
        self.image = tk.PhotoImage(width=self.size, height=self.size) if self.sheet else None
        if self.image is not None:
            super().__init__(parent, image=self.image, bg=bg, bd=0, highlightthickness=0)
            self.show_frame(0)
        else:
            self.image = load_photo('evilkey_logo_overview.png')
            if self.image is not None:
                super().__init__(parent, image=self.image, bg=bg, bd=0, highlightthickness=0)
            else:
                super().__init__(parent, text='EVILKEY', font=F(16, 'bold'), fg=TEAL, bg=bg)

    def show_frame(self, phase):
        if self.sheet is None:
            return
        index = phase % self.FRAMES
        left = (index % self.COLUMNS) * self.size
        top = (index // self.COLUMNS) * self.size
        self.tk.call(str(self.image), 'copy', str(self.sheet),
                     '-from', left, top, left + self.size, top + self.size,
                     '-to', 0, 0)

def setup(root):
    global FACTOR, FAMILY
    import os
    if os.name == 'nt':
        # Keep the 1440x960 desktop layout inside the usable monitor area at
        # high Windows DPI. The screen's physical scale remains the upper bound.
        width_fit = max(1.0, (root.winfo_screenwidth() - 40) / 1440)
        height_fit = max(1.0, (root.winfo_screenheight() - 75) / 960)
        FACTOR = min(2.5, root.winfo_fpixels('1i') / 96, width_fit, height_fit)
    else:
        FACTOR = 1.0
    families = set(tkfont.families(root))
    if 'Segoe UI Variable Text' in families:
        FAMILY = 'Segoe UI Variable Text'
    elif 'Segoe UI' in families:
        FAMILY = 'Segoe UI'
    elif 'Inter' in families:
        FAMILY = 'Inter'
    else:
        FAMILY = 'DejaVu Sans'
    root.option_add('*Font', F(15))
    root.option_add('*TCombobox*Listbox.font', F(14))
    root.option_add('*TCombobox*Listbox.background', SURFACE_ALT)
    root.option_add('*TCombobox*Listbox.foreground', INK)
    root.option_add('*TCombobox*Listbox.selectBackground', ACCENT_SOFT)
    root.option_add('*TCombobox*Listbox.selectForeground', INK)
    root.option_add('*Text.selectBackground', ACCENT_SOFT)
    root.option_add('*Text.selectForeground', INK)
    st = ttk.Style(root); st.theme_use('clam')
    st.configure('.', font=F(15), background=BG, foreground=INK)
    st.configure('TFrame', background=BG)
    st.configure('White.TFrame', background=WHITE)
    st.configure('TLabel', background=BG, foreground=INK)
    st.configure('White.TLabel', background=WHITE, foreground=INK)
    st.configure('TEntry', fieldbackground=INPUT_BG, background=INPUT_BG, foreground=INK,
                 padding=(S(10),S(8)), bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                 insertcolor=INK, relief='flat')
    st.map('TEntry', bordercolor=[('focus', TEAL)], lightcolor=[('focus', TEAL)], darkcolor=[('focus', TEAL)],
           fieldbackground=[('disabled','#0A0B0D')], foreground=[('disabled','#65666B')])
    st.configure('Invalid.TEntry', bordercolor=RED, lightcolor=RED, darkcolor=RED)
    st.configure('TCombobox', padding=(S(10),S(8)), fieldbackground=INPUT_BG, background=SURFACE_ALT, foreground=INK,
                 bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, arrowsize=S(14), arrowcolor=MUTED, relief='flat')
    st.map('TCombobox', fieldbackground=[('readonly',INPUT_BG),('disabled','#0A0B0D')],
           foreground=[('readonly',INK),('disabled','#65666B')],
           selectbackground=[('readonly',INPUT_BG)], selectforeground=[('readonly',INK)],
           bordercolor=[('focus',TEAL)])
    st.configure('TSpinbox', padding=(S(9),S(7)), fieldbackground=INPUT_BG, background=SURFACE_ALT, foreground=INK,
                 bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, arrowsize=S(12), arrowcolor=MUTED, relief='flat')
    st.map('TSpinbox', bordercolor=[('focus',TEAL)], fieldbackground=[('disabled','#0A0B0D')], foreground=[('disabled','#65666B')])
    st.configure('TCheckbutton', background=WHITE, foreground=INK, padding=(0,S(5)), indicatorcolor=INPUT_BG)
    st.map('TCheckbutton', indicatorbackground=[('selected', TEAL)], background=[('active',WHITE)], foreground=[('disabled',MUTED)])
    st.configure('Horizontal.TProgressbar', troughcolor=INPUT_BG, background=TEAL, borderwidth=0,
                 lightcolor=TEAL, darkcolor=TEAL, thickness=S(4))
    st.configure('Vertical.TScrollbar', background='#24272B', troughcolor=BG, borderwidth=0, arrowsize=S(12),
                 darkcolor='#24272B', lightcolor='#24272B')
    st.configure('Treeview', font=F(14), rowheight=S(46), fieldbackground=WHITE, background=WHITE,
                 foreground=INK, borderwidth=0, relief='flat')
    st.configure('Treeview.Heading', font=F(12,'bold'), background=SURFACE_ALT, foreground=MUTED,
                 padding=(S(11),S(10)), relief='flat', borderwidth=0)
    st.map('Treeview', background=[('selected',ACCENT_SOFT)], foreground=[('selected',INK)])
    return st

def rounded(c,x,y,w,h,r=10,**kw):
    r=min(r,w/2,h/2)
    return c.create_polygon(x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y, smooth=True, splinesteps=20, **kw)

def icon(c,name,x,y,size=22,color=INK,width=1.7):
    """Draw scalable symbols, independent of icon fonts and external resources."""
    a=size/24; lw=max(1,width*a)
    def line(*p): c.create_line(*[v*a+(x if i%2==0 else y) for i,v in enumerate(p)],fill=color,width=lw,capstyle='round',joinstyle='round')
    def rect(l,t,r,b): c.create_rectangle(x+l*a,y+t*a,x+r*a,y+b*a,outline=color,width=lw)
    def oval(l,t,r,b): c.create_oval(x+l*a,y+t*a,x+r*a,y+b*a,outline=color,width=lw)
    def arc(l,t,r,b,st=0,ex=180): c.create_arc(x+l*a,y+t*a,x+r*a,y+b*a,start=st,extent=ex,style='arc',outline=color,width=lw)
    if name in ('monitor','screen'):
        rect(2,3,22,17);line(12,17,12,21);line(7,21,17,21)
    elif name=='lock':
        arc(6,2,18,15);rect(4,10,20,22);oval(10.5,14,13.5,17);line(12,17,12,19)
    elif name=='shield':
        line(12,1,22,5,22,13,19,19,12,23,5,19,2,13,2,5,12,1);icon(c,'lock',x+size*.25,y+size*.28,size*.5,color,width)
    elif name=='home': line(2,10,12,2,22,10);line(5,9,5,22,10,22,10,15,14,15,14,22,19,22,19,9)
    elif name=='card': rect(2,4,22,20);line(2,9,22,9);line(5,15,9,15)
    elif name=='file':line(5,2,15,2,21,8,21,22,5,22,5,2);line(15,2,15,8,21,8);line(8,13,18,13);line(8,17,18,17)
    elif name=='chip':
        rect(5,5,19,19)
        for n in (8,12,16):line(n,1,n,5);line(n,19,n,23);line(1,n,5,n);line(19,n,23,n)
    elif name=='search': oval(2,2,16,16);line(15,15,22,22)
    elif name=='refresh': arc(3,3,21,21,40,300);line(21,2,21,8,15,8)
    elif name=='save': line(3,2,17,2,22,7,22,22,2,22,2,2);rect(7,2,16,9);rect(6,14,18,22)
    elif name in ('export','import'):
        line(3,14,3,22,21,22,21,14)
        if name=='export':line(12,17,12,2);line(7,7,12,2,17,7)
        else:line(12,2,12,17);line(7,12,12,17,17,12)
    elif name=='usb':
        rect(7,9,17,22);rect(9,2,15,9);line(11,4,11,6);line(13,4,13,6)
    elif name=='sun':
        oval(7,7,17,17)
        for t in range(8):
            a1=t*math.pi/4;line(12+8*math.cos(a1),12+8*math.sin(a1),12+11*math.cos(a1),12+11*math.sin(a1))
    elif name=='clock':oval(2,2,22,22);line(12,5,12,12,17,15)
    elif name=='eye':line(1,12,5,7,12,4,19,7,23,12,19,17,12,20,5,17,1,12);oval(8,8,16,16)
    elif name=='check':line(4,12,9,17,20,6)
    elif name=='close':line(5,5,19,19);line(19,5,5,19)
    elif name=='info':oval(2,2,22,22);line(12,10,12,18);oval(11.5,6,12.5,7)
    elif name=='gear':
        oval(5,5,19,19);oval(9,9,15,15)
        for t in range(8):
            a1=t*math.pi/4;line(12+7*math.cos(a1),12+7*math.sin(a1),12+11*math.cos(a1),12+11*math.sin(a1))
    elif name=='tool':line(4,21,14,11,18,12,22,8,22,3,18,7,15,4,19,1,14,1,10,5,11,9,1,19,4,21)
    elif name=='trash':line(3,6,21,6);line(9,6,9,2,15,2,15,6);line(5,6,6,22,18,22,19,6);line(10,10,10,18);line(14,10,14,18)
    elif name=='palette':oval(2,2,22,22);oval(6,7,8,9);oval(11,5,13,7);oval(16,8,18,10);oval(6,13,8,15)
    elif name=='arrow':line(3,12,21,12);line(16,7,21,12,16,17)
    elif name=='edit':line(4,16,17,3,22,8,9,21,3,22,4,16);line(14,6,19,11)
    elif name=='touch':line(9,15,9,5,11,3,13,5,13,13,16,12,20,14,20,20,16,23,9,23,3,16,4,13,9,17)
    elif name=='pico':
        # Legacy decorative icon; product identity uses the EvilKey logo assets.
        for st,ex,box in ((18,118,(1,1,13,13)), (138,238,(1,1,13,13)), (258,338,(1,1,13,13)),
                          (42,128,(4,4,10,10)), (212,298,(4,4,10,10)),
                          (100,175,(6,6,8,8))):
            arc(*box, st=st, ex=ex)
        line(12,6.5,20,6.5)
        line(17,9.5,23,9.5)
        line(14.5,12.5,18.5,12.5)
        line(19,12.5,19,16.8)
        line(16,12.5,16,15.8)
        arc(14.2,15.1,17.8,18.7, st=200, ex=140)
        arc(17.2,16.1,20.8,19.7, st=200, ex=140)
    else: oval(3,3,21,21)

class Icon(tk.Canvas):
    def __init__(self,parent,name,size=24,color=INK,bg=WHITE):
        super().__init__(parent,width=S(size),height=S(size),bg=bg,highlightthickness=0)
        icon(self,name,0,0,S(size),color)

class Label(tk.Label):
    def __init__(self,parent,text='',size=15,bold=False,color=INK,bg=WHITE,**kwargs):
        super().__init__(parent,text=text,font=F(size,'bold' if bold else 'normal'),fg=color,bg=bg,anchor='w',justify='left',**kwargs)

class Card(tk.Frame):
    """Elevated dark surface with a restrained border and top highlight."""
    def __init__(self,parent,padding=22,bg=WHITE,radius=16):
        super().__init__(parent,bg=BG)
        self._surface=bg; self._radius=radius
        self.back=tk.Canvas(self,bg=BG,highlightthickness=0)
        self.back.place(x=0,y=0,relwidth=1,relheight=1)
        self.body=tk.Frame(self,bg=bg)
        self.body.pack(fill='both',expand=True,padx=S(padding),pady=S(padding))
        self.back.bind('<Configure>',self._paint)
    def _paint(self,e):
        self.back.delete('all')
        w,h=e.width,e.height
        if w<4 or h<4:return
        rounded(self.back,S(2),S(4),w-S(4),h-S(5),S(self._radius),fill=SHADOW,outline='')
        rounded(self.back,S(1),S(1),w-S(2),h-S(3),S(self._radius),fill=self._surface,outline=BORDER)
        # One neutral highlight is enough to separate the surface on OLED-black.
        self.back.create_line(S(20),S(2),max(S(20),w-S(20)),S(2),fill='#303338',width=1)
    def title(self,text,subtitle='',name=None):
        r=tk.Frame(self.body,bg=self._surface);r.pack(fill='x',pady=(0,S(18)))
        if name:
            IconBadge(r,name,40).pack(side='left',padx=(0,S(13)))
        b=tk.Frame(r,bg=self._surface);b.pack(side='left',fill='x',expand=True)
        Label(b,text,21,True,bg=self._surface).pack(anchor='w')
        if subtitle:
            lab=Label(b,subtitle,13,color=MUTED,bg=self._surface);lab.pack(fill='x',pady=(S(4),0))
            lab.bind('<Configure>',lambda e:lab.configure(wraplength=max(S(180),e.width-S(8))))
        return r

class IconBadge(tk.Canvas):
    def __init__(self,parent,name,size=40,color=TEAL,bg=None):
        bg = bg if bg is not None else parent.cget('bg')
        super().__init__(parent,width=S(size),height=S(size),bg=bg,highlightthickness=0)
        self.name=name;self.color=color;self.size=size
        self.bind('<Configure>',lambda _:self.draw());self.after_idle(self.draw)
    def draw(self):
        self.delete('all'); s=S(self.size); pad=S(1)
        self.create_oval(pad,pad,s-pad,s-pad,fill=PALE,outline='#29443D',width=1)
        icon(self,self.name,S(9),S(9),S(self.size-18),self.color,1.8)

class Button(tk.Canvas):
    """Canvas button with keyboard support and restrained hover/press feedback."""
    def __init__(self,parent,text,command=None,kind='secondary',name=None,width=None,height=44):
        self._text=text;self._command=command;self._state='normal';self.kind=kind;self.name=name
        self.hover=False;self.focused=False;self.pressed=False
        self._hover_t=0.0;self._hover_after=None;self._hover_started=0.0;self._hover_from=0.0;self._hover_to=0.0
        font=tkfont.Font(font=F(14,'bold' if kind=='primary' else 'normal'))
        w=width or ((font.measure(text)/FACTOR)+38+(27 if name else 0))
        super().__init__(parent,width=S(w),height=S(height),bg=parent.cget('bg'),highlightthickness=0,takefocus=1,cursor='hand2')
        self.bind('<Configure>',lambda _:self.draw())
        self.bind('<Enter>',lambda _:self.flag('hover',True))
        self.bind('<Leave>',self._leave)
        self.bind('<FocusIn>',lambda _:self.flag('focused',True))
        self.bind('<FocusOut>',lambda _:self.flag('focused',False))
        self.bind('<ButtonPress-1>',self._press)
        self.bind('<ButtonRelease-1>',self.click)
        self.bind('<space>',lambda _:self.invoke());self.bind('<Return>',lambda _:self.invoke())
        self.after_idle(self.draw)
    def flag(self,k,v):
        setattr(self,k,v)
        if k=='hover':self._animate_hover(1.0 if v else 0.0)
        else:self.draw()
    def _animate_hover(self,target):
        self._hover_from=self._hover_t;self._hover_to=float(target);self._hover_started=time.perf_counter()
        if self._hover_after is not None:
            try:self.after_cancel(self._hover_after)
            except tk.TclError:pass
        self._hover_step()
    def _hover_step(self):
        if not self.winfo_exists():return
        p=min(1.0,(time.perf_counter()-self._hover_started)/0.12);e=ease(p)
        self._hover_t=self._hover_from+(self._hover_to-self._hover_from)*e;self.draw()
        if p<1.0:
            try:self._hover_after=self.after(16,self._hover_step)
            except tk.TclError:self._hover_after=None
        else:self._hover_after=None
    def _inside(self,e):return 0<=e.x<self.winfo_width() and 0<=e.y<self.winfo_height()
    def _press(self,e):
        self.focus_set()
        if self._state!='disabled' and self._inside(e):self.pressed=True;self.draw()
    def _leave(self,e=None):
        self.hover=False;self.pressed=False;self._animate_hover(0.0)
    def click(self,e):
        was_pressed=self.pressed;inside=self._inside(e);self.pressed=False;self.draw()
        if was_pressed and inside:self.invoke()
    def invoke(self):
        if self._state!='disabled' and self._command:return self._command()
    def configure(self,cnf=None,**kw):
        if cnf:kw.update(cnf)
        redraw=False
        for k in ('text','command','state'):
            if k in kw:setattr(self,'_'+k,kw.pop(k));redraw=True
        result=super().configure(**kw) if kw else None
        if redraw and self.winfo_exists():self.draw()
        return result
    config=configure
    def destroy(self):
        if self._hover_after is not None:
            try:self.after_cancel(self._hover_after)
            except tk.TclError:pass
            self._hover_after=None
        super().destroy()
    def cget(self,k):
        if k in ('text','command','state'):return getattr(self,'_'+k)
        return super().cget(k)
    def draw(self):
        if not self.winfo_exists():return
        self.delete('all');w=self.winfo_width();h=self.winfo_height()
        if w<5:w=int(super().cget('width'))
        if h<5:h=int(super().cget('height'))
        disabled=self._state=='disabled'
        ht=ease(self._hover_t)
        if self.kind=='primary':
            bg=TEAL_DARK if self.pressed else mix(TEAL,'#77EFD3',ht);fg='#03100F';border=bg
        elif self.kind=='danger':
            bg=mix('#1B1114','#30181E',ht);fg=RED;border=mix('#4A2A2E',RED,0.55*ht if not self.focused else 1.0)
        else:
            bg=mix(SURFACE_ALT,SURFACE_HOVER,ht);fg=INK;border=TEAL if self.focused else mix(BORDER,'#40524D',ht)
        if disabled:bg='#0A0B0D';fg='#65666B';border='#222428'
        yoff=S(1) if self.pressed else 0
        rounded(self,S(1),S(1)+yoff,w-S(2),h-S(2)-yoff,S(10),fill=bg,outline=border,width=S(2) if self.focused and not disabled else 1)
        if self.kind=='primary' and not disabled and not self.pressed:
            self.create_line(S(15),S(3),w-S(15),S(3),fill=mix('#9AF3DF','#D0FFF4',ht),width=1)
        f=tkfont.Font(font=F(14,'bold' if self.kind=='primary' else 'normal'))
        total=f.measure(self._text)+(S(29) if self.name else 0);left=(w-total)/2
        if self.name:icon(self,self.name,left,(h-S(21))/2+yoff,S(21),fg);left+=S(29)
        self.create_text(left,h/2+yoff,text=self._text,font=f,fill=fg,anchor='w')

class Toggle(tk.Canvas):
    def __init__(self,parent,variable,text='',width=420):
        self.var=variable;self.label=text;self.enabled=True;self.focused=False;self.hover=False
        self._knob=None;self._anim_after=None;self._anim_from=0.0;self._anim_to=0.0;self._anim_started=0.0
        super().__init__(parent,width=S(width),height=S(38),bg=parent.cget('bg'),highlightthickness=0,takefocus=1,cursor='hand2')
        self.var.trace_add('write',lambda *_:self._value_changed());self.bind('<Configure>',lambda _:self.draw())
        self.bind('<Button-1>',lambda _:(self.focus_set(),self.toggle()));self.bind('<space>',lambda _:self.toggle())
        self.bind('<Enter>',lambda _:(setattr(self,'hover',True),self.draw()));self.bind('<Leave>',lambda _:(setattr(self,'hover',False),self.draw()))
        self.bind('<FocusIn>',lambda _:(setattr(self,'focused',True),self.draw()));self.bind('<FocusOut>',lambda _:(setattr(self,'focused',False),self.draw()))
    def toggle(self):
        if self.enabled:self.var.set(not self.var.get())
    def configure(self,cnf=None,**kw):
        if cnf:kw.update(cnf)
        if 'state' in kw:self.enabled=kw.pop('state')!='disabled';self.draw()
        return super().configure(**kw) if kw else None
    config=configure
    def destroy(self):
        if self._anim_after is not None:
            try:self.after_cancel(self._anim_after)
            except tk.TclError:pass
            self._anim_after=None
        super().destroy()
    def _value_changed(self):
        target=float(S(25 if self.var.get() else 4))
        if self._knob is None:self._knob=target;self.draw();return
        self._anim_from=float(self._knob);self._anim_to=target;self._anim_started=time.perf_counter()
        if self._anim_after is not None:
            try:self.after_cancel(self._anim_after)
            except tk.TclError:pass
        self._animate_knob()
    def _animate_knob(self):
        if not self.winfo_exists():return
        p=min(1.0,(time.perf_counter()-self._anim_started)/0.14);e=ease(p)
        self._knob=self._anim_from+(self._anim_to-self._anim_from)*e;self.draw()
        if p<1.0:
            try:self._anim_after=self.after(16,self._animate_knob)
            except tk.TclError:self._anim_after=None
        else:self._anim_after=None
    def draw(self):
        if not self.winfo_exists():return
        self.delete('all');on=self.var.get();track=TEAL if on else OFF
        if not self.enabled:track='#24262A'
        if self.hover and self.enabled:track='#76EFD4' if on else '#4A4D52'
        outline=TEAL if self.focused else ('#31564D' if on else '#55585D')
        rounded(self,S(1),S(6),S(48),S(26),S(13),fill=track,outline=outline)
        if self._knob is None:self._knob=float(S(25 if on else 4))
        x=self._knob
        knob='#06110E' if on else '#F4F4F5'
        self.create_oval(x,S(9),x+S(20),S(29),fill=knob,outline=knob)
        if self.label:self.create_text(S(62),S(19),anchor='w',text=self.label,font=F(14),fill=INK if self.enabled else MUTED)

class Slider(tk.Canvas):
    def __init__(self,parent,variable,low,high,steps=None):
        self.steps=steps;self.var=variable;self.low=low;self.high=high;self.enabled=True;self.focused=False;self.hover=False
        super().__init__(parent,height=S(36),width=S(150),bg=parent.cget('bg'),highlightthickness=0,takefocus=1,cursor='hand2')
        self.var.trace_add('write',lambda *_:self.draw());self.bind('<Configure>',lambda _:self.draw())
        self.bind('<Button-1>',self.move);self.bind('<B1-Motion>',self.move)
        self.bind('<Enter>',lambda _:(setattr(self,'hover',True),self.draw()));self.bind('<Leave>',lambda _:(setattr(self,'hover',False),self.draw()))
        self.bind('<Left>',lambda _:self.nudge(-1));self.bind('<Right>',lambda _:self.nudge(1));self.bind('<Home>',lambda _:self.set_value(self.low));self.bind('<End>',lambda _:self.set_value(self.high))
        self.bind('<FocusIn>',lambda _:(setattr(self,'focused',True),self.draw()));self.bind('<FocusOut>',lambda _:(setattr(self,'focused',False),self.draw()))
    def configure(self,cnf=None,**kw):
        if cnf:kw.update(cnf)
        if 'state' in kw:self.enabled=kw.pop('state')!='disabled';self.draw()
        return super().configure(**kw) if kw else None
    config=configure
    def value(self):
        try:return min(self.high,max(self.low,int(self.var.get())))
        except (ValueError,tk.TclError):return self.low
    def set_value(self,v):
        if self.enabled:self.var.set(str(min(self.high,max(self.low,v))))
    def nudge(self,d):
        if self.steps:
            val=self.value();values=[v for v in self.steps if v>val] if d>0 else [v for v in reversed(self.steps) if v<val]
            if values:self.set_value(values[0])
        else:self.set_value(self.value()+d)
    def move(self,e):
        if not self.enabled:return
        self.focus_set();position=max(0,min(1,(e.x-S(13))/max(1,self.winfo_width()-S(26))))
        v=self.steps[round(position*(len(self.steps)-1))] if self.steps else self.low+round(position*(self.high-self.low))
        self.set_value(v)
    def draw(self):
        if not self.winfo_exists():return
        self.delete('all');w=max(S(30),self.winfo_width());y=S(18);l=S(13);r=w-S(13)
        val=self.value();position=(val-self.low)/(self.high-self.low)
        if self.steps:
            for i in range(len(self.steps)-1):
                lo,hi=self.steps[i:i+2]
                if lo<=val<=hi:position=(i+(val-lo)/(hi-lo))/(len(self.steps)-1);break
        p=l+(r-l)*position;active=TEAL if self.enabled else '#294049'
        self.create_line(l,y,r,y,fill=INPUT_BG,width=S(5),capstyle='round')
        self.create_line(l,y,p,y,fill=active,width=S(5),capstyle='round')
        rr=S(11 if self.hover or self.focused else 9)
        if self.focused:self.create_oval(p-S(13),y-S(13),p+S(13),y+S(13),outline='#2C6F68',width=1)
        self.create_oval(p-rr,y-rr,p+rr,y+rr,fill=active,outline=INK if self.enabled else BORDER,width=S(2))

class PercentEntry(ttk.Entry):
    """Expose percentages without changing the 8-bit firmware representation."""
    def __init__(self,parent,raw,low,high):
        self.raw=raw;self.low=low;self.high=high;self.display=tk.StringVar()
        super().__init__(parent,textvariable=self.display,width=8,justify='right')
        self.raw.trace_add('write',lambda *_:self.sync());self.sync()
        self.bind('<FocusOut>',lambda _:self.try_commit());self.bind('<Return>',lambda _:self.try_commit())
    def sync(self):
        try:self.display.set(f'{int(self.raw.get())*100/255:.2f}');self.configure(style='TEntry')
        except (ValueError,tk.TclError):pass
    def commit(self):
        try:
            value=float(self.display.get().replace(',','.'))
            if not math.isfinite(value) or not round(self.low*100/255,2)<=value<=round(self.high*100/255,2):raise ValueError()
            raw=round(value*255/100)
            if not self.low<=raw<=self.high:raise ValueError()
        except ValueError:
            self.configure(style='Invalid.TEntry');raise UserError(f'Brightness: enter {self.low*100/255:.2f}–{self.high*100/255:.2f}%.')
        self.raw.set(str(raw));self.configure(style='TEntry')
    def try_commit(self):
        try:self.commit()
        except UserError:pass

class ScrollPage(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG)
        self.canvas=tk.Canvas(self,bg=BG,highlightthickness=0)
        self.scroll=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.body=tk.Frame(self.canvas,bg=BG)
        self.item=self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.canvas.pack(side='left',fill='both',expand=True);self.scroll.pack(side='right',fill='y')
        self.body.bind('<Configure>',self.changed);self.canvas.bind('<Configure>',self.resize)
    def changed(self,e=None):self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    def resize(self,e):self.canvas.itemconfigure(self.item,width=e.width)
    def reset(self):self.canvas.yview_moveto(0)
