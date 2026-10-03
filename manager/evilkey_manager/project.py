# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Safe source configuration. Never executes header expressions or flashes USB."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
from . import __version__
from .models import DisplaySettings, UserError, integer

# Fixed USB identity of the Air Mouse role, first device-tested in 0.3.0. The Manager export
# replaces FidoConfig.h, so these definitions must accompany every export.
AIR_MOUSE_USB_DEFINITIONS = {
 "FIDO_V1_AIR_MOUSE_VID": "0xFEFF",
 "FIDO_V1_AIR_MOUSE_PID": "0xFCFA",
 "FIDO_V1_AIR_MOUSE_BCD_DEVICE": "0x0103",
 "FIDO_V1_AIR_MOUSE_PRODUCT": '"EvilKey Air Mouse DEV"',
 "FIDO_V1_AIR_MOUSE_MANUFACTURER": '"EvilKey development"',
}

DEFAULTS={
 "FIDO_V1_USB_PROFILE":2,"FIDO_V1_CUSTOM_VID":0xFEFF,"FIDO_V1_CUSTOM_PID":0xFCFD,
 "FIDO_V1_CUSTOM_PRODUCT":"EvilKey Waveshare V1 DEV","FIDO_V1_CUSTOM_MANUFACTURER":"EvilKey development",
 "FIDO_V1_CUSTOM_BCD_DEVICE":0x0100,"FIDO_V1_MANAGEMENT_SERIAL":0,
 "FIDO_V1_MANAGER_DRIVE":1,"FIDO_V1_MANAGER_DRIVE_DEFAULT":0,"FIDO_V1_MANAGER_DRIVE_READ_ONLY_DEFAULT":0,"FIDO_V1_MANAGER_DRIVE_SD_HZ":20000000,
 "FIDO_V1_MANAGER_DRIVE_VID":0xFEFF,"FIDO_V1_MANAGER_DRIVE_PID":0xFCFC,
 "FIDO_V1_MANAGER_DRIVE_PRODUCT":"EvilKey + Manager DEV",
 "FIDO_V1_MANAGER_DRIVE_MANUFACTURER":"EvilKey development","FIDO_V1_MANAGER_DRIVE_BCD_DEVICE":0x0101,
 "FIDO_V1_USB_TOOL":1,"FIDO_V1_USB_TOOL_DEFAULT":0,"FIDO_V1_USB_TOOL_VARIABLE_EXFIL":1,
 "FIDO_V1_USB_TOOL_KEYSTROKE_REFLECTION":1,"FIDO_V1_USB_TOOL_LAYOUT_DEFAULT":0,"FIDO_V1_USB_TOOL_LANGUAGE_DEFAULT":"us",
 "FIDO_V1_USB_TOOL_SD_HZ":20000000,"FIDO_V1_USB_TOOL_MAX_PAYLOAD":262144,
 "FIDO_V1_USB_TOOL_VID":0xFEFF,"FIDO_V1_USB_TOOL_PID":0xFCFB,
 "FIDO_V1_USB_TOOL_PRODUCT":"EvilKey USB Tool DEV",
 "FIDO_V1_USB_TOOL_MANUFACTURER":"EvilKey development","FIDO_V1_USB_TOOL_BCD_DEVICE":0x0102,
 "FIDO_V1_DISPLAY":1,"FIDO_V1_TOUCH_CONFIRM":1,"FIDO_V1_LOCAL_UV":1,"FIDO_V1_BOOT_CONFIRM_FALLBACK":0,
 "FIDO_V1_BRIGHTNESS":90,"FIDO_V1_DIM_BRIGHTNESS":8,"FIDO_V1_DIM_AFTER_SECONDS":30,
 "FIDO_V1_OFF_AFTER_DIM_SECONDS":60,"FIDO_V1_PRESENCE_TIMEOUT_SECONDS":30,
 "FIDO_V1_UV_TIMEOUT_SECONDS":120,"FIDO_V1_GUI_ACCENT_RGB":0x4DE3C1,"FIDO_V1_GUI_ANIMATION":1}
