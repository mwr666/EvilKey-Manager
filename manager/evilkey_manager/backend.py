# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Real CTAP operations. Exactly one selected HID target and one job per process.

The GUI never receives PIN/UV tokens or largeBlobKeys. Mutating commands are not
retried. Connection failures are not interpreted as proof that a write failed.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import importlib.metadata
import logging
import os
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable
from .models import (DisplaySettings, ManagerDriveSettings, READ_ID, WRITE_ID, DRIVE_READ_ID, DRIVE_WRITE_ID, UserError, descriptor_public,
    descriptor_same, device_identity, integer, path_unpack, rp_ids,
    validate_existing_pin, validate_new_pin)

MUTATIONS={"set_pin","change_pin","always_uv","pin_policy","delete_credential",
    "rename_credential","display_write","drive_write","enterprise","reset","resident_keys","makecred_uv"}
AUTH_JOBS={"metadata","credentials","always_uv","pin_policy","delete_credential",
    "rename_credential","display_read","display_write","drive_read","drive_write","enterprise","resident_keys","makecred_uv"}

class Cancelled(UserError):pass

def load_api() -> Any:
    try:
        version=importlib.metadata.version("fido2")
        if version!="2.2.1":raise UserError("fido2 version 2.2.1 is required. Run install.cmd in the application folder.")
        from fido2.hid import CtapHidDevice, get_descriptor, list_descriptors, open_connection
        from fido2.ctap2 import Ctap2
        from fido2.ctap2.pin import ClientPin, PinProtocolV1, PinProtocolV2
        from fido2.ctap2.credman import CredentialManagement
        from fido2.ctap2.config import Config
        from fido2.ctap import CtapError
        from fido2 import cbor
    except (ImportError,importlib.metadata.PackageNotFoundError) as exc:
        raise UserError("No fido2 library. Start install.cmd or use a working .venv-probe-new environment.") from exc
    # Library diagnostics may contain public account data or raw protocol data.
    logging.getLogger("fido2").disabled=True
    logging.disable(logging.CRITICAL)
    return SimpleNamespace(**locals())

def error_public(exc: BaseException, mutation: bool=False) -> dict[str,Any]:
    code=getattr(exc,"code",None)
    try: code=int(code) if code is not None else None
    except (ValueError,TypeError):code=None
    win=getattr(exc,"winerror",None)
    messages={
        0x01:"The command is not supported by this firmware.",
        0x21:"The key has reported a processing error. Do not rerun the operation automatically.",
        0x27:"The operation was turned down on the key.",
        0x2B:"This key does not support this function. EvilKey firmware 0.2.6 or newer is required.",
        0x2D:"The key confirmed the cancellation of the request.",
        0x2E:"There are no matching credentials.",
        0x2F:"The waiting time for user action has expired.",
        0x30:"Operation not allowed. For M1 settings, read the current revision. Check the time from full power on for reset.",
        0x31:"Invalid PIN. The attempt may have reduced the counter. I do not repeat automatically.",
        0x32:"The PIN is locked. Do not try any more codes.",
        0x33:"Authorization has been rejected. Do not change the PIN or reset the key for diagnostic purposes.",
        0x34:"PIN verification requires full key power off.",
        0x35:"The PIN has not been set.",
        0x36:"This operation requires PIN or on-device verification.",
        0x37:"The PIN does not meet key policy. Check the minimum length and active rules.",
        0x38:"The authorization session has expired. Start a new operation manually.",
        0x3C:"On-device verification is blocked.",
        0x3F:"Invalid PIN on the panel. Not automatically repeated.",
        0x40:"The required PIN/UV authorization token is missing.",
    }
    if isinstance(exc,UserError):text=str(exc)
    elif code is not None:text=messages.get(code,f"The device returned CTAP error 0x{code:02X}. The operation will not be retried automatically.")
    elif isinstance(exc,OSError):
        text=("No access to FIDO HID. Run the application as an administrator and close other key support programs."
            if win==5 else "The USB connection has been lost or the key cannot be opened. Select the device again.")
    else:text="Invalid response or application error. Operation stopped; raw data is not saved."
    if mutation:text+=" A write may already have been applied. Read device state before another change."
    return {"message":text,"ctap":code,"winerror":win,
        "kind":type(exc).__name__,"connection_lost":isinstance(exc,OSError)}

