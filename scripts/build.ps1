<#
.SYNOPSIS
    Build Wallcraft for Windows.

.DESCRIPTION
    Produces:
      dist\Wallcraft.exe                  single-file portable build
      dist\Wallcraft\                     folder build (input for the installer)
      dist\Wallcraft-<ver>-Setup.exe      installer, if Inno Setup 6 (iscc) is available

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -SkipTests -PortableOnly
#>
param(
    [switch]$SkipTests,
    [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = (Select-String -Path "src\wallcraft\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Building Wallcraft $version" -ForegroundColor Cyan

python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

python scripts\fetch_mpv.py
if ($LASTEXITCODE -ne 0) { throw "Downloading mpv failed" }
$env:WALLCRAFT_REQUIRE_MPV = "1"

if (-not $SkipTests) {
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
}

Write-Host "Building portable exe..." -ForegroundColor Cyan
$env:WALLCRAFT_ONEFILE = "1"
python -m PyInstaller --noconfirm --clean wallcraft.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (onefile) failed" }

if ($PortableOnly) { Write-Host "Done: dist\Wallcraft.exe" -ForegroundColor Green; exit 0 }

Write-Host "Building folder version..." -ForegroundColor Cyan
$env:WALLCRAFT_ONEFILE = "0"
python -m PyInstaller --noconfirm wallcraft.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (onedir) failed" }

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = Get-Item $candidate }
}
if ($iscc) {
    Write-Host "Building installer..." -ForegroundColor Cyan
    & $iscc.Source "/DAppVersion=$version" "installer\wallcraft.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
} else {
    Write-Warning "Inno Setup 6 not found; skipping installer (https://jrsoftware.org/isdl.php)"
}

Write-Host "Done. Output in dist\" -ForegroundColor Green
