# Trend Chaser Nifty 50

Independent Windows desktop watchlist for five-minute NSE underlying-share trends using Upstox. Version 1.0.0, based on Trend Chase Version 1 layout update 1.0.1. The original Trend Chase and EMA scanner remain separate applications.

## Install and preview
Extract the complete Windows release ZIP, open the extracted folder and double-click INSTALL.bat. Use the existing Trend Chaser Nifty 50 Desktop shortcut after updating.

The per-user installer includes a private Python/Tk runtime and all pinned dependencies; no existing Python or administrator rights are needed. Windows 10/11 Intel/AMD x64 is required. This first Nifty 50 release creates its own installation. Reinstalling it updates only Trend Chaser Nifty 50 and preserves its settings, encrypted token, confirmed trend state and logs.

Before installing, open demo.html in the extracted release folder or view demo.png. After installing, use Start Menu > Trend Chaser Nifty 50 > Trend Chaser Nifty 50 Demo for an offline preview that does not load saved tokens or write live data. The normal app also has a Demo tab. Demo numbers are fictional layout samples for 7 October 2026, not a forecast or recorded market results.

## Current Nifty 50 universe
Each connection downloads the official Nifty 50 constituent CSV from NSE Indices and the current Upstox NSE instrument master. Membership is matched by ISIN, then restricted to underlying equities with unexpired stock-option contracts. Symbols follow the official list, including company renames. Only those matched shares are subscribed and scanned; the complete exchange master is not subscribed.

The constituent CSV must contain exactly 50 unique equity members with valid ISINs and symbols. A network failure or malformed list stops connection with a Nifty 50 error; it never substitutes all F&O shares or a dated bundled list. A constituent without a current option contract is excluded and named in Diagnostics. The eligibility and receiving counts show actual coverage. Index changes are picked up on the next connection.

## Seven-per-side dashboard
The Scanner tab displays bullish and bearish panels side by side, with seven visible rows each. The normal pre-cross table has been removed from the display; its underlying computation and events remain unchanged. All fourteen trend rows fit without scrolling at a 1200 by 680 window. Columns show rank, share, provisional/confirmed state, frozen crossover angle, current angle, live price and entry time in IST. Click a share for its EMA9, EMA21 and distance details. New visible rows receive a brief highlight. The optional reference chart opens in its own tab so it does not push dashboard rows off-screen.

## Two lists
The normal scanner retains the existing provisional EMA9/EMA21 pre-cross rules. The trend panels show up to seven bullish and seven bearish shares, ranked by the signed EMA9 angle captured at an observed crossover (descending direction-aligned strength).

LONG: EMA9 crosses above EMA21 with positive angle and price above EMA9. SHORT mirrors the rule. New members are provisional until the crossing candle closes with the correct EMA relationship and price on the correct side of EMA9. A live crossover reversal removes them.

Confirmed LONG members remain eligible until a completed five-minute candle closes below EMA9; confirmed SHORT members until a close above EMA9. Wicks, intrabar price movement and exact touches do not remove confirmed membership. This is a watchlist change; no order or trade-exit action is performed. A later setup follows the normal scanner rules, and another observed EMA crossover is required to rejoin the trend panels.

All eligible candidates are tracked. Only the top seven per side are displayed. Their order can change as other candidates join, leave or become unavailable, but each captured crossover score stays fixed. Current angle is a separate informational column. Distance from EMA9 describes extension and does not boost ranking.

## Connection and saved token
In Settings & Upstox, paste a current access token and connect. Remember Token is enabled by default on Windows. The token is protected for the current Windows user using DPAPI, never saved as plaintext or written to logs. Use Forget Token to remove it. Broker expiry still applies: replace an expired token. Live streaming requires Upstox permissions, Internet and the normal NSE session.

## Recovery, chart and logs
Fresh quotes and complete candle history are required for active rows. Paused rows are excluded from active ranking. Confirmed membership can survive a reconnect or same-day restart, but every completed candle since capture is checked before it returns; an adverse close during a gap removes it even if price subsequently recovered. Provisional state does not survive true continuity loss. Membership resets each IST trading day, with a fresh history check on rollover.

The reference chart is hidden by default. Show Chart opens the Reference Chart tab; angle calculation is unchanged. Geometry uses 60 candles by default, a 2:1 plot and a two-interval EMA9 chord. Angle depends on this reference geometry and can differ from an independently zoomed broker chart.

App data is independent at %LOCALAPPDATA%\Trend_Chaser_Nifty_50\data. Daily JSONL logs in data\logs include normal signal events and trend add/confirm/remove events with available price, EMA values, captured angle and candle time. Confirmed trend snapshots are saved asynchronously and drained on graceful shutdown. Reinstallation preserves this app's data; uninstall retains it unless explicitly removed. Other scanners' files/settings/shortcuts are untouched.

## Independent Windows installation
Program files and the private runtime live in %LOCALAPPDATA%\Trend_Chaser_Nifty_50\program. The installer uses its own .trend-chaser-nifty50-owned marker, HKCU uninstall entry Trend_Chaser_Nifty_50, Desktop shortcut Trend Chaser Nifty 50, and Start Menu folder Trend Chaser Nifty 50. Main and offline Demo shortcuts use the packaged custom icon. It refuses a pre-existing root without the matching ownership marker and refuses replacement while the app holds its instance lock.

Uninstall using Windows Installed Apps > Trend Chaser Nifty 50, with the app closed. This removes program files, shortcuts and the app's registry entry while retaining data. To deliberately erase retained data, run the installed uninstall.ps1 with -RemoveData. Reinstall the same ZIP to restore the program with retained settings; confirmed state still requires same-day market revalidation.

## Development and release verification
From trend_chaser_nifty50/ with Python 3.12+ x64 and the pinned dependencies installed:

```sh
python -m unittest discover -v
python verify_install.py             # requires a display; --no-display omits Tk rendering
python tools/benchmark.py            # synthetic 210-stock burst, no broker credentials
python -m tools.repackage_release --base /path/to/extracted/Trend_Chase_V1_1.0.0 --output dist
# Alternatively rebuild the runtime from the pinned original source archive:
python tools/build_release.py --runtime /path/to/authenticated-runtime.tar.gz
python tools/build_release.py --verify build/release/Trend_Chaser_Nifty_50_1.0.0
```

Linux GUI tests require Tk and a running display, such as Xvfb. The builder accepts only the pinned runtime SHA-256 and the complete 12-wheel Windows set. Installer dependencies use --no-index and --require-hashes; package hashes are checked before installation. PowerShell tests/test_installer.ps1 exercises safe paths, ownership, swap/rollback, retained data and corruption without Windows registry or shell access.

## Validation limits
See docs/VALIDATION.md for actual test and package results. Linux GUI checks and installer filesystem checks do not establish native Windows shortcut/registry/DPAPI behaviour or authenticated Upstox feed readiness. Validate on the target laptop and compare EMA values with five-minute underlying-share charts before relying on alerts.
