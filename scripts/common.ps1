function Find-CondaExe {
    $candidates = @(
        (Join-Path ([Environment]::GetFolderPath('UserProfile')) "miniconda3\Scripts\conda.exe"),
        "C:\ProgramData\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "conda was not found. Install Miniconda/Anaconda, then rerun the command."
}

function Ensure-Folder {
    param([Parameter(Mandatory=$true)][string]$Path)
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Convert-ToYamlPath {
    param([Parameter(Mandatory=$true)][string]$Path)
    return $Path.Replace("\", "/")
}

function Get-SafeProjectName {
    param([Parameter(Mandatory=$true)][string]$ProjectName)

    $safeName = ($ProjectName.Trim() -replace "[^A-Za-z0-9._-]+", "_").Trim("_")
    if (-not $safeName -or $safeName -in @('.', '..') -or $safeName -notmatch '[A-Za-z0-9]') {
        throw "ProjectName must contain at least one letter or number."
    }
    if ($safeName.EndsWith('.') -or ($safeName.Split('.')[0] -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$')) {
        throw "ProjectName must be a portable directory name."
    }
    return $safeName
}

function New-ProcessingProject {
    param(
        [Parameter(Mandatory=$true)][string]$ProjectName,
        [Parameter(Mandatory=$true)][string]$ConfigTemplatePath,
        [string]$ProjectRoot = "D:\a\SSS_processing\projects",
        [string]$RunKind = "full"
    )

    if (-not (Test-Path $ConfigTemplatePath)) {
        throw "Config template not found: $ConfigTemplatePath"
    }

    $safeName = Get-SafeProjectName $ProjectName
    $RunKind = Get-SafeProjectName $RunKind
    $projectDir = Join-Path $ProjectRoot $safeName
    $georefDir = Join-Path $projectDir "georef_out"
    $previewDir = Join-Path $projectDir "previews"
    $configDir = Join-Path $projectDir "configs"
    $logDir = Join-Path $projectDir "logs"

    foreach ($path in @($projectDir, $georefDir, $previewDir, $configDir, $logDir)) {
        Ensure-Folder $path
    }

    $runtimeConfigPath = Join-Path $configDir ("{0}.runtime.yml" -f $RunKind)
    $config = Get-Content -Raw -Path $ConfigTemplatePath
    $config = [regex]::Replace(
        $config,
        "(?m)^(\s*georef_dir:\s*).+$",
        { param($match) $match.Groups[1].Value + (Convert-ToYamlPath $georefDir) }
    )
    $config = [regex]::Replace(
        $config,
        "(?m)^(\s*working_dir:\s*).+$",
        { param($match) $match.Groups[1].Value + (Convert-ToYamlPath $previewDir) }
    )
    Set-Content -Path $runtimeConfigPath -Value $config

    return [pscustomobject]@{
        Name = $safeName
        ProjectDir = $projectDir
        GeorefDir = $georefDir
        PreviewDir = $previewDir
        ConfigDir = $configDir
        LogDir = $logDir
        RuntimeConfigPath = $runtimeConfigPath
    }
}

function Set-SidescanToolsPythonPath {
    param([Parameter(Mandatory=$true)][string]$SidescanToolsRepo)

    $srcPath = Join-Path $SidescanToolsRepo "src"
    if (-not (Test-Path $srcPath)) {
        throw "SidescanTools src folder not found: $srcPath"
    }
    $env:PYTHONPATH = $srcPath
}

function Get-SonarFiles {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    $item = Get-Item -LiteralPath $Path
    if (-not $item.PSIsContainer) {
        if ($item.Extension -in @(".xtf", ".jsf")) {
            return @($item)
        }
        return @()
    }

    $files = @()
    foreach ($extension in @("*.xtf", "*.jsf")) {
        $files += Get-ChildItem -LiteralPath $item.FullName -Filter $extension -File -ErrorAction SilentlyContinue
    }
    return @($files | Sort-Object Name)
}

function Resolve-SonarInputPath {
    param(
        [string]$ProvidedPath = "",
        [Parameter(Mandatory=$true)][string]$SolutionRoot,
        [ValidateSet("full", "test")][string]$Purpose = "full"
    )

    $checked = New-Object System.Collections.Generic.List[string]

    if ($ProvidedPath) {
        $resolvedPath = (Resolve-Path -LiteralPath $ProvidedPath -ErrorAction Stop).Path
        $files = @(Get-SonarFiles $resolvedPath)
        if ($files.Count -eq 0) {
            throw "InputPath exists but contains no .xtf or .jsf files: $resolvedPath"
        }
        return [pscustomobject]@{
            Path = $resolvedPath
            Files = $files
            Source = "explicit -InputPath"
        }
    }

    $workspaceRoot = Split-Path -Parent $SolutionRoot
    $candidatePaths = @()

    if ($env:SSS_INPUT_PATH) {
        $candidatePaths += $env:SSS_INPUT_PATH
    }

    if ($Purpose -eq "test") {
        $candidatePaths += @(
            (Join-Path $SolutionRoot "data\test_small"),
            (Join-Path $SolutionRoot "data\test"),
            (Join-Path $workspaceRoot "SSS_processing\test_small")
        )
    }

    $candidatePaths += @(
        (Join-Path $SolutionRoot "data\raw"),
        (Join-Path $SolutionRoot "data\sss_raw"),
        (Join-Path $workspaceRoot "SSS RAW"),
        (Join-Path $workspaceRoot "SSS_raw"),
        (Join-Path $workspaceRoot "SSS")
    )

    foreach ($candidate in ($candidatePaths | Select-Object -Unique)) {
        $checked.Add($candidate) | Out-Null
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        $resolvedPath = (Resolve-Path -LiteralPath $candidate).Path
        $files = @(Get-SonarFiles $resolvedPath)
        if ($files.Count -gt 0) {
            if ($Purpose -eq 'test') {
                $smallest = $files | Sort-Object Length, Name | Select-Object -First 1
                return [pscustomobject]@{
                    Path = $smallest.FullName
                    Files = @($smallest)
                    Source = 'auto-discovered smallest sonar file for test'
                }
            }
            return [pscustomobject]@{
                Path = $resolvedPath
                Files = $files
                Source = "auto-discovered"
            }
        }
    }

    $message = @()
    $message += "No sonar input data was found automatically."
    $message += "Checked:"
    foreach ($candidate in $checked) {
        $message += "  - $candidate"
    }
    $message += "Run again with an explicit input folder, for example:"
    $message += "  powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName `"lagos_main_100m`" -InputPath `"D:\a\SSS RAW`""
    throw ($message -join [Environment]::NewLine)
}

function Write-SonarInputSummary {
    param([Parameter(Mandatory=$true)]$ResolvedInput)

    $totalBytes = ($ResolvedInput.Files | Measure-Object Length -Sum).Sum
    Write-Host "Input source: $($ResolvedInput.Source)"
    Write-Host "Input path: $($ResolvedInput.Path)"
    Write-Host "Sonar files found: $($ResolvedInput.Files.Count)"
    Write-Host ("Total input size: {0} GB" -f ([math]::Round($totalBytes / 1GB, 2)))
    Write-Host ""
}
