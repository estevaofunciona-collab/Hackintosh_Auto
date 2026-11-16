# Hackintosh_Auto

Scripts that help you prepare an **OpenCore EFI folder** and the **macOS recovery image** for a Hackintosh.

> **Status: experimental.** The **Linux / Termux / Windows** version (v0.2) is interactive: it asks desktop or notebook and dual boot, reads (or asks for) your hardware, checks compatibility, lets you choose the macOS version and the Mac model, then builds the EFI with the right kexts and a generated `config.plist`. The **Windows** `.bat` (v0.2) now runs the same flow: it reads the hardware of the PC itself, asks desktop/notebook and dual boot, and builds the EFI. None of this is guaranteed to boot your machine: use at your own risk and always keep a backup of any EFI that already works.

## What it does

| Step | Windows (v0.2) | Linux (v0.2) | Termux (v0.2) |
|---|---|---|---|
| Asks desktop / notebook and dual boot | yes | yes | yes |
| Gets your hardware | reads it itself (WMI), saves `hardware_report.txt` | detects it automatically (`lscpu`, `lspci`, `lsusb`) | `--report hardware_report.txt`, or asks you (CPU, board, GPU, Ethernet, audio, Wi-Fi, Bluetooth) |
| Compatibility check (CPU generation, GPU, and Wi-Fi + Bluetooth on notebooks) | yes | yes | yes |
| Bluetooth by USB ID (VID:PID): Broadcom BCM20702, Intel, CSR (`0a12:0001`, best-effort), Realtek/Atheros/MediaTek (not supported) | yes | yes | yes (type the chip vendor) |
| Lists the compatible macOS versions and lets you pick the **macOS** and the **Mac model (SMBIOS)** | yes | yes | yes |
| Downloads the latest **OpenCore** | yes | yes | yes |
| Picks and downloads the **kexts** for your hardware and writes them to `config.plist` in load order | yes | yes | yes |
| Writes `config.plist` (SMBIOS + serial, quirks, SSDTs, iGPU platform-id, boot-args) and runs `ocvalidate` | yes | yes | yes (`ocvalidate` on x86_64 Linux only) |
| Enables the **OpenCanopy** graphical boot menu with mouse | yes | yes | yes |
| Downloads the **macOS recovery** (`com.apple.recovery.boot`) for the macOS you chose | yes | yes | yes |

The output folder contains `EFI/`, `com.apple.recovery.boot/` and `BUILD_INFO.txt` (what was chosen and what is left to do). For a USB installer, copy **both** folders to the **root** of a FAT32 drive with a GUID partition map.

## What it does NOT do

- It does **not** partition, format or write to any disk.
- It does **not** guarantee a bootable EFI. The generated `config.plist` is a good starting point but BIOS settings, ACPI patches, USB mapping, audio layout and iGPU/GPU details are hardware specific. The compatibility data in the script is approximate: read the Dortania guide.
- AMD processors are detected but not built yet (they need extra kernel patches).
- It does **not** apply the OpenCore Legacy Patcher root patch. Hardware that Apple no longer supports (for example NVIDIA Kepler GPUs) needs that step inside macOS, and it can break boot on macOS versions that the patcher version does not support.
- It does **not** redistribute any Apple files: everything is downloaded from Apple/GitHub at run time.

## Usage

### Windows
1. Download `windows/Hackintosh_Auto.bat` (Windows 10 or 11).
2. Double-click it. It reads your hardware (read-only), then asks: desktop or notebook, dual boot, which macOS and which Mac model. Plug your Bluetooth dongle in first so it is detected. It also detects keyboard/mouse/touchpad (PS/2, I2C or USB), the USB controllers, and other devices such as webcam, fingerprint reader and card reader, and tells you which ones work on macOS.
3. If Python 3 is not installed it downloads a small portable copy (about 10 MB) by itself.
4. The result is created on your Desktop in `Hackintosh_Auto_Output` (`EFI` + `com.apple.recovery.boot` + `BUILD_INFO.txt`). A copy of the hardware report is saved as `hardware_report.txt` on your Desktop.

`windows/read_hardware_pc.bat` is still there if you only want the report (with kext suggestions).

