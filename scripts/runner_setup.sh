#!/usr/bin/env bash
# Destructive SDK cleanup is permitted ONLY on an ephemeral GitHub-hosted runner.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]]
[[ "${RUNNER_OS:-}" == Linux && -n "${RUNNER_TEMP:-}" ]]
for path in /usr/share/dotnet /usr/local/lib/android /opt/ghc \
            /usr/local/.ghcup /usr/local/share/boost /opt/hostedtoolcache \
            /usr/share/swift /usr/local/share/chromium; do
  if [[ -e "$path" ]]; then sudo rm -rf --one-file-system -- "$path"; fi
done
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  git curl aria2 ca-certificates python3 python-is-python3 build-essential bc bison flex zip unzip \
  rsync cpio lz4 zstd xz-utils mtools patchelf fontconfig gperf \
  libncurses-dev libssl-dev libelf-dev libxml2-utils xsltproc \
  autoconf automake libtool pkg-config uuid-dev liblz4-dev libzstd-dev \
  liblzma-dev zlib1g-dev lib32z1 libc6-i386 lib32stdc++6
sudo apt-get clean
df -h "$RUNNER_TEMP"
python3 - <<'PY'
import os, shutil
available = shutil.disk_usage(os.environ['RUNNER_TEMP']).free / 2**30
print(f'Free runner storage: {available:.1f} GiB')
if available < 62:
    raise SystemExit('Need at least 62 GiB after runner cleanup; no build started.')
PY
swap="$RUNNER_TEMP/dada-build.swap"
[[ ! -e "$swap" ]]
sudo fallocate -l 8G "$swap"
sudo chmod 600 "$swap"
sudo mkswap "$swap"
sudo swapon "$swap"
free -h
