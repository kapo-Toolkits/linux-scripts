# Build the Windows bundle + installer for PrintHub.
#
# Requires: Python 3, and Inno Setup (iscc.exe) on PATH for the installer step.
#   winget install JRSoftware.InnoSetup
#
# Usage:  powershell -File packaging\windows\build-windows.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

Write-Host ">> Building standalone bundle with PyInstaller"
python -m pip install --upgrade pyinstaller PySide6
pyinstaller --noconfirm packaging\printhub.spec    # -> dist\PrintHub\

$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue)
if ($null -eq $iscc) {
    Write-Warning "iscc.exe (Inno Setup) not found; skipping installer."
    Write-Host   "Bundle is ready at dist\PrintHub\PrintHub.exe"
    exit 0
}

Write-Host ">> Compiling installer with Inno Setup"
& $iscc.Source "packaging\windows\printhub.iss"
Write-Host ">> Done. Installer in dist\"

# --- MSIX alternative -------------------------------------------------------
# To ship through the Microsoft Store instead of an .exe installer, wrap the
# same dist\PrintHub\ folder with makeappx.exe + an AppxManifest.xml and sign
# it. Inno is the simpler default and needs no code-signing cert to run.
