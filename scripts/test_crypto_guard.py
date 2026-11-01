"""Exercise the KeyMint gate with mocked properties, never a real device."""
import json
from pathlib import Path
import subprocess

import argparse
p = argparse.ArgumentParser()
p.add_argument('device', type=Path)
p.add_argument('--report', type=Path, required=True)
args = p.parse_args()
text = (args.device / 'recovery/root/odm/bin/prepdecrypt.sh').read_text()
start = text.index('start_crypto_services() {')
end = text.index('\n}\n', start) + 3
func = text[start:end]
rows = []
for release, system_patch, vendor_patch, reset_fails, allowed in [
    ('17', '2026-09-01', '2026-09-01', False, True),
    ('99.87.36', '2099-12-31', '2099-12-31', False, False),
    ('17', '2026-10-01', '2026-09-01', False, False),
    ('17', '2026-09-01', '', False, False),
    ('16', '2026-09-01', '2026-09-01', False, False),
    ('17', '2026-09-01', '2026-09-01', True, False),
]:
    script = '''
getprop() {
 case "$1" in
  ro.build.version.release) printf '%s' "$OS_RELEASE" ;;
  ro.build.version.security_patch) printf '%s' "$SYSTEM_PATCH" ;;
  ro.vendor.build.security_patch) printf '%s' "$VENDOR_PATCH" ;;
  ro.bootimage.build.version.security_patch) printf '%s' "$BOOT_PATCH" ;;
 esac
}
setprop() { printf 'SETPROP %s %s\\n' "$1" "$2"; }
resetprop() {
 printf 'RESETPROP %s %s\\n' "$1" "$2"
 [ "$RESET_FAILS" = 1 ] && return 1
 BOOT_PATCH="$2"
}
log_print() { :; }
wait_for_service() { return 0; }
setprop_bin=resetprop
''' + func + '\nstart_crypto_services\n'
    env = {'OS_RELEASE': release, 'SYSTEM_PATCH': system_patch, 'VENDOR_PATCH': vendor_patch,
           'RESET_FAILS': '1' if reset_fails else '0', 'BOOT_PATCH': '2099-12-31'}
    proc = subprocess.run(['/bin/sh'], input=script, env=env, capture_output=True, text=True)
    launched = 'SETPROP ctl.start vendor.keymint-qti' in proc.stdout
    assert launched == allowed and (proc.returncode == 0) == allowed, proc
    if allowed:
        assert 'RESETPROP ro.bootimage.build.version.security_patch 2026-09-01' in proc.stdout
    rows.append({'release': release, 'system_patch': system_patch,
                 'vendor_patch': vendor_patch, 'reset_fails': reset_fails,
                 'keymint_started': launched, 'passed': True})
args.report.write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
