"""Recreate the OS4 device tree using pinned upstream code and stock firmware.

No ADB/fastboot access. The input images must match config/payload-images.json.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
BASE_URL = 'https://github.com/YuKongA/twrp_device_xiaomi_sm8750_thales.git'
BASE_REV = 'ba8dc259c86d8287f9260e5f393f0a4cf230f4e7'


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Unsafe relative path: {value}')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=Path, help='Optional existing pinned upstream clone')
    parser.add_argument('--dump-erofs', default='dump.erofs')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f'Refusing to overwrite {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = json.loads((REPO / 'config/payload-images.json').read_text())
    for name, record in expected.items():
        image = args.images / f'{name}.img'
        assert image.stat().st_size == record['size'], name
        assert sha(image) == record['sha256'], name

    with tempfile.TemporaryDirectory(prefix='dada-port-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        base = args.base
        if base is None:
            base = temporary / 'base'
            run('git', 'init', '-q', base)
            run('git', '-C', base, 'remote', 'add', 'origin', BASE_URL)
            run('git', '-C', base, 'fetch', '--depth=1', 'origin', BASE_REV)
            run('git', '-C', base, 'checkout', '--detach', 'FETCH_HEAD')
        revision = subprocess.check_output(['git', '-C', str(base), 'rev-parse', 'HEAD'], text=True).strip()
        assert revision == BASE_REV, revision
        assert not subprocess.check_output(['git', '-C', str(base), 'status', '--porcelain']).strip()
        shutil.copytree(base, output, symlinks=True, ignore=shutil.ignore_patterns('.git'))
        run('git', 'init', '-q', output)
        records = []
        for index, item in enumerate(json.loads((REPO / 'config/blobs.json').read_text())):
            target = output / 'recovery/root' / relative(item['target'])
            source_path = relative(item['source'])
            partition = source_path.parts[0]
            internal = '/' + '/'.join(source_path.parts[1:])
            if item['old_sha256'] is None:
                assert not target.exists(), str(target)
                target.parent.mkdir(parents=True, exist_ok=True)
            else:
                assert target.is_file() and not target.is_symlink(), str(target)
                assert sha(target) == item['old_sha256'], item['target']
            if partition == 'modem':
                extracted = temporary / f'blob-{index}'
                run('mcopy', '-i', args.images / 'modem.img', f'::{internal}', extracted)
                content = extracted.read_bytes()
                extracted.unlink()
            else:
                content = subprocess.check_output([
                    args.dump_erofs, '--cat', f'--path={internal}',
                    str(args.images / f'{partition}.img')])
            assert hashlib.sha256(content).hexdigest() == item['source_sha256'], item['source']
            target.write_bytes(content)
            for patch in item['elf_patches']:
                if set(patch) == {'replace_needed'}:
                    run('patchelf', '--replace-needed', *patch['replace_needed'], target)
                elif set(patch) == {'add_needed'}:
                    run('patchelf', '--add-needed', patch['add_needed'], target)
                else:
                    raise ValueError(f'Unknown ELF patch: {patch}')
            records.append(item | {'result_sha256': sha(target)})

        boot = (args.images / 'boot.img').read_bytes()
        assert boot[:8] == b'ANDROID!' and struct.unpack_from('<I', boot, 40)[0] == 4
        length = struct.unpack_from('<I', boot, 8)[0]
        assert 0 < length <= len(boot) - 4096
        (output / 'prebuilt/kernel').write_bytes(boot[4096:4096 + length])
        patch = REPO / 'config/device.patch'
        run('git', '-C', output, 'apply', '--check', patch)
        run('git', '-C', output, 'apply', patch)
        shutil.rmtree(output / '.git')
        (output.parent / 'port-blob-provenance.json').write_text(json.dumps(records, indent=2) + '\n')
        run('python3', REPO / 'scripts/test_crypto_guard.py', output,
            '--report', output.parent / 'crypto-guard-tests.json')
        print(json.dumps({'device_base': revision, 'hardware_files': len(records),
                          'output': str(output)}, indent=2))


if __name__ == '__main__':
    main()
