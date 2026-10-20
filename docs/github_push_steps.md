# GitHub Push Steps

Run these from PowerShell after reviewing the solution folder.

```powershell
cd D:\a\seabed_sidescan_solution
git init
git add .
git status
git commit -m "feat: introduce Seabed Sidescan 0.1.0"
```

Then create an empty GitHub repository online and connect it:

```powershell
git remote add origin https://github.com/BezalelBenUri/seabed-sidescan.git
git branch -M main
git push -u origin main
```

Before pushing, check that raw data and heavy outputs are not staged:

```powershell
git status
```

Do not commit files such as:

```text
*.xtf
*.tif
*.csv
*.png
```

Raw data can stay outside the repository, for example:

```text
D:\a\SSS RAW
```

The scripts can find it automatically when it is beside the solution folder, or you can pass it explicitly with `-InputPath`.

The repo includes third-party SidescanTools code under `vendor\sidescantools-main`. Keep its `LICENSE` file in place.
