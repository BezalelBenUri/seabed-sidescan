param(
    [string]$ProjectName = "",
    [string]$ProjectRoot = "",
    [string]$GeorefDir = "",
    [string]$OutputDir = "",
    [string]$ReportDir = "",
    [string]$EnvName = "env_sidescantools_cli",
    [string[]]$Channels = @("0", "1"),
    [double]$MinValidPercent = 1.0,
    [double]$MinStd = 0.5,
    [double]$MinPercentileRange = 2.0,
    [double]$EdgeTrimPercent = 2.0,
    [double]$FeatherPercent = 8.0,
    [double]$BalanceLowPercentile = 10.0,
    [double]$BalanceMidPercentile = 50.0,
    [double]$BalanceHighPercentile = 90.0,
    [switch]$CleanOutput,
    [switch]$SkipCombined,
    [switch]$IncludeReview,
    [switch]$AlsoRaw
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$SolutionRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Join-Path (Split-Path -Parent $SolutionRoot) "SSS_processing\projects"
}

if (-not $ProjectName -and -not $GeorefDir) {
    $latestProject = Get-ChildItem -Path $ProjectRoot -Directory -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latestProject) {
        throw "No project folders found in $ProjectRoot. Provide -ProjectName or -GeorefDir."
    }
    $ProjectName = $latestProject.Name
}

if ($ProjectName) {
    $projectDir = Join-Path $ProjectRoot (Get-SafeProjectName $ProjectName)
}
elseif ($GeorefDir) {
    $projectDir = Split-Path -Parent (Resolve-Path -LiteralPath $GeorefDir).Path
}

if (-not $GeorefDir) {
    $GeorefDir = Join-Path $projectDir "georef_out"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $projectDir "mosaics"
}
if (-not $ReportDir) {
    $ReportDir = Join-Path $projectDir "qc"
}

if (-not (Test-Path -LiteralPath $GeorefDir)) {
    throw "GeoTIFF input folder not found: $GeorefDir"
}

Ensure-Folder $OutputDir
Ensure-Folder $ReportDir

$conda = Find-CondaExe

$argsList = @(
    "run",
    "--no-capture-output",
    "-n",
    $EnvName,
    "python",
    "-m",
    "seabed_sidescan.mosaic",
    "--georef-dir",
    $GeorefDir,
    "--output-dir",
    $OutputDir,
    "--report-dir",
    $ReportDir,
    "--channels"
)
$argsList += $Channels
$argsList += @(
    "--min-valid-percent",
    $MinValidPercent,
    "--min-std",
    $MinStd,
    "--min-percentile-range",
    $MinPercentileRange,
    "--edge-trim-percent",
    $EdgeTrimPercent,
    "--feather-percent",
    $FeatherPercent,
    "--balance-low-percentile",
    $BalanceLowPercentile,
    "--balance-mid-percentile",
    $BalanceMidPercentile,
    "--balance-high-percentile",
    $BalanceHighPercentile
)
if ($CleanOutput) {
    $argsList += "--clean-output"
}
if ($IncludeReview) {
    $argsList += "--include-review"
}
if ($SkipCombined) {
    $argsList += "--skip-combined"
}
if ($AlsoRaw) {
    $argsList += "--also-raw"
}

Write-Host "GeoTIFF input folder: $GeorefDir"
Write-Host "Mosaic output folder: $OutputDir"
Write-Host "QC report folder: $ReportDir"
Write-Host "Channels: $($Channels -join ', ')"
Write-Host "Mosaic product: standard corrected relative acoustic-intensity mosaic"
Write-Host "Line balancing percentiles: P$BalanceLowPercentile / P$BalanceMidPercentile / P$BalanceHighPercentile"
Write-Host "Edge trim percent: $EdgeTrimPercent"
Write-Host "Feather percent: $FeatherPercent"
if ($AlsoRaw) {
    Write-Host "Raw acoustic-intensity audit mosaics: enabled"
}
if ($CleanOutput) {
    Write-Host "Clean old mosaic products before rebuild: enabled"
}
Write-Host ""

& $conda @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Mosaic build failed with code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Mosaic build complete."
