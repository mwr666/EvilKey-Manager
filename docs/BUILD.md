# Build EvilKey Manager 1.1.6

Use 64-bit Windows and Python with Tk. From the repository root, run `powershell -File scripts/build_windows.ps1` under the machine's normal PowerShell policy. The builder detects Python, creates an isolated `.venv-exe`, installs the pinned packages from `packaging/requirements-build.txt`, collects dependency notices, runs host-side tests, creates a USB worker and builds `dist/EvilKeyManager.exe`.

The frozen EXE self-test runs without opening the USB device. It may trigger Windows UAC because the application requests administrator privileges for device management. A successful build copies the tested EXE to `artifacts/manager/` and records its SHA-256 in `RELEASE_CURRENT.json`.

The EXE does not contain firmware source. To export a complete firmware project from the Manager, put an extracted [EvilKey firmware](https://github.com/mwr666/EvilKey-firmware) `firmware/` directory beside the EXE or select it in the application. Leave Air Mouse before using the Manager because the mouse-only USB role is separate from FIDO management.

For source use without a packaged EXE, run `manager/install.cmd` and then `manager/start_admin.cmd`. Do not use real FIDO credentials or PINs for a first demonstration. See [component validation](VALIDATION.md) for the tested baseline and its limits.


For firmware 0.9.1, keep the complete public source project together, including
PUBLIC_EXPORT_FILES.json and EvilKey.cmd in its root. Select its firmware/
directory in Manager. The updated source installation uses that explicit
manifest to export a complete native project, including trust/PCB recipes and
public verification fixtures. It never copies local keys, backups or build
outputs. The old 1.1.6 EXE retains its previous export behavior; use this source
installation for the complete native export.

Apply exported build-time settings through the firmware's EvilKey.cmd and
sign with the device's trusted key. Manager cannot replace an enrolled signer
or undo Secure Boot. See the [firmware workflow](https://github.com/mwr666/EvilKey-firmware/blob/main/docs/FIRMWARE_WORKFLOW.md).
