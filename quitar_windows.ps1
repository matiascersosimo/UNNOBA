# Detiene y elimina las tareas del bot (por ejemplo, antes de mudarlo a otra computadora).
foreach ($t in "AulasBot-Bot", "AulasBot-Ingesta", "AulasBot-Notificar") {
    Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Eliminada: $t"
}
