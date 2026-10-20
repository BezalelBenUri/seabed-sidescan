param([string]$SidescanToolsRepo = '')

$ErrorActionPreference = 'Stop'
$solutionRoot = Split-Path -Parent $PSScriptRoot
$reviewedRepo = Join-Path $solutionRoot 'vendor\sidescantools-main'
if (-not $SidescanToolsRepo) { $SidescanToolsRepo = $reviewedRepo }
$reviewedRepo = (Resolve-Path -LiteralPath $reviewedRepo).Path
$SidescanToolsRepo = (Resolve-Path -LiteralPath $SidescanToolsRepo).Path

# The checked-in, dated source is the canonical patch. Copying these reviewed
# files also prevents an old embedded wrapper template reverting safety fixes.
# This targets the recorded 1.0.0 source snapshot; review any upstream update.
$files = @(
    'src\sidescantools\__init__.py',
    'src\sidescantools\xtf_wrapper.py',
    'src\sidescantools\sidescan_file.py',
    'src\sidescantools\jsf.py',
    'src\sidescantools\georef_thread.py',
    'src\sidescantools\main_cli.py',
    'environment_cli.yml'
)
$license = Join-Path $SidescanToolsRepo 'LICENSE'
$metadata = Join-Path $SidescanToolsRepo 'pyproject.toml'
if (-not (Test-Path -LiteralPath $license) -or -not (Test-Path -LiteralPath $metadata)) {
    throw "Expected a SidescanTools source checkout: $SidescanToolsRepo"
}
if ((Get-FileHash -LiteralPath $license).Hash -ne (Get-FileHash -LiteralPath (Join-Path $reviewedRepo 'LICENSE')).Hash) {
    throw 'The upstream license differs from the reviewed snapshot. Review the checkout before patching.'
}
if ((Get-Content -Raw -LiteralPath $metadata) -notmatch '(?m)^version\s*=\s*"1\.0\.0"\s*$') {
    throw 'Only the reviewed SidescanTools 1.0.0 snapshot is supported. Review upstream changes before patching.'
}
foreach ($relative in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $SidescanToolsRepo $relative))) {
        throw "Required SidescanTools file not found: $relative"
    }
}
foreach ($relative in ($files + @('THIRD_PARTY.md'))) {
    $source = Join-Path $reviewedRepo $relative
    $destination = Join-Path $SidescanToolsRepo $relative
    if ((-not (Test-Path -LiteralPath $destination)) -or
        ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash)) {
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}
Write-Host 'Reviewed SidescanTools CLI/Klein safety patches are present (2026-10-20).'
