#!/usr/bin/env bash
set -euo pipefail
project="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${RUNNER_TEMP:?}/dada-os4-build"
[[ "${GITHUB_ACTIONS:-}" == true && ! -e "$build_root" ]]
mkdir -p "$build_root" "$project/artifacts"
cd "$build_root"
version=OS4.0.0.11.XOCMIXM
package=dada_global-ota_full-OS4.0.0.11.XOCMIXM-user-17.0-19e034272e.zip
curl --fail --location --retry 5 --retry-all-errors --connect-timeout 30 \
  --output firmware.zip "https://bigota.d.miui.com/$version/$package" || \
curl --fail --location --retry 5 --retry-all-errors --connect-timeout 30 \
  --output firmware.zip "https://hugeota.d.miui.com/$version/$package"
[[ "$(stat -c %s firmware.zip)" == 8766363938 ]]
python3 "$project/scripts/extract_payload.py" --package firmware.zip \
  --output extracted --expected "$project/config/payload-images.json"
git init -q erofs-utils
git -C erofs-utils remote add origin https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git
git -C erofs-utils fetch --depth=1 origin f36cadb5c563995ab3aa8572a60ed6b721b9557d
git -C erofs-utils checkout --detach FETCH_HEAD
(
  cd erofs-utils
  ./autogen.sh
  ./configure --prefix="$build_root/tools" --enable-lz4 --enable-lzma
  make -j4
  make install
)
python3 "$project/scripts/prepare_device.py" --images extracted/images \
  --output "$build_root/device" --dump-erofs "$build_root/tools/bin/dump.erofs"
cp port-blob-provenance.json crypto-guard-tests.json "$project/artifacts/"
cp "$project/config/pinned-manifest.xml" "$project/artifacts/"
tar --exclude=.git -czf "$project/artifacts/device-source.tar.gz" -C "$build_root" device
# Only files created inside this job's dedicated directory are removed.
[[ "$PWD" == "$RUNNER_TEMP/dada-os4-build" ]]
rm -rf -- firmware.zip extracted erofs-utils tools
df -h .
