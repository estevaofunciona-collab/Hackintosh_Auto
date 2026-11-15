@echo off
title Hackintosh_Auto - builds an OpenCore EFI (with OpenCanopy)
echo.
echo Hackintosh_Auto v0.1 (experimental)
echo Starting... internet connection required. This can take several minutes.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $i=$s.LastIndexOf('#PS_START'); iex $s.Substring($i)"
echo.
pause
exit /b
#PS_START
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$out = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Hackintosh_Auto_Output'
$tmp = Join-Path $out '_temp'
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
Write-Host "Output folder: $out" -ForegroundColor Cyan

function Get-Latest($repo, $pattern, $label) {
    Write-Host "Downloading $label ..." -ForegroundColor Yellow
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers @{ 'User-Agent' = 'hackintosh-auto' }
        $asset = $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
        if (-not $asset) { throw "asset not found in $repo" }
        $zip = Join-Path $tmp $asset.name
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
        $dir = Join-Path $tmp ($label -replace '[^A-Za-z0-9]', '')
        Expand-Archive -Path $zip -DestinationPath $dir -Force
        Write-Host ("   OK: " + $asset.name) -ForegroundColor Green
        return $dir
    } catch {
        Write-Host ("   WARNING: failed to get $label - " + $_.Exception.Message) -ForegroundColor Red
        return $null
    }
}

function Copy-Kext($srcDir, $kextName, $dest) {
    if (-not $srcDir) { return }
    $k = Get-ChildItem -Path $srcDir -Recurse -Directory -Filter $kextName |
         Where-Object { $_.FullName -notmatch 'Debug|dSYM' } | Select-Object -First 1
    if ($k) { Copy-Item $k.FullName -Destination $dest -Recurse -Force }
    else { Write-Host "   WARNING: $kextName not found" -ForegroundColor Red }
}

# ---------- OpenCore ----------
$oc = Get-Latest 'acidanthera/OpenCorePkg' '^OpenCore-.*-RELEASE\.zip$' 'OpenCore'
$efi = Join-Path $out 'EFI'
Copy-Item (Join-Path $oc 'X64\EFI') -Destination $out -Recurse -Force

# Keep only the drivers we need (OpenCanopy.efi comes from the SAME zip, so versions always match)
$drv = Join-Path $efi 'OC\Drivers'
Get-ChildItem $drv -File | Where-Object { $_.Name -notin 'OpenRuntime.efi','OpenCanopy.efi' } | Remove-Item -Force
$tools = Join-Path $efi 'OC\Tools'
Get-ChildItem $tools -File | Where-Object { $_.Name -ne 'OpenShell.efi' } | Remove-Item -Force

# HfsPlus.efi (needed to read the installer / recovery)
Write-Host "Downloading HfsPlus.efi ..." -ForegroundColor Yellow
Invoke-WebRequest -Uri 'https://github.com/acidanthera/OcBinaryData/raw/master/Drivers/HfsPlus.efi' -OutFile (Join-Path $drv 'HfsPlus.efi') -UseBasicParsing

# Base config.plist (Sample.plist) - must be edited afterwards
Copy-Item (Join-Path $oc 'Docs\Sample.plist') (Join-Path $efi 'OC\config.plist') -Force

# ---------- Graphical boot menu (OpenCanopy) + mouse ----------
$cfgPath = Join-Path $efi 'OC\config.plist'
$t = [IO.File]::ReadAllText($cfgPath)
function Enable-Driver($text, $name) {
    $pat = '(<key>Enabled</key>\s*)<false/>((?:\s*<key>(?:HideVerbose|LoadEarly)</key>\s*<(?:true|false)/>)*\s*<key>Path</key>\s*<string>' + [regex]::Escape($name) + '</string>)'
    return [regex]::Replace($text, $pat, '${1}<true/>${2}')
}
$t = Enable-Driver $t 'OpenCanopy.efi'
$t = Enable-Driver $t 'OpenRuntime.efi'
$t = Enable-Driver $t 'HfsPlus.efi'
$t = [regex]::Replace($t, '(<key>PickerMode</key>\s*<string>)[^<]*(</string>)', '${1}External${2}')
$t = [regex]::Replace($t, '(<key>PointerSupport</key>\s*)<false/>', '${1}<true/>')
$t = [regex]::Replace($t, '(<key>PointerSupportMode</key>\s*)<string>[^<]*</string>', '${1}<string>ASUS</string>')
[IO.File]::WriteAllText($cfgPath, $t)
if (-not (Test-Path (Join-Path $drv 'OpenCanopy.efi'))) { Write-Host 'WARNING: OpenCanopy.efi was not in the zip' -ForegroundColor Red }
if (-not (Test-Path (Join-Path $efi 'OC\Resources'))) { Write-Host 'WARNING: OC\Resources folder was not in the zip' -ForegroundColor Red }
else { Write-Host 'Graphical boot menu (OpenCanopy) + mouse configured.' -ForegroundColor Green }

