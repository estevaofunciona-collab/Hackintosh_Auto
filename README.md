# Hackintosh_Auto

Scripts that help you prepare an **OpenCore EFI folder** and the **macOS recovery image** for a Hackintosh.

> **Status: v0.1 - experimental.** The scripts build a *base* EFI (OpenCore + OpenCanopy graphical menu + common kexts + the installer download). They do **not** produce a finished, guaranteed-to-boot EFI: you still need to edit `config.plist` for your hardware. Use at your own risk and always keep a backup of any EFI that already works.

## What it does

| Step | Windows | Linux | Termux (Android) |
|---|---|---|---|
| Downloads the latest **OpenCore** | yes | yes | yes |
| Enables the **OpenCanopy** graphical boot menu with mouse support | yes | yes | yes |
| Downloads common **kexts** (Lilu, VirtualSMC, WhateverGreen, AppleALC, Ethernet, NVMeFix, USBToolBox) | yes | yes | yes |
| Downloads example **SSDTs** (Haswell desktop) | yes | yes | yes |
| Downloads the **macOS recovery** (`com.apple.recovery.boot`) with `macrecovery` | yes | yes | yes |
| Reads the hardware of the PC and writes a report | `read_hardware_pc.bat` | summary at the end | no (a phone cannot see your PC) |

The output folder contains `EFI/` and `com.apple.recovery.boot/` side by side. For a USB installer, copy **both** folders to the **root** of a FAT32 drive with a GUID partition map.

## What it does NOT do

- It does **not** partition, format or write to any disk.
- It does **not** generate a ready-to-use `config.plist`. The file is OpenCore's `Sample.plist` with only the drivers/menu settings above changed. You must set the SMBIOS and serial numbers (for example with GenSMBIOS / `macserial`), the kext entries (ProperTree "OC Snapshot"), ACPI patches, and a USB map for your machine.
- It does **not** apply the OpenCore Legacy Patcher root patch. Hardware that Apple no longer supports (for example NVIDIA Kepler GPUs) needs that step inside macOS, and it can break boot on macOS versions that the patcher version does not support.
- It does **not** redistribute any Apple files: everything is downloaded from Apple/GitHub at run time.

## Usage

### Windows
1. Download `windows/Hackintosh_Auto.bat`.
2. Double-click it. Python is needed for the recovery download (install it from python.org if missing).
3. The result is created on your Desktop in `Hackintosh_Auto_Output`.

To see what hardware you have first, run `windows/read_hardware_pc.bat`. It is read-only and saves `hardware_report.txt` on your Desktop, with kext suggestions (Ethernet, Bluetooth, GPU notes).

### Linux
```bash
sudo apt install git curl unzip python3   # or the equivalent for your distro
git clone https://github.com/estevaofunciona-collab/Hackintosh_Auto
cd Hackintosh_Auto
bash linux-termux/hackintosh_auto.sh
```
Output: `~/Hackintosh_Auto_Output` (set `HA_OUT=/some/path` to change it).

### Termux (Android)
```bash
pkg install git curl unzip python
termux-setup-storage
git clone https://github.com/estevaofunciona-collab/Hackintosh_Auto
cd Hackintosh_Auto
bash linux-termux/hackintosh_auto.sh
```
Output: `Hackintosh_Auto_Output` in your phone's shared storage. Copy it to a USB drive with an OTG adapter. The recovery image is several hundred MB, so use a good connection and free space.

## After the EFI is built

1. Keep only the Ethernet kext that matches your board (`IntelMausi` or `RealtekRTL8111`); delete the other. Delete `NVMeFix` if you have no NVMe drive.
2. Open `EFI/OC/config.plist` in ProperTree or OpenCore Auxiliary Tools, run the OC Snapshot (select the `OC` folder) so the kext list matches the folder, and set the SMBIOS for your CPU generation.
3. Boot the USB drive, install macOS to a **separate** drive, then copy the EFI to the internal drive's EFI partition.
4. Map your USB ports with USBToolBox (this creates `UTBMap.kext`).

Follow the [Dortania OpenCore Install Guide](https://dortania.github.io/OpenCore-Install-Guide/) for the details of your hardware generation.

## Dual boot with Windows

The safest setup is **one operating system per physical drive**. OpenCore shows Windows in its boot menu automatically. If Windows and macOS show different times, run this once in an administrator Command Prompt on Windows:

```
reg add "HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" /v RealTimeIsUniversal /t REG_DWORD /d 1 /f
```
In the BIOS, put OpenCore first in the boot order, and disable Fast Boot if the PC keeps going straight to Windows.

## Roadmap

- Interactive menu: desktop or laptop, dual boot or not, target Mac model and macOS version.
- Compatibility check based on the detected CPU, GPU, Ethernet, Wi-Fi and Bluetooth (for laptops it will check the Wi-Fi/Bluetooth chips).
- Automatic kext selection from the hardware report and a validated `config.plist` (`ocvalidate`).

## Disclaimer

This project is not affiliated with Apple or the OpenCore project. macOS is licensed by Apple for use on Apple-branded hardware. You are responsible for complying with the licenses and laws that apply to you. Never publish your own serial numbers, MLB or ROM values.

## License

MIT - see [LICENSE](LICENSE).
