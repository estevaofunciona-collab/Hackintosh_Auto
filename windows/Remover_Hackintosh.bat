@echo off
title Hackintosh_Auto - Remover o OpenCore (Hackintosh) deste PC
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $a=$s.IndexOf([string][char]10+'#PS_'+'START'); iex $s.Substring($a)"
echo.
pause
exit /b
#PS_START
$ErrorActionPreference = 'Stop'
$Desktop = [Environment]::GetFolderPath('Desktop')
$log = Join-Path $Desktop 'remover_hackintosh_log.txt'
Start-Transcript -Path $log -Force | Out-Null
try {
Write-Host ''
Write-Host '=== Hackintosh_Auto: remover o OpenCore (Hackintosh) deste PC ===' -ForegroundColor Cyan
Write-Host 'Isto tira o OpenCore da particao EFI. NAO apaga o macOS, nem o Windows, nem seus arquivos.'
Write-Host 'Antes de apagar, faz uma COPIA da pasta EFI na sua Area de Trabalho.'
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
if ($found.Count -eq 0) { Write-Host 'Nao achei OpenCore em nenhuma particao EFI. Nao mexi em nada.' -ForegroundColor Yellow; return }

Write-Host 'OpenCore encontrado em:' -ForegroundColor Cyan
for ($i = 0; $i -lt $found.Count; $i++) {
  $f = $found[$i]
  $extra = ''
  if ($f.Shared) { $extra = '  (a EFI e compartilhada com o Windows; so o OpenCore sera removido)' }
  Write-Host ('  ' + ($i + 1) + ') Disco ' + $f.Disk + ': ' + $f.Name + ' - ' + $f.SizeGB + ' GB' + $extra)
}
$pick = Read-Host 'Qual remover? Digite o numero (ou Enter para cancelar)'
$n = 0
if (-not [int]::TryParse($pick, [ref]$n) -or $n -lt 1 -or $n -gt $found.Count) { Write-Host 'Cancelado. Nao mexi em nada.'; return }
$t = $found[$n - 1]
Write-Host ''
Write-Host ('Vai remover o OpenCore do Disco ' + $t.Disk + ' (' + $t.Name + ').') -ForegroundColor Yellow
Write-Host 'O macOS desse disco continua la, mas deixa de dar boot. Uma copia da EFI sera salva antes.'
$ok = Read-Host 'Para continuar digite REMOVER (em maiusculas)'
if ($ok -cne 'REMOVER') { Write-Host 'Cancelado. Nao mexi em nada.'; return }

$letter = $null
foreach ($l in @('Z','Y','X','W')) { if (-not (Test-Path ($l + ':\'))) { $letter = $l; break } }
Add-PartitionAccessPath -DiskNumber $t.Disk -PartitionNumber $t.Part -AccessPath ($letter + ':\')
try {
  $efi = $letter + ':\EFI'
  $bk = Join-Path (Join-Path $Desktop 'Backup EFI') ('EFI-antes-de-remover-' + (Get-Date -Format 'yyyyMMdd-HHmm'))
  New-Item -ItemType Directory -Force -Path $bk | Out-Null
  Copy-Item $efi $bk -Recurse -Force
  $a1 = @(Get-ChildItem $efi -Recurse -File -Force).Count
  $a2 = @(Get-ChildItem (Join-Path $bk 'EFI') -Recurse -File -Force).Count
  if ($a1 -ne $a2 -or $a1 -eq 0) { throw ('Backup nao bateu (' + $a1 + ' x ' + $a2 + ' arquivos). Nao apaguei nada.') }
  Write-Host ('Backup feito (' + $a1 + ' arquivos): ' + $bk) -ForegroundColor Green

  Remove-Item ($efi + '\OC') -Recurse -Force
  Write-Host 'Removido: EFI\OC (OpenCore)' -ForegroundColor Green
  if (-not $t.Shared -and (Test-Path ($efi + '\BOOT'))) {
    Remove-Item ($efi + '\BOOT') -Recurse -Force
    Write-Host 'Removido: EFI\BOOT' -ForegroundColor Green
  } elseif (Test-Path ($efi + '\BOOT')) {
    Write-Host 'EFI\BOOT foi mantida porque a EFI e compartilhada com o Windows.' -ForegroundColor Yellow
  }
} finally {
  Remove-PartitionAccessPath -DiskNumber $t.Disk -PartitionNumber $t.Part -AccessPath ($letter + ':\') -ErrorAction SilentlyContinue
}

# entradas de boot (NVRAM) chamadas "OpenCore"
try {
  $txt = (& bcdedit /enum firmware) -join "`n"
  foreach ($blk in ($txt -split "`n\s*`n")) {
    if ($blk -match 'OpenCore') {
      $m = [regex]::Match($blk, '\{[0-9a-fA-F-]{36}\}')
      if ($m.Success) {
        & bcdedit /delete $m.Value | Out-Null
        Write-Host ('Removida a entrada de boot "OpenCore" ' + $m.Value) -ForegroundColor Green
      }
    }
  }
} catch { Write-Host 'Nao consegui limpar as entradas de boot (sem problema, ajuste na BIOS).' -ForegroundColor Yellow }

Write-Host ''
Write-Host 'PRONTO. O OpenCore foi tirado.' -ForegroundColor Green
Write-Host 'Entre na BIOS (Del/F2) e deixe o Windows Boot Manager em primeiro na ordem de boot.'
Write-Host 'Se quiser o espaco do disco do Mac de volta: Gerenciamento de Disco -> apague as particoes do Mac'
Write-Host '(isso e manual, de proposito: o script nunca apaga o macOS sozinho).'
Write-Host ('Backup da EFI: ' + $bk)
} catch { Write-Host ('ERRO: ' + $_.Exception.Message) -ForegroundColor Red }
finally { Stop-Transcript | Out-Null }