# ---------- Kexts ----------
$kx = Join-Path $efi 'OC\Kexts'
Get-ChildItem $kx -Force | Remove-Item -Recurse -Force

$d = Get-Latest 'acidanthera/Lilu' '^Lilu-.*-RELEASE\.zip$' 'Lilu'
Copy-Kext $d 'Lilu.kext' $kx

$d = Get-Latest 'acidanthera/VirtualSMC' '^VirtualSMC-.*-RELEASE\.zip$' 'VirtualSMC'
foreach ($n in 'VirtualSMC.kext','SMCProcessor.kext','SMCSuperIO.kext') { Copy-Kext $d $n $kx }

$d = Get-Latest 'acidanthera/WhateverGreen' '^WhateverGreen-.*-RELEASE\.zip$' 'WhateverGreen'
Copy-Kext $d 'WhateverGreen.kext' $kx

$d = Get-Latest 'acidanthera/AppleALC' '^AppleALC-.*-RELEASE\.zip$' 'AppleALC'
Copy-Kext $d 'AppleALC.kext' $kx

# Ethernet: both are downloaded - delete the one that does NOT match your board
$d = Get-Latest 'acidanthera/IntelMausi' '^IntelMausi-.*-RELEASE\.zip$' 'IntelMausi'
Copy-Kext $d 'IntelMausi.kext' $kx
$d = Get-Latest 'Mieze/RTL8111_driver_for_OS_X' '^RealtekRTL8111-.*\.zip$' 'RealtekRTL8111'
Copy-Kext $d 'RealtekRTL8111.kext' $kx

# NVMe SSD (delete if you have no NVMe drive)
$d = Get-Latest 'acidanthera/NVMeFix' '^NVMeFix-.*-RELEASE\.zip$' 'NVMeFix'
Copy-Kext $d 'NVMeFix.kext' $kx

# USB mapping tool kext (UTBMap.kext is generated by the USBToolBox tool, not downloaded)
$d = Get-Latest 'USBToolBox/kext' '^USBToolBox-.*RELEASE\.zip$' 'USBToolBoxKext'
Copy-Kext $d 'USBToolBox.kext' $kx

# ---------- SSDTs (Haswell desktop example) ----------
$acpi = Join-Path $efi 'OC\ACPI'
Get-ChildItem $acpi -Force | Remove-Item -Recurse -Force
$ssdtBase = 'https://raw.githubusercontent.com/dortania/Getting-Started-With-ACPI/master/extra-files/compiled/'
foreach ($f in 'SSDT-PLUG-DRTNIA.aml','SSDT-EC-USBX-DESKTOP.aml') {
    try {
        Write-Host "Downloading $f ..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri ($ssdtBase + $f) -OutFile (Join-Path $acpi $f) -UseBasicParsing
    } catch {
        Write-Host "   WARNING: failed $f - download it manually from dortania.github.io/Getting-Started-With-ACPI" -ForegroundColor Red
    }
}

# ---------- macrecovery (macOS installer) ----------
$mr = Join-Path $out 'macrecovery'
Copy-Item (Join-Path $oc 'Utilities\macrecovery') -Destination $mr -Recurse -Force

$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py' }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = 'python' }

if ($py) {
    Write-Host "Downloading the macOS Ventura recovery image (this can take a while) ..." -ForegroundColor Yellow
    Push-Location $mr
    try {
        & $py macrecovery.py -b Mac-4B682C642B45593E -m 00000000000000000 download
    } catch {
        Write-Host "   WARNING: macrecovery failed. Run it manually later." -ForegroundColor Red
    }
    Pop-Location
    # macrecovery.py creates com.apple.recovery.boot (BaseSystem.dmg + chunklist). Move it next to the EFI folder.
    $rb = Join-Path $mr 'com.apple.recovery.boot'
    if (Test-Path (Join-Path $rb 'BaseSystem.dmg')) {
        Move-Item $rb (Join-Path $out 'com.apple.recovery.boot') -Force
        Write-Host "com.apple.recovery.boot folder is ready in: $out" -ForegroundColor Green
    } else {
        Write-Host "WARNING: the installer download did not finish (no BaseSystem.dmg). Re-run the macrecovery step." -ForegroundColor Red
    }
} else {
    Write-Host "Python not found. Install it from python.org, then run inside the macrecovery folder:" -ForegroundColor Red
    Write-Host "   python macrecovery.py -b Mac-4B682C642B45593E -m 00000000000000000 download" -ForegroundColor Red
}

Remove-Item $tmp -Recurse -Force

Write-Host ""
Write-Host "DONE. Folder: $out" -ForegroundColor Green
Write-Host "USB drive (FAT32, GUID): copy BOTH the EFI folder and the com.apple.recovery.boot folder to the ROOT of the drive." -ForegroundColor Cyan
Write-Host "Still to do: edit config.plist (ProperTree/OCAT), set SMBIOS + serial, map USB (generates UTBMap.kext), keep only the right ethernet kext." -ForegroundColor Cyan
Start-Process explorer.exe $out
