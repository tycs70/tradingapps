EMA PRE-CROSS SCANNER 1.0.1 - WINDOWS 10/11, INTEL/AMD 64-BIT

1. Extract the complete ZIP first (right-click > Extract All).
2. Open the extracted EMA_PreCross_Scanner_1.0.1 folder.
3. Double-click INSTALL.bat. No administrator rights or existing Python required.
4. Open EMA Pre-Cross Scanner from the new Desktop shortcut.
5. In Settings & Upstox, paste your current Upstox access token.
   Tick Remember token if you want it saved, then click Connect.
   The saved token is encrypted for your Windows user account and filled in on
   the next launch. Click Connect to use it. Expired tokens still need replacing.
   Untick Remember token to delete the saved token. Do not share tokens in chat.

UPDATING FROM 1.0.0
Close EMA Pre-Cross Scanner, extract this new ZIP and run its INSTALL.bat.
No uninstall is needed. Existing settings and logs are retained.

The installer includes its private Python/Tk runtime and every dependency.
Installation is offline. Live scanning needs Internet and an Upstox account
with market data access. Never run INSTALL.bat from inside the unopened ZIP.

RULES
Five-minute underlying equity EMA9 / EMA21, both bullish and bearish.
ARMED means near crossover, still provisional. Default gap is <= 0.05% of LTP.
Bullish: EMA9 below EMA21, rising, converging, positive reference-chart angle.
Bearish: EMA9 above EMA21, falling, converging, negative reference-chart angle.
Rank is by current direction-aligned EMA9 chart angle. No ATR is used.
The board shows up to the Top 20 fresh ARMED stocks in the selected All,
Bullish or Bearish view. It shows fewer when fewer stocks qualify.
Scanning, Diagnostics and Events still cover the full eligible universe.
Chart defaults: 60 candles, 2:1 aspect ratio, chord over two intervals.
A fast jump may cross without an earlier ARMED observation.
The app scans the current stock-option eligible universe, approximately 210
underlyings, not a fixed list. Counts and paused-stock reasons are visible.
Startup history loading can take a few minutes; independently ready stocks scan
while others load. Stale or incomplete data is excluded from actionable ranking.
This release is a share-signal scanner and does not place orders.

INSTALL / REMOVE
Install folder: %LOCALAPPDATA%\EMA_PreCross_Scanner
Settings / logs / encrypted token: data subfolder in that install folder.
Close the app before re-running INSTALL.bat. App data is retained.
Remove via Windows Settings > Apps > EMA Pre-Cross Scanner > Uninstall.
Uninstall retains app data by default; untick Remember token before removal
if you want to forget the token.
Old applications are independent and are not changed by this installer.

VALIDATION
Automated strategy, data, state, desktop UI and package checks were run in the
Linux cloud build environment. Native Windows installation and authenticated
Upstox live streaming require testing on a Windows laptop. The installer itself
checks Python, Tk, dependencies and Windows token protection before applying
the staged installation.
Before relying on alerts, compare EMA values and times with a five-minute
Upstox share chart and check that eligible/subscribed/ready counts are correct.
See app\docs\VALIDATION.md and app\README.md for details and source.
