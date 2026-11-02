param(
    [ValidateSet('Setup', 'Configure', 'Start', 'Build')]
    [string]$Action = 'Start'
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Get-ProjectPython([string]$Directory) {
    $taskPython = Join-Path $PSScriptRoot "$Directory/Scripts/python.exe"
    if (!(Test-Path -LiteralPath $taskPython)) {
        if (Get-Command py.exe -ErrorAction SilentlyContinue) {
            & py.exe -3.13 -m venv $Directory
        } else {
            & python.exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required. See DEPLOYMENT.md.' }
            & python.exe -m venv $Directory
        }
        if ($LASTEXITCODE -ne 0) { throw "Unable to create $Directory." }
    }
    & $taskPython -c "import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix and sys.version_info[:2] == (3, 13) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "$Directory must use Python 3.13. See DEPLOYMENT.md." }
    return $taskPython
}

function Install-ProjectDependencies([string]$Python, [switch]$Build) {
    $taskPackages = @('-r', (Join-Path $PSScriptRoot 'requirements.txt'))
    if ($Build) { $taskPackages += 'pyinstaller==6.19.0' }
    & $Python -m pip install --disable-pip-version-check @taskPackages
    if ($LASTEXITCODE -ne 0) { throw 'Project dependency installation failed.' }
}

switch ($Action) {
    'Setup' {
        $taskPython = Get-ProjectPython '.venv'
        Install-ProjectDependencies $taskPython
        & $taskPython -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Project dependency check failed.' }
        Write-Host 'Dependencies installed in .venv. Next: manage.ps1 -Action Configure'
    }
    'Build' {
        $taskPython = Get-ProjectPython '.build-venv'
        Install-ProjectDependencies $taskPython -Build
        & $taskPython -m PyInstaller --noconfirm --clean RoomSearch.spec
        if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
        Copy-Item -LiteralPath ./dist/RoomSearch.exe -Destination ./RoomSearch.exe
        Get-FileHash -Algorithm SHA256 -LiteralPath ./RoomSearch.exe
    }
    'Configure' {
        $taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
        if (!(Test-Path -LiteralPath $taskPython)) { throw 'Run manage.ps1 -Action Setup first.' }
        & $taskPython classroom.py configure-database
        if ($LASTEXITCODE -ne 0) { throw 'Database configuration failed.' }
    }
    'Start' {
        $taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
        if (!(Test-Path -LiteralPath $taskPython)) { throw 'Run manage.ps1 -Action Setup first.' }
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
                ArgumentList = @('-u', 'classroom.py', 'serve')
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
        if (!$taskReady) { throw 'Service startup failed. Check data/classroom-server-error.log, database and port.' }
        Start-Process $taskUrl
    }
}
