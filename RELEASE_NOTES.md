EvilKey Manager remains **1.1.6**. This source snapshot updates configuration-export and demo labels for firmware **0.9.1**; the original public executable remains unchanged.

Firmware 0.9.1 adds ABI6-NP1 with ABI4/5 compatibility, asynchronous USB storage and signed SD UPDATE/RESCUE packages for PCB V1.0 and V1.1. Its EvilKey.cmd groups builds, own-key/trust/bootloader setup, packages, backups and recovery.

The updated Manager source exports the complete current public native project through its explicit source-file manifest. Keep the complete firmware source package together and select its firmware/ directory. Build-time settings require rebuilding and signing with the device's trusted key. Manager cannot bypass signatures, change enrolled trust or enable protection.

Choose your own RSA3072 key and matching bootloader **before** Secure Boot activation. Release-key devices then accept only compatible repository-signed updates; own-key devices need the same private key for future updates and recovery. Secure Boot activation is irreversible.

The existing executable is available in the [original 1.1.6 release](https://github.com/mwr666/EvilKey-Manager/releases/tag/v1.1.6). Use the updated source installation for the complete native export. This archive contains no firmware or game source.

[Firmware 0.9.1](https://github.com/mwr666/EvilKey-firmware/releases/tag/v0.9.1) · [Run and build](https://github.com/mwr666/EvilKey-Manager/tree/v1.1.6-fw0.9.1#run-and-build) · [Signing workflow](https://github.com/mwr666/EvilKey-firmware/blob/v0.9.1/docs/FIRMWARE_WORKFLOW.md)
