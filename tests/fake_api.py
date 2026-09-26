"""Deterministic API-shaped test doubles based on python-fido2 2.2.1.
These are NOT hardware tests and do not replace the production library.
"""
from types import SimpleNamespace
import hashlib,hmac
from dataclasses import asdict,replace
from evilkey_manager.models import DisplaySettings,ManagerDriveSettings,READ_ID,WRITE_ID,DRIVE_READ_ID,DRIVE_WRITE_ID

def cbor_encode(x):
    def head(m,n):
        if n<24:return bytes([m*32+n])
        size=1 if n<256 else 2 if n<65536 else 4 if n<2**32 else 8
        return bytes([m*32+{1:24,2:25,4:26,8:27}[size]])+n.to_bytes(size,'big')
    if isinstance(x,bool):return b'\xf5' if x else b'\xf4'
    if isinstance(x,int):return head(0,x) if x>=0 else head(1,-x-1)
    if isinstance(x,bytes):return head(2,len(x))+x
    if isinstance(x,str):data=x.encode();return head(3,len(data))+data
    if isinstance(x,list):return head(4,len(x))+b''.join(map(cbor_encode,x))
    if isinstance(x,dict):
        pairs=sorted([(cbor_encode(k),cbor_encode(v)) for k,v in x.items()],key=lambda p:(len(p[0]),p[0]))
        return head(5,len(pairs))+b''.join(k+v for k,v in pairs)
    raise TypeError(type(x))

class CtapError(Exception):
    def __init__(self,code):self.code=code;super().__init__('sensitive raw data must never be displayed')

