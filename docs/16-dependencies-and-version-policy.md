# 16 — Python and dependency version policy

## Status and scope

This is the documentation target for a production-oriented proof of concept. It records what the repository currently declares and the version controls still needed before a reproducible release. This chapter does not claim that a new dependency lock or container build has been verified.

## Python and infrastructure baseline

| Component | Documented baseline | Current repository state |
|---|---|---|
| Python runtime | CPython 3.12.x, same minor version on developer machines, CI, and containers | The Playwright image uses Ubuntu 24.04 Noble, whose default Python is 3.12; the Dockerfile does not pin a Python patch release |
| Browser image | `mcr.microsoft.com/playwright/python:v1.55.0-noble` | Fixed tag in `Dockerfile`; browser binaries match Playwright 1.55.0 |
| PostgreSQL | Major version 17 | `postgres:17` in `compose.yaml`; the image tag can move to a newer 17.x patch release |
| Operating system | Ubuntu 24.04 LTS in the application image | Defined by the Playwright Noble image |

Python 3.12 is the proposed project baseline because Ubuntu 24.04 defaults to it. The exact Python patch version must be recorded from the chosen image when an immutable image digest is selected. Do not assume a developer's `python3` executable is 3.12 without checking it.

References: [Ubuntu's Python version table](https://ubuntu.com/developers/docs/reference/availability/python/), [Playwright's Docker guidance](https://playwright.dev/python/docs/docker).

## Direct Python packages

The table is an inventory of every third-party package explicitly declared by this repository. The **declared version** column reproduces the dependency files; a range is not an exact installed version.

| Package | Import or purpose | Declared version | File | Used by |
|---|---|---|---|---|
| Playwright | `playwright`, browser capture | `==1.55.0` | `requirements.txt` | Runtime, tests that exercise browser integration later |
| OpenCV, headless build | `cv2`, image decoding and ROI processing | `==4.11.0.86` | `requirements.txt` | Runtime, synthetic image tool, tests |
| NumPy | `numpy`, image arrays | `>=1.26,<3` | `requirements.txt` | Runtime, synthetic image tool, tests |
| PyYAML | `yaml`, table configuration | `>=6.0,<7` | `requirements.txt` | Runtime, synthetic image tool, tests |
| XlsxWriter | `xlsxwriter`, Excel reports | `>=3.2,<4` | `requirements.txt` | Runtime, report tests |
| Psycopg 3 with binary package | `psycopg`, PostgreSQL access | `>=3.2,<3.4` | `requirements.txt` | Runtime, database tests, legacy import |
| python-docx | `docx`, DOCX handbook generation | `==1.2.0` | `docs-requirements.txt` | Documentation build only |
| ReportLab | `reportlab`, PDF handbook generation | `==4.4.4` | `docs-requirements.txt` | Documentation build only |

The `psycopg[binary]` extra also installs a matching `psycopg-binary` distribution. Other packages may pull in further indirect distributions; their exact names and versions belong in the future resolved lock, not in a guessed list.

The Python standard library supplies `argparse`, `asyncio`, `collections`, `csv`, `dataclasses`, `datetime`, `hashlib`, `html`, `json`, `math`, `os`, `pathlib`, `re`, `sqlite3` (legacy import only), `tempfile`, `textwrap`, `time`, `typing`, `unittest`, `uuid`, `zipfile`, and `zoneinfo`. These modules do not belong in a pip requirements file. PostgreSQL, Chromium, and browser system libraries are external runtime components, not pip packages.

## Reproducibility gap and release policy

The four packages with `>=` constraints can resolve to different versions on different build dates. Direct pins also do not pin their indirect dependencies. For that reason, the current dependency files are a **version policy for the POC**, not a complete production lockfile. The repository does not yet contain an exact, hash-checked lock of the full Python dependency graph. No exact transitive version should be inferred from this document.

Before a production-oriented release:

1. Choose an immutable application-image digest and PostgreSQL-image digest. Record the Python 3.12 patch version present in the application image.
2. Keep a short list of direct dependencies, resolve it under Python 3.12 on the target Linux architecture, and commit an exact lock containing every direct and indirect distribution and its hashes. Lock documentation-build packages separately from runtime packages.
3. Install from the committed lock in CI and in the application Dockerfile. Keep the Playwright Python package version equal to the browser image version.
4. Rebuild and run the unit, PostgreSQL integration, browser smoke, documentation-build, and security checks after every dependency update. Record the lock revision, image digests, and test result for each release.
5. Review PostgreSQL major upgrades separately, including backup and restore. Allow controlled patch updates only after validation.

These steps are release requirements, not a claim that the current POC has already completed them. Do not change `requirements.txt`, `docs-requirements.txt`, or Docker images solely by copying suggested numbers from documentation; resolve and test the complete graph first.
