#!/usr/bin/env bash
set -euo pipefail
project="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${RUNNER_TEMP:?}/dada-os4-build"
[[ "${GITHUB_ACTIONS:-}" == true && -d "$build_root/device" ]]
cd "$build_root"
git init -q manifest
cp "$project/config/pinned-manifest.xml" manifest/default.xml
git -C manifest add default.xml
git -C manifest -c user.name=dada-build -c user.email=dada-build@users.noreply.github.com \
  commit -qm 'Pinned TWRP source manifest'
git clone --depth=1 --branch v2.71 https://gerrit.googlesource.com/git-repo repo-tool
[[ "$(git -C repo-tool rev-parse HEAD)" == c5340585b8175f91a483d6d0fe30724e6b277c0b ]]
mkdir source
cd source
repo="$build_root/repo-tool/repo"
python3 "$repo" init -u "file://$build_root/manifest" --depth=1 \
  --partial-clone --clone-filter=blob:none --no-clone-bundle \
  --repo-rev=v2.71 --no-use-superproject
python3 "$repo" sync -n -c -j4 --no-tags --no-clone-bundle --fail-fast
# Apply sparse checkout BEFORE the first working-tree checkout. In particular,
# Rust bindgen needs clang-r530567 in addition to the default clang-r547379.
for item in 'prebuilts/clang/host/linux-x86:clang' 'prebuilts/rust:rust'; do
  path="${item%:*}"
  config="${item#*:}"
  gitdir="$build_root/source/.repo/projects/$path.git"
  [[ -d "$gitdir" ]]
  git --git-dir="$gitdir" config core.sparseCheckout true
  git --git-dir="$gitdir" config core.sparseCheckoutCone true
  mkdir -p "$gitdir/info"
  cp "$project/config/$config-sparse-checkout" "$gitdir/info/sparse-checkout"
done
python3 "$repo" sync -l -c -j4 --fail-fast
[[ "$(git -C .repo/repo rev-parse HEAD)" == c5340585b8175f91a483d6d0fe30724e6b277c0b ]]
mkdir -p device/xiaomi
cp -a "$build_root/device" device/xiaomi/sm8750_thales
prebuilts/clang/host/linux-x86/clang-r530567/bin/clang --version
prebuilts/clang/host/linux-x86/clang-r547379/bin/clang --version
ldd prebuilts/clang/host/linux-x86/clang-r530567/lib/libclang.so | tee "$project/artifacts/libclang-ldd.txt"
if grep -q 'not found' "$project/artifacts/libclang-ldd.txt"; then exit 1; fi
test -x prebuilts/rust/linux-x86/1.83.0/bin/rustc
python3 "$repo" manifest -r -o "$project/artifacts/resolved-manifest.xml"
df -h .
python3 - <<'PY'
import shutil
available = shutil.disk_usage('.').free / 2**30
if available < 16:
    raise SystemExit(f'Only {available:.1f} GiB free; need 16 GiB for build outputs.')
PY
