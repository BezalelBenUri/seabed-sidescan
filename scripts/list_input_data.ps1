param(
    [string]$InputPath = "",
    [ValidateSet("full", "test")]
    [string]$Purpose = "full"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$SolutionRoot = Split-Path -Parent $PSScriptRoot
$resolvedInput = Resolve-SonarInputPath -ProvidedPath $InputPath -SolutionRoot $SolutionRoot -Purpose $Purpose

Write-SonarInputSummary $resolvedInput
$resolvedInput.Files |
    Select-Object Name,@{Name="SizeMB";Expression={[math]::Round($_.Length / 1MB, 2)}} |
    Format-Table -AutoSize
