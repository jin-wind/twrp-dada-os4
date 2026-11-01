#!/usr/bin/env bash
set -eo pipefail
project="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${RUNNER_TEMP:?}/dada-os4-build"
[[ "${GITHUB_ACTIONS:-}" == true ]]
cd "$build_root/source"
export ALLOW_MISSING_DEPENDENCIES=true
export BUILD_USERNAME=dada-port
export BUILD_HOSTNAME=github-actions
export GOMAXPROCS=4
export SOONG_GOMEMLIMIT=10GiB
export LC_ALL=C.UTF-8 LANG=C.UTF-8
source build/envsetup.sh
lunch twrp_sm8750_thales
m -j4 recoveryimage
image=out/target/product/sm8750_thales/recovery.img
python3 "$project/scripts/inspect_image.py" "$image" \
  --report "$project/artifacts/image-inspection.json" \
  --blob-provenance "$build_root/port-blob-provenance.json"
cp "$image" "$project/artifacts/twrp-dada-OS4.0.0.11-exp1.img"
cp bootable/recovery/NOTICE "$project/artifacts/TWRP-NOTICE.txt"
cp "$project/README.txt" "$project/artifacts/README.txt"
cd "$project/artifacts"
sha256sum twrp-dada-OS4.0.0.11-exp1.img > SHA256SUMS
printf 'NOT_TESTED: boot, touch, decryption, MTP, Wi-Fi, backup/restore, OTA.\n' > runtime-results.txt
