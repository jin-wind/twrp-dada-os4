#!/usr/bin/env bash
set -euo pipefail
project="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${RUNNER_TEMP:?}/dada-os4-build"
[[ "${GITHUB_ACTIONS:-}" == true && ! -e "$build_root" ]]
mkdir -p "$build_root"
cd "$build_root"
git init -q manifest
cp "$project/config/pinned-manifest.xml" manifest/default.xml
git -C manifest add default.xml
git -C manifest -c user.name=dada-build -c user.email=dada-build@users.noreply.github.com \
  commit -qm 'Pinned TWRP source manifest'
git clone --depth=1 --branch v2.71 https://gerrit.googlesource.com/git-repo repo-tool
repo_revision=338ddb7d83ea35d5aef94d3c5d95c74fa3845780
actual_revision="$(git -C repo-tool rev-parse HEAD)"
if [[ "$actual_revision" != "$repo_revision" ]]; then
  echo "Unexpected repo tool revision: $actual_revision (expected $repo_revision)" >&2
  exit 1
fi
mkdir source
cd source
python3 "$build_root/repo-tool/repo" init -u "file://$build_root/manifest" --depth=1 \
  --partial-clone --clone-filter=blob:none --no-clone-bundle \
  --repo-url=https://gerrit.googlesource.com/git-repo --repo-rev=v2.71 --no-use-superproject
actual_revision="$(git -C .repo/repo rev-parse HEAD)"
if [[ "$actual_revision" != "$repo_revision" ]]; then
  echo "Unexpected installed repo tool revision: $actual_revision (expected $repo_revision)" >&2
  exit 1
fi
