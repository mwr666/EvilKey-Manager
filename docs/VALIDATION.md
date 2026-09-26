# Manager 1.1.6 validation

The standalone Windows build from this repository produced a 30,594,386-byte
`EvilKeyManager.exe` with SHA-256
`f473eab6f08c354b80d870cd0661d29f1b48ed36ba8401ad351b142f3462909a`.

The build completed the host-side logic tests (83 run, 11 skipped), loot decoder
tests (10 passed), and GUI tests (28 passed). The frozen EXE self-test returned
`ok=true`, `frozen=true`, `usb_opened=false`, with six GUI pages and a working
bundled USB worker using `fido2 2.2.1` and `cryptography 50.0.1`.

This standalone build has not been retested with a physical EvilKey over USB.
The earlier combined-project EXE passed a separate frozen self-test, but it is
not the EXE distributed by this repository's release.
