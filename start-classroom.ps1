$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    throw '请先按 README.md 初始化本项目独立的 .venv 虚拟环境。'
}
$taskUrl = 'http://127.0.0.1:8766'
$taskReady = $false
try {
    $taskMeta = Invoke-RestMethod "$taskUrl/api/meta" -TimeoutSec 2
    $taskReady = $taskMeta.application -eq 'pku-classroom'
} catch {}
if (!$taskReady) {
    $taskData = if ($env:PKU_CLASSROOM_DATA_DIR) { $env:PKU_CLASSROOM_DATA_DIR } else { Join-Path $PSScriptRoot 'data' }
    $null = New-Item -ItemType Directory -Path $taskData -Force
    $taskLaunch = @{
        FilePath = $taskPython
        ArgumentList = @('-u','classroom.py','serve')
        WorkingDirectory = $PSScriptRoot
        WindowStyle = 'Hidden'
        PassThru = $true
        RedirectStandardOutput = (Join-Path $taskData 'classroom-server.log')
        RedirectStandardError = (Join-Path $taskData 'classroom-server-error.log')
    }
    $taskServer = Start-Process @taskLaunch
    $taskServer.Id | Set-Content -LiteralPath (Join-Path $taskData 'classroom-server.pid')
    for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
        try {
            $taskMeta = Invoke-RestMethod "$taskUrl/api/meta" -TimeoutSec 2
            if ($taskMeta.application -eq 'pku-classroom') { $taskReady = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 300
    }
}
if (!$taskReady) { throw '教室服务未启动，请查看 data/classroom-server-error.log 并检查数据库与端口。' }
Start-Process $taskUrl
