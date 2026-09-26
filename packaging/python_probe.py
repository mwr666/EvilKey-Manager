# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Check the EXE build interpreter without importing the app or accessing USB.

Run as a file, not inline Python code through PowerShell's legacy -c quoting.
The one-line ASCII JSON result is readable in both Windows PowerShell 5.1 and 7.
"""
from __future__ import annotations

import json
import struct
import sys
import sysconfig
from typing import Any

SCHEMA = "evilkey-build-python-v1"


def runtime_info() -> dict[str, Any]:
    """Report the interpreter that actually ran this file, including virtualenvs."""
    return {
        "schema": SCHEMA,
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "version_tuple": list(sys.version_info[:3]),
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "architecture": sysconfig.get_platform(),
        "bits": struct.calcsize("P") * 8,
    }


def validate_runtime(info: dict[str, Any]) -> list[str]:
    """Keep build requirements separate from probing the optional GUI runtime."""
    errors: list[str] = []
    if info["implementation"] != "cpython":
        errors.append("CPython is required; other Python implementations are unsupported.")
    if info["platform"] != "win32":
        errors.append("Build the Windows EXE on Windows, not Linux, WSL, or macOS.")
    if info["bits"] != 64 or info["architecture"] != "win-amd64":
        errors.append("64-bit Python (win-amd64) is required; x86 and ARM64 are unsupported.")
    if not (3, 12) <= tuple(info["version_tuple"][:2]) < (3, 15):
        errors.append("Supported versions: CPython 3.12, 3.13, and 3.14.")
    return errors


def probe_tk() -> dict[str, str]:
    """Initialize real Tcl/Tk and ttk; importing tkinter alone is insufficient."""
    import tkinter as tk
    from tkinter import ttk

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        frame = ttk.Frame(root)
        frame.destroy()
        root.update_idletasks()
        return {
            "tcl": str(root.tk.call("info", "patchlevel")),
            "tk": str(root.tk.call("package", "require", "Tk")),
        }
    finally:
        if root is not None:
            root.destroy()


def build_report() -> dict[str, Any]:
    report = runtime_info()
    errors = validate_runtime(report)
    report["tcl_tk"] = None
    if not errors:
        try:
            report["tcl_tk"] = probe_tk()
        except Exception as exc:
            errors.append("Tcl/Tk: {}: {}".format(type(exc).__name__, str(exc)))
    report["errors"] = errors
    report["ok"] = not errors
    return report


def main() -> int:
    report = build_report()
    # ASCII JSON preserves non-ASCII paths independently of the terminal codepage.
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
