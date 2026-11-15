@echo off
title Read PC hardware (read-only)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $i=$s.LastIndexOf('#PS_START'); iex $s.Substring($i)"
echo.
pause
exit /b
#PS_START
$ErrorActionPreference = 'SilentlyContinue'
$out = Join-Path ([Environment]::GetFolderPath('Desktop')) 'hardware_report.txt'
$L = New-Object System.Collections.Generic.List[string]
function Add-Line($t) { $L.Add($t); Write-Host $t }
function Section($t) { Add-Line ''; Add-Line ('=== ' + $t + ' ===') }

Add-Line 'HARDWARE REPORT (read-only - nothing was changed on this PC)'
Add-Line ('Date: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))

Section 'CPU'
Get-CimInstance Win32_Processor | ForEach-Object {
  Add-Line ('Name: ' + $_.Name.Trim())
  Add-Line ('Cores: ' + $_.NumberOfCores + '  Threads: ' + $_.NumberOfLogicalProcessors)
}

Section 'MOTHERBOARD / BIOS'
$bb = Get-CimInstance Win32_BaseBoard
Add-Line ('Board: ' + $bb.Manufacturer + ' ' + $bb.Product)
$bi = Get-CimInstance Win32_BIOS
Add-Line ('BIOS: ' + $bi.Manufacturer + ' ' + $bi.SMBIOSBIOSVersion)
try { Add-Line ('UEFI / Secure Boot on: ' + (Confirm-SecureBootUEFI)) } catch { Add-Line 'UEFI/Secure Boot: could not read (legacy BIOS?)' }

Section 'MEMORY'
$mem = Get-CimInstance Win32_PhysicalMemory
Add-Line ('Total: ' + [math]::Round(($mem | Measure-Object Capacity -Sum).Sum / 1GB) + ' GB')
$mem | ForEach-Object { Add-Line ('  Module: ' + [math]::Round($_.Capacity/1GB) + ' GB @ ' + $_.Speed + ' MHz ' + $_.Manufacturer) }

Section 'GPU'
Get-CimInstance Win32_VideoController | ForEach-Object {
  Add-Line ('Name: ' + $_.Name)
  Add-Line ('  PNP: ' + $_.PNPDeviceID)
}

Section 'NETWORK (physical adapters)'
Get-CimInstance Win32_NetworkAdapter | Where-Object { $_.PhysicalAdapter -eq $true } | ForEach-Object {
  Add-Line ('Name: ' + $_.Name)
  Add-Line ('  PNP: ' + $_.PNPDeviceID)
}

Section 'AUDIO'
Get-CimInstance Win32_SoundDevice | ForEach-Object {
  Add-Line ('Name: ' + $_.Name + '  Vendor: ' + $_.Manufacturer)
  Add-Line ('  PNP: ' + $_.PNPDeviceID)
}
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'HDAUDIO\FUNC_01*' } | ForEach-Object { Add-Line ('HDA codec: ' + $_.InstanceId) }

Section 'BLUETOOTH'
$bt = Get-PnpDevice -PresentOnly | Where-Object { $_.Class -eq 'Bluetooth' -or $_.FriendlyName -like '*Bluetooth*' }
if (-not $bt) { Add-Line 'No Bluetooth device found (plug the adapter in before running).' }
$bt | ForEach-Object { Add-Line ('Name: ' + $_.FriendlyName); Add-Line ('  ID: ' + $_.InstanceId) }

Section 'DRIVES'
Get-PhysicalDisk | ForEach-Object { Add-Line ($_.FriendlyName + '  ' + [math]::Round($_.Size/1GB) + ' GB  ' + $_.MediaType + '  ' + $_.BusType) }

Section 'USB CONTROLLERS'
Get-PnpDevice -PresentOnly -Class USB | Where-Object { $_.FriendlyName -match 'Host Controller|xHCI|EHCI' } | ForEach-Object { Add-Line ($_.FriendlyName + '  ' + $_.InstanceId) }

Section 'AUTOMATIC SUGGESTIONS (double-check before using)'
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$gpu = (Get-CimInstance Win32_VideoController | Select-Object -First 1).Name
$nic = (Get-CimInstance Win32_NetworkAdapter | Where-Object { $_.PhysicalAdapter -eq $true } | Select-Object -First 1).PNPDeviceID
$btid = ($bt | Select-Object -First 1).InstanceId

if ($cpu -match 'E3-12\d\d v3|i[3579]-4\d{3}|Haswell') { Add-Line 'CPU: Haswell family -> suggested SMBIOS MacPro7,1 (or iMac14,x/iMac15,1); needs SSDT-PLUG and SSDT-EC-USBX' }
elseif ($cpu -match 'i[3579]-[6-9]\d{3}|i[3579]-1\d{4}') { Add-Line 'CPU: Skylake or newer -> follow the matching Dortania guide' }
else { Add-Line ('CPU: ' + $cpu + ' -> not recognised by this script; check the Dortania guide') }

if ($gpu -match 'GT ?7[0-9]{2}|GTX ?6[0-9]{2}|GT ?6[0-9]{2}') { Add-Line 'NVIDIA Kepler GPU: Apple dropped the drivers. Needs OpenCore Legacy Patcher root patching; experimental on the newest macOS.' }
elseif ($gpu -match 'RX ?(4|5)[0-9]{2}|RX ?5[0-9]{2}0|Radeon') { Add-Line 'AMD GPU: usually works with WhateverGreen (no patching).' }
elseif ($gpu -match 'Intel') { Add-Line 'Intel iGPU: use WhateverGreen + device properties (platform-id) for your generation.' }
else { Add-Line ('GPU: ' + $gpu + ' -> check compatibility') }

if ($nic -match 'VEN_10EC&DEV_8168|VEN_10EC&DEV_8111') { Add-Line 'Realtek RTL8111/8168 Ethernet -> RealtekRTL8111 kext' }
elseif ($nic -match 'VEN_8086') { Add-Line 'Intel Ethernet -> IntelMausi kext (or igc/i225 kext depending on the model)' }
elseif ($nic -match 'VEN_10EC&DEV_8125') { Add-Line 'Realtek 2.5G (RTL8125) Ethernet -> LucyRTL8125Ethernet kext' }
else { Add-Line ('Ethernet: ' + $nic + ' -> check which kext applies') }

if ($btid -match 'VID_0A5C') { Add-Line 'Broadcom Bluetooth -> BlueToolFixup + BrcmPatchRAM + BrcmFirmwareData (usually works well)' }
elseif ($btid -match 'VID_8087') { Add-Line 'Intel Bluetooth -> IntelBluetoothFirmware + BlueToolFixup (depends on the model)' }
elseif ($btid -match 'VID_0BDA') { Add-Line 'Realtek Bluetooth -> usually does NOT work on macOS' }
elseif ($btid -match 'VID_0A12') { Add-Line 'CSR Bluetooth -> generic adapters; often do not work on macOS' }
elseif ($btid) { Add-Line ('Bluetooth: ' + $btid + ' -> open an issue with this ID') }

Add-Line ''
Add-Line 'Done.'
$L | Out-File -FilePath $out -Encoding UTF8
Write-Host ''
Write-Host ('Report saved to: ' + $out) -ForegroundColor Green
