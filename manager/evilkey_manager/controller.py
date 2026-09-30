# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Application actions and guarded device operations."""
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog, colorchooser
from . import __version__
from .backend import AUTH_JOBS, MUTATIONS
from .models import DisplaySettings, UserError, display_text, validate_new_pin, validate_existing_pin
from .project import DEFAULTS, BOOL_FIELDS, HEX_FIELDS, read_header, validate_config, export_project
from .dialogs import FormDialog

class Actions:
    def opts(self):return (self.info or {}).get('options',{})

    def owned(self):return bool(self.info and self.owner.get())

    def protected(self,cap=None):
        return self.owned() and (not cap or self.opts().get(cap) is True)

    def has_auth(self):
        return self.protected('pinUvAuthToken') and self.opts().get('clientPin') is True and (self.auth.get()!='PIN on device' or self.opts().get('uv') is True)

    def submit(self,operation,extra=None):
        if self.runner.busy:return
        args=dict(extra or {})
        try:
            if operation!='scan':
                if not self.device:raise UserError("First, select the key from the list.")
                args.update(device=self.device,protocol={'Auto (prefer 2)':0,"Protocol 1":1,"Protocol 2":2}[self.protocol.get()])
                if self.info:args['identity']=self.info['identity']
                args['owner_confirmed']=self.owner.get()
            if operation in AUTH_JOBS:
                if not self.has_auth():raise UserError("Read the key, confirm its selection and select the authorisation method available.")
                if self.auth.get()=='PIN on device':args['auth']={'method':'panel'}
                elif self.demo:args['auth']={'method':'host'}
                else:
                    def validate(values):validate_existing_pin(values['pin'])
                    dialog=FormDialog(self.root,'PIN authorization',"The PIN is used only for this operation. An incorrect PIN may reduce the remaining attempt count.",[('pin','Current PIN',True,'')],validator=validate)
                    if dialog.result is None:return
                    args['auth']={'method':'host','pin':dialog.result['pin']};dialog.result.clear()
            self.runner.start(operation,args);self.progressbar.start(12);self.refresh_enabled()
            self.log_operation(operation, "Started")
        except Exception as exc:self.show_error(exc)
        finally:
            if isinstance(args.get('auth'),dict):args['auth'].clear()
            for key in ('old_pin','new_pin'):args.pop(key,None)

    def filter_credentials(self):
        if not hasattr(self,'credential_table'):return
        self.credential_table.delete(*self.credential_table.get_children());needle=self.filter.get().casefold()
        for i,row in enumerate(self.credentials):
            if needle and needle not in ' '.join(str(row[k]) for k in ('rp','name','display_name')).casefold():continue
            self.credential_table.insert('','end',iid=str(i),values=(display_text(row['rp']),display_text(row['name']),display_text(row['display_name']),row['credential_id'][:18]+'…'))
        self.refresh_enabled()

    def selected_credential(self):
        if not hasattr(self,'credential_table'):return None
        selected=self.credential_table.selection()
        try:return dict(self.credentials[int(selected[0])]) if selected else None
        except (IndexError,ValueError):return None

    def pin_dialog(self,change):
        minimum=(self.info or {}).get('min_pin_length',4)
        def validate(v):
            if change:validate_existing_pin(v['old_pin'])
            validate_new_pin(v['new_pin'],minimum)
            if v['new_pin']!=v['repeat']:raise UserError("The new PINs are different.")
        fields=([('old_pin','Current PIN',True,'')] if change else [])+[('new_pin','New PIN — digits 0–9',True,''),('repeat',"Repeat new PIN",True,'')]
        dialog=FormDialog(self.root,"Change PIN" if change else 'Set PIN',f'At least {minimum} digits are required. PINs are not saved to files. Changing the PIN does not reset credentials.',fields,button="Change PIN" if change else 'Set PIN',validator=validate)
        if dialog.result is not None:
            args={k:v for k,v in dialog.result.items() if k!='repeat'};args['pin_confirmed']=True
            self.submit('change_pin' if change else 'set_pin',args);dialog.result.clear();args.clear()

    def always_apply(self):
        desired=self.always.get()
        if messagebox.askyesno("User verification",f"Set required verification to {'on' if desired else 'off'}?\nThis may affect sign-in compatibility in some applications.",parent=self.root):self.submit('always_uv',{'enabled':desired,'policy_confirmed':True})

    def vendor_apply(self,kind):
        enabled=self.rk_enabled.get() if kind=='resident_keys' else self.mcuv_allowed.get()
        if kind=='makecred_uv' and enabled and self.opts().get('alwaysUv'):
            self.show_error(UserError("First disable verification on every sign-in. These settings conflict."));return
        if messagebox.askyesno('Change registration policy',f"Save the selected setting as {'on' if enabled else 'off'}?",parent=self.root):
            self.submit(kind,{'enabled':enabled,'policy_confirmed':True})

    def policy_apply(self):
        try:
            minimum=int(self.minimum.get());rps=[x.strip() for x in self.rp_text.get('1.0','end').splitlines() if x.strip()]
            from .models import integer,rp_ids
            integer(minimum,max(4,self.info.get('min_pin_length',4)),63,"Minimum PIN length");rp_ids(rps,min(120,self.info.get('max_rpids',0)))
            force_text='yes' if self.force.get() else 'no (unless the new minimum exceeds the current PIN length)'
            if not messagebox.askyesno('Change PIN policy',f'Minimum: {minimum} digits.\nNew RP list: {len(rps)} entries; this replaces the previous list.\nForce PIN change: {force_text}.\n\nThis command cannot lower the minimum. Continue?',parent=self.root):return
            self.submit('pin_policy',{'minimum':minimum,'rp_ids':rps,'force_change':self.force.get(),'replace_rp_list':True,'policy_confirmed':True})
        except Exception as exc:self.show_error(exc)

    def rename_credential(self):
        row=self.selected_credential()
        if not row:return
        def validate(v):
            for x in v.values():
                if not x or len(x.encode('utf-8'))>64 or not x.isprintable():raise UserError("Type 1–64 bytes UTF-8 without control characters.")
        d=FormDialog(self.root,"Edit credential description","Service: "+display_text(row['rp'])+"\nThis changes the description on the device, not the account on the website.",[('name',"Username",False,row['name']),('display_name','Display name',False,row['display_name'])],validator=validate)
        if d.result is not None:self.submit('rename_credential',dict(d.result,credential=row,confirmation='RENAME:'+row['credential_id']))

    def delete_credential(self):
        row=self.selected_credential()
        if not row:return
        def validate(v):
            if v['confirm']!="DELETE":raise UserError("Type DELETE exactly.")
        d=FormDialog(self.root,"Delete one credential",f"Service: {display_text(row['rp'])}\nUser: {display_text(row['name'])}\nID: {row['credential_id'][:24]}…\n\nDeletion is permanent. Make sure you have another way to sign in to this account.",[('confirm',"Type DELETE",False,'')],button="Delete credential",validator=validate)
        if d.result is not None:self.submit('delete_credential',{'credential':row,'confirmation':'DELETE:'+row['credential_id']})

    def get_display(self):
        if self.display_record is None:raise UserError("First read the current screen settings.")
        try:
            args={k:(var.get() if k=='animation' else int(var.get().lstrip('#'),16) if k=='accent_rgb' else int(var.get())) for k,var in self.screen_vars.items()}
        except ValueError as exc:raise UserError("Check RGB numbers and color in the form.") from exc
        return DisplaySettings(**args,revision=self.display_record['settings']['revision']).validate()

    def pick_color(self):
        if self.runner.busy:return
        try:result=colorchooser.askcolor(color=self.screen_vars['accent_rgb'].get(),parent=self.root,title='Bright interface accent')
        except tk.TclError:self.show_error(UserError('Enter a color in #RRGGBB format.'));return
        if result[1]:self.screen_vars['accent_rgb'].set(result[1].upper())

    def display_write(self):
        try:
            settings=self.get_display()
            if messagebox.askyesno("Save display settings",f'Save display and interaction settings to the selected device?\nDim after: {settings.dim_seconds} s; turn off: {settings.off_seconds} s after dimming.\nThe PIN and credentials are unaffected.',parent=self.root):self.submit('display_write',{'settings':asdict(settings),'display_confirmed':True})
        except Exception as exc:self.show_error(exc)

    def drive_write(self):
        try:
            if self.drive_record is None:raise UserError("Read Manager Drive mode first.")
            desired=bool(self.drive_read_only.get())
            mode='read only' if desired else 'read and write'
            warning="\n\nBefore enabling write protection, finish copying the EXE file to the microSD card." if desired else ''
            if messagebox.askyesno('Manager Drive',f'Set the microSD card to {mode}?{warning}\n\nThis does not affect FIDO storage, the PIN, or credentials.',parent=self.root):
                self.submit('drive_write',{'read_only':desired,'drive_confirmed':True})
        except Exception as exc:self.show_error(exc)

    def export_display(self):
        try:
            # Export the form intentionally; file import never claims a device write.
            settings=self.get_display();path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',initialfile='evilkey_display.json',filetypes=[('JSON','*.json')])
            if path:Path(path).write_text(json.dumps(settings.export(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');self.progress("Form settings saved. This file is not a credential backup.")
        except Exception as exc:self.show_error(exc)

    def import_display(self):
        try:
            path=filedialog.askopenfilename(parent=self.root,filetypes=[('JSON','*.json')])
            if not path:return
            if Path(path).stat().st_size>16384:raise UserError("The settings file is too big.")
            settings=DisplaySettings.import_for_revision(json.loads(Path(path).read_text(encoding='utf-8-sig')),self.display_record['settings']['revision'])
            self.fill_display(settings);self.progress('Settings loaded into the form. Writing them to the device requires separate confirmation.')
        except Exception as exc:self.show_error(exc)

    def import_header(self):
        try:
            path=filedialog.askopenfilename(parent=self.root,title='Current FidoConfig.h',filetypes=[('C configuration','*.h')])
            if not path:return
            values=read_header(Path(path))
            for key,var in self.project_vars.items():
                shown=self.project_choices[key][values[key]] if key in self.project_choices else f'0x{values[key]:X}' if key in HEX_FIELDS else str(values[key])
                var.set(bool(values[key]) if key in BOOL_FIELDS else shown)
            self.progress("Source configuration loaded. No file or device changed.")
        except Exception as exc:self.show_error(exc)

    def project_values(self):
        def read_value(key,var):
            raw=var.get()
            if key in self.project_choices:
                choices={label:number for number,label in self.project_choices[key].items()}
                if raw not in choices:raise UserError("Select a value from the list:"+key)
                return choices[raw]
            if key in BOOL_FIELDS:return int(raw)
            if key in HEX_FIELDS:return int(raw,16)
            return raw if isinstance(DEFAULTS[key],str) else int(raw)
        try:return validate_config({key:read_value(key,var) for key,var in self.project_vars.items()})
        except ValueError as exc:raise UserError("Check the number values of the project configuration.") from exc

    def export_source(self):
        try:
            firmware=self.firmware
            if firmware is None:
                selected=filedialog.askdirectory(parent=self.root,title="Select the separately downloaded firmware folder")
                if not selected:return
                firmware=Path(selected)
                if not (firmware/'prepare_arduino.py').is_file():
                    raise UserError("Select the firmware folder from the EvilKey firmware source package.")
                self.firmware=firmware
            values=self.project_values();parent=filedialog.askdirectory(parent=self.root,title="Select a place to save the project")
            if not parent:return
            name='EvilKey_0.5.0_'+datetime.now().strftime('%Y%m%d_%H%M%S');dest=Path(parent)/name
            export_project(firmware,dest,values)
            self.progress("The project is ready for compilation. To apply the settings, upload firmware to the key.")
            messagebox.showinfo('Project exported',str(dest)+"\n\nSee README_MANAGER.md. Build the project in Arduino IDE and upload it without erasing device storage.",parent=self.root)
        except Exception as exc:self.show_error(exc)

    def save_report(self):
        try:
            path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',initialfile='evilkey_status.json',filetypes=[('JSON','*.json')])
            if not path:return
            device={k:self.device[k] for k in ('vid','pid','product','in','out')}
            Path(path).write_text(json.dumps({'schema':'evilkey-public-status-v1','manager':__version__,'demo':self.demo,'device':device,'info':self.info},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            self.progress("Public status report saved. It contains no PINs, tokens, or account list.")
        except Exception as exc:self.show_error(exc)

    def reset_dialog(self):
        def validate(v):
            if v['confirmation']!='RESET EVILKEY':raise UserError("Enter exactly RESET EVILKEY.")
        d=FormDialog(self.root,'Reset FIDO — permanent action',"Reset permanently deletes all FIDO credentials and the PIN.\n\nFirst enter the phrase below. Fully power off the device (disconnect USB and the battery or any other power source), then power it on and immediately press the reset button in this window. Firmware accepts reset only briefly after startup. Confirm the action on the device.\n\nThe application sends one request and does not retry. A USB path change stops the operation.",[('confirmation',"Type RESET EVILKEY",False,'')],button="Send reset now",validator=validate)
        if d.result is not None:self.submit('reset',{'confirmation':'RESET EVILKEY'})

    def enterprise(self):
        if messagebox.askyesno('Enterprise Attestation',"Enable Enterprise Attestation?\nThis may reveal an organizational device identifier. This application cannot reverse the change.",parent=self.root):self.submit('enterprise',{'policy_confirmed':True})

    def cancel(self):self.runner.cancel();self.refresh_enabled()

    def pump(self):
        if not self.root.winfo_exists():return
        self.runner.pump()
        if self.closed and not self.runner.busy:self.shutdown_ui();self.root.destroy();return
        self._pump_handle=self.root.after(60,self.pump)

    def destroyed(self,event):
        if event.widget is self.root:
            for handle in (getattr(self,'_pump_handle',None),getattr(self,'_scan_handle',None)):
                if handle:
                    try:self.root.after_cancel(handle)
                    except tk.TclError:pass
