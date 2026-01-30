# dgmt Task Scheduler Setup
# Run this in PowerShell (non-admin is fine for user-level task)

$InstallDir = "$env:USERPROFILE\.dgmt"
$PythonPath = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) {
    $PythonPath = (Get-Command python).Source -replace 'python\.exe$', 'pythonw.exe'
}

$TaskName = "dgmt"
$Description = "Dylan's Google Drive Management Tool - Syncthing health monitor and rclone backup"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: run pythonw with dgmt.py
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$InstallDir\dgmt.py`"" `
    -WorkingDirectory $InstallDir

# Trigger: at logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: restart on failure, don't stop on idle, run indefinitely
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit 0  # Run indefinitely

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $Description `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Limited

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " dgmt scheduled task created!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Task: $TaskName"
Write-Host "Runs: At logon, restarts up to 3x on failure"
Write-Host ""
Write-Host "Commands:"
Write-Host "  Start now:    schtasks /run /tn dgmt"
Write-Host "  Stop:         schtasks /end /tn dgmt"
Write-Host "  Status:       schtasks /query /tn dgmt /v /fo list"
Write-Host "  Remove:       schtasks /delete /tn dgmt /f"
Write-Host ""
Write-Host "Or use Task Scheduler GUI: taskschd.msc"
Write-Host ""
