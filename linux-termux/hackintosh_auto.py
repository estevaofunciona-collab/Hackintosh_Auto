#!/usr/bin/env python3
"""
Hackintosh_Auto v0.2 (experimental) - Linux and Termux (Android)

Interactive builder for an OpenCore EFI:
  1. asks desktop / notebook and dual boot
  2. reads the hardware (automatic on a Linux PC, from a report file, or by asking you)
  3. checks CPU / GPU (and Wi-Fi / Bluetooth on notebooks) and lists the compatible macOS versions
  4. lets you choose the macOS version and the Mac model (SMBIOS)
  5. downloads OpenCore + the kexts your hardware needs, writes config.plist
     (kext order, SSDTs, drivers, OpenCanopy + mouse, SMBIOS, quirks) and downloads the macOS recovery image

It never partitions, formats or writes to any disk. Compatibility data is APPROXIMATE - always read the
Dortania guide for your exact hardware: https://dortania.github.io/OpenCore-Install-Guide/
"""
import argparse
import os
import platform
import plistlib
import re
import secrets
import shutil
import string
import subprocess
import sys
import uuid
import zipfile

VERSION = "0.2"
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
IS_WINDOWS = os.name == "nt"
USE_COLOR = sys.stdout.isatty() or os.environ.get("HA_COLOR") == "1"
if IS_WINDOWS:
    try:
        os.system("")  # enables ANSI colours in the Windows 10+ console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _c(code, s):
    return "\033[%sm%s\033[0m" % (code, s) if USE_COLOR else s


def info(s): print(_c("36", s))
def ok(s): print(_c("32", s))
def warn(s): print(_c("31", s))
def step(s): print(_c("33", s))


# ----------------------------------------------------------------------------------------------
# input helpers (EOF-safe: an empty answer / closed stdin always falls back to the default)
# ----------------------------------------------------------------------------------------------
def ask(prompt, default=""):
    try:
        s = input(prompt).strip()
    except EOFError:
        s = ""
    return s or default


def yesno(prompt, default=True):
    d = "Y/n" if default else "y/N"
    s = ask("%s [%s] " % (prompt, d)).lower()
    if not s:
        return default
    return s.startswith("y") or s.startswith("s")


def choose(title, options, default=1):
    """options: list of strings. Returns the 0-based index."""
    print()
    print(title)
    for i, o in enumerate(options, 1):
        print("  %d) %s" % (i, o))
    for _ in range(3):
        s = ask("Choose [%d]: " % default)
        if not s:
            return default - 1
        if s.isdigit() and 1 <= int(s) <= len(options):
            return int(s) - 1
        print("  Please type a number from 1 to %d." % len(options))
    return default - 1


# ----------------------------------------------------------------------------------------------
# knowledge base (approximate - see the disclaimer at the top)
# ----------------------------------------------------------------------------------------------
Z = "00000000000000000"
# name, version, macrecovery board id, MLB argument, extra macrecovery args  (from OpenCorePkg recovery_urls.txt)
MACOS = [
    ("High Sierra", 10.13, "Mac-7BA5B2D9E42DDD94", "00000000000J80300", []),
    ("Mojave", 10.14, "Mac-7BA5B2DFE22DDD8C", "00000000000KXPG00", []),
    ("Catalina", 10.15, "Mac-00BE6ED71E35EB86", Z, []),
    ("Big Sur", 11, "Mac-2BD1B31983FE1663", Z, []),
    ("Monterey", 12, "Mac-E43C1C25D4880AD6", Z, []),
    ("Ventura", 13, "Mac-B4831CEBD52A0C4C", Z, []),
    ("Sonoma", 14, "Mac-827FAC58A8FDFA22", Z, []),
    ("Sequoia", 15, "Mac-7BA5B2D9E42DDD94", Z, []),
    ("Tahoe", 26, "Mac-CFF7D910A743CAAF", Z, ["-os", "latest"]),
]
DARWIN = {11: 20, 12: 21, 13: 22, 14: 23, 15: 24, 26: 25}


def vlabel(v):
    return ("macOS %.2f" % v) if v < 11 else ("macOS %d" % v)


GEN_NAMES = {1: "Nehalem/Westmere", 2: "Sandy Bridge", 3: "Ivy Bridge", 4: "Haswell", 5: "Broadwell",
             6: "Skylake", 7: "Kaby Lake", 8: "Coffee Lake", 9: "Coffee Lake Refresh", 10: "Comet Lake",
             11: "Rocket Lake / Tiger Lake", 12: "Alder Lake", 13: "Raptor Lake", 14: "Raptor Lake Refresh"}

# SMBIOS: last macOS each model officially supports
MODEL_LAST = {
    "iMac12,2": 10.13, "iMac13,2": 11, "iMac14,4": 12, "iMac16,2": 12, "iMac17,1": 12, "iMac18,3": 13,
    "iMac19,1": 15, "iMac20,1": 26, "iMacPro1,1": 15, "MacPro6,1": 12, "MacPro7,1": 26,
    "MacBookPro8,1": 10.13, "MacBookPro9,2": 11, "MacBookPro11,1": 12, "MacBookPro12,1": 12,
    "MacBookPro13,1": 12, "MacBookPro14,1": 13, "MacBookPro15,1": 15, "MacBookPro15,2": 15,
    "MacBookPro16,1": 26,
}
DESK_BY_GEN = {2: "iMac12,2", 3: "iMac13,2", 4: "iMac14,4", 5: "iMac16,2", 6: "iMac17,1", 7: "iMac18,3",
               8: "iMac19,1", 9: "iMac19,1"}
NB_BY_GEN = {2: "MacBookPro8,1", 3: "MacBookPro9,2", 4: "MacBookPro11,1", 5: "MacBookPro12,1",
             6: "MacBookPro13,1", 7: "MacBookPro14,1", 8: "MacBookPro15,2", 9: "MacBookPro15,1"}

# Intel iGPU AAPL,ig-platform-id (Dortania defaults - verify for your exact chip)  gen -> (desktop, laptop)
IG_PLATFORM = {2: (0x00030010, 0x00010000), 3: (0x0166000A, 0x01660003), 4: (0x04120004, 0x0A260006),
               5: (0x16260004, 0x16260006), 6: (0x19120001, 0x191B0000), 7: (0x59120003, 0x591B0000),
               8: (0x3E9B0007, 0x3EA50009), 9: (0x3E9B0007, 0x3EA50009), 10: (0x3E9B0007, None)}


# ----------------------------------------------------------------------------------------------
# hardware model
# ----------------------------------------------------------------------------------------------
def new_hw():
    return {"cpu": "", "board": "", "gpus": [], "eth": [], "wifi": [], "bt": [], "audio": [], "nvme": None}


def dev(name, vid="", did=""):
    return {"name": name.strip(), "vid": vid.lower(), "did": did.lower()}


