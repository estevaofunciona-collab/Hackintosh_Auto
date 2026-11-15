#!/usr/bin/env bash
# Hackintosh_Auto v0.1 (experimental) - Linux and Termux (Android)
# Builds an OpenCore EFI folder (with OpenCanopy graphical menu) and downloads the macOS recovery image.
# It does NOT partition, format or write to any disk.

set -u

C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_CYN=$'\033[36m'; C_OFF=$'\033[0m'
info()  { printf '%s%s%s\n' "$C_CYN" "$*" "$C_OFF"; }
ok()    { printf '%s%s%s\n' "$C_GRN" "$*" "$C_OFF"; }
warn()  { printf '%s%s%s\n' "$C_RED" "$*" "$C_OFF"; }
step()  { printf '%s%s%s\n' "$C_YEL" "$*" "$C_OFF"; }

echo
echo "Hackintosh_Auto v0.1 (experimental) - Linux / Termux"
echo

# ---------- environment ----------
IS_TERMUX=0
if [ -n "${PREFIX:-}" ] && [ -d "${PREFIX:-}/bin" ] && printf '%s' "$PREFIX" | grep -q 'com.termux'; then IS_TERMUX=1; fi

missing=""
for cmd in curl unzip python3; do
  command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
done
if [ -n "$missing" ]; then
  warn "Missing required tools:$missing"
  if [ "$IS_TERMUX" = 1 ]; then
    echo "Install them with:  pkg install curl unzip python"
  else
    echo "Install them with your package manager, e.g.:  sudo apt install curl unzip python3"
  fi
  exit 1
fi

if [ "$IS_TERMUX" = 1 ]; then
  if [ ! -d "$HOME/storage/shared" ]; then
    warn "Storage access is not set up. Run:  termux-setup-storage   then run this script again."
    exit 1
  fi
  OUT="$HOME/storage/shared/Hackintosh_Auto_Output"
else
  OUT="${HA_OUT:-$HOME/Hackintosh_Auto_Output}"
fi
TMP="$OUT/_temp"
rm -rf "$OUT"
mkdir -p "$TMP"
info "Output folder: $OUT"

