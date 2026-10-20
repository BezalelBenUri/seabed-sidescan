# Seabed Sidescan: publication and launch plan

Prepared on 20 October 2026 for the first public release, 0.1.0.

The objective is to make Seabed Sidescan easy to discover, install, evaluate and
cite. A useful release and a reproducible demonstration give people reasons to
share it. Viral reach is an aspiration, not a result that can be promised.

This is a proposed execution plan. It does not authorize or record an upload,
account change, community post or outreach message.

## 1. Current position

| Item | Verified position | Consequence |
| --- | --- | --- |
| Public source | [BezalelBenUri/seabed-sidescan](https://github.com/BezalelBenUri/seabed-sidescan), default branch `main`, commit `8cc23f1`, Issues enabled | Repository creation is complete. |
| GitHub presentation | Description, website and topics are empty; no release is published | Complete the repository landing page and create a versioned release after the release checks pass. |
| Remote tests | All eight jobs passed at `8cc23f1`: Windows and Linux on Python 3.10, 3.12 and 3.13, plus both distribution jobs | The Windows CI blocker is resolved. Require passing checks on the final release commit too. |
| Local validation | A clean checkout of `8cc23f1` passed 213 Windows tests, strict metadata checks, both plugin ZIP checks, source rebuilds and installed-wheel smoke checks; existing source-matched evidence covers 30 QGIS tests and the real-XTF workflow with both channel pairs | Retain exact-commit evidence and repeat relevant checks after changes. |
| Python publishing | Manual TestPyPI/PyPI workflow exists; neither project API returned an existing package at the check | Configure ownership and rehearse publication. Name availability is not reserved. |
| QGIS publishing | Public ZIP is built locally; directory approval has not been established | Submit separately and distinguish a downloadable ZIP from an approved directory listing. |
| Public documentation | This checkout corrects stale repository-creation wording and labels private `logs/` evidence as local files; public CI results are linked separately | Commit the documentation updates and keep public results distinct from local records. |

The successful CI result is recorded in [run 39414940067](https://github.com/BezalelBenUri/seabed-sidescan/actions/runs/39414940067).
Each Windows test job passed 214 tests with one POSIX-only skip. Each Linux job
passed 213 tests with two Windows-only skips. Ruff and both distribution jobs
also passed. The fix isolates the Windows PowerShell test subprocess from
inherited PowerShell 7 module paths and adds a regression case; processing code
is unchanged. Existing local QGIS and real-data records remain evidence of
those separately performed checks.

## 2. Product identity and claims

Use one name and one principal source of information:

| Surface | Name or destination |
| --- | --- |
| Project and QGIS display name | **Seabed Sidescan** |
| Python distribution and command | `seabed-sidescan` |
| Python import | `seabed_sidescan` |
| Repository and initial landing page | `https://github.com/BezalelBenUri/seabed-sidescan` |
| Public contact | `diamondinyang@gmail.com` |

Suggested repository description:

> Open-source side-scan sonar processing and acoustic facies analysis through a Python library and QGIS plugin.

Suggested topics: `sidescan-sonar`, `hydrography`, `qgis-plugin`, `geospatial`,
`seabed-mapping`, `marine-geophysics`, `raster-processing`, `python`.
Topics help connect repositories with related subjects. [GitHub topic guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)

The release message should explain that the two interfaces use the same engine.
Keep these boundaries visible in the README, package description, plugin About
text, demonstrations and announcements:

- XTF conversion is implemented and has real-file checks on one four-channel recording using both selected pairs. Broader manufacturer-specific coverage is not established.
- JSF envelope conversion remains experimental. Other JSF encodings and mismatched channels are rejected.
- GeoTIFF supports the raster-analysis workflow. The output classes describe acoustic facies or texture clusters.
- Guided installation is validated on 64-bit Windows with QGIS 3.40.1. Other QGIS platforms and versions need their own evidence; current metadata excludes QGIS 4.
- Internet is needed for guided setup. The tested processing workflow used local files under the documented network restrictions.
- Do not advertise sediment identification, survey certification, calibrated absolute backscatter, universal format support or unmeasured speed advantages.

No new raw-format reader or field campaign is required for this launch. Existing
format reliability, installation, documentation and reproducible examples take
priority over additional features.

## 3. Execution order and release gates

The time windows below are planning targets after work starts, not promised
publication dates. Account setup and QGIS review can extend the schedule.

| Phase | Owner | Deliverable | Completion gate |
| --- | --- | --- | --- |
| 0. Resolve remote CI (complete at `8cc23f1`) | Maintainer and development support | Windows subprocess correction and regression coverage; all eight jobs passed | Preserve this gate for the exact intended release commit after further changes. |
| 1. Prepare public onboarding | Maintainer | Working links, public validation summary, one example and two installation paths | A new visitor can identify requirements and reproduce the example without private folders or data. |
| 2. Independent pilots | Maintainer and 3–5 testers | Fresh-machine installation and example feedback | At least one QGIS user and one Python user independently finish the example; installation blockers are resolved. |
| 3. TestPyPI rehearsal | Owner account action, prepared workflow | Test upload and independent index installation | Downloaded wheel matches its retained checksum; imports, dependency checks, command line and a raster operation pass. |
| 4. Public Python release | Owner account action | PyPI 0.1.0, GitHub release and archived source | Published package installs from PyPI; version, release commit and artifact records agree. |
| 5. QGIS submission | OSGeo account owner and QGIS reviewers | Source-only public ZIP and review response | Approval is confirmed before advertising installation from the official directory. |
| 6. Targeted launch | Maintainer | Demonstration, tutorial and audience-specific announcements | Every announcement links to a working installation path and an accurately labelled release. |
| 7. First 90 days | Maintainer and early users | Support, external use cases and maintenance releases | Adoption feedback determines subsequent work. |

Account setup, demonstration preparation and QGIS review preparation can run in
parallel. The main public announcement should follow a successful release and
independent use. If QGIS approval is pending, advertise the manual ZIP route and
its status explicitly.

A practical starting cadence is to use the first 1–2 working days for repository
presentation, the rest of the first week for the
example and account setup, and the second week for independent pilots and the
index rehearsal. Publish when the gates pass, rather than on a fixed calendar
date. QGIS review and any new installation or CI issues may extend that schedule.

## 4. Immediate work before publishing

### Keep the CI release gate

The Windows failure is resolved and the complete matrix passed at `8cc23f1`.
After committing documentation or other release changes, confirm all required
checks pass for the new revision and retain its commit SHA. If a regression
appears, use the affected job's full test output to reproduce and correct it
while preserving meaningful assertions. The existing publishing workflow
tests its Ubuntu build; do not assume that dispatching it also enforces a
successful Windows matrix. Verify the required CI checks for that same commit
before dispatch, or add an explicit CI gate to the publication process.

### Make the public repository useful

- [ ] Set the description, website and topics. Use the README as the initial landing page; a separate website can wait.
- [ ] Put **Use in QGIS** and **Use in Python** near the start of the README.
- [ ] Update documentation that still says the repository needs to be created.
- [ ] Check README links as rendered on both GitHub and the package index. Use absolute public documentation links where relative links would resolve incorrectly on PyPI.
- [ ] Replace publicly broken local-log links with a public, sanitized validation summary or release attachment. Keep private raw logs in the maintainer checkout.
- [ ] Add a short compatibility table, troubleshooting page and expected example outputs.
- [ ] Add issue templates for installation failures and processing bugs, plus contribution and support instructions. Ask for versions, parameters and sanitized errors, not public uploads of private survey files.
- [ ] Add `CITATION.cff` with accurate authorship. Use actual author names and identifiers supplied by contributors; do not invent ORCID identifiers or a DOI.
- [ ] Review release files and public examples for private survey information and retain existing licenses and third-party credits.

### Prepare a reproducible demonstration

Create one small example that works through both interfaces, with a documented
CRS, pixel size, NoData, parameters and expected outputs. A clearly labelled
synthetic GeoTIFF is sufficient for an initial analysis tutorial. A raw-XTF
tutorial needs a redistributable recording with clear permission or licensing;
the fact that a file was available for local testing does not establish that it
can be published.

Provide a runnable Python script or notebook and a matching QGIS walkthrough.
Include the input source, provenance/license, approximate storage and memory
requirements, tested software versions, expected output names and a reference
result. Keep a raw-conversion tutorial separate if its dependencies and runtime
make the first example too heavy. Do not relabel synthetic results as a survey
case study.

The current `.gitignore` excludes images, rasters and most data files. Add narrow
exceptions for approved documentation images if needed; keep raw survey and
working-output exclusions intact. Larger permitted datasets can be distributed
through a separate archive with checksums and a documented download step.

## 5. Python publication procedure

Configure verified owner accounts on TestPyPI and PyPI. These are separate
services with separate account databases. [TestPyPI guide](https://packaging.python.org/en/latest/guides/using-testpypi/)
Enable the required two-factor authentication on PyPI and securely retain
account recovery codes. Check the corresponding account requirements on
TestPyPI when setting it up. [PyPI account security](https://pypi.org/help/#two-factor-authentication)

Create GitHub environments and pending Trusted Publishers with these matching
values:

| Setting | Rehearsal | Production |
| --- | --- | --- |
| Project name | `seabed-sidescan` | `seabed-sidescan` |
| GitHub owner | `BezalelBenUri` | `BezalelBenUri` |
| Repository | `seabed-sidescan` | `seabed-sidescan` |
| Workflow filename | `publish-python.yml` | `publish-python.yml` |
| Environment | `testpypi` | `pypi` |

Apply the available environment review and branch controls before use. Pending
publishers can create a project on first publication, but do not reserve its
name. [Pending publisher setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
The prepared workflow uses a separate publishing job with short-lived identity
credentials. Account tokens do not need to be pasted into chat or stored in
source. [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)

1. Confirm the selected revision has passed all required CI checks.
2. Open **Actions → Publish Python distributions manually → Run workflow** and select `testpypi`.
3. Retain its wheel, source archive, checksums, commit SHA and public QGIS ZIP.
4. In a fresh environment outside the checkout, download only the candidate wheel from TestPyPI. Install that local wheel with its dependencies deliberately obtained from PyPI, avoiding ambiguous mixed-index dependency resolution.
5. Compare the downloaded checksum with the retained artifact. Run `pip check`, verify installed version and import location, run help/version commands, and complete the small raster example.
6. Correct any problems and repeat the relevant checks. Uploads cannot be treated as overwriteable files; choose a valid new candidate version where needed and keep package, plugin and engine version constants aligned.
7. Select `pypi` only after the rehearsal and release revision are reviewed. The current workflow rebuilds its selected commit; it does not automatically promote the exact bytes from a previous TestPyPI run. Preserve the new artifacts and verify their origin. If exact-byte promotion is required, implement it before publication.
8. Verify `python -m pip install seabed-sidescan==0.1.0` from a clean environment and check public metadata, documentation and license links.

After production publication, code changes require a new release such as 0.1.1.
Do not replace published files or move an already published release tag.

## 6. GitHub release, research archive and citation

Prepare a GitHub release tied to the actual successful release commit, tagged
`v0.1.0`. Attach the public QGIS ZIP, wheel, source archive, checksums and a
sanitized verification summary. Include installation links, formats, platform
limits, changes and known issues. CI artifacts expire; retain the intended
release assets with the release. [GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

Connect the repository to Zenodo before publishing the release intended for
archiving. Verify the resulting software record and citation metadata, then
add the genuine DOI to the public documentation and citation file. Keep a
version-specific citation available for reproducibility. Do not invent a DOI
or retag the published source merely to update a documentation link.
[Zenodo GitHub archiving](https://help.zenodo.org/docs/github/archive-software/github-upload/)

GitHub can display citation information from `CITATION.cff`. Include appropriate
software authorship while retaining dependency and SidescanTools attribution
in their existing notices. [Citation files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files)

## 7. QGIS publication procedure

Prepare QGIS submission alongside the Python rehearsal; the two distribution
channels are separate. The plugin includes its engine source and does not need
a public PyPI release URL for guided installation.

1. Verify public source, homepage, documentation and issue links; keep the compatible license and upstream notices.
2. Build with `python tools/build_qgis_plugin.py` and retain `seabed_sidescan_qgis-0.1.0.zip`, rather than the development ZIP, as the submission candidate.
3. Install that exact ZIP in a clean supported QGIS profile. Confirm setup, the shared example and useful failure messages.
4. Disclose runtime downloads, internet access during setup, installation storage requirements, Windows-only guided bootstrap and experimental JSF. Keep binaries out of the archive and stay within the directory's 25 MB ZIP limit.
5. Address the cross-platform question explicitly. QGIS recommends and reviewers expect cross-platform operation. Validate the manual engine path on other intended platforms or discuss the scoped support with reviewers; Windows-only validation is not evidence that every platform works, nor proof of automatic rejection.
6. Upload through the owner's OSGeo account, review automated findings and respond to reviewer requests. Approval timing is external to this plan.
7. Once approved, verify search, installation and displayed metadata in the official plugin manager. Current metadata marks the plugin experimental; explain the **Show also Experimental Plugins** setting where necessary.

The directory rules and reviewer process are described in the [publication requirements](https://plugins.qgis.org/docs/publish/) and [approval process](https://plugins.qgis.org/docs/approval/).
The experimental-plugin setting is documented in the [QGIS plugin manager guide](https://docs.qgis.org/testing/en/docs/user_manual/plugins/plugins.html).

## 8. Independent pilots and launch material

Recruit 3–5 relevant testers before broad promotion: a QGIS analyst who does not
code, a Python researcher and a hydrographer with compatible XTF data. Include
someone installing on a different machine. Ask each person to follow the public
instructions before providing assistance, then record:

- Whether installation and the example completed; software versions and hardware.
- Time to first useful output and the point at which instructions were unclear.
- Errors, workarounds and whether outputs were usable.
- Whether they would use it again, for which task, and which missing capability matters most.

Aim for at least one successful independent user of each interface. Obtain
permission before publishing anyone's name, comments, data or case study.

Prepare these reusable materials:

| Material | Content and purpose |
| --- | --- |
| 60–90 second demonstration | Show input, mosaic, texture and acoustic classes; show QGIS use and one equivalent Python call; add captions and a single installation link. |
| 5–10 minute tutorial | Install, run the shared example, explain outputs and resolve one common problem. |
| Three clear screenshots | Setup/toolbox, mosaic/texture and acoustic classification, with an honest legend and no private information. |
| Runnable example | Data/source instructions, script or notebook, QGIS steps, parameters and expected results. |
| Release page and FAQ | Who it serves, what it does, supported formats, requirements, limitations, citation and support. |
| Social preview | One readable project image consistent with the icon and screenshots, under 1 MB. GitHub recommends at least 640 × 320 pixels, ideally 1280 × 640. |

Use visible, understandable results rather than unsupported claims. Any speed
comparison should state data dimensions, hardware, dependency versions and
method. A polished image must not imply that a synthetic example is a measured
survey. [GitHub social preview guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)

## 9. Discovery and outreach

Start with people who already need sidescan processing. The strongest initial
message is a practical result with a working example. Tailor each post to its
audience and disclose that the author maintains the project. No posting or
contacting is performed by this plan.

| Audience and channel | Recommended approach |
| --- | --- |
| QGIS plugin directory | Main discovery route for noncoders once approval is confirmed. Link to the actual plugin listing. |
| QGIS users and relevant user groups | Share one user-focused tutorial; offer a short demonstration session. Read recent activity and follow the community's posting rules. |
| OSHydro | Propose a relevant project-directory entry and a reproducible sidescan example for its hydrographic open-source community. |
| Hydrographic and marine-mapping colleagues | Invite a small number of relevant researchers, instructors and survey users to test. Ask for feedback or a case study rather than stars. |
| LinkedIn and tutorial video | Explain one processing problem, show the result, identify intended users and link to installation and the example. Follow with useful troubleshooting or a case study. |
| Research labs and training programmes | Offer a reproducible exercise or short workshop. Provide citation metadata and clear format/platform limits. |
| Hydrographic publications | After an external use case exists, propose a technically grounded project story. Editorial acceptance is discretionary. |

Relevant official entry points are [QGIS support and community channels](https://qgis.org/resources/support/), [QGIS user groups](https://www.qgis.org/community/groups/list/), [OSHydro](https://www.oshydro.org/) and [Hydro International's editorial invitation](https://www.hydro-international.com/content/news/seeking-hydrographic-stories-share-your-expertise).

Do not send the same advertisement to many lists, buy engagement or substitute
manufactured activity for user adoption. Share a useful example, answer the
questions it produces and make the next user's installation easier. Paid
promotion can wait until ordinary users reliably reach a result.

### Suggested announcement structure, after release

> Seabed Sidescan 0.1.0 is available: open-source tools for processing side-scan sonar and producing acoustic facies maps through Python and QGIS. The shared workflow covers mosaics, masks, textures and unsupervised classification, with an optional XTF conversion backend. A small example and installation guide are available in the project repository. JSF remains experimental, and guided setup is currently validated on 64-bit Windows with QGIS 3.40.1. Feedback from hydrographers, GIS users and researchers is welcome through GitHub Issues.

Attach the actual demonstration and published installation links. If directory
approval is pending, replace any implication of official QGIS availability with
the manual ZIP installation route and its pending status.

## 10. Adoption targets and maintenance

These are internal planning goals, not forecasts or guaranteed outcomes.

| Period | Useful outcome |
| --- | --- |
| Before the main announcement | 3–5 pilot testers; at least two independent successful example runs covering both interfaces. |
| Release week | Working publication links, one short demonstration, one full tutorial and a small number of appropriate announcements. |
| First 30 days after launch | 5–10 confirmed users completing a workflow; a troubleshooting page based on actual installation questions. |
| Days 30–60 | Two external use cases, with permission, and one demonstration or training session if there is interest. |
| Days 60–90 | A feedback-driven maintenance release and a decision on the next compatibility or workflow improvement. |

Track reach, successful use and research use separately. Review repository
visitors, referrals, issues, completed examples, repeat users, case studies and
citations. Record weekly GitHub traffic observations because its visitor/clone
view covers the preceding 14 days. [GitHub traffic](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository)
Download counts do not establish unique or active users, and can be distorted
by caching, mirrors and automated activity. [PyPI download analysis](https://packaging.python.org/en/latest/guides/analyzing-pypi-package-downloads/)

Choose a realistic maintenance schedule, such as two issue-review sessions per
week. Prioritize incorrect output, data safety and installation failures before
cosmetic requests. Document decisions, keep release notes current and issue a
new version for published fixes. Use voluntary feedback initially; a usage
tracking system is not required for a successful launch.

After initial adoption, broaden XTF test coverage, obtain representative JSF
fixtures before promoting its status, measure representative workload memory
and runtime, and validate additional QGIS/platform combinations before making
new support claims. Keep new format readers outside the initial scope.

A software paper is a later credibility route. JOSS currently requires more
than six months of public development and research use, so a newly public
repository should not treat immediate acceptance as a launch task. Review the
full current authorship, disclosure and submission requirements when it becomes
appropriate. [JOSS submission requirements](https://joss.readthedocs.io/en/latest/submitting.html)

## 11. Next actions

1. Commit the reviewed documentation updates and confirm the full CI matrix passes on that revision.
2. Complete repository presentation and prepare a releasable example.
3. Configure TestPyPI/PyPI accounts and the exact Trusted Publisher/environment values above.
4. Complete the TestPyPI installation rehearsal and at least two independent pilot runs.
5. Publish PyPI 0.1.0 and its versioned GitHub release; submit the QGIS ZIP and handle review separately.
6. Launch the demonstration through a few relevant communities, then use installation feedback and external use cases to sustain interest.

Existing build commands and artifact checks are documented in [releasing.md](releasing.md).
Format limits are in [formats.md](formats.md), and the implementation evidence
and remaining software limits are in [quality_review.md](quality_review.md).
