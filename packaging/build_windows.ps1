param(
    [string]$Version = "1.2.4"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$venvDir = Join-Path $projectRoot ".venv-packaging"
$outputRoot = Join-Path $projectRoot "packaging\output"
$specPath = Join-Path $projectRoot "packaging\pyinstaller\dnd_campaign_presenter.spec"
$issPath = Join-Path $projectRoot "packaging\windows\DndCampaignPresenter.iss"
$buildRoot = Join-Path $projectRoot "dist\DND Campaign Presenter"
$outputBaseFilename = "DND-Campaign-Presenter-$Version-Windows-x64-Setup"

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.13 -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return @("py", "-3.13")
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3.13 is required to build the Windows package."
}

function Invoke-CommandArray {
    param(
        [string[]]$CommandParts
    )

    $command = $CommandParts[0]
    $arguments = @()
    if ($CommandParts.Length -gt 1) {
        $arguments = $CommandParts[1..($CommandParts.Length - 1)]
    }
    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($CommandParts -join ' ')"
    }
}

function Get-InnoSetupCompiler {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    throw "Inno Setup 6 was not found. Install it and rerun this script."
}

$pythonCommand = Get-PythonCommand

Write-Host "Preparing packaging virtual environment..."
Invoke-CommandArray ($pythonCommand + @("-m", "venv", $venvDir))

$venvPython = Join-Path $venvDir "Scripts\python.exe"
Invoke-CommandArray @($venvPython, "-m", "pip", "install", "--upgrade", "pip")
Invoke-CommandArray @(
    $venvPython,
    "-m",
    "pip",
    "install",
    "-r",
    (Join-Path $projectRoot "requirements.txt"),
    "-r",
    (Join-Path $projectRoot "packaging\requirements-build.txt")
)

Write-Host "Cleaning previous packaging outputs..."
foreach ($path in @(
    (Join-Path $projectRoot "build"),
    (Join-Path $projectRoot "dist"),
    $outputRoot
)) {
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
    }
}
New-Item -ItemType Directory -Path $outputRoot | Out-Null

Write-Host "Building frozen Windows app with PyInstaller..."
$env:APP_VERSION = $Version
Invoke-CommandArray @($venvPython, "-m", "PyInstaller", "--clean", "--noconfirm", $specPath)

if (-not (Test-Path $buildRoot)) {
    throw "Expected PyInstaller output not found: $buildRoot"
}

$iscc = Get-InnoSetupCompiler

Write-Host "Creating Windows installer with Inno Setup..."
Invoke-CommandArray @(
    $iscc,
    "/DAppVersion=$Version",
    "/DBuildRoot=$buildRoot",
    "/DOutputDir=$outputRoot",
    "/DOutputBaseFilename=$outputBaseFilename",
    $issPath
)

Write-Host "Windows package created:"
Write-Host "  $(Join-Path $outputRoot "$outputBaseFilename.exe")"