class FakeAPI:
    def __init__(self):
        self.calls=[];self.closed=0;self.fail=None;self.hid_change=False;self.cbor=SimpleNamespace(encode=cbor_encode)
        self.CtapError=CtapError;self.token=b'T'*32;self.settings=DisplaySettings();self.drive=ManagerDriveSettings();self.pin_retries=8;self.uv_retries=8;self.power=False
        self.descriptor=SimpleNamespace(path=b'fake-hid-path',vid=0x1050,pid=0x0402,product_name='Pico DEV',serial_number='mockserial',report_size_in=64,report_size_out=64)
        self.info=SimpleNamespace(options={'clientPin':True,'uv':True,'pinUvAuthToken':True,'credMgmt':True,'rk':True,'authnrCfg':True,'alwaysUv':False,'setMinPINLength':True,'makeCredUvNotRqd':False},
            aaguid=b'A'*16,pin_uv_protocols=[1,2],versions=['FIDO_2_1'],min_pin_length=4,max_rpids_for_min_pin=120,max_msg_size=1024,extensions=[],firmware_version=0x00020E00,
            vendor_prototype_config_commands=[0x00052b41f53590d3,0x000377913e17951f])
        self.rp='example.test';self.rph=hashlib.sha256(self.rp.encode()).digest()
        self.rows=[{6:{'id':b'U'*16,'name':'test','displayName':'Test'},7:{'id':b'C'*40,'type':'public-key'},8:{3:-7},10:3,11:b'SECRET_LARGE_BLOB_KEY'}]
        api=self
        class Connection:
            def close(self):api.closed+=1
        self.open_connection=lambda d:Connection()
        class HID:
            def __init__(self,d,conn):api.calls.append(('INIT',))
            def ping(self,data):api.calls.append(('PING',));return data
        self.CtapHidDevice=HID
        class Proto:
            VERSION=1
            def authenticate(self,token,data):return hmac.new(token,data,'sha256').digest()[:16 if self.VERSION==1 else 32]
        class Proto2(Proto):VERSION=2
        self.PinProtocolV1=Proto;self.PinProtocolV2=Proto2
        class CTAP:
            def __init__(self,device,strict_cbor=True):
                assert strict_cbor;self.info=self.get_info()
            def send_cbor(self,cmd,data=None,*,event=None,on_keepalive=None):
                assert event is not None and on_keepalive is not None
                api.calls.append(('CBOR',cmd));return api.info
            def get_info(self):return self.send_cbor(4)
            def config(self,sub,params,version,signature):
                assert sub==255;api.calls.append(('CONFIG',sub,params))
                expected=(Proto2() if version==2 else Proto()).authenticate(api.token,b'\xff'*32+b'\x0d\xff'+cbor_encode(params))
                assert signature==expected
                if api.fail:raise api.fail
                command=params[1]
                if command==WRITE_ID:
                    settings=DisplaySettings.decode(params[2])
                    if settings.revision!=api.settings.revision:raise CtapError(0x30)
                    api.settings=replace(settings,revision=settings.revision+1)
                elif command==DRIVE_WRITE_ID:
                    api.drive=ManagerDriveSettings.decode(params[2])
                    return {1:1,2:api.drive.encode(),3:'0.2.14-dev',4:True,5:True,6:True}
                elif command==DRIVE_READ_ID:
                    return {1:1,2:api.drive.encode(),3:'0.2.14-dev',4:True,5:True,6:True}
                elif command==0x00052b41f53590d3:api.info.options['rk']=not api.info.options['rk'];return {}
                elif command==0x000377913e17951f:api.info.options['makeCredUvNotRqd']=not api.info.options['makeCredUvNotRqd'];return {}
                elif command!=READ_ID:raise CtapError(0x2B)
                return {1:1,2:api.settings.encode(),3:'0.2.14-dev',4:True,5:11}
            def reset(self,*,event=None,on_keepalive=None):
                api.calls.append(('RESET',))
                if api.fail:raise api.fail
        self.Ctap2=CTAP
        class Client:
            def __init__(self,ctap,proto):self.protocol=proto
            @staticmethod
            def is_supported(info):return 'clientPin' in info.options
            def get_pin_retries(self):api.calls.append(('PIN_RETRIES',));return api.pin_retries,api.power
            def get_uv_retries(self):api.calls.append(('UV_RETRIES',));return api.uv_retries
            def get_uv_token(self,permissions=None,permissions_rpid=None,event=None,on_keepalive=None):
                api.calls.append(('UV_TOKEN',permissions));
                if api.fail:raise api.fail
                return api.token
            def get_pin_token(self,pin,permissions=None):
                api.calls.append(('PIN_TOKEN',permissions))
                if api.fail:raise api.fail
                return api.token
            def set_pin(self,pin):
                api.calls.append(('SET_PIN',));api.info.options['clientPin']=True
                if api.fail:raise api.fail
            def change_pin(self,old,new):
                api.calls.append(('CHANGE_PIN',))
                if api.fail:raise api.fail
        self.ClientPin=Client
        class CM:
            def __init__(self,ctap,proto,token):assert token==api.token;self.index=0
            @staticmethod
            def is_supported(info):return info.options.get('credMgmt') is True
            is_update_supported=is_supported
            def get_metadata(self):return {1:len(api.rows),2:256-len(api.rows)}
            def enumerate_rps_begin(self):
                if not api.rows:raise CtapError(0x2E)
                return {3:{'id':api.rp},4:api.rph,5:1}
            def enumerate_rps_next(self):raise AssertionError('unexpected next RP')
            def enumerate_creds_begin(self,rph):
                assert rph==api.rph;self.index=0
                if not api.rows:raise CtapError(0x2E)
                return dict(api.rows[0],**{})|{9:len(api.rows)}
            def enumerate_creds_next(self):self.index+=1;return api.rows[self.index]
            def delete_cred(self,descriptor):
                api.calls.append(('DELETE',descriptor));api.rows=[r for r in api.rows if r[7]['id']!=descriptor['id']]
                if api.fail:raise api.fail
            def update_user_info(self,descriptor,user):
                api.calls.append(('RENAME',descriptor,user));api.rows[0][6]=user
                if api.fail:raise api.fail
        self.CredentialManagement=CM
        class Config:
            def __init__(self,ctap,proto,token):assert token==api.token
            @staticmethod
            def is_supported(info):return info.options.get('authnrCfg') is True
            def toggle_always_uv(self):api.calls.append(('ALWAYS_UV',));api.info.options['alwaysUv']=not api.info.options['alwaysUv']
            def set_min_pin_length(self,min_pin_length=None,rp_ids=None,force_change_pin=False,pin_complexity_policy=False):
                api.calls.append(('POLICY',min_pin_length,rp_ids,force_change_pin));api.info.min_pin_length=min_pin_length
            def enable_enterprise_attestation(self):api.calls.append(('EA',));api.info.options['ep']=True
        self.Config=Config
    def get_descriptor(self,path):
        assert path==self.descriptor.path
        if self.hid_change:self.descriptor.pid=1
        return self.descriptor
    def list_descriptors(self):return [self.descriptor]
