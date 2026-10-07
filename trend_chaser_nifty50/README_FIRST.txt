TREND CHASER NIFTY 50 - version 1.0.0
Windows 10/11 Intel/AMD x64.

This is the first separate Nifty 50 app, based on Trend Chase Version 1 1.0.1.
Signal rules, ranking, entry/removal rules and the seven-per-side layout are the same.
It scans current Nifty 50 shares with active stock options, using NSE Indices and
Upstox's instrument master on each connection. It places no orders.

1. Extract the COMPLETE ZIP to a folder. Do not run INSTALL.bat inside the ZIP.
2. Double-click INSTALL.bat. Private Python/Tk and dependencies are included;
   installation is offline, per Windows user, with no admin rights needed.
3. Open Trend Chaser Nifty 50 from your Desktop or Start Menu.
4. In Settings & Upstox, paste a current Upstox access token and connect.
   Internet is needed to load the current index list, instruments and live feed.
5. Remember Token uses Windows user-scoped DPAPI. Saved tokens can expire.
6. Start Menu > Trend Chaser Nifty 50 > Trend Chaser Nifty 50 Demo provides an
   offline preview using fictional sample data. demo.html and demo.png also preview it.

Program: %LOCALAPPDATA%\Trend_Chaser_Nifty_50\program
Data:    %LOCALAPPDATA%\Trend_Chaser_Nifty_50\data
Logs:    %LOCALAPPDATA%\Trend_Chaser_Nifty_50\data\logs

This app has separate settings, encrypted token, trend state, logs, shortcuts,
instance lock and Installed Apps entry. It does not replace Trend Chase Version 1.
Reinstalling this Nifty 50 app updates its existing installation and retains data.

The dashboard shows seven bullish and seven bearish shares side by side. The
lower pre-cross table is removed. The optional reference chart has its own tab.
Confirmed membership removal is a scanner event, not a trade exit.

If the current Nifty 50 list cannot be downloaded or validated, connection stops
with a clear error; the app never switches to scanning the full F&O universe.

Full usage and verification: app\README.md and app\docs\VALIDATION.md.
Native Windows installation and live Upstox/NSE connections require laptop validation.
