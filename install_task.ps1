<#
.SYNOPSIS
    Enregistre les tâches planifiées de lolbuilds (prefetch nocturne + interface).
    Le prefetch planifié ne fait rien tant que [prefetch] nightly = false dans config.toml.

.EXAMPLE
    .\install_task.ps1                      # prefetch chaque jour à 4h
    .\install_task.ps1 -WithApp             # + interface lolbuilds à l'ouverture de session (recommandé)
    .\install_task.ps1 -Uninstall           # supprime les tâches
#>
param(
    [string]$At = "04:00",
    [switch]$WithApp,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$Pythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$PrefetchTask = "lolbuilds-prefetch"
$OldChampSelectTask = "lolbuilds-champselect"  # ancienne version sans interface : supprimée si présente
$AppTask = "lolbuilds-app"

if ($Uninstall) {
    foreach ($name in @($PrefetchTask, $OldChampSelectTask, $AppTask)) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "Tâche supprimée : $name"
        }
    }
    return
}

if (-not (Test-Path $Pythonw)) {
    throw "pythonw introuvable ($Pythonw). Créez d'abord le venv : py -3.13 -m venv .venv ; .venv\Scripts\pip install -e ."
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

# --- Prefetch quotidien : -StartWhenAvailable rattrape l'exécution si le PC était éteint à l'heure prévue.
$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-m lolbuilds.prefetch --scheduled" -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $PrefetchTask -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Mise à jour nocturne du cache de builds LoL" -Force | Out-Null
Write-Host "Tâche enregistrée : $PrefetchTask (tous les jours à $At, rattrapage au démarrage)"

# --- Interface au démarrage de session (optionnel).
if ($WithApp) {
    $action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-m lolbuilds.app" -WorkingDirectory $ProjectDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $AppTask -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Description "Interface lolbuilds (builds en champ select)" -Force | Out-Null
    Write-Host "Tâche enregistrée : $AppTask (à l'ouverture de session)"
}

# --- Ancienne tâche « champ select sans interface » : retirée, tout passe par l'interface.
if (Get-ScheduledTask -TaskName $OldChampSelectTask -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $OldChampSelectTask -Confirm:$false
    Write-Host "Ancienne tâche supprimée : $OldChampSelectTask"
}
