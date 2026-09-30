# Manager 1.1.6 validation

## Firmware 0.5.0 source-export candidate

The Manager source now labels a new configuration export as firmware 0.5.0.
The 84 host tests passed (11 skipped because bundled firmware is absent). A
temporary export of the standalone 0.5.0 firmware retained the ABI v4
interpreter and contained no `.ekapp` or `.wasm` files. This change remains
local preparation; the existing v1.1.6 executable and GitHub Release are
unchanged. No physical USB test was performed for this Manager change.

After the firmware's PSRAM and microSD save fix, an export from the corrected
standalone public-source tree preserved `ek_vm.c`, `ek_service.cpp` and
Wasm3's `m3_core.c` byte-for-byte. The export contained no `.ekapp`, `.wasm`
or firmware release asset. The 84 Manager host tests passed (11 skipped for
the absent bundled firmware). This verifies source export only; the public
firmware release and a new Manager executable have not been published.

## Earlier 1.1.6 build

The standalone Windows build from this repository produced a 30,594,234-byte
`EvilKeyManager.exe` with SHA-256
`21d3f5b49cf2cfc63686103e36977ed02e7062d2dcdf6d9ed0177681af9f7e47`.

The build completed the host-side logic tests (including the app-package
exclusion check; 11 tests requiring bundled firmware were skipped), loot decoder
tests, and GUI tests. The frozen EXE self-test returned
`ok=true`, `frozen=true`, `usb_opened=false`, with six GUI pages and a working
bundled USB worker using `fido2 2.2.1` and `cryptography 50.0.1`.

A separate source-export check used the prepared standalone firmware 0.4.0
tree. The exported project retained the Apps interpreter and omitted app
packages, Wasm guests, and build output. No USB device was opened.

This standalone build has not been retested with a physical EvilKey over USB.
The earlier combined-project EXE passed a separate frozen self-test, but it is
not the EXE distributed by this repository's release.
The rebuilt EXE recorded above remains a local source-build check. The public
v1.1.6 release asset and its `RELEASE_CURRENT.json` record are unchanged.
