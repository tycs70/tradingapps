# Trend Chase Version 1 validation

Version 1.0.0. Checks executed on 6 October 2026 in the isolated Linux cloud
checkout, using Python 3.12 x64, Tk on an Xorg dummy display :98, and PowerShell 7.5.3.
The results below distinguish cross-platform checks from native Windows checks.

## Tests and startup

Working directory: trend_chase/.

| Command | Actual result |
| --- | --- |
| `DISPLAY=:98 /workspace/tradingapps/.venv/bin/python -m unittest discover -v` | 118 tests: 117 passed, one skipped; zero failures/errors; final run 9.190 seconds. |
| `DISPLAY=:98 /workspace/tradingapps/.venv/bin/python verify_install.py` | Passed Python x64/dependencies, V3 protobuf decoding, EMA, mirrored trend lifecycle, offline samples and real Tk Demo tables. |
| `.../pwsh -NoProfile -File tests/test_installer.ps1` | Passed quoted/Unicode paths, unsafe manifest paths, wrong ownership markers, atomic program swap/rollback, retained settings/trends/token fixture/logs, corruption/missing/unexpected file rejection. |
| PowerShell `Parser.ParseFile` over installer/tests scripts | Four scripts parsed without errors. |
| `/workspace/tradingapps/.venv/bin/python tools/benchmark.py` | 210 stocks, all 420 transitions; 0.7239 seconds; event latency p99 684.813 ms, maximum 712.368 ms. |
| `git diff --check` | Clean. |

The sole skipped test is
`tests.test_credentials.TokenStorageTest.test_native_windows_roundtrip_and_tamper_rejection`:
native Windows DPAPI is unavailable on Linux. The verifier explicitly reports
this boundary and verifies that unavailable protection creates no plaintext
fallback. On Windows, installation requires a disposable synthetic DPAPI
roundtrip, encrypted-file check and damaged-blob rejection; no user credential
is read by the verifier.

The offline verifier exercises observed LONG/SHORT add, completed-candle
confirmation, fixed crossover score/current-angle separation, equality/wick
retention, adverse-close removal and no resurrection. It checks ten trend and
three normal samples, standalone HTML equality with the shared sample model,
empty live membership after an offline connect call, charts hidden by default,
and no settings writes. The full suite additionally covers gap recovery,
same-day persistence, new-day reset, ranking, normal pre-cross behaviour, token
controls, demo error-path isolation and responsive chart geometry.

The benchmark uses a synthetic processing queue. It excludes broker/network
latency, Windows rendering, market data quality and real trading performance.
The Demo PNG is an actual Tk desktop capture; the HTML is standalone with
embedded SVG and requires no remote resources. Neither contains market results.

## Artifact integrity and package

The prior verified 1.0.1 ZIP is used only as a trusted source of pinned wheels.
Its SHA-256 is
`8b464695b0a34aef54c9fd2fb2f6c1bc01b161eb78e11b9d1689d4c2e47a06af`.
All 53 manifest file hashes were independently checked and all twelve copied
Windows wheel hashes match that manifest.

The authoritative CPython 3.12.15 Windows x64 runtime source archive has SHA-256
`6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402`.
The builder checks this exact hash before converting it into runtime.zip, then
requires Python/pythonw, pip, _tkinter and Tcl/Tk library entries. No TLS or
integrity check was disabled.

Build and verify using:

```sh
python tools/build_release.py --runtime /path/to/cpython-3.12.15-windows-x86_64.tar.gz
python tools/build_release.py --verify build/release/Trend_Chase_V1_1.0.0
```

The output is `Trend_Chase_V1_1.0.0_Windows_x64.zip` plus a `.zip.sha256`
companion. The package manifest covers source, tests, build tools, approved
design/plan, this validation record, PNG/multisize ICO assets, app and standalone
demo HTML/PNG, README_FIRST, installer/helpers/uninstaller, runtime.zip, all
twelve wheels and their hash-required Windows lock. Root-level demo.html and
demo.png can be previewed immediately after extraction.

Installer and uninstaller identity is independent: root `%LOCALAPPDATA%\Trend_Chase_V1`,
marker `.trend-chase-v1-owned`, own HKCU uninstall key, own Desktop link and
Start Menu folder. Main and offline Demo shortcuts use `app\assets\trend-chase.ico`.
Reinstall swaps only program files; uninstall retains data unless `-RemoveData`
is explicitly requested. Original scanner source and old release artifacts
remain unchanged.

## Target laptop checks still required

Native Windows installation, WScript shortcuts, Windows registry integration,
native DPAPI, and authenticated Upstox/live-market behaviour were not executed
in this Linux environment. PowerShell parsing and filesystem tests do not
establish those capabilities. On the target Windows 10/11 Intel/AMD x64 laptop,
extract and install, check both shortcuts and the Installed Apps entry, open
the offline Demo, then connect with a current authorized token and compare
EMA values to five-minute underlying-share charts. Saved tokens can expire;
Remember Token does not extend broker validity. This watchlist has no order or
trade-exit actions.