ALIASES={"FIDO_PROFILE_LOCAL_DEV":0,"FIDO_PROFILE_YK5_FIDO_COMPAT":1,"FIDO_PROFILE_CUSTOM_USB":2}
BOOL_FIELDS={"FIDO_V1_DISPLAY","FIDO_V1_TOUCH_CONFIRM","FIDO_V1_LOCAL_UV","FIDO_V1_BOOT_CONFIRM_FALLBACK","FIDO_V1_GUI_ANIMATION",
 "FIDO_V1_MANAGER_DRIVE","FIDO_V1_MANAGER_DRIVE_DEFAULT","FIDO_V1_MANAGER_DRIVE_READ_ONLY_DEFAULT",
 "FIDO_V1_USB_TOOL","FIDO_V1_USB_TOOL_DEFAULT","FIDO_V1_USB_TOOL_VARIABLE_EXFIL",
 "FIDO_V1_USB_TOOL_KEYSTROKE_REFLECTION"}
HEX_FIELDS={"FIDO_V1_CUSTOM_VID","FIDO_V1_CUSTOM_PID","FIDO_V1_CUSTOM_BCD_DEVICE","FIDO_V1_GUI_ACCENT_RGB",
 "FIDO_V1_MANAGER_DRIVE_VID","FIDO_V1_MANAGER_DRIVE_PID","FIDO_V1_MANAGER_DRIVE_BCD_DEVICE",
 "FIDO_V1_USB_TOOL_VID","FIDO_V1_USB_TOOL_PID","FIDO_V1_USB_TOOL_BCD_DEVICE"}
DISPLAY_MAP={"brightness":"FIDO_V1_BRIGHTNESS","dim_brightness":"FIDO_V1_DIM_BRIGHTNESS",
 "dim_seconds":"FIDO_V1_DIM_AFTER_SECONDS","off_seconds":"FIDO_V1_OFF_AFTER_DIM_SECONDS",
 "presence_seconds":"FIDO_V1_PRESENCE_TIMEOUT_SECONDS","uv_seconds":"FIDO_V1_UV_TIMEOUT_SECONDS",
 "accent_rgb":"FIDO_V1_GUI_ACCENT_RGB"}

def find_firmware_source() -> Path | None:
    """Find a separately supplied firmware tree beside the EXE or source checkout."""
    starts = [Path(sys.executable).resolve().parent] if getattr(sys, 'frozen', False) else [Path(__file__).resolve().parents[2]]
    for start in starts:
        for parent in (start, *list(start.parents)[:2]):
            candidate = parent / 'firmware'
            if (candidate / 'prepare_arduino.py').is_file() and (candidate / 'EvilKeyV1' / 'FidoConfig.h').is_file():
                return candidate
    return None

def parse_value(text: str):
    # A comment marker inside a quoted USB product name is ordinary text.
    token=re.fullmatch(r'\s*("(?:[^"\\]|\\.)*"|[A-Za-z0-9_xX]+)\s*(?:(?://[^\n]*)|(?:/\*.*?\*/))?\s*',text)
    if not token:raise UserError("A definition must contain a single number, alias, or string.")
    text=token.group(1)
    if text in ALIASES:return ALIASES[text]
    if re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]*",text):
        value=re.sub(r"[uUlL]+$","",text)
        return int(value,16 if value.lower().startswith('0x') else 10)
    if text.startswith('"') and text.endswith('"'):
        try:
            result=ast.literal_eval(text)
            if isinstance(result,str):return result
        except (ValueError,SyntaxError):pass
    raise UserError("Configuration contains an expression instead of a single value. I do not execute the code from the header.")

