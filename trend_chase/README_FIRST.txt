TREND CHASE VERSION 1 - version 1.0.0
Windows 10/11 Intel/AMD x64. Independent from EMA Pre-Cross Scanner.

1. Extract the COMPLETE ZIP to a folder first. Do not run INSTALL.bat inside ZIP.
2. Preview demo.html in a browser or open demo.png before installing.
3. Double-click INSTALL.bat. Private Python/Tk and all dependencies are included;
   installation is offline, per Windows user, with no admin rights needed.
4. Open Trend Chase Version 1 from the Desktop or Start Menu.
5. To preview without a broker or saved token, use Start Menu > Trend Chase
   Version 1 > Trend Chase Version 1 Demo. Its data is fictional SAMPLE DATA.
6. For live data, Settings & Upstox accepts a current Upstox access token.
   Remember Token defaults on with Windows user-scoped DPAPI. Saved tokens can
   expire. Forget Token removes the encrypted saved token.

Location: %LOCALAPPDATA%\Trend_Chase_V1\program
Data:     %LOCALAPPDATA%\Trend_Chase_V1\data
Reinstall preserves this app's settings, token, logs and confirmed trend state.
Windows Installed Apps uninstall retains data by default. To erase retained
data deliberately, close the app and use the installed uninstall.ps1 -RemoveData.
The original scanner's installation and data are separate.

Top 5 Bullish / Top 5 Bearish rank by fixed crossover angle strength. Current
angle is informational. A completed close strictly across EMA9 removes trend
membership; it does not place orders or close trades. Wicks and touches do not
remove confirmed membership. Charts start hidden behind Show Chart.

Full usage, verification and known limits: app\README.md, app\docs\VALIDATION.md.
Linux checks do not prove native Windows installation/shortcuts/DPAPI or live
Upstox behaviour. Demo is a layout illustration, never a prediction.
