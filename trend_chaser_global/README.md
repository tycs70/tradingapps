# Trend Chaser Global 1.0.0

One Windows desktop scanner with pinned Indices, ranked Forex and ranked Shares.
LONG rows are green, SHORT rows red; rankings use the EMA9 angle captured at an
observed EMA9/21 crossover on five-minute candles. Read-only Spotware cTrader demo
data supplies signals; trading on Olymp Trade remains manual.

The starting catalog contains 20 candidates: 3 indices, 10 currency pairs and
7 shares. Nine name matches are supported by the supplied screenshots. NASDAQ's
benchmark and Forex matches need verification in the connection screen before
they enter actionable rankings. Missing broker symbols stay visible in grey.

Extract the Windows ZIP and run `INSTALL.bat`. The private Python/Tk runtime and
all seven dependencies are included; installation needs no existing Python.
Use the separate Offline Sample Start Menu shortcut to inspect fictional data.

See [cTrader connection guide](docs/CONNECT_CTRADER.md) for application registration,
authorization, demo account selection, mapping verification and troubleshooting.
The app contains no order-placement operations. Keep client secrets and tokens
in the app; optional retention uses current-Windows-user DPAPI.

Development: Python 3.12+ x64; install `requirements.lock.txt` with hash checking.
Run `python -m unittest discover -v`, `python verify_install.py`, and
`python tools/benchmark.py`. A display is required for GUI tests.
Run `python run_app.pyw --demo` for offline sample mode.

Build: `python -m tools.fetch_windows_wheels`, then
`python tools/build_release.py --runtime /path/to/Nifty_Next50_1.0.2_Windows.zip`.
The uploaded reference ZIP and all its manifest entries must match pinned hashes
before the runtime is reused. Builds are deterministic, with an independent file
manifest and ZIP SHA-256. Wheel licenses remain inside the bundled wheels;
the runtime retains Python/Tcl/Tk licenses and protocol sources retain Spotware's license.

Automated Linux checks do not verify native Windows installation, DPAPI or an
authenticated cTrader stream. See `docs/VALIDATION.md` for final evidence.
