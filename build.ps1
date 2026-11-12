# Build a self-contained Windows executable using only this project's environment.
[CmdletBinding()]
param(
    [string]$PythonPath = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    [string]$UpdateRepository = '',
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$entryPath = Join-Path $projectRoot 'main.py'
$buildPath = Join-Path $projectRoot 'build'
$exePath = Join-Path $projectRoot 'OrangePet.exe'
$defaultRepositoryFile = Join-Path $projectRoot 'orange-pet-update-repository.txt'
if (-not $PSBoundParameters.ContainsKey('UpdateRepository') -and (Test-Path -LiteralPath $defaultRepositoryFile)) {
    $UpdateRepository = (Get-Content -LiteralPath $defaultRepositoryFile -Raw -Encoding utf8).Trim()
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the project .venv and install requirements-build.txt first. See README.md.'
}

& $PythonPath -B -c 'import PyInstaller; import PySide6.QtWidgets; import psutil; import winrt.windows.media.control'
if ($LASTEXITCODE -ne 0) {
    throw 'Build dependencies are missing. Run .venv\Scripts\python.exe -m pip install -r requirements-build.txt.'
}

$runningBuild = Get-Process -Name OrangePet -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $exePath }
if ($runningBuild) {
    throw 'Quit OrangePet from its menu before rebuilding. This script will not stop it for you.'
}

New-Item -ItemType Directory -Path $buildPath -Force | Out-Null
$iconPath = Join-Path $buildPath 'orangepet_icon.ico'
$renderIcon = @'
import sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtWidgets import QApplication
from orange_pet.art import character_icon
app = QApplication([])
if not character_icon(size=256).pixmap(256, 256).save(sys.argv[2], 'ICO'):
    raise RuntimeError('Unable to save the OrangePet icon')
'@
& $PythonPath -B -c $renderIcon $projectRoot $iconPath
if ($LASTEXITCODE -ne 0) {
    throw 'Could not render the application icon.'
}
$buildArguments = @(
    '-m', 'PyInstaller',
    '--clean',
    '--noconfirm',
    '--onefile',
    '--windowed',
    '--name', 'OrangePet',
    '--icon', $iconPath,
    '--distpath', $projectRoot,
    '--workpath', (Join-Path $buildPath 'pyinstaller'),
    '--specpath', $buildPath,
    '--paths', $projectRoot
)
if ($UpdateRepository) {
    $repo = & $PythonPath -B -c 'import sys; sys.path.insert(0, sys.argv[1]); from orange_pet.updates import repository_name; print(repository_name(sys.argv[2]))' $projectRoot $UpdateRepository
    if ($LASTEXITCODE -ne 0 -or -not $repo) {
        throw 'UpdateRepository must be a GitHub owner/repository or repository URL.'
    }
    $repoFile = Join-Path $buildPath 'orange-pet-update-repository.txt'
    [IO.File]::WriteAllText($repoFile, $repo)
    $buildArguments += @('--add-data', "${repoFile}:.")
}
$buildArguments += $entryPath
# Do not let another application's ICU or OpenSSL enter PyInstaller's search path.
$pythonBase = & $PythonPath -B -c 'import sys; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0 -or -not $pythonBase) {
    throw 'Could not locate the Python runtime.'
}
$savedPath = $env:Path
$savedCache = $env:PYINSTALLER_CONFIG_DIR
try {
    $env:Path = @(
        (Split-Path -Parent $PythonPath),
        $pythonBase,
        (Join-Path $pythonBase 'Library\bin'),
        (Join-Path $env:SystemRoot 'System32'),
        $env:SystemRoot
    ) -join ';'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $buildPath 'pyinstaller-cache'
    & $PythonPath @buildArguments
    $buildExit = $LASTEXITCODE
} finally {
    $env:Path = $savedPath
    $env:PYINSTALLER_CONFIG_DIR = $savedCache
}
if ($buildExit -ne 0 -or -not (Test-Path -LiteralPath $exePath)) {
    throw 'Packaging failed. Review the PyInstaller output above.'
}

Write-Host "Built: $exePath"
Write-Host 'Launch OrangePet.exe or the .cmd launcher. Runtime data is stored in data/ beside the executable.'
if ($SkipInstaller) {
    return
}

# ---- Optional: build a full installer with Inno Setup -----------------------
# If Inno Setup (ISCC.exe) is on PATH, compile installer.iss into a setup exe.
# Skip gracefully if Inno Setup is not installed.
$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    # Also check the default install location
    $defaultIscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if (Test-Path -LiteralPath $defaultIscc) {
        $iscc = [PSCustomObject]@{ Source = $defaultIscc }
    }
}
if ($iscc) {
    $issPath = Join-Path $buildPath 'installer.iss'
    if (Test-Path -LiteralPath $issPath) {
        $version = & $PythonPath -B -c 'import sys; sys.path.insert(0, sys.argv[1]); from orange_pet import __version__; print(__version__)' $projectRoot
        if ($LASTEXITCODE -ne 0 -or -not $version) {
            throw 'Could not read the application version.'
        }
        & $iscc.Source "/DMyAppVersion=$version" $issPath
        if ($LASTEXITCODE -eq 0) {
            $setupPath = Join-Path $projectRoot 'installer_output\OrangePetSetup.exe'
            if (Test-Path -LiteralPath $setupPath) {
                Write-Host "Installer built: $setupPath"
            }
        } else {
            Write-Warning 'Inno Setup compilation failed. Check the output above.'
        }
    } else {
        Write-Host 'installer.iss not found; skipping installer build.'
    }
} else {
    Write-Host 'Inno Setup not found. Install it from https://jrsoftware.org/isdl.php to build a setup.exe installer.'
    Write-Host 'The single-file OrangePet.exe is ready to share as-is.'
}
