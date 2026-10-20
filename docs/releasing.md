# Building and Releasing

The Python package and QGIS plugin share the first public version `0.1.0`. The corrected engine was previously verified as the local development build `0.7.0`; it was renumbered before its first publication. Historical audit logs retain their original versions, and installation and version checks were repeated for the 0.1.0 artifacts. The wheel contains the analysis engine and its portable raw-processing configuration. The plugin contains the QGIS interface and source archives for the engine and reviewed SidescanTools CLI, with their licenses and notices. Guided setup downloads a separate runtime and dependencies. Neither artifact bundles survey data, dependency binaries, or installed environments; the core wheel excludes SidescanTools.

The unpublished build numbers do not count as public releases. Starting initial
development releases at `0.1.0` follows the [Semantic Versioning guidance](https://semver.org/#how-should-i-deal-with-revisions-in-the-0yz-initial-development-phase).

## Local build

From the repository root, in a separate Python environment:

```console
python -m pip install -e ".[dev]"
python -m pytest -W error
python -m ruff check src tests qgis_plugin tools
python tools/build_setup_resources.py
python -m build
python -m twine check --strict dist/*.whl dist/*.tar.gz
python tools/build_qgis_plugin.py --development
python tools/verify_distributions.py --dist-dir dist
```

The development plugin ZIP can be installed locally for evaluation. It is explicitly marked as a development build and may omit public maintainer or repository metadata. It includes the project's GPL-3.0-or-later license. Do not submit it to the QGIS directory. The normal builder refuses an incomplete public-release configuration.

Install the wheel in a new environment and run commands from a directory outside this checkout. An editable install can conceal missing resources and accidental repository dependencies. Build an sdist, unpack it separately, build its wheel, and compare their package contents. Check that Python artifacts exclude the vendor tree, survey data and outputs, environments and raw sonar files. Inspect the plugin's `resources/setup/engine-source.zip` and `sidescantools-cli-source.zip` separately: only reviewed engine/raw CLI source, build metadata, required resources, licenses and notices belong there. Exclude vendor artwork, GUI resources, binaries, caches and survey files. Retain `manifest.json` and verify its archive checksums and environment specifications.

On 64-bit Windows, the main QGIS user flow is **Set up processing tools > Install tools**. The explicit action downloads pinned, checksum-verified micromamba, creates an isolated conda-forge Python 3.12 environment with the selected dependencies, then installs the bundled source with `pip --no-deps --no-build-isolation`. Raw conversion includes GMT and the reviewed backend; users can instead select the eight raster tools only. Preinstall the build dependencies in the managed environment. Users do not need a separate Python, wheel or raw-backend checkout, and setup does not depend on a public PyPI release. Existing-engine/manual configuration remains an advanced path. Keep source archives available in the public repository so the plugin matches its advertised source.

The Windows64/QGIS 3.40.1 guided path has passed a full fresh online setup in 206.234 seconds, a new raster-only setup using cached packages in 50.640 seconds and its eight-operation workflow in 9.076 seconds. A cold-start real-XTF workflow passed all nine provider operations in 115.922 seconds using saved setup settings, without backend overrides and with the input unchanged. It used a private GMT directory, a Python connection guard, closed proxies and disabled PROJ network access. This was a guarded offline test; native connections outside those controls were outside its boundary, and no operating-system firewall was used. Retain the online setup record (local: `logs/guided_online_verification.json`), raster-only record (local: `logs/guided_core_online_verification.json`) and offline workflow record (local: `logs/guided_offline_verification.json`). These are observed run times rather than installation or performance guarantees.

The `logs/...` paths identify maintainer-local records, excluded from the public
repository and distributions; they are not downloadable evidence.

## Maintainer and publication setup

The maintainer is `BezalelBenUri`; the public contact is
`diamondinyang@gmail.com`. Package and plugin metadata use that handle.
The source is published at
[BezalelBenUri/seabed-sidescan](https://github.com/BezalelBenUri/seabed-sidescan)
on the `main` branch. Keep the source, documentation and issue tracker publicly
readable. Confirm the intended release commit passes
[GitHub Actions](https://github.com/BezalelBenUri/seabed-sidescan/actions/workflows/ci.yml)
before publication. Publishing source on GitHub does not upload a package to
PyPI or submit the plugin to the QGIS directory. If the repository is renamed,
update both metadata files and the links before building again.

| File produced by this codebase | Purpose |
| --- | --- |
| `.whl` | Python installation package, uploaded to PyPI so users can install with pip. |
| `.tar.gz` | Python source distribution, also uploaded to PyPI and independently rebuilt during verification. |
| `.zip` | QGIS plugin installation archive, submitted separately to the QGIS plugin directory. |

These files are generated from the reviewed source; end users do not need to
create them. QGIS guided setup installs its included source and downloads its
runtime, so QGIS users do not select a Python wheel.

The project's own code, including the Python package and QGIS plugin, is licensed under GPL-3.0-or-later. The existing SidescanTools license applies to that third-party code independently and is unchanged.

Before a public release:

1. Verify the full GPLv3 text in root `LICENSE`, the GPL-3.0-or-later grant and third-party attribution in `NOTICE`, the SPDX expression in `[project].license`, and `license-files = ["LICENSE", "NOTICE"]` in `pyproject.toml`. Check the license and notices are included in the Python artifacts and plugin ZIP and that their metadata agrees.
2. Confirm the supplied maintainer details and keep the public repository readable. Verify the homepage, documentation, source and issue-tracker links in `[project.urls]` and `qgis_plugin/seabed_sidescan_qgis/metadata.txt` actually work. The plugin requires `email`, `license`, `homepage`, `repository`, and `tracker`.
3. Update package, plugin, and plugin engine version constants together. The builder checks plugin/package consistency; a test checks Python distribution metadata too.
4. Review the current validation record and remaining software checks in [quality_review.md](quality_review.md). Complete the 0.1.0 confirmation record from actual test logs. The older [distribution_audit.md](distribution_audit.md) records the 0.6.0 baseline. Verify georeferencing calculations, CRS handling, valid outputs, installation, and the formats, platforms, Python versions, and QGIS versions you advertise. Record workload dimensions, runtime, and peak memory using available survey data or a reproducible synthetic workload. The minimum metadata version does not establish testing on every later release.
5. Run `python tools/build_qgis_plugin.py` without `--development` and inspect the final ZIP. Retain the passing guided online/offline evidence above and repeat the relevant checks if the setup source, runtime specs, bootstrap or installation logic changes. Exercise actual online dependency downloads, source installation, raw-backend and core checks, cancellation/failure handling and local processing with no editable checkout or supplied Python on the engine path. Retain the earlier wheel-install checks as separate evidence and test additional supported platforms before advertising them.

Release 0.1.0 covers side-scan processing and acoustic characterization. Independent absolute-position control and field sediment ground truth establish the quality and interpretation of a particular survey; they are outside this software release's requirements. Document these boundaries in the package and plugin. Numerical georeferencing tests, correct CRS and resolution handling, reliable output validation, and fresh installation checks remain software requirements. Keep untested raw formats and platforms experimental or outside advertised support until their processing and installation paths are verified.

The GPL permits commercial use and carries source-sharing obligations when distributing covered modifications. Preserve applicable licenses, notices, and source availability when distributing the project or a modified vendor backend. Relevant primary sources are the [GPLv3 text](https://www.gnu.org/licenses/gpl-3.0.html), [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html#GPLPlugins), and [QGIS publication requirements](https://plugins.qgis.org/docs/publish).

## PyPI

First verify project-name availability and create the project or pending publisher in the account you intend to own it. The local name is `seabed-sidescan`; an absent search result does not reserve it.

Use TestPyPI for the first publication rehearsal, then install that distribution into an isolated environment. TestPyPI is a separate service and may not contain your dependencies; obtain dependencies from a deliberate source rather than assuming the test index mirrors PyPI.

The repository includes two distinct workflows. `build-distributions.yml` only
builds and retains reviewable artifacts. `publish-python.yml` can upload Python
distributions when explicitly started through **Actions > Publish Python
distributions manually > Run workflow**. It defaults to `testpypi`; choose
`pypi` only after the rehearsal succeeds and its result has been reviewed.
Pushes and tags do not trigger publication.

Configure these account and repository settings first:

| Setting | Test rehearsal | Public Python release |
| --- | --- | --- |
| Index account | TestPyPI account with verified email | PyPI account with verified email |
| Project | `seabed-sidescan` | `seabed-sidescan` |
| Trusted Publisher owner | `BezalelBenUri` | `BezalelBenUri` |
| Repository | `seabed-sidescan` | `seabed-sidescan` |
| Workflow filename | `publish-python.yml` | `publish-python.yml` |
| GitHub environment | `testpypi` | `pypi` |

Create both GitHub environments explicitly and configure their allowed release
branches and review rules before running the upload workflow. The workflow
requires publicly readable source, a working issue tracker/documentation,
passing tests, metadata checks, source rebuilds and a complete public plugin ZIP.
Only its separate publishing job receives OIDC permission. It downloads the
verified wheel and source archive without checking out or executing the project.
No long-lived PyPI API token belongs in the repository. A pending publisher does
not reserve the package name; recheck availability when configuring ownership.

Each manual run builds and verifies its selected commit. A production run does
not automatically promote the bytes from a previous TestPyPI run. Retain the
workflow artifacts and checksum record and review the selected commit. Duplicate
uploads fail rather than being silently skipped. Once a version is public, use
a new version for subsequent changes; do not overwrite a public 0.1.0 release.

For the TestPyPI installation rehearsal, use a new environment and an empty
download directory. Download only the candidate wheel from the test index, then
install that local file with dependencies deliberately obtained from PyPI:

```console
python -m venv release-check
release-check/Scripts/python -m pip download --index-url https://test.pypi.org/simple/ --no-deps --only-binary=:all: --dest test-download seabed-sidescan==0.1.0
release-check/Scripts/python -m pip install --index-url https://pypi.org/simple/ test-download/seabed_sidescan-0.1.0-py3-none-any.whl
release-check/Scripts/python -m pip check
release-check/Scripts/python -I -m seabed_sidescan --version
release-check/Scripts/python -I -m seabed_sidescan --help
```

On Linux/macOS use `release-check/bin/python`. Compare the downloaded wheel's
SHA-256 with the retained artifact, verify the installed package path is under
that new environment, and run a small raster operation from outside the source
checkout. This index rehearsal is still pending until the account/repository
setup is complete; local installed-wheel tests do not establish that an upload
or index download has succeeded.

Follow the [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/) and [PyPI Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/). Public publication is a separate action from building local artifacts.

## QGIS directory

The plugin archive must contain one top-level `seabed_sidescan_qgis` directory with `metadata.txt`, `__init__.py`, `LICENSE`, documentation, plugin source, and the reviewed setup source archives and notices. Include the unchanged SidescanTools GPLv3 license and dated modification/provenance notice in its source archive; retain the vendor's license grant. Its About text must disclose the external runtime download, internet requirement during setup, Windows64 guided-setup restriction, and experimental raw-format limits. QGIS publication rules exclude binaries and cap the plugin ZIP at 25 MB. After the public repository is available, build with `python tools/build_qgis_plugin.py`, install that exact ZIP in QGIS and verify setup and processing. Submit `dist/seabed_sidescan_qgis-0.1.0.zip`, not the development ZIP, through the owner's OSGeo account on the QGIS plugin site. The Python publication workflow retains this ZIP as a separate artifact; it does not upload it to PyPI or QGIS. Directory approval is performed by QGIS reviewers; a successful local ZIP build does not imply approval.

The official [QGIS release guide](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/releasing.html) and [publication requirements](https://plugins.qgis.org/docs/publish) describe the submission requirements.
