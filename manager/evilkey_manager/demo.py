# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Explicit, in-memory GUI demonstration. This module never opens USB."""
from dataclasses import asdict, replace
from .models import DisplaySettings, UserError
from .project import DEFAULTS

DEVICE={'path':{'kind':'str','value':'DEMO-NO-USB'},'vid':0xFEFF,'pid':0xFCFD,
        'product':"EvilKey · Demonstration mode",'serial_hash':'','in':64,'out':64}
INFO={'identity':'demo-only','aaguid':'00'*16,'versions':['FIDO_2_0','FIDO_2_1'],
      'options':{'clientPin':True,'uv':True,'pinUvAuthToken':True,'credMgmt':True,
                 'rk':True,'authnrCfg':True,'alwaysUv':False,'setMinPINLength':True},
      'protocols':[1,2],'pin_retries':8,'uv_retries':8,'power_cycle':False,
      'min_pin_length':4,'force_pin_change':False,'max_rpids':120,'max_msg_size':1024,
      'extensions':['credProtect','hmac-secret'],'remaining_disc_creds':254,
      'firmware_reported':0x00040000,'vendor_commands':[0x00052b41f53590d3,0x000377913e17951f]}

class DemoRunner:
    def __init__(self,root,on_progress,on_done):
        self.root=root;self.on_progress=on_progress;self.on_done=on_done;self.busy=False
        self.settings=DisplaySettings();self.drive_read_only=False;self.info=dict(INFO);self.info['options']=dict(INFO['options'])
        self.rows=[{'rp':'example.test','rp_hash':'00'*32,'credential_id':'01'*40,
              'user_id':'ab'*16,'name':'test.account','display_name':'Test Account',
              'protection':3,'algorithm':-7},
              {'rp':'lab.example.test','rp_hash':'11'*32,'credential_id':'02'*40,
              'user_id':'cd'*16,'name':'laboratory','display_name':'Laboratory',
              'protection':3,'algorithm':-7}]
        self.cancelled=False
    def start(self,op,args):
        if self.busy:raise UserError('A demonstration operation is already in progress.')
        args=dict(args)
        self.busy=True;self.cancelled=False
        self.on_progress("Operation on sample data.")
        def finish():
            if self.cancelled:
                result={'type':'error','error':{'message':"The simulation was canceled.",'connection_lost':False}}
            else:
                data={}
                if op=='scan':data=[dict(DEVICE)]
                elif op=='info':data=self.info
                elif op=='ping':data={'ping_ok':True}
                elif op=='metadata':data={'existing':len(self.rows),'remaining_estimate':256-len(self.rows)}
                elif op=='credentials':data={'credentials':list(self.rows),'existing':len(self.rows),'remaining_estimate':256-len(self.rows)}
                elif op.startswith('display_'):
                    if op=='display_write':self.settings=replace(DisplaySettings.from_dict(args['settings']),revision=self.settings.revision+1)
                    data={'settings':asdict(self.settings),'firmware':'0.4.0 (demo)','storage_ok':True,'build_flags':11}
                elif op.startswith('drive_'):
                    if op=='drive_write':self.drive_read_only=bool(args['read_only'])
                    data={'settings':{'read_only':self.drive_read_only},'firmware':'0.4.0 (demo)','storage_ok':True,'compiled':True,'enabled':True}
                elif op in ('delete_credential','rename_credential'):
                    selected=args['credential']['credential_id']
                    if op=='delete_credential':self.rows=[r for r in self.rows if r['credential_id']!=selected]
                    else:
                        for row in self.rows:
                            if row['credential_id']==selected:row.update(name=args['name'],display_name=args['display_name'])
                    data={'acknowledged':True,'requires_refresh':True}
                elif op in ('resident_keys','makecred_uv'):self.info['options']['rk' if op=='resident_keys' else 'makeCredUvNotRqd']=args['enabled'];data={'acknowledged':True}
                elif op=='always_uv':self.info['options']['alwaysUv']=args['enabled'];data={'acknowledged':True}
                elif op=='pin_policy':self.info['min_pin_length']=args['minimum'];data={'acknowledged':True}
                elif op in ('set_pin','change_pin'):self.info['options']['clientPin']=True;data={'acknowledged':True}
                elif op=='reset':self.rows=[];self.info['options']['clientPin']=False;data={'reset_acknowledged':True}
                result={'type':'result','data':data}
            self.busy=False;self.on_done(op,result)
        self.root.after(350,finish)
    def pump(self):pass
    def cancel(self):self.cancelled=True
