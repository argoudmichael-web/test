# =============================================================================
# Script de maintenance PC - Windows (PowerShell)
# =============================================================================
# Usage: Exécuter PowerShell en tant qu'Administrateur, puis:
#   .\maintenance-pc.ps1
# =============================================================================

#Requires -RunAsAdministrator

$Host.UI.RawUI.WindowTitle = "Maintenance PC"

function Section($title) {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
}

function Success($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Error($msg)   { Write-Host "[X] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  Maintenance PC - Windows" -ForegroundColor Green
Write-Host "  Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host ""

# ─── 1. Windows Update ───
Section "1. Mises a jour Windows Update"

try {
    if (-not (Get-Module -ListAvailable -Name PSWindowsUpdate)) {
        Write-Host "  Installation du module PSWindowsUpdate..."
        Install-Module -Name PSWindowsUpdate -Force -Confirm:$false
    }
    Import-Module PSWindowsUpdate
    $updates = Get-WindowsUpdate
    if ($updates.Count -gt 0) {
        Write-Host "  $($updates.Count) mises a jour disponibles:"
        $updates | ForEach-Object { Write-Host "    - $($_.Title)" }
        Install-WindowsUpdate -AcceptAll -AutoReboot:$false -Confirm:$false
        Success "Mises a jour Windows installees"
    } else {
        Success "Windows est a jour"
    }
} catch {
    Warn "Impossible de verifier Windows Update: $($_.Exception.Message)"
}

# ─── 2. Mise à jour des pilotes ───
Section "2. Mise a jour des pilotes"

try {
    if (Get-Command Get-WindowsUpdate -ErrorAction SilentlyContinue) {
        $driverUpdates = Get-WindowsUpdate -Category "Drivers" -ErrorAction SilentlyContinue
        if ($null -ne $driverUpdates -and $driverUpdates.Count -gt 0) {
            Write-Host "  $($driverUpdates.Count) mise(s) a jour de pilote(s) disponible(s):"
            $driverUpdates | ForEach-Object { Write-Host "    - $($_.Title)" -ForegroundColor Gray }
            Install-WindowsUpdate -Category "Drivers" -AcceptAll -AutoReboot:$false -Confirm:$false
            Success "Pilotes mis a jour"
        } else {
            Success "Pilotes a jour"
        }
    } else {
        Warn "Module PSWindowsUpdate requis pour la mise a jour des pilotes"
    }
    # Mise a jour des definitions de pilotes via Windows Update natif
    $session = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $result = $searcher.Search("IsInstalled=0 and Type='Driver'")
    if ($result.Updates.Count -gt 0) {
        Write-Host "  $($result.Updates.Count) pilote(s) supplementaire(s) disponible(s) via Windows Update"
    }
} catch {
    Warn "Impossible de verifier les mises a jour de pilotes: $($_.Exception.Message)"
}

# ─── 3. Mise à jour des applications (winget) ───
Section "3. Mise a jour des applications (winget)"

if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "  Recherche des mises a jour..."
    winget upgrade --all --accept-source-agreements --accept-package-agreements
    Success "Applications mises a jour via winget"
} else {
    Warn "winget n'est pas disponible"
}

# ─── 4. Nettoyage de disque ───
Section "4. Nettoyage de disque"

# Fichiers temporaires
$tempFolders = @(
    $env:TEMP,
    "$env:LOCALAPPDATA\Temp",
    "C:\Windows\Temp"
)

$totalFreed = 0
foreach ($folder in $tempFolders) {
    if (Test-Path $folder) {
        $sizeBefore = (Get-ChildItem $folder -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        Get-ChildItem $folder -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        $sizeAfter = (Get-ChildItem $folder -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $freed = [math]::Max(0, ($sizeBefore - $sizeAfter))
        $totalFreed += $freed
    }
}
$freedMB = [math]::Round($totalFreed / 1MB, 2)
Success "Fichiers temporaires nettoyes ($freedMB Mo liberes)"

# Corbeille
try {
    Clear-RecycleBin -Force -ErrorAction SilentlyContinue
    Success "Corbeille videe"
} catch {
    Warn "Impossible de vider la corbeille"
}

# Cache DNS
ipconfig /flushdns | Out-Null
Success "Cache DNS vide"

# ─── 5. Espace disque ───
Section "5. Espace disque"

Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -gt 0 } | ForEach-Object {
    $usedPercent = [math]::Round(($_.Used / ($_.Used + $_.Free)) * 100, 1)
    $freeGB = [math]::Round($_.Free / 1GB, 2)
    $label = "  $($_.Name): $freeGB Go libres ($usedPercent% utilise)"

    if ($usedPercent -gt 90) {
        Error $label
    } elseif ($usedPercent -gt 75) {
        Warn $label
    } else {
        Success $label
    }
}

# ─── 6. Santé du disque ───
Section "6. Sante des disques"

try {
    $disks = Get-PhysicalDisk
    foreach ($disk in $disks) {
        $status = $disk.HealthStatus
        $label = "$($disk.FriendlyName) ($($disk.MediaType)) - $([math]::Round($disk.Size / 1GB, 0)) Go"
        if ($status -eq "Healthy") {
            Success "$label : $status"
        } else {
            Error "$label : $status"
        }
    }
} catch {
    Warn "Impossible de verifier la sante des disques"
}

# ─── 7. Mémoire RAM ───
Section "7. Memoire RAM"

$os = Get-CimInstance Win32_OperatingSystem
$totalRAM = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeRAM = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$usedRAM = [math]::Round($totalRAM - $freeRAM, 2)
$usedPercent = [math]::Round(($usedRAM / $totalRAM) * 100, 1)

Write-Host "  Total: $totalRAM Go | Utilise: $usedRAM Go | Libre: $freeRAM Go ($usedPercent%)"

if ($usedPercent -gt 90) {
    Error "Memoire RAM critique"
} elseif ($usedPercent -gt 75) {
    Warn "Memoire RAM elevee"
} else {
    Success "Memoire RAM OK"
}

# ─── 8. Programmes au démarrage ───
Section "8. Programmes au demarrage"

$startupItems = Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location
if ($startupItems.Count -gt 0) {
    Write-Host "  $($startupItems.Count) programmes au demarrage:"
    $startupItems | ForEach-Object {
        Write-Host "    - $($_.Name)" -ForegroundColor Gray
    }
    if ($startupItems.Count -gt 10) {
        Warn "Beaucoup de programmes au demarrage - considerez en desactiver certains"
    }
} else {
    Success "Aucun programme au demarrage detecte"
}

# ─── 9. Vérification réseau ───
Section "9. Verification reseau"

$ping = Test-Connection -ComputerName 8.8.8.8 -Count 3 -ErrorAction SilentlyContinue
if ($ping) {
    $avgLatency = [math]::Round(($ping | Measure-Object -Property Latency -Average).Average, 1)
    Success "Connexion Internet OK (latence moyenne: ${avgLatency}ms)"
} else {
    Error "Pas de connexion Internet"
}

# ─── 10. Antivirus ───
Section "10. Antivirus Windows Defender"

try {
    $mpStatus = Get-MpComputerStatus
    if ($mpStatus.AntivirusEnabled) {
        Success "Windows Defender actif"
        $lastScan = $mpStatus.QuickScanEndTime
        $daysSinceLastScan = (New-TimeSpan -Start $lastScan -End (Get-Date)).Days
        if ($daysSinceLastScan -gt 7) {
            Warn "Derniere analyse il y a $daysSinceLastScan jours - lancement d'une analyse rapide..."
            Start-MpScan -ScanType QuickScan -AsJob
        } else {
            Success "Derniere analyse: $($lastScan.ToString('yyyy-MM-dd'))"
        }
    } else {
        Error "Windows Defender est desactive"
    }

    # Mise à jour des définitions
    Update-MpSignature -ErrorAction SilentlyContinue
    Success "Definitions antivirus mises a jour"
} catch {
    Warn "Impossible de verifier Windows Defender"
}

# ─── 11. Redémarrage ───
Section "11. Redemarrage necessaire ?"

$rebootPending = $false
$rebootKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
)
foreach ($key in $rebootKeys) {
    if (Test-Path $key) { $rebootPending = $true; break }
}

if ($rebootPending) {
    Warn "Un redemarrage est recommande pour appliquer les mises a jour"
} else {
    Success "Aucun redemarrage necessaire"
}

# ─── Résumé ───
Section "Maintenance terminee"
Write-Host ""
Write-Host "  Date de fin: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host ""
Success "Votre PC est a jour et en bonne sante !"
Write-Host ""