def parse_cpu(s):
    """Return (intel_generation|None, is_amd)."""
    if re.search(r"AMD|Ryzen|EPYC|Athlon|Threadripper", s, re.I):
        return None, True
    m = re.search(r"E[357]-?\s?\d{4}\s*(?:L\s*)?v(\d)", s, re.I)  # Xeon E3/E5 v1..v6
    if m:
        return {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7}.get(int(m.group(1))), False
    m = re.search(r"i[3579][- ]?(\d{3,5})([A-Z]\d)?", s, re.I)
    if m:
        n, suffix = m.group(1), m.group(2)
        if len(n) == 3:
            return 1, False
        if suffix and suffix[0].upper() == "G":  # i5-1135G7 -> 11th gen
            return int(n[:2]), False
        return (int(n[:2]) if len(n) == 5 else int(n[0])), False
    return None, False


def vendor_of(text, vid=""):
    t = text.lower()
    vid = vid.lower()
    if vid == "8086" or re.search(r"intel", t):
        return "intel"
    if vid in ("14e4", "0a5c") or re.search(r"broadcom|bcm\d|dell wireless 15|dw1", t):
        return "broadcom"
    if vid in ("10ec", "0bda") or re.search(r"realtek|rtl\d", t):
        return "realtek"
    if vid in ("168c", "1969", "17cb", "0cf3") or re.search(r"qualcomm|atheros|killer|qca\d|ar9", t):
        return "atheros"
    if vid in ("14c3", "0e8d") or re.search(r"mediatek|ralink|mt7", t):
        return "mediatek"
    return "unknown"


# ----------------------------------------------------------------------------------------------
# hardware sources: Linux auto-detection, hardware_report.txt (from the Windows tool), manual
# ----------------------------------------------------------------------------------------------
def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return ""


def detect_linux():
    hw = new_hw()
    for line in run(["lscpu"]).splitlines():
        if line.strip().startswith("Model name"):
            hw["cpu"] = line.split(":", 1)[1].strip()
    for f, key in (("board_vendor", "v"), ("board_name", "n")):
        try:
            hw.setdefault("_b", {})[key] = open("/sys/class/dmi/id/" + f).read().strip()
        except Exception:
            pass
    b = hw.pop("_b", {})
    hw["board"] = (b.get("v", "") + " " + b.get("n", "")).strip()
    for line in run(["lspci", "-nn"]).splitlines():
        m = re.match(r"\S+\s+(.+?)\s+\[([0-9a-f]{4})\]:\s+(.+?)\s+\[([0-9a-f]{4}):([0-9a-f]{4})\]", line)
        if not m:
            continue
        cls, name, vid, did = m.group(1), m.group(3), m.group(4), m.group(5)
        d = dev(name, vid, did)
        if re.search(r"VGA|3D|Display", cls):
            hw["gpus"].append(d)
        elif "Ethernet" in cls:
            hw["eth"].append(d)
        elif "Network controller" in cls:
            hw["wifi"].append(d)
        elif "Audio" in cls:
            hw["audio"].append(d)
        elif "Non-Volatile" in cls:
            hw["nvme"] = True
    for line in run(["lsusb"]).splitlines():
        m = re.search(r"ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)", line)
        if m and re.search(r"bluetooth", m.group(3), re.I):
            hw["bt"].append(dev(m.group(3), m.group(1), m.group(2)))
    if hw["nvme"] is None:
        hw["nvme"] = bool(run(["ls", "/dev"]).count("nvme"))
    return hw


def parse_report(path):
    """Parse the hardware_report.txt written by windows/read_hardware_pc.bat."""
    hw = new_hw()
    sec = ""
    cur = None
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        lines = [l.rstrip("\n") for l in fh]
    for l in lines:
        m = re.match(r"=== (.+?) ===", l)
        if m:
            sec = m.group(1).upper()
            cur = None
            continue
        s = l.strip()
        if sec == "CPU" and s.startswith("Name:"):
            hw["cpu"] = s[5:].strip()
        elif sec.startswith("MOTHERBOARD") and s.startswith("Board:"):
            hw["board"] = s[6:].strip()
        elif sec == "GPU" or sec.startswith("NETWORK") or sec == "AUDIO":
            if s.startswith("Name:"):
                name = s[5:].split("  Vendor:")[0].strip()
                cur = dev(name)
                key = "gpus" if sec == "GPU" else ("audio" if sec == "AUDIO" else
                      ("wifi" if re.search(r"wi-?fi|wireless|wlan|802\.11|\bAX\d|\bAC\b", name, re.I) else "eth"))
                hw[key].append(cur)
            elif s.startswith("PNP:") and cur:
                v = re.search(r"VEN_([0-9A-F]{4})", s, re.I)
                d = re.search(r"DEV_([0-9A-F]{4})", s, re.I)
                if v: cur["vid"] = v.group(1).lower()
                if d: cur["did"] = d.group(1).lower()
        elif sec == "BLUETOOTH":
            if s.startswith("Name:"):
                cur = dev(s[5:])
                hw["bt"].append(cur)
            elif s.startswith("ID:") and cur:
                v = re.search(r"VID_([0-9A-F]{4})", s, re.I)
                p = re.search(r"PID_([0-9A-F]{4})", s, re.I)
                if v: cur["vid"] = v.group(1).lower()
                if p: cur["did"] = p.group(1).lower()
        elif sec == "DRIVES" and re.search(r"NVMe", s):
            hw["nvme"] = True
    if hw["nvme"] is None:
        hw["nvme"] = False
    return hw


def manual_hw(hw):
    print()
    info("Tell me about the computer you are building the EFI for (press Enter to skip what you do not know).")
    hw["cpu"] = ask("  Processor model (e.g. Intel Core i5-4590, Xeon E3-1231 v3, i7-8750H): ", hw["cpu"])
    hw["board"] = ask("  Motherboard / chipset (e.g. H81, Z390, ThinkPad T480): ", hw["board"])
    g = ask("  Graphics card(s), comma separated (e.g. GT 730, RX 580, Intel UHD 630): ")
    hw["gpus"] = [dev(x) for x in g.split(",") if x.strip()]
    e = ask("  Ethernet chip (e.g. Realtek RTL8111, Intel I219-V): ")
    hw["eth"] = [dev(e)] if e else []
    a = ask("  Audio codec (e.g. ALC662, ALC892): ")
    hw["audio"] = [dev(a)] if a else []
    hw["nvme"] = yesno("  Do you use an NVMe SSD?", False)
    w = ask("  Wi-Fi chip, if any (e.g. Intel AX200, Broadcom BCM94360, Realtek RTL8821): ")
    hw["wifi"] = [dev(w)] if w else []
    b = ask("  Bluetooth chip / dongle vendor, if any (Intel, Broadcom, Realtek, CSR...): ")
    hw["bt"] = [dev(b)] if b else []
    return hw


