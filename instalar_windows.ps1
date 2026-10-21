# Registra 3 tareas en el Programador de tareas de Windows:
#   AulasBot-Bot        bot.py siempre corriendo (arranca al iniciar sesion, se reinicia solo si falla)
#   AulasBot-Ingesta    06:30 todos los dias: baja el PDF, reconstruye aulas.db, backup
#   AulasBot-Notificar  07:00 todos los dias: manda los avisos
# Uso: abrir PowerShell, pararse en la carpeta del proyecto y ejecutar:  .\instalar_windows.ps1
$ErrorActionPreference = "Stop"
$dir = (Get-Location).Path
if (-not (Test-Path (Join-Path $dir "bot.py"))) { throw "Ejecutalo desde la carpeta que contiene bot.py" }
if (-not (Test-Path (Join-Path $dir ".env"))) { throw "Falta el archivo .env (copia .env.example y completalo)" }

$py = (& py -c "import sys; print(sys.executable)").Trim()
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { throw "No encuentro pythonw.exe junto a $py" }

$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

function Registrar($nombre, $argumentos, $disparador) {
    $accion = New-ScheduledTaskAction -Execute $pyw -Argument $argumentos -WorkingDirectory $dir
    Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador -Settings $config -Force | Out-Null
    Write-Host "OK: $nombre"
}

Registrar "AulasBot-Bot" "bot.py" (New-ScheduledTaskTrigger -AtLogOn)
Registrar "AulasBot-Ingesta" "diario.py ingesta" (New-ScheduledTaskTrigger -Daily -At "06:30")
Registrar "AulasBot-Notificar" "diario.py notificar" (New-ScheduledTaskTrigger -Daily -At "07:00")

Start-ScheduledTask -TaskName "AulasBot-Bot"
Write-Host "Listo. El bot ya esta corriendo. Logs en la carpeta logs\"
