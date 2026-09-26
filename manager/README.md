# EvilKey Manager 1.1.6

The Windows Manager provides local device information, FIDO PIN and policy controls, credential management, display settings, firmware configuration export, and USB Tool data decoding. The header mark is static; the 3D logo beside the device name on Overview is animated.

Firmware export uses the separately distributed firmware source and includes the Air Mouse USB identity; its initial values match this release's `FidoConfig.h`. Put the `firmware/` directory beside the EXE or select it when prompted. The EXE does not embed firmware source. Air Mouse pointer preferences are set on the key. Exit the mouse-only USB role to reconnect Manager in FIDO mode.

Run `scripts/build_windows.ps1` from the repository root to build and test the EXE. A source installation can use `install.cmd` followed by `start_admin.cmd`; `demo.cmd` opens an in-memory preview without USB. The USB worker requires pinned `fido2==2.2.1`. The GUI does not store PINs or PIN/UV tokens. A write is never retried automatically after a connection error because it may already have reached the key.

The *USB Tool data* tab works offline. It reads EvilKey `loot.bin` variable records (little-endian 16-bit values) or raw feedback bytes and exports CSV. A matching `.idx` sidecar identifies mixed segments and is verified against file size and SHA-256. Without an index, select the format manually.

See [build instructions](../docs/BUILD.md) and [release validation](../docs/VALIDATION.md).

The Manager source is available for private noncommercial use under [EvilKey Manager License 1.0](LICENSE.md). Bundled dependencies retain their own terms in `licenses/`. The [firmware and device GUI](https://github.com/mwr666/EvilKey-firmware) are separately distributed under GNU AGPL version 3.
