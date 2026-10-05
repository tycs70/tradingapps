# EMA Pre-Cross Scanner

Fresh Windows desktop Upstox scanner for near EMA9/EMA21 crossovers on five-minute NSE underlying shares. Both LONG and SHORT use mirrored rules. It ranks **fresh ARMED** setups by the signed slope of EMA9 on its own inspectable reference chart. It does not use ATR, place orders or select option strikes.

Extract the release ZIP and run `INSTALL.bat`; use the new Desktop shortcut. The installer bundles a private Python/Tk runtime and all pinned dependencies, creates Start Menu and Installed Apps entries, preserves this app's settings/logs on reinstall, and does not depend on old apps. Windows 10/11 Intel/AMD x64 is required.

Paste a current Upstox token in Settings & Upstox. Enable **Remember token** to save it with Windows DPAPI protection for the current user. The token is stored as an encrypted binary file in this app's data directory, never in settings or logs. It is filled into the masked input on the next launch; click Connect to use it. Connect also reuses the saved token if the input is empty during the same session. Untick Remember token to remove the saved file. Expired Upstox tokens still need replacing. The input is cleared after connection; with Remember token disabled, the app keeps the token only in memory.

The board shows the **Top 20 fresh ARMED** stocks in the selected All, Bullish or Bearish view. Direction filtering happens before the limit. Fewer than 20 are shown when fewer qualify; scanning, Diagnostics, Events and ready-stock charts still cover the full universe. Live data requires a normal NSE session, a fresh quote (15 seconds), and verified historical candle coverage. Watch coverage and Diagnostics while history warms; the current stock-option universe determines the eligible count.

Version **1.0.1** updates the existing install: close the app, extract the new ZIP and run its `INSTALL.bat`. Existing settings, logs and encrypted token are preserved. Uninstall also retains app data by default, so forget the token in Settings first if you want to remove it.

Default pre-cross proximity is `100 * abs(EMA9 - EMA21) / LTP <= 0.05%`. LONG requires EMA9 below EMA21, rising relative to its previous closed value, a narrowing gap and a positive angle. SHORT mirrors those conditions. Every tick derives its provisional EMA from the last completed candle's EMA. The reference chart uses 60 candles, a 2:1 plot, 5% padded price range held within the candle, and a two-interval EMA9 chord. External zoom/aspect changes produce different visual angles. A gap in received data resets crossover observation continuity; initial observations never invent previous cross times.

The release has automated Linux strategy/data/GUI/package validation. **Native Windows installation and authenticated Upstox streaming have not been run in this cloud build.** Validate displayed EMA values and coverage against the broker chart before relying on alerts. See [validation](docs/VALIDATION.md) and [approved design](docs/superpowers/specs/2026-10-05-ema-pre-cross-scanner-design.md).

Development (Python 3.12):

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
.venv/bin/python -m unittest discover -v
.venv/bin/python tools/benchmark.py
.venv/bin/python verify_install.py --no-display
```

GUI tests need a display (Xorg dummy/Xvfb in Linux or Windows desktop). The release builder consumes the verified Astral Windows runtime archive and twelve Windows/pure-Python wheels in `build/wheels`:

```sh
python3 tools/build_release.py --runtime /path/to/cpython-3.12.15-windows-x86_64.tar.gz
python3 tools/build_release.py --verify build/release/EMA_PreCross_Scanner_1.0.1
```

Runtime provenance and original archive digest are retained in the package manifest. Python/Tcl/Tk and wheel distributions retain their bundled third-party license files. Application code is newly implemented for this project; uploaded older application folders remain separate.
