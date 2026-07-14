$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ScriptDir "data\fetch.log"
$Python = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
"----- Scheduled fetch run: $Timestamp -----" | Out-File -Append -FilePath $LogFile -Encoding utf8

& $Python (Join-Path $ScriptDir "run_fetch.py") | Out-File -Append -FilePath $LogFile -Encoding utf8
"----- Exit code: $LASTEXITCODE -----" | Out-File -Append -FilePath $LogFile -Encoding utf8
