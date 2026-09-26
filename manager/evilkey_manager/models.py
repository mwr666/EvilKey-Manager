# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Validated public settings and transport records. No secret-bearing log models."""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import hashlib
import re
import struct
from typing import Any

class UserError(Exception):
    """A deliberately public, actionable error. Never interpolate a PIN/token."""

READ_ID = 0x50464D3100000001
WRITE_ID = 0x50464D3100000002
DRIVE_READ_ID = 0x50464D3200000001
DRIVE_WRITE_ID = 0x50464D3200000002
WIRE = struct.Struct(">4sBBBBHHHHII8s")
DRIVE_WIRE = struct.Struct(">4sBBBB")

def integer(value: Any, low: int, high: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise UserError(f"{label}: allowed range is {low}–{high}.")
    return value


@dataclass(frozen=True)
class ManagerDriveSettings:
    read_only: bool = False

    def validate(self) -> ManagerDriveSettings:
        if not isinstance(self.read_only,bool):
            raise UserError("The read-only mode must be a logical value.")
        return self

    def encode(self) -> bytes:
        self.validate()
        return DRIVE_WIRE.pack(b"PFM2",1,1 if self.read_only else 0,0,0)

    @classmethod
    def decode(cls,data: bytes) -> ManagerDriveSettings:
        if not isinstance(data,bytes) or len(data)!=DRIVE_WIRE.size:
            raise UserError("Invalid response length Manager Drive.")
        magic,version,flags,r0,r1=DRIVE_WIRE.unpack(data)
        if magic!=b"PFM2" or version!=1 or flags not in (0,1) or r0 or r1:
            raise UserError("Unsupported Manager Drive Settings Format. Nothing saved.")
        return cls(bool(flags)).validate()

@dataclass(frozen=True)
class DisplaySettings:
    brightness: int = 90
    dim_brightness: int = 8
    animation: bool = True
    dim_seconds: int = 30
    off_seconds: int = 60
    presence_seconds: int = 30
    uv_seconds: int = 120
    accent_rgb: int = 0x4DE3C1
    revision: int = 0

    def validate(self) -> DisplaySettings:
        integer(self.brightness,8,255,"Brightness")
        integer(self.dim_brightness,1,min(32,self.brightness),"Brightness after dimming")
        for label, value in (("Time to dim",self.dim_seconds),("Time to turn off",self.off_seconds)):
            integer(value,0,3600,label)
            if 0 < value < 5: raise UserError(label+": enter 0 or 5–3600 seconds.")
        integer(self.presence_seconds,1,120,"Time for confirmation")
        integer(self.uv_seconds,15,120,"On-device PIN timeout")
        integer(self.accent_rgb,0,0xFFFFFF,"RGB color")
        integer(self.revision,0,0xFFFFFFFF,"Revision of settings")
        if not isinstance(self.animation,bool): raise UserError("Animation: Logical value required.")
        r,g,b = self.accent_rgb>>16,(self.accent_rgb>>8)&255,self.accent_rgb&255
        if 299*r+587*g+114*b < 128000:
            raise UserError("The selected accent is too dark. Choose a brighter color for button readability.")
        return self

    def encode(self) -> bytes:
        self.validate()
        return WIRE.pack(b"PFM1",1,self.brightness,self.dim_brightness,int(self.animation),
            self.dim_seconds,self.off_seconds,self.presence_seconds,self.uv_seconds,
            self.accent_rgb,self.revision,b"\0"*8)

    @classmethod
    def decode(cls, data: bytes) -> DisplaySettings:
        if not isinstance(data,bytes) or len(data)!=WIRE.size:
            raise UserError("Invalid response length of M1 settings.")
        magic,version,bright,dim,flags,ds,os,ps,us,rgb,rev,reserved=WIRE.unpack(data)
        if magic!=b"PFM1" or version!=1 or flags not in (0,1) or reserved!=b"\0"*8:
            raise UserError("Unsupported M1 Settings Format. Nothing saved.")
        return cls(bright,dim,bool(flags),ds,os,ps,us,rgb,rev).validate()

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> DisplaySettings:
        if not isinstance(obj,dict) or set(obj)!=set(cls.__dataclass_fields__):
            raise UserError("The settings file has missing or unknown fields.")
        try: return cls(**obj).validate()
        except TypeError as exc: raise UserError("Invalid Settings Format.") from exc

    def export(self) -> dict[str, Any]:
        return {"schema":"evilkey-display-v1","settings":asdict(self)}

    @classmethod
    def import_for_revision(cls, obj: Any, revision: int) -> DisplaySettings:
        if (not isinstance(obj,dict) or set(obj)!={"schema","settings"} or
                obj.get("schema") not in ("evilkey-display-v1","pico-fido-display-v1")):
            raise UserError("This is not the EvilKey Manager screen settings file.")
        # A file from another board may never supply a concurrency revision.
        return replace(cls.from_dict(obj["settings"]),revision=revision)

def validate_new_pin(pin: str, minimum: int=4) -> None:
    if not isinstance(pin,str) or not re.fullmatch(r"[0-9]{4,63}",pin):
        raise UserError("The new PIN must have 4–63 digits 0–9. The keypad on the key is numeric.")
    if len(pin)<max(4,minimum): raise UserError(f"The device requires a PIN with at least {max(4,minimum)} digits.")

def validate_existing_pin(pin: Any) -> None:
    # Existing host PIN can include characters; do not normalize or strip it.
    if not isinstance(pin,str) or not 4<=len(pin.encode("utf-8"))<=63 or "\x00" in pin:
        raise UserError("Enter the current PIN. It is not stored in the configuration file.")

def rp_ids(value: Any, maximum: int) -> list[str]:
    if not isinstance(value,list) or len(value)>maximum:
        raise UserError(f"The RP list can contain at most {maximum} entries.")
    result=[]
    for item in value:
        if not isinstance(item,str) or not item or item!=item.strip() or any(c in item for c in "/:@?#\\"):
            raise UserError("Enter an RP ID such as example.com, without https:// or a path.")
        try: text=item.encode("idna").decode("ascii").lower()
        except UnicodeError as exc: raise UserError("Invalid RP ID.") from exc
        if len(text)>253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",p) for p in text.split('.')):
            raise UserError("Invalid RP ID.")
        if text in result: raise UserError("The list of RP contains a repetition.")
        result.append(text)
    return result

def display_text(value: Any, limit: int=160) -> str:
    text=str(value) if value is not None else "—"
    text="".join(c for c in text if c.isprintable())
    return text[:limit]

def path_pack(path: str | bytes) -> dict[str,str]:
    return {"kind":"bytes","value":path.hex()} if isinstance(path,bytes) else {"kind":"str","value":path}

def path_unpack(value: Any) -> str | bytes:
    if not isinstance(value,dict) or set(value)!={"kind","value"} or not isinstance(value["value"],str) or len(value["value"])>8192:
        raise UserError("Invalid device path.")
    if value["kind"]=="str": return value["value"]
    if value["kind"]=="bytes":
        try:return bytes.fromhex(value["value"])
        except ValueError:pass
    raise UserError("Invalid device path.")

def descriptor_public(d: Any) -> dict[str,Any]:
    serial=str(getattr(d,"serial_number","") or "")
    return {"path":path_pack(d.path),"vid":int(d.vid),"pid":int(d.pid),
        "product":str(d.product_name or ""),
        "serial_hash":hashlib.sha256(serial.encode()).hexdigest() if serial else "",
        "in":int(d.report_size_in),"out":int(d.report_size_out)}

def descriptor_same(a: dict,b: dict) -> bool:
    return all(a.get(k)==b.get(k) for k in ("path","vid","pid","product","serial_hash","in","out"))

def device_identity(d: dict,aaguid: str) -> str:
    import json
    data={k:d.get(k) for k in ("vid","pid","product","serial_hash")}
    data["aaguid"]=aaguid
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
