$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ScriptDir "data\server.log"
$Python = Join-Path $ScriptDir ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
Set-Location $ScriptDir

& $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 | Out-File -Append -FilePath $LogFile -Encoding utf8
