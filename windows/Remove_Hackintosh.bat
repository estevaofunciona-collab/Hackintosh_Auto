@echo off
title Hackintosh_Auto - Remove OpenCore (Hackintosh) from this PC
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $a=$s.IndexOf([string][char]10+'#PS_'+'START'); iex $s.Substring($a)"
echo.
pause
exit /b
#PS_START
$ErrorActionPreference = 'Stop'
$Desktop = [Environment]::GetFolderPath('Desktop')
$log = Join-Path $Desktop 'remove_hackintosh_log.txt'
Start-Transcript -Path $log -Force | Out-Null
try {
Write-Host ''
Write-Host '=== Hackintosh_Auto: remove OpenCore (Hackintosh) from this PC ===' -ForegroundColor Cyan
Write-Host 'This takes OpenCore out of the EFI partition. It does NOT delete macOS, Windows or your files.'
Write-Host 'Before deleting anything it saves a COPY of the EFI folder on your Desktop.'
Write-Host ''
$efiGuid = '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
$found = @()
foreach ($p in @(Get-Partition | Where-Object { $_.GptType -eq $efiGuid })) {
  $d = Get-Disk -Number $p.DiskNumber
  $letter = $null
  foreach ($l in @('Z','Y','X','W')) { if (-not (Test-Path ($l + ':\'))) { $letter = $l; break } }
  if (-not $letter) { continue }
  Add-PartitionAccessPath -DiskNumber $p.DiskNumber -PartitionNumber $p.PartitionNumber -AccessPath ($letter + ':\')
  try {
    if (Test-Path ($letter + ':\EFI\OC\OpenCore.efi')) {
      $found += [pscustomobject]@{
        Disk = $p.DiskNumber; Part = $p.PartitionNumber; Name = $d.FriendlyName
        SizeGB = [math]::Round($d.Size / 1GB); Shared = (Test-Path ($letter + ':\EFI\Microsoft'))
      }
    }
  } finally {
    Remove-PartitionAccessPath -DiskNumber $p.DiskNumber -PartitionNumber $p.PartitionNumber -AccessPath ($letter + ':\') -ErrorAction SilentlyContinue
  }
}
if ($found.Count -eq 0) { Write-Host 'No OpenCore found on any EFI partition. Nothing was changed.' -ForegroundColor Yellow; return }

Write-Host 'OpenCore found on:' -ForegroundColor Cyan
for ($i = 0; $i -lt $found.Count; $i++) {
  $f = $found[$i]
  $extra = ''
  if ($f.Shared) { $extra = '  (EFI is shared with Windows; only OpenCore will be removed)' }
  Write-Host ('  ' + ($i + 1) + ') Disk ' + $f.Disk + ': ' + $f.Name + ' - ' + $f.SizeGB + ' GB' + $extra)
}
$pick = Read-Host 'Which one to remove? Type the number (or press Enter to cancel)'
$n = 0
if (-not [int]::TryParse($pick, [ref]$n) -or $n -lt 1 -or $n -gt $found.Count) { Write-Host 'Cancelled. Nothing was changed.'; return }
$t = $found[$n - 1]
Write-Host ''
Write-Host ('This will remove OpenCore from Disk ' + $t.Disk + ' (' + $t.Name + ').') -ForegroundColor Yellow
Write-Host 'The macOS on that disk stays there, but it will no longer boot. A copy of the EFI is saved first.'
$ok = Read-Host 'To continue type REMOVE (capital letters)'
if ($ok -cne 'REMOVE') { Write-Host 'Cancelled. Nothing was changed.'; return }

$letter = $null
foreach ($l in @('Z','Y','X','W')) { if (-not (Test-Path ($l + ':\'))) { $letter = $l; break } }
Add-PartitionAccessPath -DiskNumber $t.Disk -PartitionNumber $t.Part -AccessPath ($letter + ':\')
try {
  $efi = $letter + ':\EFI'
  $bk = Join-Path (Join-Path $Desktop 'Backup EFI') ('EFI-before-remove-' + (Get-Date -Format 'yyyyMMdd-HHmm'))
  New-Item -ItemType Directory -Force -Path $bk | Out-Null
  Copy-Item $efi $bk -Recurse -Force
  $a1 = @(Get-ChildItem $efi -Recurse -File -Force).Count
  $a2 = @(Get-ChildItem (Join-Path $bk 'EFI') -Recurse -File -Force).Count
  if ($a1 -ne $a2 -or $a1 -eq 0) { throw ('Backup does not match (' + $a1 + ' vs ' + $a2 + ' files). Nothing was deleted.') }
  Write-Host ('Backup done (' + $a1 + ' files): ' + $bk) -ForegroundColor Green

  Remove-Item ($efi + '\OC') -Recurse -Force
  Write-Host 'Removed: EFI\OC (OpenCore)' -ForegroundColor Green
  if (-not $t.Shared -and (Test-Path ($efi + '\BOOT'))) {
    Remove-Item ($efi + '\BOOT') -Recurse -Force
    Write-Host 'Removed: EFI\BOOT' -ForegroundColor Green
  } elseif (Test-Path ($efi + '\BOOT')) {
    Write-Host 'EFI\BOOT was kept because the EFI is shared with Windows.' -ForegroundColor Yellow
  }
} finally {
  Remove-PartitionAccessPath -DiskNumber $t.Disk -PartitionNumber $t.Part -AccessPath ($letter + ':\') -ErrorAction SilentlyContinue
}

# firmware boot entries (NVRAM) named "OpenCore"
try {
  $txt = (& bcdedit /enum firmware) -join "`n"
  foreach ($blk in ($txt -split "`n\s*`n")) {
    if ($blk -match 'OpenCore') {
      $m = [regex]::Match($blk, '\{[0-9a-fA-F-]{36}\}')
      if ($m.Success) {
        & bcdedit /delete $m.Value | Out-Null
        Write-Host ('Removed the "OpenCore" boot entry ' + $m.Value) -ForegroundColor Green
      }
    }
  }
} catch { Write-Host 'Could not clean the boot entries (no problem, fix the boot order in the BIOS).' -ForegroundColor Yellow }

Write-Host ''
Write-Host 'DONE. OpenCore was removed.' -ForegroundColor Green
Write-Host 'Enter the BIOS (Del/F2) and put Windows Boot Manager first in the boot order.'
Write-Host 'To get the Mac disk space back: Disk Management -> delete the Mac partitions'
Write-Host '(this is manual on purpose: the script never deletes macOS by itself).'
Write-Host ('EFI backup: ' + $bk)
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red }
finally { Stop-Transcript | Out-Null }