### Linux
```bash
sudo apt install git curl python3   # or the equivalent for your distro
git clone https://github.com/estevaofunciona-collab/Hackintosh_Auto
cd Hackintosh_Auto
bash linux-termux/hackintosh_auto.sh
```
The script detects the hardware of the computer you run it on, shows it, and asks you to confirm. Then you choose the macOS version and the Mac model and it builds everything. Output: `~/Hackintosh_Auto_Output` (`--out DIR` or `HA_OUT=DIR` to change it).

Options: `--report FILE` (use a `hardware_report.txt` from another PC instead of detecting), `--out DIR`, `--skip-recovery` (do not download the macOS image now).

### macOS (build the EFI from a Mac)
1. Download `macos/Hackintosh_Auto.command`. First time: right-click it -> **Open** (macOS blocks files downloaded from the internet).
2. It needs Python 3.8+ (`xcode-select --install` installs it). The Mac is not the target PC, so it asks about the PC you are building for - or run `Hackintosh_Auto.bat` on that PC first and pass `--report hardware_report.txt` (`bash` / Terminal: `python3 hackintosh_auto.py --report hardware_report.txt`).
3. The finished `EFI` and `com.apple.recovery.boot` folders are in `Desktop/Hackintosh_Auto_Output`.

### Termux (Android)
A phone cannot see your PC's hardware, so there are two ways to tell it:

1. **Report:** run `windows/read_hardware_pc.bat` on the PC, copy `hardware_report.txt` to the phone, then `bash linux-termux/hackintosh_auto.sh --report hardware_report.txt`.
2. **Questions:** run it without `--report` and answer (processor, board, graphics card, Ethernet, audio, Wi-Fi, Bluetooth).

```bash
pkg install git curl python
termux-setup-storage
git clone https://github.com/estevaofunciona-collab/Hackintosh_Auto
cd Hackintosh_Auto
bash linux-termux/hackintosh_auto.sh
```
Output: `Hackintosh_Auto_Output` in your phone's shared storage. Copy it to a USB drive with an OTG adapter. The recovery image is several hundred MB, so use a good connection and free space.

## Removing the Hackintosh again (Windows)
`windows/Remove_Hackintosh.bat` takes OpenCore out of the EFI partition if you want to go back to Windows only. It copies the EFI folder to `Desktop\Backup EFI` first, asks you to type `REMOVE` to confirm, and **never deletes macOS or any partition** (reclaim the disk yourself in Disk Management). If the EFI is shared with Windows, only OpenCore is removed. It is not part of the normal flow - run it only when you want out.

## After the EFI is built

1. Read `BUILD_INFO.txt`: it lists what is left to do for your hardware.
2. Replace placeholder serial numbers with ones from `macserial` / GenSMBIOS if the notes say so, and never publish them.
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

- Test the Windows `.bat` on more machines (it is new and was written without a Windows test machine).
- Bluetooth: CSR8510 (`0a12:0001`) "V5.0" dongles have no macOS 12+ driver. The tool adds only BlueToolFixup + the NVRAM keys (`bluetoothExternalDongleFailed`, `bluetoothInternalControllerInfo`) so you can try it, and tells you to buy a Broadcom BCM20702 dongle (`0a5c:21e8`, ASUS USB-BT400 `0b05:17cb`) for reliable Bluetooth.
- Serial numbers: every run asks `macserial` for 30 serials and picks one at random, so nobody shares a serial. Check it at https://checkcoverage.apple.com (it should NOT be valid). If Apple says "this Mac was used to create many Apple Accounts", the serial is burned: create the account on a phone and sign in, or build again for a new serial. Nothing can promise Apple will accept a serial.
- AMD CPU support, more Mac models, and a better Wi-Fi/Bluetooth chip database for notebooks.
- Test reports from real hardware.

## Disclaimer

This project is not affiliated with Apple or the OpenCore project. macOS is licensed by Apple for use on Apple-branded hardware. You are responsible for complying with the licenses and laws that apply to you. Never publish your own serial numbers, MLB or ROM values.

## License

MIT - see [LICENSE](LICENSE).