def admin_access_available() -> bool:
    if os.name!='nt':return True
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())

class Session:
    def __init__(self,api: Any,args: dict,event: Event,progress: Callable[[str],None]):
        self.api=api;self.args=args;self.event=event;self.progress=progress
        self.connection=None;self.device=None;self.ctap=None

    def __enter__(self):
        if not admin_access_available():
            raise UserError("Administrative access to FIDO HID requires the application to be run as an administrator.")
        expected=self.args.get("device")
        if not isinstance(expected,dict):raise UserError("First pick and read the key.")
        d=self.api.get_descriptor(path_unpack(expected.get("path")))
        actual=descriptor_public(d)
        if not descriptor_same(actual,expected):raise UserError("The device or its USB profile has changed. Select the key again.")
        if actual["in"]!=64 or actual["out"]!=64:raise UserError("This USB profile does not match the EvilKey transport.")
        if self.event.is_set():raise Cancelled("Cancelled before opening USB.")
        self.progress("Opening the selected key...")
        try:
            self.connection=self.api.open_connection(d)
            self.device=self.api.CtapHidDevice(d,self.connection)
            event=self.event;progress=self.progress;base=self.api.Ctap2
            class BoundCtap(base):
                def send_cbor(self,cmd,data=None,*,event=None,on_keepalive=None):
                    if self._cancel.is_set():raise Cancelled("Cancelled before the next USB command.")
                    return super().send_cbor(cmd,data,event=event if event is not None else self._cancel,
                        on_keepalive=on_keepalive if on_keepalive is not None else self._keepalive)
                def __init__(self,device):
                    self._cancel=event
                    self._keepalive=lambda status:progress("Enter PIN / confirm on key screen..." if int(status)==2 else "The device is processing the request…")
                    super().__init__(device,strict_cbor=True)
            self.ctap=BoundCtap(self.device)
            self.identity=device_identity(actual,self.aaguid())
            if self.args.get("identity") and self.args["identity"]!=self.identity:
                raise UserError("The answer came from another key profile. No change was sent.")
            return self
        except BaseException:
            self.close();raise

    def aaguid(self) -> str:
        return bytes(self.ctap.info.aaguid).hex()

    def __exit__(self,*exc):self.close()
    def close(self):
        if self.connection is not None:
            try:self.connection.close()
            except Exception:pass
        self.connection=None;self.device=None;self.ctap=None

    def client(self):
        info=self.ctap.info
        protocols=list(info.pin_uv_protocols)
        version=self.args.get("protocol",0)
        if version==0:version=2 if 2 in protocols else 1
        if version not in (1,2) or version not in protocols:
            raise UserError("The selected PIN/UV protocol is not supported. No PIN test has been performed.")
        proto=self.api.PinProtocolV2() if version==2 else self.api.PinProtocolV1()
        return self.api.ClientPin(self.ctap,proto),proto

    def require_owner(self):
        if self.args.get("owner_confirmed") is not True or self.args.get("identity")!=self.identity:
            raise UserError("Confirm that the selected key is your EvilKey. Changes are blocked.")

    def auth(self,permission: int):
        self.require_owner()
        if self.ctap.info.options.get("pinUvAuthToken") is not True:
            raise UserError("The key does not share tokens with limited permissions.")
        client,proto=self.client();auth=self.args.get("auth",{})
        token=b""
        if auth.get("method")=="panel":
            if self.ctap.info.options.get("uv") is not True:
                raise UserError("The PIN on the panel is not ready. Check the PIN setting or select the authorization on your computer.")
            retries=client.get_uv_retries()
            if retries<=0:raise UserError("No on-device PIN attempts remain. The PIN request was not sent.")
            self.progress(f"On-device authorization — remaining PIN attempts: {retries}.")
            token=client.get_uv_token(permissions=permission,event=self.event,
                on_keepalive=lambda s:self.progress("Enter PIN on device…" if int(s)==2 else "Authorization in progress…"))
        elif auth.get("method")=="host":
            validate_existing_pin(auth.get("pin"))
            retries,power=client.get_pin_retries()
            if retries<=0 or power:raise UserError("The PIN is blocked or requires full power off. No test was done.")
            self.progress(f"ClientPIN authorization — remaining attempts: {retries}.")
            token=client.get_pin_token(auth["pin"],permissions=permission)
        else:raise UserError("Select the authorization method.")
        if not isinstance(token,bytes) or len(token)!=32:raise UserError("The device returned an invalid authorization token.")
        return proto,token

    def snapshot(self) -> dict:
        info=self.ctap.info;pin=None;uv=None;power=None
        if self.api.ClientPin.is_supported(info):
            client,_=self.client();pin,power=client.get_pin_retries()
            if "uv" in info.options:
                try:uv=client.get_uv_retries()
                except self.api.CtapError as exc:
                    if int(exc.code) not in (0x01,0x2B):raise
        return {"identity":self.identity,"aaguid":self.aaguid(),"versions":list(info.versions),
            "options":dict(info.options),"protocols":list(info.pin_uv_protocols),
            "pin_retries":pin,"uv_retries":uv,"power_cycle":power,
            "min_pin_length":getattr(info,"min_pin_length",4),
            "force_pin_change":bool(getattr(info,"force_pin_change",False)),
            "max_rpids":getattr(info,"max_rpids_for_min_pin",0),
            "max_msg_size":info.max_msg_size,
            "remaining_disc_creds":getattr(info,"remaining_disc_creds",None),
            "firmware_reported":getattr(info,"firmware_version",None),
            "extensions":list(getattr(info,"extensions",[])),
            "authenticator_config_commands":getattr(info,"authenticator_config_commands",None),
            "vendor_commands":list(getattr(info,"vendor_prototype_config_commands",[]))}

    def _manager_reply(self,result: Any) -> dict:
        if not isinstance(result,dict) or result.get(1)!=1 or not isinstance(result.get(2),bytes) or not isinstance(result.get(4),bool):
            raise UserError("The answer does not confirm the M1 API support. I do not consider the settings to be saved.")
        settings=DisplaySettings.decode(result[2])
        return {"settings":asdict(settings),"firmware":str(result.get(3,""))[:40],
            "storage_ok":result[4],"build_flags":int(result.get(5,0))}

    def display(self,write: bool=False) -> dict:
        if not self.api.Config.is_supported(self.ctap.info):raise UserError("No configuration interface in key.")
        params={1:WRITE_ID if write else READ_ID}
        wanted=None
        if write:
            wanted=DisplaySettings.from_dict(self.args.get("settings"))
            if self.args.get("display_confirmed") is not True:raise UserError("Writing the settings requires confirmation.")
            params[2]=wanted.encode()
        proto,token=self.auth(0x20)
        try:
            self.progress("Save screen settings..." if write else "Reading screen settings...")
            message=b"\xff"*32+b"\x0d\xff"+self.api.cbor.encode(params)
            signature=proto.authenticate(token,message)
            result=self._manager_reply(self.ctap.config(255,params,proto.VERSION,signature))
            if write:
                actual=DisplaySettings.from_dict(result["settings"])
                expected=asdict(wanted);expected["revision"]+=1
                if asdict(actual)!=expected or not result["storage_ok"]:
                    raise UserError("The key did not confirm these settings exactly. Read the status before the next change.")
            return result
        finally:token=b""

    def _drive_reply(self,result: Any) -> dict:
        if not isinstance(result,dict) or result.get(1)!=1 or not isinstance(result.get(2),bytes) or not isinstance(result.get(4),bool) or not isinstance(result.get(5),bool) or not isinstance(result.get(6),bool):
            raise UserError("The answer does not confirm the support of API Manager Drive. I do not consider the settings saved.")
        settings=ManagerDriveSettings.decode(result[2])
        return {"settings":asdict(settings),"firmware":str(result.get(3,""))[:40],
            "storage_ok":result[4],"compiled":result[5],"enabled":result[6]}

    def drive(self,write: bool=False) -> dict:
        if not self.api.Config.is_supported(self.ctap.info):raise UserError("No configuration interface in key.")
        params={1:DRIVE_WRITE_ID if write else DRIVE_READ_ID}
        wanted=None
        if write:
            wanted=ManagerDriveSettings(self.args.get("read_only")).validate()
            if self.args.get("drive_confirmed") is not True:raise UserError("Changing write protection requires confirmation.")
            params[2]=wanted.encode()
        proto,token=self.auth(0x20)
        try:
            self.progress("Enable microSD write protection..." if write and wanted.read_only else "Disable microSD write protection..." if write else "Reading Manager Drive mode...")
            message=b"\xff"*32+b"\x0d\xff"+self.api.cbor.encode(params)
            signature=proto.authenticate(token,message)
            result=self._drive_reply(self.ctap.config(255,params,proto.VERSION,signature))
            if write:
                actual=ManagerDriveSettings(**result["settings"])
                if actual!=wanted or not result["storage_ok"]:
                    raise UserError("The key did not accurately confirm the write protection. Read the condition before the next change.")
            return result
        finally:token=b""

    def credential_manager(self):
        if not self.api.CredentialManagement.is_supported(self.ctap.info):
            raise UserError("The key does not make the credential management available.")
        proto,token=self.auth(0x04)
        return self.api.CredentialManagement(self.ctap,proto,token)

    def _rps(self,cm):
        try:first=cm.enumerate_rps_begin()
        except self.api.CtapError as exc:
            if int(exc.code)==0x2E:return []
            raise
        total=integer(first.get(5),0,256,"Number of RPs in key response")
        if total==0:return []
        result=[first]
        for _ in range(1,total):result.append(cm.enumerate_rps_next())
        return result

    def _creds(self,cm,rp_hash):
        try:first=cm.enumerate_creds_begin(rp_hash)
        except self.api.CtapError as exc:
            if int(exc.code)==0x2E:return []
            raise
        total=integer(first.get(9,1),1,256,"Credential count in device response")
        result=[first]
        for _ in range(1,total):result.append(cm.enumerate_creds_next())
        return result

    @staticmethod
    def public_credential(rp: str,rp_hash: bytes,row: dict) -> dict:
        user=row.get(6,{});credential=row.get(7,{})
        cid=credential.get("id");uid=user.get("id")
        if not isinstance(cid,bytes) or not 1<=len(cid)<=1024 or not isinstance(uid,bytes) or not 1<=len(uid)<=64:
            raise UserError("The key returned an invalid credential ID.")
        if credential.get("type")!="public-key":raise UserError("Unsupported type of credential.")
        # Deliberately never forward row[11] (largeBlobKey), even to the GUI.
        return {"rp":rp,"rp_hash":rp_hash.hex(),"credential_id":cid.hex(),"user_id":uid.hex(),
            "name":str(user.get("name","")),"display_name":str(user.get("displayName","")),
            "protection":row.get(10),"algorithm":row.get(8,{}).get(3)}

    def metadata(self) -> dict:
        cm=self.credential_manager()
        try:
            raw=cm.get_metadata()
            return {"existing":integer(raw.get(1),0,256,"Credential count"),
                "remaining_estimate":integer(raw.get(2),0,256,"Estimated free credential slots")}
        finally:cm=None

    def credentials(self) -> dict:
        cm=self.credential_manager()
        try:
            metadata=cm.get_metadata();result=[];hashes=set();ids=set()
            for item in self._rps(cm):
                rp=item.get(3,{}).get("id");rp_hash=item.get(4)
                if not isinstance(rp,str) or not isinstance(rp_hash,bytes) or len(rp_hash)!=32 or hashlib.sha256(rp.encode()).digest()!=rp_hash or rp_hash in hashes:
                    raise UserError("Incoherent response to the list of RPs. I do not display a partial list.")
                hashes.add(rp_hash)
                for row in self._creds(cm,rp_hash):
                    public=self.public_credential(rp,rp_hash,row)
                    if public["credential_id"] in ids or len(result)>=256:raise UserError("Incoherent list of credentials.")
                    ids.add(public["credential_id"]);result.append(public)
            if len(result)!=metadata.get(1):raise UserError("The number of credentials changed during reading. Refresh the list manually.")
            return {"credentials":result,"existing":len(result),
                "remaining_estimate":integer(metadata.get(2),0,256,"Estimated free credential slots")}
        finally:cm=None

    def edit_credential(self,delete: bool) -> dict:
        selected=self.args.get("credential")
        if not isinstance(selected,dict):raise UserError("Select the credential from the read list.")
        try:cid=bytes.fromhex(selected["credential_id"]);rph=bytes.fromhex(selected["rp_hash"])
        except (KeyError,ValueError,TypeError) as exc:raise UserError("Invalid credential selection.") from exc
        if not 1<=len(cid)<=1024 or len(rph)!=32:raise UserError("Invalid credential selection.")
        if not isinstance(selected.get("rp"),str) or hashlib.sha256(selected["rp"].encode()).digest()!=rph:
            raise UserError("Incoherent service of the selected credential.")
        expected=("DELETE:" if delete else "RENAME:")+selected["credential_id"]
        if self.args.get("confirmation")!=expected:raise UserError("No confirmation of the operation on a specific credential.")
        name=self.args.get("name","");display=self.args.get("display_name","")
        if not delete:
            if not self.api.CredentialManagement.is_update_supported(self.ctap.info):raise UserError("No function to change the description of the credential.")
            for text in (name,display):
                if not isinstance(text,str) or not text or len(text.encode())>64 or any(not c.isprintable() for c in text):
                    raise UserError("The name and description shall be 1–64 bytes of UTF-8 and shall not contain control characters.")
        cm=self.credential_manager()
        try:
            matches=[]
            for row in self._creds(cm,rph):
                public=self.public_credential(selected["rp"],rph,row)
                if public["credential_id"]==selected["credential_id"]:matches.append(public)
            if len(matches)!=1 or any(matches[0].get(k)!=selected.get(k) for k in ("user_id","name","display_name")):
                raise UserError("The credential has changed since the last reading. Refresh the list and select them again.")
            descriptor={"id":cid,"type":"public-key"}
            if delete:
                cm.delete_cred(descriptor)
            else:
                cm.update_user_info(descriptor,{"id":bytes.fromhex(selected["user_id"]),"name":name,"displayName":display})
            # No auto-retry on lost acknowledgement. A separate read confirms state.
            return {"acknowledged":True,"requires_refresh":True}
        finally:cm=None

    def policy(self,kind: str) -> dict:
        if not self.api.Config.is_supported(self.ctap.info):raise UserError("The key does not provide FIDO configuration.")
        info=self.ctap.info;opts=info.options
        if self.args.get("policy_confirmed") is not True:raise UserError("Changing policy requires confirmation.")
        if kind=="always_uv":
            wanted=self.args.get("enabled")
            if not isinstance(wanted,bool) or "alwaysUv" not in opts:raise UserError("AlwaysUV is not available.")
            if wanted==opts["alwaysUv"]:return {"unchanged":True}
        elif kind=="pin_policy":
            minimum=integer(self.args.get("minimum"),max(4,getattr(info,"min_pin_length",4)),63,"Minimum PIN length")
            rps=rp_ids(self.args.get("rp_ids"),min(120,getattr(info,"max_rpids_for_min_pin",0)))
            force=self.args.get("force_change")
            if not isinstance(force,bool) or opts.get("setMinPINLength") is not True:raise UserError("Setting the minimum length of the PIN is not available.")
            if self.args.get("replace_rp_list") is not True:raise UserError("Confirm replacing the list of RP. The previous list is not read by GetInfo.")
            example={1:3,2:{1:minimum,2:rps,3:force},3:2,4:b"\0"*32}
            if 1+len(self.api.cbor.encode(example))>info.max_msg_size:raise UserError("The list of RP does not fit in one key command. Shorten the list.")
        elif kind=="enterprise":
            if "ep" not in opts:raise UserError("This profile does not enable Enterprise Attestation.")
            if opts["ep"] is True:return {"unchanged":True}
        proto,token=self.auth(0x20)
        try:
            cfg=self.api.Config(self.ctap,proto,token)
            if kind=="always_uv":cfg.toggle_always_uv()
            elif kind=="pin_policy":cfg.set_min_pin_length(min_pin_length=minimum,rp_ids=rps,force_change_pin=force)
            else:cfg.enable_enterprise_attestation()
            new=self.ctap.get_info()
            if kind=="always_uv" and new.options.get("alwaysUv")!=wanted:raise UserError("The check readout didn't confirm the requested alwaysUV.")
            if kind=="pin_policy" and getattr(new,"min_pin_length",4)!=minimum:raise UserError("The check readout did not confirm the minimum length of the PIN.")
            return {"acknowledged":True,"requires_refresh":True}
        finally:token=b""

    def vendor_policy(self,kind: str) -> dict:
        """Two pinned Pico configuration flags, with desired-state readback."""
        self.require_owner()
        if self.args.get("policy_confirmed") is not True:raise UserError("Changing policy requires confirmation.")
        key,command=("rk",0x00052b41f53590d3) if kind=="resident_keys" else ("makeCredUvNotRqd",0x000377913e17951f)
        opts=self.ctap.info.options;wanted=self.args.get("enabled")
        if command not in getattr(self.ctap.info,"vendor_prototype_config_commands",[]) or key not in opts or not isinstance(wanted,bool):
            raise UserError("This key does not support this configuration change.")
        if kind=="makecred_uv" and wanted and opts.get("alwaysUv"):
            raise UserError("First, turn off allwaysUV.")
        if opts[key] is wanted:return {"unchanged":True}
        proto,token=self.auth(0x20)
        try:
            params={1:command};message=b"\xff"*32+b"\x0d\xff"+self.api.cbor.encode(params)
            self.ctap.config(255,params,proto.VERSION,proto.authenticate(token,message))
            if self.ctap.get_info().options.get(key) is not wanted:
                raise UserError("The key did not confirm the new policy value. Read the state; I do not repeat the record.")
            return {"acknowledged":True,"requires_refresh":True}
        finally:token=b""

    def pin_change(self,change: bool) -> dict:
        self.require_owner();client,_=self.client();info=self.ctap.info
        configured=info.options.get("clientPin")
        if configured is not change:raise UserError("The PIN state has changed. Read the key again.")
        new=self.args.get("new_pin");validate_new_pin(new,getattr(info,"min_pin_length",4))
        if self.args.get("pin_confirmed") is not True:raise UserError("Changing the PIN requires confirmation.")
        if change:
            old=self.args.get("old_pin");validate_existing_pin(old)
            retries,power=client.get_pin_retries()
            if retries<=0 or power:raise UserError("The PIN is blocked or requires resupply. No sample was sent.")
            client.change_pin(old,new)
        else:client.set_pin(new)
        return {"acknowledged":True,"requires_refresh":True}

    def reset(self) -> dict:
        self.require_owner()
        if self.args.get("confirmation")!="RESET EVILKEY":raise UserError("No full FIDO reset confirmation.")
        self.progress("Request FIDO reset. Confirm physically on key if request occurs.")
        self.ctap.reset(event=self.event,on_keepalive=lambda _:self.progress("Confirm reset on key..."))
        return {"reset_acknowledged":True}

