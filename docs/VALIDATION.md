# Manager 1.1.6 / firmware 0.6.1

The public source labels configuration exports as firmware 0.6.1. Export
continues to omit application packages, Wasm guests and build/release data.
The firmware source is distributed separately. Host tests run without USB;
tests requiring an embedded firmware tree are skipped in this standalone repo.

The existing public 1.1.6 executable remains available from its original
release. Its identity is retained in [RELEASE_CURRENT.json](../RELEASE_CURRENT.json).
This source synchronization is not a rebuilt executable or a new physical USB
test of Manager. Device acceptance of firmware 0.6.1 is recorded in the
[firmware validation](https://github.com/mwr666/EvilKey-firmware/blob/main/docs/VALIDATION.md).
