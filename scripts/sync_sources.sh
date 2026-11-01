#!/usr/bin/env bash
set -euo pipefail
project="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${RUNNER_TEMP:?}/dada-os4-build"
[[ "${GITHUB_ACTIONS:-}" == true && -d "$build_root/device" ]]
cd "$build_root/source"
[[ -f .repo/manifest.xml ]]
repo_revision=338ddb7d83ea35d5aef94d3c5d95c74fa3845780
repo="$build_root/repo-tool/repo"
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
actual_revision="$(git -C .repo/repo rev-parse HEAD)"
if [[ "$actual_revision" != "$repo_revision" ]]; then
  echo "Unexpected installed repo tool revision: $actual_revision (expected $repo_revision)" >&2
  exit 1
fi
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