def validate_config(values: dict[str,Any]) -> dict[str,Any]:
    if set(values)!=set(DEFAULTS):raise UserError("Missing or unknown fields of project configuration.")
    for name in BOOL_FIELDS:integer(values[name],0,1,name)
    integer(values["FIDO_V1_USB_PROFILE"],0,2,"USB profile")
    usb_ids={"FIDO_V1_CUSTOM_VID":"Key VID","FIDO_V1_CUSTOM_PID":"Key PID",
             "FIDO_V1_MANAGER_DRIVE_VID":"Drive VID","FIDO_V1_MANAGER_DRIVE_PID":"Drive PID",
             "FIDO_V1_USB_TOOL_VID":"VID USB Tool","FIDO_V1_USB_TOOL_PID":"PID USB Tool"}
    for name,label in usb_ids.items():integer(values[name],1,65534,label)
    integer(values["FIDO_V1_CUSTOM_BCD_DEVICE"],0,65535,"USB Key Version")
    integer(values["FIDO_V1_MANAGER_DRIVE_BCD_DEVICE"],0,65535,"USB drive version")
    integer(values["FIDO_V1_USB_TOOL_BCD_DEVICE"],0,65535,"USB Tool version")
    integer(values["FIDO_V1_MANAGER_DRIVE_SD_HZ"],4000000,25000000,"Card Speed Manager Drive")
    integer(values["FIDO_V1_USB_TOOL_SD_HZ"],4000000,25000000,"USB Card Speed Tool")
    integer(values["FIDO_V1_USB_TOOL_MAX_PAYLOAD"],1024,262144,"Maximum script size")
    integer(values["FIDO_V1_USB_TOOL_LAYOUT_DEFAULT"],0,4,"USB Tool Keyboard Layout")
    lang=values["FIDO_V1_USB_TOOL_LANGUAGE_DEFAULT"]
    if not isinstance(lang,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,19}",lang):
        raise UserError("USB Tool language code: use 1–19 characters: A-Z, 0-9, '-' or '_'.")
    integer(values["FIDO_V1_MANAGEMENT_SERIAL"],0,0xFFFFFFFF,"Key identification number")
    if values["FIDO_V1_MANAGER_DRIVE_DEFAULT"] and not values["FIDO_V1_MANAGER_DRIVE"]:
        raise UserError("Manager Drive cannot run as enabled when the function is disabled.")
    if values["FIDO_V1_USB_TOOL_DEFAULT"] and not values["FIDO_V1_USB_TOOL"]:
        raise UserError("The USB Tool cannot run as enabled when the function is disabled.")
    if (values["FIDO_V1_USB_TOOL_VARIABLE_EXFIL"] or values["FIDO_V1_USB_TOOL_KEYSTROKE_REFLECTION"]) and not values["FIDO_V1_USB_TOOL"]:
        raise UserError("Variable capture and return-data reception require USB Tool support.")
    if values["FIDO_V1_USB_TOOL_DEFAULT"] and values["FIDO_V1_MANAGER_DRIVE_DEFAULT"]:
        raise UserError("The USB Tool and Manager Drive cannot be the default start profile at the same time.")
    usb_names={"FIDO_V1_CUSTOM_PRODUCT":"Key name","FIDO_V1_CUSTOM_MANUFACTURER":"Key manufacturer",
               "FIDO_V1_MANAGER_DRIVE_PRODUCT":"Drive name","FIDO_V1_MANAGER_DRIVE_MANUFACTURER":"Drive manufacturer",
               "FIDO_V1_USB_TOOL_PRODUCT":"USB Tool name","FIDO_V1_USB_TOOL_MANUFACTURER":"USB Tool manufacturer"}
    for name,label in usb_names.items():
        value=values[name]
        max_len=31 if name.startswith(("FIDO_V1_MANAGER_DRIVE_","FIDO_V1_USB_TOOL_")) else 63
        if not isinstance(value,str) or not 1<=len(value)<=max_len or any(ord(c)<32 or ord(c)>126 for c in value):
            raise UserError(f"{label}: use 1–{max_len} printable ASCII characters.")
    if values["FIDO_V1_LOCAL_UV"] and not(values["FIDO_V1_DISPLAY"] and values["FIDO_V1_TOUCH_CONFIRM"]):
        raise UserError("The PIN on the key requires a screen and touch.")
    if values["FIDO_V1_TOUCH_CONFIRM"] and not values["FIDO_V1_DISPLAY"]:raise UserError("Touch confirmation requires a screen.")
    if not(values["FIDO_V1_TOUCH_CONFIRM"] or values["FIDO_V1_BOOT_CONFIRM_FALLBACK"]):raise UserError("The physical method of confirmation must remain: touch or BOOT.")
    kwargs={short:values[full] for short,full in DISPLAY_MAP.items()}
    DisplaySettings(**kwargs,animation=bool(values["FIDO_V1_GUI_ANIMATION"])).validate()
    return values

