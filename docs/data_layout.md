# Data Layout

Do not commit raw survey data or generated outputs to GitHub.

Recommended local layout:

```text
D:\a
  SSS RAW\
    raw XTF files

  SSS_processing\
    projects\
      project_name\
        georef_out\
          GeoTIFF outputs
        previews\
          processed PNG previews
        configs\
          runtime config used for that run
        logs\
          timestamped processing logs

    test_small\
      one small copied XTF for testing

    png_out\
      optional working images

  seabed_sidescan_solution\
    GitHub-ready scripts, configs, docs, and vendored SidescanTools code
```

The solution folder is what should be pushed to GitHub.

The vendored SidescanTools folder is:

```text
D:\a\seabed_sidescan_solution\vendor\sidescantools-main
```

Do not commit a Python virtual environment such as `.venv`.

## Input Discovery

The processing scripts do not need the raw data inside the Git repo.

Use the explicit input path when possible:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName "main_100m_channels_0_1" -InputPath "D:\a\SSS RAW"
```

If no `-InputPath` is provided, the script searches common locations relative to the solution folder:

```text
.\data\raw
.\data\sss_raw
..\SSS RAW
..\SSS_raw
..\SSS
```

It also checks the `SSS_INPUT_PATH` environment variable if it is set.

Preview the selected input without processing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\list_input_data.ps1
```

Example full run:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\run_full_processing.ps1 -ProjectName "main_100m_channels_0_1"
```

Example output folder:

```text
D:\a\SSS_processing\projects\main_100m_channels_0_1
```
