$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        & py.exe -3.13 -m venv .venv
    } else {
        & python.exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
        if ($LASTEXITCODE -ne 0) { throw '请使用 Python 3.13；安装说明见 REQUIREMENTS.md。' }
        & python.exe -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw '创建本项目虚拟环境失败。' }
}
& $taskPython -c "import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix and sys.version_info[:2] == (3, 13) else 1)"
if ($LASTEXITCODE -ne 0) { throw '本项目 .venv 必须使用 Python 3.13，请按 REQUIREMENTS.md 重建环境。' }
& $taskPython -m pip install --no-cache-dir -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '安装项目依赖失败。' }
& $taskPython -m pip check
if ($LASTEXITCODE -ne 0) { throw '项目依赖检查失败。' }
Write-Host '依赖已安装到本项目 .venv。使用 start-classroom.cmd 打开软件。'
