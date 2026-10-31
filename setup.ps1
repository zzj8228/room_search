$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        & py.exe -3 -m venv .venv
    } else {
        & python.exe -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw '创建本项目虚拟环境失败。' }
}
& $taskPython -m pip install --no-cache-dir -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw '安装项目依赖失败。' }
Write-Host '依赖已安装到本项目 .venv。使用 start-classroom.cmd 打开软件。'