def execute(operation: str,args: dict,event: Event,progress: Callable[[str],None],api=None) -> dict | list:
    allowed={"scan","info","ping"}|AUTH_JOBS|MUTATIONS
    if not isinstance(operation,str) or operation not in allowed or not isinstance(args,dict):
        raise UserError("Unknown operation or wrong request. No USB opened.")
    api=api or load_api()
    if operation=="scan":return [descriptor_public(d) for d in api.list_descriptors()]
    with Session(api,args,event,progress) as s:
        if operation=="info":return s.snapshot()
        if operation=="ping":
            challenge=b"EvilKeyManager:"+os.urandom(16)
            if s.device.ping(challenge)!=challenge:raise UserError("PING's answer disagrees with the question.")
            return {"ping_ok":True}
        if operation=="metadata":return s.metadata()
        if operation=="credentials":return s.credentials()
        if operation=="display_read":return s.display()
        if operation=="display_write":return s.display(True)
        if operation=="drive_read":return s.drive()
        if operation=="drive_write":return s.drive(True)
        if operation in ("always_uv","pin_policy","enterprise"):return s.policy(operation)
        if operation in ("set_pin","change_pin"):return s.pin_change(operation=="change_pin")
        if operation in ("delete_credential","rename_credential"):return s.edit_credential(operation=="delete_credential")
        if operation in ("resident_keys","makecred_uv"):return s.vendor_policy(operation)
        if operation=="reset":return s.reset()
        raise UserError("Unknown operation, no change sent.")
