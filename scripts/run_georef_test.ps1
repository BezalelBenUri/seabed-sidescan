param(
    [string]$ProjectName = ("gis_test_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")),
    [string]$SidescanToolsRepo = "",
    [string]$EnvName = "env_sidescantools_cli",
    [string]$InputPath = "",
    [string]$ConfigPath = "",
    [ValidatePattern("^\d+,\d+$")]
    [string]$ChannelPair = "0,1",
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

if (-not $SidescanToolsRepo) {
    $SolutionRoot = Split-Path -Parent $PSScriptRoot
    $SidescanToolsRepo = Join-Path $SolutionRoot "vendor\sidescantools-main"
}
else {
    $SolutionRoot = Split-Path -Parent $PSScriptRoot
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $SolutionRoot "configs\gis_georef_test_config.yml"
}

if (-not $ProjectRoot) {
    $ProjectRoot = Join-Path (Split-Path -Parent $SolutionRoot) "SSS_processing\projects"
}

$resolvedInput = Resolve-SonarInputPath -ProvidedPath $InputPath -SolutionRoot $SolutionRoot -Purpose "test"
$InputPath = $resolvedInput.Path

$conda = Find-CondaExe
$project = New-ProcessingProject -ProjectName $ProjectName -ConfigTemplatePath $ConfigPath -ProjectRoot $ProjectRoot -RunKind "georef_test"
$logPath = Join-Path $project.LogDir ("georef_test_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location $SidescanToolsRepo
$env:SIDESCANTOOLS_XTF_CHANNEL_PAIR = $ChannelPair
Set-SidescanToolsPythonPath $SidescanToolsRepo

Start-Transcript -Path $logPath -Force | Out-Null
try {
    Write-Host "Project name: $($project.Name)"
    Write-SonarInputSummary $resolvedInput
    Write-Host "Channel pair: $ChannelPair"
    Write-Host "Runtime config: $($project.RuntimeConfigPath)"
    Write-Host "GeoTIFF output folder: $($project.GeorefDir)"
    Write-Host "Preview output folder: $($project.PreviewDir)"
    Write-Host "Log file: $logPath"
    Write-Host ""

    & $conda run --no-capture-output -n $EnvName python "$SidescanToolsRepo\src\sidescantools\main_cli.py" $InputPath $project.RuntimeConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "SidescanTools exited with code $LASTEXITCODE"
    }
}
finally {
    Stop-Transcript | Out-Null
}

Write-Host ""
Write-Host "GIS test complete. Check GeoTIFFs in:"
Write-Host $project.GeorefDir
Write-Host "Log saved to:"
Write-Host $logPath
