"""Inspect a built recovery image; no phone access and no partition writes."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess

p = argparse.ArgumentParser()
p.add_argument('image', type=Path)
p.add_argument('--report', required=True, type=Path)
p.add_argument('--blob-provenance', type=Path)
args = p.parse_args()
raw = args.image.read_bytes()
assert raw[:8] == b'ANDROID!', 'Not an Android boot image'
kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from('<4I', raw, 8)
header_version = struct.unpack_from('<I', raw, 40)[0]
assert header_version == 4 and kernel_size == 0, 'dada requires a kernel-less v4 recovery'
assert 4096 + ramdisk_size <= len(raw) <= 104857600, 'Recovery exceeds partition bounds'
ramdisk = raw[4096:4096 + ramdisk_size]
if ramdisk.startswith(b'070701'):
    cpio = ramdisk
else:
    cpio = subprocess.run(['lz4', '-d', '-c'], input=ramdisk,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout
entries = {}
pos = 0
while pos + 110 <= len(cpio):
    hdr = cpio[pos:pos + 110]
    assert hdr[:6] in (b'070701', b'070702'), f'Invalid CPIO header at {pos}'
    fields = [int(hdr[6 + i * 8:14 + i * 8], 16) for i in range(13)]
    size, name_size = fields[6], fields[11]
    name = cpio[pos + 110:pos + 110 + name_size - 1].decode()
    pos = (pos + 110 + name_size + 3) & ~3
    data = cpio[pos:pos + size]
    assert len(data) == size
    pos = (pos + size + 3) & ~3
    if name == 'TRAILER!!!':
        break
    name = name.removeprefix('./')
    assert not name.startswith('/') and '..' not in PurePosixPath(name).parts
    entries[name] = {'mode': fields[1], 'data': data, 'ino': fields[0], 'nlink': fields[4]}

def required(name):
    assert name in entries and entries[name]['data'], f'Missing image file: {name}'
    return entries[name]['data']

fstab = required('system/etc/recovery.fstab').decode()
assert any(line.startswith('mi_product ') and 'slotselect' in line and 'logical' in line
           for line in fstab.splitlines()), 'Missing OS4 mi_product mount'
assert 'wrappedkey_v0' in fstab and 'metadata_encryption=' in fstab
props = '\n'.join(e['data'].decode(errors='replace') for n, e in entries.items()
                  if n.endswith(('.prop', 'prop.default')))
assert 'ro.twrp.port.target=OS4.0.0.11.XOCMIXM' in props
assert 'ro.twrp.port.status=experimental' in props
assert 'service.adb.tcp.port=5555' not in props, 'Unrequested network ADB default'
prepdecrypt = required('odm/bin/prepdecrypt.sh').decode()
keymint_rc = required('vendor/etc/init/android.hardware.security.keymint-service-qti.rc').decode()
assert 'OS4 port: refusing KeyMint with unexpected platform properties.' in prepdecrypt
assert 'ro.bootimage.build.version.security_patch)" != "2026-09-01"' in prepdecrypt
assert any(line.strip() == 'disabled' for line in keymint_rc.splitlines())
assert 'setprop prepdecrypt.setpatch true' in required('init.recovery.qcom.rc').decode()

def elf_needed(data):
    if data[:6] != b'\x7fELF\x02\x01':
        return None
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phentsize, phnum = struct.unpack_from('<HH', data, 54)
    loads, dyn = [], None
    for i in range(phnum):
        entry = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phentsize)
        typ, _, off, va, _, filesz, _, _ = entry
        if typ == 1:
            loads.append((va, off, filesz))
        elif typ == 2:
            dyn = (off, filesz)
    if dyn is None:
        return []
    tags = []
    for off in range(dyn[0], dyn[0] + dyn[1], 16):
        tag, val = struct.unpack_from('<qQ', data, off)
        if tag == 0:
            break
        tags.append((tag, val))
    strtab = next((v for t, v in tags if t == 5), None)
    if strtab is None:
        return []
    base = next(off + strtab - va for va, off, size in loads if va <= strtab < va + size)
    result = []
    for tag, offset in tags:
        if tag == 1:
            start = base + offset
            result.append(data[start:data.index(b'\0', start)].decode())
    return result

available = {PurePosixPath(name).name for name, e in entries.items()
             if e['mode'] & 0o170000 in (0o100000, 0o120000)}
missing = []
elf_count = 0
for name, entry in entries.items():
    if not name.startswith(('vendor/bin/', 'vendor/lib64/', 'odm/bin/', 'odm/lib64/',
                            'odm/variant/dada/odm/lib64/')):
        continue
    needs = elf_needed(entry['data'])
    if needs is None:
        continue
    elf_count += 1
    for dep in needs:
        if dep not in available:
            missing.append({'file': name, 'needed': dep})
report = {
    'image': str(args.image), 'size': len(raw),
    'sha256': hashlib.sha256(raw).hexdigest(), 'header_version': header_version,
    'kernel_size': kernel_size, 'ramdisk_size': ramdisk_size,
    'cpio_entries': len(entries), 'os4_fstab_present': True,
    'port_identity_present': True, 'network_adb_default_disabled': True,
    'crypto_property_guard_packaged': True, 'keymint_disabled_until_guard': True,
    'hardware_elf_files_inspected': elf_count, 'missing_needed_libraries': missing,
    'dependency_check_scope': 'File availability only; runtime symbol/linker checks remain necessary.',
    'runtime_status': 'NOT_TESTED', 'ota_install_status': 'NOT_TESTED',
}
if args.blob_provenance:
    proven = []
    for blob in json.loads(args.blob_provenance.read_text()):
        name = blob['target']
        if '/lib/modules/' not in name and '/firmware_mnt/image/' not in name:
            continue
        actual = hashlib.sha256(required(name)).hexdigest()
        assert actual == blob['source_sha256'], f'Firmware/module changed in packaging: {name}'
        proven.append(name)
    report['unaltered_os4_firmware_and_modules'] = proven
args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
if missing:
    raise SystemExit('Hardware dependencies are missing from the recovery ramdisk')
