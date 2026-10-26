$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskNode = Join-Path $taskRoot 'data\runtime\node_modules\node\bin\node.exe'
$taskLogs = Join-Path $taskRoot 'data\local-run'
if (!(Test-Path -LiteralPath $taskNode)) { throw 'Project Node runtime is missing.' }
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskContainer = docker inspect --format '{{.State.Running}}' yibiao-web-postgres 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Database container yibiao-web-postgres is missing.' }
if ($taskContainer -ne 'true') {
    docker start yibiao-web-postgres | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not start project database.' }
}
$env:PATH = (Split-Path -Parent $taskNode) + ';' + $env:PATH
foreach ($taskPort in @(3001, 5174)) {
    $taskListeners = @(Get-NetTCPConnection -State Listen -LocalPort $taskPort -ErrorAction SilentlyContinue)
    if ($taskListeners.Count) {
        foreach ($taskListener in $taskListeners) {
            $taskProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $taskListener.OwningProcess)
            if (!$taskProcess -or $taskProcess.CommandLine.IndexOf($taskRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
                throw "Port $taskPort is occupied by another application. No process was stopped."
            }
        }
        continue
    }
    if ($taskPort -eq 3001) {
        $taskCli = Join-Path $taskRoot 'server\node_modules\tsx\dist\cli.mjs'
        $taskArgs = '"' + $taskCli + '" watch src/index.ts'
        $taskWorkingDir = Join-Path $taskRoot 'server'
        $taskLabel = 'backend'
    } else {
        $taskCli = Join-Path $taskRoot 'client\node_modules\vite\bin\vite.js'
        $taskArgs = '"' + $taskCli + '" --host 127.0.0.1 --port 5174 --strictPort'
        $taskWorkingDir = Join-Path $taskRoot 'client'
        $taskLabel = 'frontend'
    }
    $taskChild = Start-Process -FilePath $taskNode -ArgumentList $taskArgs -WorkingDirectory $taskWorkingDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskLogs ($taskLabel + '.out.log')) -RedirectStandardError (Join-Path $taskLogs ($taskLabel + '.err.log')) -PassThru
    [IO.File]::WriteAllText((Join-Path $taskLogs ($taskLabel + '.pid')), [string]$taskChild.Id)
}
$taskReady = $false
for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:3001/api/system-settings' -TimeoutSec 2
        $taskPage = Invoke-WebRequest -Uri 'http://127.0.0.1:5174/' -UseBasicParsing -TimeoutSec 2
        if ($taskPage.StatusCode -eq 200) { $taskReady = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (!$taskReady) { throw "Startup did not become ready. Check logs: $taskLogs" }
Write-Output 'Web ready: http://127.0.0.1:5174/'
Write-Output 'Backend: 127.0.0.1:3001; database: 127.0.0.1:55432; desktop remains on 5173.'