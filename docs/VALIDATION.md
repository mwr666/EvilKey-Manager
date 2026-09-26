# Manager 1.1.6 validation baseline

The original combined-project Windows build produced a 30,593,902-byte Manager EXE with SHA-256 `3b5d85881eb5c300293b74ce392dbb1daca0a52332c3ba541231ccbb285172db`. It passed the frozen self-test with `ok=true`, `frozen=true`, `usb_opened=false`, six GUI pages and a working bundled USB worker using `fido2 2.2.1` and `cryptography 50.0.1`.

This split repository copies the Manager application and build sources without its earlier combined repository history. The baseline hash refers to that earlier EXE, not automatically to a new build from this split repository. Run `scripts/build_windows.ps1` and verify its new SHA-256 before distributing an EXE from here. USB device operation requires a separate physical test.