def show_hw(hw):
    print()
    info("Hardware I have:")
    print("  CPU:        %s" % (hw["cpu"] or "?"))
    print("  Board:      %s" % (hw["board"] or "?"))
    for k, label in (("gpus", "GPU"), ("eth", "Ethernet"), ("wifi", "Wi-Fi"), ("bt", "Bluetooth"), ("audio", "Audio")):
        items = hw[k]
        print("  %-11s %s" % (label + ":", "; ".join(d["name"] + (" [%s:%s]" % (d["vid"], d["did"]) if d["vid"] else "")
                                                       for d in items) if items else "none / not detected"))
    print("  NVMe SSD:   %s" % ("yes" if hw["nvme"] else "no / unknown"))


# ----------------------------------------------------------------------------------------------
# compatibility analysis
# ----------------------------------------------------------------------------------------------
def cpu_range(gen):
    """(min, max, experimental_note)"""
    if gen is None or gen < 2:
        return None
    if gen in (2, 3):
        return 10.13, 12, ""
    if gen <= 7:
        return 10.13, 26, ""
    if gen in (8, 9):
        return 10.14, 26, ""
    if gen == 10:
        return 10.15, 26, ""
    return 11, 26, "11th gen and newer (hybrid/E-cores, new iGPU) are experimental in OpenCore - read the Dortania guide first."


def gpu_info(d, gen, notebook):
    """Return dict(name, family, kind, min, native_max, extra_max, note)."""
    name, vid = d["name"], d["vid"]
    n = name
    base = {"name": name, "kind": "dgpu", "min": 10.13, "native_max": 26, "extra_max": None, "note": ""}
    if vid == "10de" or re.search(r"nvidia|geforce|\bGT[XS]?\b|\bRTX\b|quadro", n, re.I):
        m = re.search(r"(?:GT[XS]?|RTX|GeForce)\s*(\d{3,4})", n, re.I) or re.search(r"\b(\d{3,4})\b", n)
        num = int(m.group(1)) if m else 0
        if not m:
            base.update(family="NVIDIA (unknown model)", native_max=0, min=99,
                        note="Could not tell which NVIDIA card this is.")
        elif num >= 1600:
            base.update(family="NVIDIA Turing/Ampere/Ada", native_max=0, min=99,
                        note="No macOS driver exists. Use another GPU (AMD RX 400/500/Vega/6000).")
        elif num >= 900:
            base.update(family="NVIDIA Maxwell/Pascal", native_max=10.13,
                        note="Only High Sierra (10.13) with NVIDIA Web Drivers. Newer macOS has no driver.")
        elif num in (745, 750) or 750 <= num < 760 and "ti" in n.lower():
            base.update(family="NVIDIA Maxwell (GTX 750)", native_max=10.13,
                        note="Only High Sierra (10.13) with NVIDIA Web Drivers.")
        elif 600 <= num < 800 and num not in (610, 620, 630):
            base.update(family="NVIDIA Kepler", native_max=12, extra_max=26,
                        note="Kepler is native up to Monterey (12). Newer macOS needs OpenCore Legacy Patcher root patches (experimental).")
        elif 400 <= num < 700:
            base.update(family="NVIDIA Fermi", native_max=10.13,
                        note="Fermi works only up to High Sierra (10.13). (Some GT 630/730 boards are really Kepler.)")
        else:
            base.update(family="NVIDIA (old)", native_max=10.13, note="Very old NVIDIA GPU: High Sierra at most.")
    elif vid == "1002" or re.search(r"amd|ati\b|radeon|\bRX\b|vega", n, re.I):
        m = re.search(r"RX\s*(\d{3,4})", n, re.I)
        num = int(m.group(1)) if m else 0
        if re.search(r"vega|radeon vii", n, re.I):
            base.update(family="AMD Vega", note="Works natively with WhateverGreen.")
        elif 400 <= num < 600:
            base.update(family="AMD Polaris (RX 400/500)", note="Best choice: works natively, no patching.")
        elif 5000 <= num < 6000:
            base.update(family="AMD Navi (RX 5000)", min=10.15,
                        note="Needs macOS 10.15.4+. Add boot-arg agdpmod=pikera if the screen goes black.")
        elif 6000 <= num < 7000:
            base.update(family="AMD RDNA2 (RX 6000)", min=11,
                        note="RX 6800/6900 need 11.4+, RX 6600/6700 need 12+. agdpmod=pikera may be needed.")
        elif num >= 7000:
            base.update(family="AMD RDNA3 (RX 7000)", native_max=0, min=99, note="Not supported by macOS.")
        else:
            base.update(family="AMD (older GCN / APU)", native_max=12,
                        note="Older Radeon (HD 7000 / R7 / R9): works up to roughly Monterey; newer macOS may need patches.")
    elif vid == "8086" or re.search(r"intel|\bHD Graphics|\bUHD|\bIris", n, re.I):
        base["kind"] = "igpu"
        if gen is None:
            base.update(family="Intel iGPU", native_max=0, min=99, note="Unknown CPU generation.")
        elif gen == 2:
            base.update(family="Intel HD 3000", native_max=10.13, note="HD 3000: High Sierra (10.13) at most.")
        elif gen == 3:
            base.update(family="Intel HD 4000", native_max=11, extra_max=12,
                        note="HD 4000: native up to Big Sur; newer needs OCLP root patches.")
        elif gen in (4, 5):
            base.update(family="Intel HD 4400/4600/5000/6000", native_max=12, extra_max=26,
                        note="Native up to Monterey; newer macOS may need OCLP root patches.")
        elif 6 <= gen <= 10:
            base.update(family="Intel HD/UHD 5xx-6xx", native_max=15, extra_max=26,
                        note="Works with WhateverGreen + platform-id. Tahoe iGPU support is uncertain.")
        else:
            base.update(family="Intel Xe / newer iGPU", native_max=0, min=99,
                        note="Not supported. You need a supported dedicated GPU.")
    else:
        base.update(family="unknown GPU", native_max=0, min=99, note="Not recognised - check Dortania's GPU buyers guide.")
    return base


def gpu_level(g, v):
    """0 = ok, 1 = needs extra steps, 2 = no acceleration."""
    if v < g["min"]:
        return 2
    if v <= g["native_max"]:
        return 0
    if g["extra_max"] and v <= g["extra_max"]:
        return 1
    return 2


def best_gpu_level(gpus, v):
    return min((gpu_level(g, v) for g in gpus), default=2)