# ---------- helpers ----------
# get_latest <owner/repo> <asset-regex> <label>   -> prints the extracted directory (empty on failure)
get_latest() {
  local repo="$1" pattern="$2" label="$3" url zip dir
  step "Downloading $label ..." >&2
  url=$(curl -fsSL -H 'User-Agent: hackintosh-auto' "https://api.github.com/repos/$repo/releases/latest" 2>/dev/null |
        python3 -c 'import sys,json,re
pat=re.compile(sys.argv[1])
try:
    d=json.load(sys.stdin)
    for a in d.get("assets",[]):
        if pat.search(a["name"]):
            print(a["browser_download_url"]); break
except Exception:
    pass' "$pattern")
  if [ -z "$url" ]; then warn "   WARNING: could not find $label (GitHub API limit or no internet?)" >&2; return 1; fi
  zip="$TMP/$(basename "$url")"
  if ! curl -fsSL -o "$zip" "$url"; then warn "   WARNING: download failed for $label" >&2; return 1; fi
  dir="$TMP/$(printf '%s' "$label" | tr -c 'A-Za-z0-9' '_')"
  mkdir -p "$dir"
  unzip -q -o "$zip" -d "$dir" || { warn "   WARNING: could not unzip $label" >&2; return 1; }
  ok "   OK: $(basename "$url")" >&2
  printf '%s' "$dir"
}

copy_kext() { # <srcDir> <KextName.kext> <dest>
  local src="$1" name="$2" dest="$3" k
  [ -n "$src" ] || return 0
  k=$(find "$src" -type d -name "$name" ! -path '*Debug*' ! -path '*dSYM*' | head -n1)
  if [ -n "$k" ]; then cp -R "$k" "$dest/"; else warn "   WARNING: $name not found"; fi
}

# ---------- OpenCore ----------
OC_DIR=$(get_latest 'acidanthera/OpenCorePkg' '^OpenCore-.*-RELEASE\.zip$' 'OpenCore')
if [ -z "$OC_DIR" ]; then warn "OpenCore download failed. Cannot continue."; exit 1; fi
cp -R "$OC_DIR/X64/EFI" "$OUT/"
EFI="$OUT/EFI"
DRV="$EFI/OC/Drivers"

# keep only the drivers we need (OpenCanopy.efi is from the SAME zip, so versions always match)
find "$DRV" -maxdepth 1 -type f ! -name 'OpenRuntime.efi' ! -name 'OpenCanopy.efi' -delete
find "$EFI/OC/Tools" -maxdepth 1 -type f ! -name 'OpenShell.efi' -delete

step "Downloading HfsPlus.efi ..."
curl -fsSL -o "$DRV/HfsPlus.efi" 'https://github.com/acidanthera/OcBinaryData/raw/master/Drivers/HfsPlus.efi' || warn "   WARNING: HfsPlus.efi download failed"

# base config.plist (Sample.plist) - must be edited afterwards
cp "$OC_DIR/Docs/Sample.plist" "$EFI/OC/config.plist"

# ---------- graphical boot menu (OpenCanopy) + mouse ----------
python3 - "$EFI/OC/config.plist" <<'PYEOF'
import re, sys
path = sys.argv[1]
t = open(path, encoding='utf-8').read()
def enable(text, name):
    pat = (r'(<key>Enabled</key>\s*)<false/>((?:\s*<key>(?:HideVerbose|LoadEarly)</key>\s*<(?:true|false)/>)*'
           r'\s*<key>Path</key>\s*<string>' + re.escape(name) + r'</string>)')
    return re.sub(pat, r'\1<true/>\2', text)
for n in ('OpenCanopy.efi', 'OpenRuntime.efi', 'HfsPlus.efi'):
    t = enable(t, n)
t = re.sub(r'(<key>PickerMode</key>\s*<string>)[^<]*(</string>)', r'\1External\2', t)
t = re.sub(r'(<key>PointerSupport</key>\s*)<false/>', r'\1<true/>', t)
t = re.sub(r'(<key>PointerSupportMode</key>\s*)<string>[^<]*</string>', r'\1<string>ASUS</string>', t)
open(path, 'w', encoding='utf-8').write(t)
PYEOF
[ -f "$DRV/OpenCanopy.efi" ] || warn "WARNING: OpenCanopy.efi was not in the zip"
if [ -d "$EFI/OC/Resources" ]; then ok "Graphical boot menu (OpenCanopy) + mouse configured."; else warn "WARNING: OC/Resources folder was not in the zip"; fi

# ---------- kexts ----------
KX="$EFI/OC/Kexts"
rm -rf "$KX"/*
mkdir -p "$KX"

d=$(get_latest 'acidanthera/Lilu' '^Lilu-.*-RELEASE\.zip$' 'Lilu');                       copy_kext "$d" Lilu.kext "$KX"
d=$(get_latest 'acidanthera/VirtualSMC' '^VirtualSMC-.*-RELEASE\.zip$' 'VirtualSMC')
for n in VirtualSMC.kext SMCProcessor.kext SMCSuperIO.kext; do copy_kext "$d" "$n" "$KX"; done
d=$(get_latest 'acidanthera/WhateverGreen' '^WhateverGreen-.*-RELEASE\.zip$' 'WhateverGreen'); copy_kext "$d" WhateverGreen.kext "$KX"
d=$(get_latest 'acidanthera/AppleALC' '^AppleALC-.*-RELEASE\.zip$' 'AppleALC');          copy_kext "$d" AppleALC.kext "$KX"
# Ethernet: both are downloaded - delete the one that does NOT match your board
d=$(get_latest 'acidanthera/IntelMausi' '^IntelMausi-.*-RELEASE\.zip$' 'IntelMausi');    copy_kext "$d" IntelMausi.kext "$KX"
d=$(get_latest 'Mieze/RTL8111_driver_for_OS_X' '^RealtekRTL8111-.*\.zip$' 'RealtekRTL8111'); copy_kext "$d" RealtekRTL8111.kext "$KX"
# NVMe SSD (delete if you have no NVMe drive)
d=$(get_latest 'acidanthera/NVMeFix' '^NVMeFix-.*-RELEASE\.zip$' 'NVMeFix');             copy_kext "$d" NVMeFix.kext "$KX"
# USB mapping tool kext (UTBMap.kext is generated by the USBToolBox tool, not downloaded)
d=$(get_latest 'USBToolBox/kext' '^USBToolBox-.*RELEASE\.zip$' 'USBToolBoxKext');        copy_kext "$d" USBToolBox.kext "$KX"

# ---------- SSDTs (Haswell desktop example) ----------
ACPI="$EFI/OC/ACPI"
rm -rf "$ACPI"/*
mkdir -p "$ACPI"
BASE='https://raw.githubusercontent.com/dortania/Getting-Started-With-ACPI/master/extra-files/compiled/'
for f in SSDT-PLUG-DRTNIA.aml SSDT-EC-USBX-DESKTOP.aml; do
  step "Downloading $f ..."
  curl -fsSL -o "$ACPI/$f" "$BASE$f" || warn "   WARNING: failed $f - get it from dortania.github.io/Getting-Started-With-ACPI"
done

# ---------- macrecovery (macOS installer) ----------
cp -R "$OC_DIR/Utilities/macrecovery" "$OUT/macrecovery"
step "Downloading the macOS Ventura recovery image (this can take a while) ..."
( cd "$OUT/macrecovery" && python3 macrecovery.py -b Mac-4B682C642B45593E -m 00000000000000000 download ) || warn "   WARNING: macrecovery failed. Run it manually later."
if [ -f "$OUT/macrecovery/com.apple.recovery.boot/BaseSystem.dmg" ]; then
  mv "$OUT/macrecovery/com.apple.recovery.boot" "$OUT/com.apple.recovery.boot"
  ok "com.apple.recovery.boot folder is ready in: $OUT"
else
  warn "WARNING: the installer download did not finish (no BaseSystem.dmg). Re-run the macrecovery step."
fi

rm -rf "$TMP"

# ---------- optional hardware summary (Linux only) ----------
if [ "$IS_TERMUX" = 0 ]; then
  echo
  info "Hardware summary of THIS computer (read-only, informational):"
  command -v lscpu >/dev/null 2>&1 && lscpu | grep -E 'Model name' | sed 's/^/  /'
  command -v lspci >/dev/null 2>&1 && lspci | grep -Ei 'vga|3d|ethernet|network|audio' | sed 's/^/  /'
  command -v lsusb >/dev/null 2>&1 && lsusb | grep -i bluetooth | sed 's/^/  /'
fi

echo
ok "DONE. Folder: $OUT"
info "USB drive (FAT32, GUID): copy BOTH the EFI folder and the com.apple.recovery.boot folder to the ROOT of the drive."
info "Still to do: edit config.plist (ProperTree/OCAT), set SMBIOS + serial, map USB (generates UTBMap.kext), keep only the right ethernet kext."
