param(
    [string[]]$Folders = @(
        "D:\a\SSS_processing\georef_out",
        "D:\a\SSS_processing\gis_georef_test",
        "D:\a\SSS_processing\projects"
    ),
    [switch]$Delete
)

$ErrorActionPreference = "Stop"

$files = foreach ($folder in $Folders) {
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { continue }
    $resolvedRoot = (Resolve-Path -LiteralPath $folder).ProviderPath.TrimEnd('\')
    foreach ($file in (Get-ChildItem -LiteralPath $resolvedRoot -Filter "Navigation_*.csv" -File -Recurse -ErrorAction Stop)) {
        $resolvedFile = [IO.Path]::GetFullPath($file.FullName)
        if (-not $resolvedFile.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Navigation CSV target escaped the requested folder: $resolvedFile"
        }
        $file
    }
}

if (-not $files) {
    Write-Host "No Navigation_*.csv files found."
    exit 0
}

$total = ($files | Measure-Object Length -Sum).Sum
$files | Select-Object FullName,@{Name="SizeMB";Expression={[math]::Round($_.Length / 1MB, 1)}} | Format-Table -AutoSize
Write-Host ""
Write-Host ("Total navigation CSV size: {0} GB" -f ([math]::Round($total / 1GB, 2)))

if ($Delete) {
    foreach ($file in $files) { Remove-Item -LiteralPath $file.FullName -Force }
    Write-Host "Deleted navigation CSV files."
}
else {
    Write-Host "Preview only. Rerun with -Delete to remove these files."
}
