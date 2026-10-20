param(
    [string]$RawFolder = "D:\a\SSS RAW",
    [string]$TestFile = "D:\a\SSS_processing\test_small\PL018220414110300.xtf",
    [double]$TestMinutes = 2.82
)

$ErrorActionPreference = "Stop"

$rawFiles = Get-ChildItem -Path $RawFolder -Filter *.xtf -File
if (-not $rawFiles) {
    throw "No XTF files found in $RawFolder"
}

$testSize = (Get-Item $TestFile).Length
$totalSize = ($rawFiles | Measure-Object Length -Sum).Sum
$ratio = $totalSize / $testSize
$estimated = $TestMinutes * $ratio

[pscustomobject]@{
    TestFileMB = [math]::Round($testSize / 1MB, 2)
    RawFileCount = $rawFiles.Count
    TotalRawGB = [math]::Round($totalSize / 1GB, 2)
    SizeRatio = [math]::Round($ratio, 2)
    EstimatedHours = [math]::Round($estimated / 60, 2)
    Assumption = "Runtime scales linearly with input size; acquisition settings and output resolution can change this substantially."
} | Format-List