WIFI_NOTE = {
    "intel": ("OK", "Intel Wi-Fi works with itlwm (+ HeliPort app)."),
    "broadcom": ("OK", "Broadcom Wi-Fi is supported (AirportBrcmFixup). BCM94360/943602 chips work best."),
    "realtek": ("NO", "Realtek Wi-Fi does not work on macOS. Replace the card (Intel AX200 / Broadcom BCM94360) or use a USB dongle."),
    "atheros": ("NO", "Qualcomm/Atheros Wi-Fi is not supported on current macOS. Replace the card or use a USB dongle."),
    "mediatek": ("NO", "MediaTek Wi-Fi does not work on macOS. Replace the card or use a USB dongle."),
    "unknown": ("?", "Wi-Fi chip not recognised: check that it is Intel or Broadcom."),
}
BT_NOTE = {
    "intel": ("OK", "Intel Bluetooth works with IntelBluetoothFirmware."),
    "broadcom": ("OK", "Broadcom Bluetooth works (BrcmPatchRAM) - the most reliable choice."),
    "realtek": ("NO", "Realtek Bluetooth does not work on macOS. Use an Intel/Broadcom USB dongle."),
    "atheros": ("NO", "Qualcomm/Atheros Bluetooth does not work reliably on macOS. Use an Intel/Broadcom USB dongle."),
    "mediatek": ("NO", "MediaTek Bluetooth does not work on macOS. Use an Intel/Broadcom USB dongle."),
    "unknown": ("?", "Bluetooth chip not recognised (CSR and generic dongles usually do not work)."),
}


def analyse(hw, notebook):
    res = {"warnings": [], "notes": []}
    gen, amd = parse_cpu(hw["cpu"])
    if amd:
        res.update(amd=True, gen=None)
        return res
    if gen is None and hw["cpu"] is not None:
        s = ask("  I could not tell the Intel generation from '%s'. Type it (2-14, e.g. 4 for Haswell) or Enter to stop: " % hw["cpu"])
        gen = int(s) if s.isdigit() else None
    res["gen"] = gen
    res["amd"] = False
    res["range"] = cpu_range(gen)
    res["gpus"] = [gpu_info(d, gen, notebook) for d in hw["gpus"]]
    res["wifi"] = [(d, vendor_of(d["name"], d["vid"])) for d in hw["wifi"]]
    res["bt"] = [(d, vendor_of(d["name"], d["vid"])) for d in hw["bt"]]
    return res


def macos_status(res, v):
    """Return (level 0/1/2, [reasons])."""
    rng = res["range"]
    if rng is None:
        return 2, ["CPU not supported"]
    lo, hi, _ = rng
    if v < lo or v > hi:
        return 2, ["CPU: %s supports %s to %s" % (GEN_NAMES.get(res["gen"], "?"), vlabel(lo), vlabel(hi))]
    reasons = []
    lvl = 0
    if res["gpus"]:
        gl = best_gpu_level(res["gpus"], v)
        if gl == 2:
            reasons.append("no supported GPU for this version (screen would run without acceleration)")
        elif gl == 1:
            reasons.append("GPU needs OpenCore Legacy Patcher root patches")
        lvl = max(lvl, gl)
    else:
        reasons.append("no GPU information")
    if res.get("gen") and res["gen"] >= 11:
        reasons.append("experimental CPU generation")
        lvl = max(lvl, 1)
    return lvl, reasons


def smbios_pick(gen, notebook, v, has_dgpu):
    if notebook:
        m = NB_BY_GEN.get(gen, "MacBookPro16,1")
        if gen and gen >= 10:
            m = "MacBookPro16,1"
        if MODEL_LAST[m] < v:
            m = "MacBookPro15,2" if v <= 15 else "MacBookPro16,1"
        return m
    if gen and gen >= 4 and v >= 10.15 and has_dgpu:
        return "MacPro7,1"
    m = DESK_BY_GEN.get(gen, "iMac20,1")
    if gen and gen >= 10:
        m = "iMac20,1"
    if MODEL_LAST[m] < v:
        m = "iMac19,1" if v <= 15 else "iMac20,1"
    return m


def smbios_candidates(rec, notebook, v, gen):
    pool = (["MacBookPro16,1", "MacBookPro15,2", "MacBookPro14,1"] if notebook else
            (["MacPro7,1"] if gen and gen >= 4 and v >= 10.15 else []) + ["iMacPro1,1", "iMac20,1", "iMac19,1"])
    out = [rec]
    for m in pool:
        if m not in out and MODEL_LAST.get(m, 0) >= v:
            out.append(m)
    return out[:4]


# ----------------------------------------------------------------------------------------------
# downloads
# ----------------------------------------------------------------------------------------------
def curl(args):
    return subprocess.run(["curl", "-fsSL", "-H", "User-Agent: hackintosh-auto"] + args,
                          capture_output=True, text=True)


def curl_file(url, dest):
    r = subprocess.run(["curl", "-fsSL", "-o", dest, url], capture_output=True, text=True)
    return r.returncode == 0


def get_latest(repo, pattern, label, tmp):
    """Download + extract the newest release asset matching pattern. Returns directory or None."""
    import json
    step("Downloading %s ..." % label)
    extra = []
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        extra = ["-H", "Authorization: Bearer " + tok]
    r = curl(extra + ["https://api.github.com/repos/%s/releases/latest" % repo])
    url = None
    try:
        for a in json.loads(r.stdout).get("assets", []):
            if re.search(pattern, a["name"]):
                url = a["browser_download_url"]
                break
    except Exception:
        pass
    if not url:
        warn("   WARNING: could not find %s (GitHub API limit or no internet?)" % label)
        return None
    zpath = os.path.join(tmp, os.path.basename(url))
    if not curl_file(url, zpath):
        warn("   WARNING: download failed for %s" % label)
        return None
    d = os.path.join(tmp, re.sub(r"[^A-Za-z0-9]", "_", label))
    os.makedirs(d, exist_ok=True)
    try:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(d)
    except Exception:
        warn("   WARNING: could not unzip %s" % label)
        return None
    ok("   OK: %s" % os.path.basename(url))
    return d


def copy_kext(src, name, dest):
    if not src:
        return False
    for root, dirs, _ in os.walk(src):
        if any(x in root for x in ("Debug", "dSYM", "__MACOSX")):
            continue
        if name in dirs:
            shutil.copytree(os.path.join(root, name), os.path.join(dest, name), dirs_exist_ok=True)
            return True
    warn("   WARNING: %s not found in the download" % name)
    return False