def read_header(path: Path) -> dict[str,Any]:
    if not path.is_file() or path.stat().st_size>65536:raise UserError("No valid FidoConfig.h file.")
    text=path.read_text(encoding="utf-8-sig")
    if "FIDO_V1_USB_PROFILE" not in text or "FIDO_V1_LOCAL_UV" not in text:raise UserError("This is not the correct EvilKey configuration.")
    result=dict(DEFAULTS)
    for name in result:
        matches=re.findall(r"(?m)^\s*#\s*define\s+"+re.escape(name)+r"[ \t]+([^\n]*)$",text)
        if len(matches)>1:raise UserError("Ambiguous definition: "+name)
        if matches:result[name]=parse_value(matches[0])
    return validate_config(result)

def render_header(values: dict[str,Any]) -> str:
    validate_config(values)
    out=["/* SPDX-License-Identifier: AGPL-3.0-or-later */","#pragma once",
         "/* Source defaults: compile and upload to apply build/USB settings.",
         " * Runtime M1 display settings, when stored, take precedence over these defaults.",
         " * PINs, credentials and private keys must NEVER be stored in this header. */"]
    out += [f"#define {name} {v}" for name,v in ALIASES.items()]
    for name,v in values.items():
        if isinstance(v,str):value=json.dumps(v,ensure_ascii=True)
        elif name in HEX_FIELDS:value=f"0x{v:06X}UL" if name.endswith("RGB") else f"0x{v:04X}"
        else:value=str(v)
        out.extend((f"#ifndef {name}",f"#define {name} {value}","#endif"))
    out.append("/* Air Mouse USB role identity. */")
    out.extend(f"#define {name} {value}" for name,value in AIR_MOUSE_USB_DEFINITIONS.items())
    return "\n".join(out)+"\n"

def export_project(firmware_source: Path,destination: Path,values: dict) -> Path:
    """Create a NEW complete project. Never merge into an existing folder."""
    validate_config(values)
    source=firmware_source.resolve();destination=destination.expanduser().resolve()
    if destination.exists():raise UserError("The destination folder already exists. Select a different location.")
    if destination.is_relative_to(source):raise UserError("The export folder must be outside the sources of firmware.")
    if not(source/"prepare_arduino.py").is_file():raise UserError("Firmware source is unavailable. Place the separate firmware source package beside the Manager or choose its firmware folder.")
    if not destination.parent.is_dir():raise UserError("The parent export folder does not exist.")
    stage=Path(tempfile.mkdtemp(prefix='.evilkey-project-',dir=destination.parent))
    try:
        # No user venv, keys or test credential state can enter this copy.
        shutil.copytree(source,stage,dirs_exist_ok=True,ignore=shutil.ignore_patterns(
            '.cache','__pycache__','.git','.venv*','*.pyc','*.bin','*.elf',
            '*.ekapp','*.wasm','build','build-arduino*','release'))
        (stage/'EvilKeyV1/FidoConfig.h').write_text(render_header(values),encoding='utf-8',newline='\n')
        (stage/'MANAGER_EXPORT.json').write_text(json.dumps({'source_release':'0.6.0',
            'manager_release':__version__,'configuration':values,'device_write_performed':False},indent=2)+'\n',encoding='utf-8')
        if destination.exists():raise UserError("The target folder showed up during the export.")
        stage.rename(destination)
        return destination
    finally:
        if stage.exists():shutil.rmtree(stage)
