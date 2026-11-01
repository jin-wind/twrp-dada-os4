Xiaomi 15 (dada) — OS4 experimental TWRP

Target: Global OS4.0.0.11.XOCMIXM, Android 17, September 2026 security patch.
This is an experimental device port based on the pinned TWRP-Test twrp-16.0
source, not an official TWRP release or a fully validated Android 17 recovery.

The workflow downloads the official full OTA directly from Xiaomi. This Git
repository contains only build scripts, configuration changes, source revisions
and firmware hashes. No phone backup, user files, personal device identifiers or
private OTA authorization URL is required.

Build: Actions -> Build dada OS4 experimental TWRP -> Run workflow.
Uses a public-repository ubuntu-24.04 standard runner, with an 8 GiB temporary
swap file and sparse Clang/Rust checkouts. The job removes unused SDK directories
only when running on an ephemeral GitHub-hosted runner. No paid runner is used.
The preflight stops if insufficient disk space remains. Artifacts expire in
7 days; download the image and reports after a successful build.

The first local build completed, but inspection found missing dependencies of
the updated stock libqdutils. This workflow includes those libraries and their
transitive graphics dependencies from the same stock vendor image (155 stock
hardware files total). It also includes mi_product mount configuration, verified
OS4 firmware/modules, and a KeyMint initialization gate for the target version.
The default network ADB listener on TCP 5555 is disabled.

Source pins:
  Device: YuKongA/twrp_device_xiaomi_sm8750_thales
    ba8dc259c86d8287f9260e5f393f0a4cf230f4e7
  Recovery: TWRP-Test/android_bootable_recovery
    8a58fc3b586b8a908337fa87529cfbbb119ec7bb
  update_engine:
    a4c7444f722bada4e3880a5e38b42b9aa4ee37a4
  All Android project revisions: config/pinned-manifest.xml

The generated image is a kernel-less v4 image for a dedicated recovery
partition. Compilation and static checks do not establish that boot, touch,
decryption, MTP, Wi-Fi, backups/restores, or OTA installation work on a phone.
All runtime features remain NOT_TESTED until separately tested. The earlier
TWRP OTA boot loop has no confirmed root cause; this port does not claim to fix
it. Do not format Data to work around a decryption failure.

Build reports check image bounds, OS4 configuration, crypto guards, availability
of hardware ELF dependencies, and unchanged stock firmware/module hashes. The
dependency check does not prove runtime symbol or linker namespace compatibility.
KeyMint remains blocked if the installed system/version properties do not match
the exact target. A future OS update requires the gate and blobs to be reviewed.

Original upstream source license and copyright notices remain applicable.
Proprietary firmware is downloaded from Xiaomi during the build; no ownership
of those files is claimed. TWRP NOTICE accompanies successful artifacts.

https://github.com/TWRP-Test/platform_manifest_twrp_aosp
https://github.com/TWRP-Test/android_bootable_recovery
https://github.com/YuKongA/twrp_device_xiaomi_sm8750_thales