# ----------------------------------------------------------------------------------------------
# kext / SSDT plan
# ----------------------------------------------------------------------------------------------
KEXT_SRC = {
    "Lilu": ("acidanthera/Lilu", r"^Lilu-.*-RELEASE\.zip$", ["Lilu.kext"]),
    "VirtualSMC": ("acidanthera/VirtualSMC", r"^VirtualSMC-.*-RELEASE\.zip$", None),  # names set per device type
    "WhateverGreen": ("acidanthera/WhateverGreen", r"^WhateverGreen-.*-RELEASE\.zip$", ["WhateverGreen.kext"]),
    "AppleALC": ("acidanthera/AppleALC", r"^AppleALC-.*-RELEASE\.zip$", ["AppleALC.kext"]),
    "RestrictEvents": ("acidanthera/RestrictEvents", r"^RestrictEvents-.*-RELEASE\.zip$", ["RestrictEvents.kext"]),
    "IntelMausi": ("acidanthera/IntelMausi", r"^IntelMausi-.*-RELEASE\.zip$", ["IntelMausi.kext"]),
    "RealtekRTL8111": ("Mieze/RTL8111_driver_for_OS_X", r"^RealtekRTL8111-.*\.zip$", ["RealtekRTL8111.kext"]),
    "LucyRTL8125": ("Mieze/LucyRTL8125Ethernet", r"^LucyRTL8125Ethernet.*\.zip$", ["LucyRTL8125Ethernet.kext"]),
    "NVMeFix": ("acidanthera/NVMeFix", r"^NVMeFix-.*-RELEASE\.zip$", ["NVMeFix.kext"]),
    "USBToolBox": ("USBToolBox/kext", r"^USBToolBox-.*RELEASE\.zip$", ["USBToolBox.kext"]),
    "VoodooPS2": ("acidanthera/VoodooPS2", r"^VoodooPS2Controller-.*-RELEASE\.zip$", ["VoodooPS2Controller.kext"]),
    "VoodooI2C": ("VoodooI2C/VoodooI2C", r"^VoodooI2C-.*\.zip$", ["VoodooI2C.kext", "VoodooI2CHID.kext"]),
    "BrightnessKeys": ("acidanthera/BrightnessKeys", r"^BrightnessKeys-.*-RELEASE\.zip$", ["BrightnessKeys.kext"]),
    "ECEnabler": ("1Revenger1/ECEnabler", r"^ECEnabler-.*-RELEASE\.zip$", ["ECEnabler.kext"]),
    "itlwm": ("OpenIntelWireless/itlwm", r"^itlwm.*\.zip$", ["itlwm.kext"]),
    "IntelBT": ("OpenIntelWireless/IntelBluetoothFirmware", r"^IntelBluetoothFirmware.*\.zip$",
                ["IntelBluetoothFirmware.kext", "IntelBTPatcher.kext", "IntelBluetoothInjector.kext"]),
    "BrcmPatchRAM": ("acidanthera/BrcmPatchRAM", r"^BrcmPatchRAM-.*-RELEASE\.zip$",
                     ["BlueToolFixup.kext", "BrcmFirmwareData.kext", "BrcmPatchRAM3.kext", "BrcmBluetoothInjector.kext"]),
    "AirportBrcmFixup": ("acidanthera/AirportBrcmFixup", r"^AirportBrcmFixup-.*-RELEASE\.zip$", ["AirportBrcmFixup.kext"]),
}
KEXT_ORDER = ["Lilu", "VirtualSMC", "SMCProcessor", "SMCSuperIO", "SMCBatteryManager", "SMCLightSensor",
              "WhateverGreen", "AppleALC", "RestrictEvents", "ECEnabler", "BrightnessKeys", "IntelMausi",
              "RealtekRTL8111", "LucyRTL8125Ethernet", "NVMeFix", "USBToolBox", "UTBMap", "VoodooPS2Controller",
              "VoodooI2C", "VoodooI2CHID", "IntelBluetoothFirmware", "IntelBTPatcher", "IntelBluetoothInjector",
              "BlueToolFixup", "BrcmFirmwareData", "BrcmPatchRAM3", "BrcmBluetoothInjector", "itlwm",
              "AirportBrcmFixup"]
KEXT_LIMITS = {"BlueToolFixup.kext": ("21.0.0", ""), "IntelBluetoothInjector.kext": ("", "20.99.99"),
               "BrcmBluetoothInjector.kext": ("", "20.99.99")}


def make_plan(hw, res, notebook, v):
    """Return (list of KEXT_SRC keys, notes)."""
    plan = ["Lilu", "VirtualSMC", "WhateverGreen", "AppleALC", "RestrictEvents", "USBToolBox"]
    notes = []
    # ethernet
    eth_kind = None
    for d in hw["eth"]:
        t = d["name"].lower()
        vend = vendor_of(d["name"], d["vid"])
        if re.search(r"8125|2\.5g", t) or d["did"] == "8125":
            eth_kind = "LucyRTL8125"
        elif vend == "realtek":
            eth_kind = "RealtekRTL8111"
        elif vend == "intel":
            if re.search(r"i225|i226|igc", t):
                notes.append("Intel I225/I226 2.5G Ethernet needs the AppleIGC kext (not downloaded automatically).")
            else:
                eth_kind = "IntelMausi"
        else:
            notes.append("Ethernet '%s' not recognised: find the right kext in the Dortania Ethernet guide." % d["name"])
        if eth_kind:
            break
    if eth_kind:
        plan.append(eth_kind)
    elif not hw["eth"]:
        plan += ["IntelMausi", "RealtekRTL8111"]
        notes.append("Ethernet chip unknown: both IntelMausi and RealtekRTL8111 were added - delete the one you do not need.")
    if hw["nvme"]:
        plan.append("NVMeFix")
    # Wi-Fi / Bluetooth
    bt_vend = {x[1] for x in res["bt"]}
    wifi_vend = {x[1] for x in res["wifi"]}
    if "intel" in wifi_vend:
        plan.append("itlwm")
        notes.append("Intel Wi-Fi: install the HeliPort app on macOS to connect to networks.")
    if "broadcom" in wifi_vend:
        plan.append("AirportBrcmFixup")
    if "intel" in bt_vend:
        plan += ["IntelBT", "BrcmPatchRAM"]  # BrcmPatchRAM zip also carries BlueToolFixup (needed on macOS 12+)
    if "broadcom" in bt_vend and "BrcmPatchRAM" not in plan:
        plan.append("BrcmPatchRAM")
    if notebook:
        plan += ["VoodooPS2", "BrightnessKeys", "ECEnabler"]
        tp = hw.get("touchpad", "ps2")
        if tp == "i2c":
            plan.append("VoodooI2C")
    return plan, notes


# ----------------------------------------------------------------------------------------------
# config.plist
# ----------------------------------------------------------------------------------------------
def kext_entries(kxdir, v):
    names = [n for n in os.listdir(kxdir) if n.endswith(".kext")]

    def prio(n):
        b = n[:-5]
        return KEXT_ORDER.index(b) if b in KEXT_ORDER else 500
    entries = []

    def add(rel, base):
        full = os.path.join(kxdir, rel)
        exe = ""
        macos = os.path.join(full, "Contents", "MacOS")
        if os.path.isdir(macos):
            files = sorted(os.listdir(macos))
            if files:
                exe = "Contents/MacOS/" + (base if base in files else files[0])
        mn, mx = KEXT_LIMITS.get(os.path.basename(rel), ("", ""))
        entries.append({"Arch": "Any", "BundlePath": rel, "Comment": os.path.basename(rel)[:-5],
                        "Enabled": True, "ExecutablePath": exe, "MaxKernel": mx, "MinKernel": mn,
                        "PlistPath": "Contents/Info.plist"})
        plug = os.path.join(full, "Contents", "PlugIns")
        if os.path.isdir(plug):
            subs = sorted((p for p in os.listdir(plug) if p.endswith(".kext")),
                          key=lambda p: (p != "VoodooInput.kext", p))
            for p in subs:
                add(rel + "/Contents/PlugIns/" + p, p[:-5])

    for n in sorted(names, key=lambda n: (prio(n), n)):
        add(n, n[:-5])
    return entries


