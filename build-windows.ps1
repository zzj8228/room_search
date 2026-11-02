$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.build-venv/Scripts/python.exe')) {
    py.exe -3.13 -m venv .build-venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create build environment.' }
}
& ./.build-venv/Scripts/python.exe -m pip install 'pyinstaller==6.19.0' -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
& ./.build-venv/Scripts/python.exe -m PyInstaller --noconfirm --clean RoomSearch.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
Copy-Item -LiteralPath ./dist/RoomSearch.exe -Destination ./RoomSearch.exe
Get-FileHash -Algorithm SHA256 -LiteralPath ./RoomSearch.exe