def gen_serial(oc_dir, model):
    """Returns (serial, mlb, used_macserial)."""
    exe = os.path.join(oc_dir, "Utilities", "macserial", "macserial.exe" if IS_WINDOWS else "macserial.linux")
    if os.path.isfile(exe) and platform.machine() in ("x86_64", "AMD64"):
        try:
            if not IS_WINDOWS:
                os.chmod(exe, 0o755)
            out = subprocess.run([exe, "--model", model, "--num", "1"], capture_output=True, text=True, timeout=30).stdout
            m = re.search(r"^\s*(\S+)\s*\|\s*(\S+)", out, re.M)
            if m:
                return m.group(1), m.group(2), True
        except Exception:
            pass
    al = string.ascii_uppercase + string.digits
    rnd = lambda n: "".join(secrets.choice(al) for _ in range(n))
    return "C02" + rnd(9), "C02" + rnd(14), False


def write_config(cfg_path, oc_dir, efi, choice, hw, res, notebook, dual, v, plan_ok):
    cfg = plistlib.load(open(cfg_path, "rb"))
    gen = res["gen"]
    model = choice["smbios"]
    notes = []

    # --- graphical picker + mouse + drivers
    drv_dir = os.path.join(efi, "OC", "Drivers")
    drivers = [f for f in ("OpenRuntime.efi", "HfsPlus.efi", "OpenCanopy.efi") if os.path.isfile(os.path.join(drv_dir, f))]
    cfg["UEFI"]["Drivers"] = [{"Arguments": "", "Comment": "", "Enabled": True, "HideVerbose": False, "LoadEarly": False, "Path": f}
                              for f in drivers]
    cfg["Misc"]["Boot"]["PickerMode"] = "External"
    cfg["Misc"]["Security"]["ScanPolicy"] = 0
    cfg["UEFI"]["Input"]["PointerSupport"] = True
    cfg["UEFI"]["Input"]["PointerSupportMode"] = "ASUS"
    if "HfsPlus.efi" not in drivers:
        notes.append("HfsPlus.efi was NOT downloaded: copy it from acidanthera/OcBinaryData into EFI/OC/Drivers or the macOS recovery will not show.")

    # --- ACPI
    acpi_dir = os.path.join(efi, "OC", "ACPI")
    cfg["ACPI"]["Add"] = [{"Comment": f, "Enabled": True, "Path": f}
                          for f in sorted(os.listdir(acpi_dir)) if f.endswith(".aml")]

    # --- kexts
    cfg["Kernel"]["Add"] = kext_entries(os.path.join(efi, "OC", "Kexts"), v)

    # --- kernel quirks by generation
    q = cfg["Kernel"]["Quirks"]
    q["DisableIoMapper"] = True
    if gen in (2, 3):
        q["AppleCpuPmCfgLock"] = True
    elif gen and gen >= 4:
        q["AppleXcpmCfgLock"] = True
    bq = cfg["Booter"]["Quirks"]
    if gen and gen >= 8:
        bq["EnableWriteUnprotector"] = False
        bq["RebuildAppleMemoryMap"] = True
        bq["SyncRuntimePermissions"] = True

    # --- boot-args
    args = ["-v", "keepsyms=1", "debug=0x100", "alcid=1"]
    gp = res["gpus"]
    if any(re.search(r"Navi|RDNA", g["family"]) for g in gp):
        args.append("agdpmod=pikera")
    if notebook and gp and any(g["kind"] == "dgpu" and gpu_level(g, v) == 2 for g in gp):
        args.append("-wegnoegpu")
        notes.append("Unsupported dedicated GPU in a notebook: -wegnoegpu was added so only the Intel iGPU is used.")
    nv = cfg["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]
    nv["boot-args"] = " ".join(args)
    nv["csr-active-config"] = b"\x00\x00\x00\x00"
    if any(g["family"] == "NVIDIA Kepler" and v > 12 for g in gp):
        notes.append("Kepler GPU on macOS %s: after installing, use OpenCore Legacy Patcher root patches; you may also need "
                     "boot-arg amfi=0x80 (as worked for the author on Tahoe) and csr-active-config 03 0A 00 00." % vlabel(v))

    # --- iGPU platform-id
    ig = [g for g in gp if g["kind"] == "igpu"]
    dgpu_ok = any(g["kind"] == "dgpu" and gpu_level(g, v) < 2 for g in gp)
    cfg["DeviceProperties"]["Add"] = {}
    if ig and gen in IG_PLATFORM and (notebook or not dgpu_ok):
        pid = IG_PLATFORM[gen][1 if notebook else 0]
        if pid is not None:
            cfg["DeviceProperties"]["Add"]["PciRoot(0x0)/Pci(0x2,0x0)"] = {
                "AAPL,ig-platform-id": pid.to_bytes(4, "little")}
            notes.append("Intel iGPU platform-id 0x%08X was set (Dortania default for %s %s). If you get a black screen, "
                         "try another id from the Dortania iGPU guide." % (pid, GEN_NAMES.get(gen, ""), "laptops" if notebook else "desktops"))
        else:
            notes.append("No default iGPU platform-id for this notebook generation: set AAPL,ig-platform-id from the Dortania guide.")
    elif ig and dgpu_ok and not notebook:
        notes.append("Desktop with a dedicated GPU: the Intel iGPU is best left enabled in BIOS but unused (headless id optional) or disabled.")

    # --- SMBIOS
    serial, mlb, real = gen_serial(oc_dir, model)
    g = cfg["PlatformInfo"]["Generic"]
    g["SystemProductName"] = model
    g["SystemSerialNumber"] = serial
    g["MLB"] = mlb
    g["SystemUUID"] = str(uuid.uuid4()).upper()
    g["ROM"] = secrets.token_bytes(6)
    cfg["PlatformInfo"]["Automatic"] = True
    cfg["PlatformInfo"]["UpdateDataHub"] = True
    cfg["PlatformInfo"]["UpdateNVRAM"] = True
    cfg["PlatformInfo"]["UpdateSMBIOS"] = True
    if not real:
        notes.append("Serial/MLB are random placeholders (macserial could not run here). Generate real ones with "
                     "macserial or GenSMBIOS before using iServices.")
    plistlib.dump(cfg, open(cfg_path, "wb"), sort_keys=False)
    return notes, (serial, mlb)


# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Hackintosh_Auto: interactive OpenCore EFI builder")
    ap.add_argument("--report", help="hardware_report.txt made by windows/read_hardware_pc.bat")
    ap.add_argument("--out", help="output folder")
    ap.add_argument("--skip-recovery", action="store_true", help="do not download the macOS recovery image")
    args = ap.parse_args()

    print()
    print("Hackintosh_Auto v%s (experimental) - %s" % (VERSION, "Termux" if IS_TERMUX else ("Windows" if IS_WINDOWS else "Linux")))
    print("Compatibility data is approximate. Read https://dortania.github.io/OpenCore-Install-Guide/ before installing.")

    # ---- output folder
    if args.out:
        out = args.out
    elif IS_WINDOWS:
        out = os.path.join(os.path.expanduser("~"), "Desktop", "Hackintosh_Auto_Output")
    elif IS_TERMUX:
        home = os.path.expanduser("~")
        if not os.path.isdir(os.path.join(home, "storage", "shared")):
            warn("Storage access is not set up. Run:  termux-setup-storage   then run this script again.")
            sys.exit(1)
        out = os.path.join(home, "storage", "shared", "Hackintosh_Auto_Output")
    else:
        out = os.environ.get("HA_OUT") or os.path.join(os.path.expanduser("~"), "Hackintosh_Auto_Output")

    # ---- questions
    notebook = choose("What kind of computer is this EFI for?", ["Desktop PC", "Notebook / laptop"], 1) == 1
    dual = choose("Do you want to dual boot with Windows (or another OS)?",
                  ["No - macOS only", "Yes - keep Windows in the boot menu"], 1) == 1

    # ---- hardware
    if args.report:
        hw = parse_report(args.report)
        info("Hardware read from %s" % args.report)
    elif not IS_TERMUX and not IS_WINDOWS:
        hw = detect_linux()
        if shutil.which("lspci") is None or shutil.which("lscpu") is None:
            warn("lspci/lscpu not found, so some hardware cannot be detected. Install them with: sudo apt install pciutils usbutils util-linux")
        info("Hardware detected on this computer.")
    else:
        hw = None
        if IS_WINDOWS:
            warn("No hardware report given. Run Hackintosh_Auto.bat (it reads this PC for you) or answer the questions below.")
    if hw is not None:
        show_hw(hw)
        if not yesno("\nIs this correct?", True):
            hw = manual_hw(hw)
    else:
        hw = manual_hw(new_hw())
    if not hw["cpu"]:
        hw["cpu"] = ask("  Processor model (needed): ")
    if notebook:
        tp = choose("Touchpad type? (if unsure choose PS/2)", ["PS/2 / Synaptics / ELAN (most common)", "I2C (precision touchpad)"], 1)
        hw["touchpad"] = "i2c" if tp == 1 else "ps2"

    # ---- analysis
    res = analyse(hw, notebook)
    print()
    info("=== Compatibility report ===")
    if res.get("amd"):
        warn("AMD processor detected. AMD CPUs need extra kernel patches (AMD Vanilla) that this tool does not build yet.")
        warn("See: https://dortania.github.io/OpenCore-Install-Guide/  (AMD section).  Nothing was built.")
        sys.exit(0)
    gen = res["gen"]
    if gen is None or res["range"] is None:
        warn("CPU generation unknown or too old (Nehalem and older are not handled). Nothing was built.")
        sys.exit(0)
    print("CPU: %s -> %s (generation %d)" % (hw["cpu"], GEN_NAMES.get(gen, "?"), gen))
    for g in res["gpus"]:
        print("GPU: %s -> %s. %s" % (g["name"], g["family"], g["note"]))
    if not res["gpus"]:
        print("GPU: none given. A supported GPU (or Intel iGPU) is required for a usable desktop.")
    if res["range"][2]:
        warn("Note: " + res["range"][2])
    if notebook or res["wifi"] or res["bt"]:
        for d, vend in res["wifi"]:
            lvl, msg = WIFI_NOTE[vend]
            print("Wi-Fi: %s -> [%s] %s" % (d["name"], lvl, msg))
        for d, vend in res["bt"]:
            lvl, msg = BT_NOTE[vend]
            print("Bluetooth: %s -> [%s] %s" % (d["name"], lvl, msg))
        if notebook and not res["wifi"]:
            warn("Notebook: no Wi-Fi card given. Without a supported card there is no Wi-Fi on macOS.")
        if notebook and not res["bt"]:
            warn("Notebook: no Bluetooth device given.")
    print()
    info("macOS versions for this computer:")
    labels, avail = [], []
    for name, ver, board, mlb, extra in MACOS:
        lvl, why = macos_status(res, ver)
        tag = {0: "compatible", 1: "compatible with extra steps", 2: "NOT recommended"}[lvl]
        labels.append("%-12s (%s)  %s%s" % (name, vlabel(ver), tag, (" - " + "; ".join(why)) if why and lvl else ""))
        avail.append(lvl)
    good = [i for i, l in enumerate(avail) if l == 0]
    maybe = [i for i, l in enumerate(avail) if l == 1]
    default = (good[-1] if good else maybe[-1] if maybe else len(MACOS) - 1) + 1
    idx = choose("Which macOS do you want?", labels, default)
    name, ver, board, mlb, extra = MACOS[idx]
    if avail[idx] == 2:
        warn("This version is not recommended for your hardware; continuing anyway as you asked.")

    has_dgpu = any(g["kind"] == "dgpu" and gpu_level(g, ver) < 2 for g in res["gpus"])
    rec = smbios_pick(gen, notebook, ver, has_dgpu)
    cands = smbios_candidates(rec, notebook, ver, gen)
    mi = choose("Which Mac model (SMBIOS) should this PC pretend to be?",
                [c + ("  (recommended)" if c == rec else "") for c in cands] + ["Type another model"], 1)
    model = cands[mi] if mi < len(cands) else ask("Model (e.g. MacPro7,1): ", rec)
    choice = {"smbios": model, "macos": name}

    plan, plan_notes = make_plan(hw, res, notebook, ver)
    print()
    info("Summary: %s | %s | %s | %s | dual boot: %s" % (("notebook" if notebook else "desktop"), vlabel(ver) + " " + name, model,
                                                        "kexts: " + ", ".join(plan), "yes" if dual else "no"))
    if not yesno("Build the EFI now?", True):
        print("Cancelled. Nothing was written.")
        sys.exit(0)

    # ---- build
    if os.path.isdir(out):
        shutil.rmtree(out)
    tmp = os.path.join(out, "_temp")
    os.makedirs(tmp)
    info("Output folder: %s" % out)

    oc = get_latest("acidanthera/OpenCorePkg", r"^OpenCore-.*-RELEASE\.zip$", "OpenCore", tmp)
    if not oc:
        warn("OpenCore download failed. Cannot continue.")
        sys.exit(1)
    shutil.copytree(os.path.join(oc, "X64", "EFI"), os.path.join(out, "EFI"))
    efi = os.path.join(out, "EFI")
    drv = os.path.join(efi, "OC", "Drivers")
    for f in os.listdir(drv):
        if f not in ("OpenRuntime.efi", "OpenCanopy.efi"):
            os.remove(os.path.join(drv, f))
    tools = os.path.join(efi, "OC", "Tools")
    for f in os.listdir(tools):
        if f != "OpenShell.efi":
            os.remove(os.path.join(tools, f))
    step("Downloading HfsPlus.efi ...")
    if not curl_file("https://github.com/acidanthera/OcBinaryData/raw/master/Drivers/HfsPlus.efi", os.path.join(drv, "HfsPlus.efi")):
        warn("   WARNING: HfsPlus.efi download failed")
    cfg_path = os.path.join(efi, "OC", "config.plist")
    shutil.copy(os.path.join(oc, "Docs", "Sample.plist"), cfg_path)

    kx = os.path.join(efi, "OC", "Kexts")
    shutil.rmtree(kx, ignore_errors=True)
    os.makedirs(kx)
    for key in plan:
        repo, pat, names = KEXT_SRC[key]
        d = get_latest(repo, pat, key, tmp)
        if key == "VirtualSMC":
            names = (["VirtualSMC.kext", "SMCProcessor.kext", "SMCBatteryManager.kext", "SMCLightSensor.kext"]
                     if notebook else ["VirtualSMC.kext", "SMCProcessor.kext", "SMCSuperIO.kext"])
        if d:
            for n in names:
                # extra BrcmPatchRAM pieces only when they are needed
                if key == "BrcmPatchRAM":
                    bt_v = {x[1] for x in res["bt"]}
                    need = {"BlueToolFixup.kext"}
                    if "broadcom" in bt_v:
                        need |= {"BrcmFirmwareData.kext", "BrcmPatchRAM3.kext", "BrcmBluetoothInjector.kext"}
                    if n not in need:
                        continue
                copy_kext(d, n, kx)

    acpi = os.path.join(efi, "OC", "ACPI")
    shutil.rmtree(acpi, ignore_errors=True)
    os.makedirs(acpi)
    base = "https://raw.githubusercontent.com/dortania/Getting-Started-With-ACPI/master/extra-files/compiled/"
    ssdts = ["SSDT-PLUG-DRTNIA.aml", "SSDT-EC-USBX-LAPTOP.aml" if notebook else "SSDT-EC-USBX-DESKTOP.aml"]
    if gen >= 8 and not notebook:
        ssdts.append("SSDT-AWAC.aml")
    for f in ssdts:
        step("Downloading %s ..." % f)
        if not curl_file(base + f, os.path.join(acpi, f)):
            warn("   WARNING: failed %s - get it from dortania.github.io/Getting-Started-With-ACPI" % f)
            if os.path.exists(os.path.join(acpi, f)):
                os.remove(os.path.join(acpi, f))
    if gen in (2, 3):
        plan_notes.append("Sandy/Ivy Bridge: generate a CPU power-management SSDT with ssdtPRGen (SSDT-PLUG does not apply).")
    if dual:
        plan_notes.append("Dual boot: ScanPolicy is 0, so Windows appears in the OpenCanopy menu. If Windows and macOS are on the same "
                          "PC, fix the clock: in Windows run  reg add \"HKLM\\SYSTEM\\CurrentControlSet\\Control\\TimeZoneInformation\" "
                          "/v RealTimeIsUniversal /t REG_DWORD /d 1 /f")

    cfg_notes, (serial, mlb) = write_config(cfg_path, oc, efi, choice, hw, res, notebook, dual, ver, plan)
    ok("config.plist written (drivers, kext order, SSDTs, SMBIOS, quirks, OpenCanopy + mouse).")

    # ---- ocvalidate (x86_64 Linux / Windows only)
    oc_val = os.path.join(oc, "Utilities", "ocvalidate", "ocvalidate.exe" if IS_WINDOWS else "ocvalidate.linux")
    if os.path.isfile(oc_val) and platform.machine() in ("x86_64", "AMD64"):
        try:
            if not IS_WINDOWS:
                os.chmod(oc_val, 0o755)
            r = subprocess.run([oc_val, cfg_path], capture_output=True, text=True, timeout=60)
            tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
            info("ocvalidate:")
            for l in tail:
                print("  " + l)
        except Exception:
            pass

    # ---- macOS recovery
    shutil.copytree(os.path.join(oc, "Utilities", "macrecovery"), os.path.join(out, "macrecovery"))
    if args.skip_recovery:
        warn("Recovery download skipped (--skip-recovery).")
    else:
        step("Downloading the macOS %s recovery image (this can take a while) ..." % name)
        cmd = [sys.executable, "macrecovery.py", "-b", board, "-m", mlb] + extra + ["download"]
        r = subprocess.run(cmd, cwd=os.path.join(out, "macrecovery"))
        bs = os.path.join(out, "macrecovery", "com.apple.recovery.boot", "BaseSystem.dmg")
        if r.returncode == 0 and os.path.isfile(bs):
            shutil.move(os.path.join(out, "macrecovery", "com.apple.recovery.boot"), os.path.join(out, "com.apple.recovery.boot"))
            ok("com.apple.recovery.boot folder is ready in: %s" % out)
        else:
            warn("WARNING: the recovery download did not finish. Run this later inside %s/macrecovery:" % out)
            print("   python3 macrecovery.py -b %s -m %s %s download" % (board, mlb, " ".join(extra)))

    # ---- report
    todo = plan_notes + cfg_notes + [
        "Map your USB ports (USBToolBox tool, generates UTBMap.kext) - the number of ports on macOS is limited.",
        "Audio uses layout alcid=1; if there is no sound try other layout ids for your codec (AppleALC wiki).",
        "Check BIOS settings: disable Secure Boot, CSM/Legacy; enable UEFI; XHCI hand-off; disable CFG-Lock if possible.",
    ]
    with open(os.path.join(out, "BUILD_INFO.txt"), "w", encoding="utf-8") as f:
        f.write("Hackintosh_Auto v%s\n\n" % VERSION)
        f.write("Device: %s\nmacOS: %s (%s)\nSMBIOS: %s\nDual boot: %s\nCPU: %s\nBoard: %s\nKexts: %s\n\n" % (
            "notebook" if notebook else "desktop", name, vlabel(ver), model, dual, hw["cpu"], hw["board"], ", ".join(plan)))
        f.write("TO DO / NOTES\n")
        for t in todo:
            f.write(" - %s\n" % t)
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    ok("DONE. Folder: %s" % out)
    info("USB drive (FAT32, GUID): copy BOTH the EFI folder and the com.apple.recovery.boot folder to the ROOT of the drive.")
    print()
    info("Notes:")
    for t in todo:
        print(" - " + t)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
