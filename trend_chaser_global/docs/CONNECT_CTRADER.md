# Connect Trend Chaser Global to your Spotware demo account

The app reads cTrader prices and calculates the Trend Chaser signals. You place any trade manually in Olymp Trade. Logging in to cTrader Desktop alone does not authorize this separate app to read your account through Open API.

## 1. Register your cTrader Open API application

1. Open **https://openapi.ctrader.com/** in your browser and sign in with the cTrader ID that owns your Spotware demo account.
2. Open application management and create an application for **Trend Chaser Global**. Supply the actual application/contact details requested by the portal.
3. Register this redirect URI exactly: **`http://localhost/`**. Keep the trailing slash. The same value must appear in the app's Connection screen.
4. Complete any activation or approval required by Spotware. A demo trading account is supported, but the API application still has to be authorized. If the portal reports pending approval, wait for activation before trying to connect.
5. Keep the application's **Client ID** and **Client Secret** private. Enter them only in the app's masked connection controls. Do not send them in chat or include them in screenshots.

The app uses Spotware's Open API service, not a cTrader Algo robot. It does not need the cTrader Desktop window to stay open after authorization.

## 2. Authorize read-only access

1. Start **Trend Chaser Global** and open **Connection**.
2. Enter **Client ID**, **Client Secret**, and **Redirect URI** (`http://localhost/`).
3. Click **Open read-only authorization**. Your browser opens the official cTrader authorization page.
4. Sign in with the same cTrader ID and grant access to the Spotware demo account. The app requests the `accounts` scope for reading account/market data; it does not request trading permission.
5. After approval, the browser redirects to a URL like `http://localhost/?code=...`.

This version uses a manual authorization-code handoff. There is no local web server, so the browser may show that localhost cannot be reached. If the address bar contains the returned `code`, that page error does not mean the authorization failed. Copy the full redirect URL from the address bar, or just its code value.

6. Paste it into **Authorization code / redirect URL** in the app, then click **Exchange code**. Codes are temporary; generate a fresh one if it has expired or was already used.

The app exchanges the code directly with the official HTTPS token endpoint. The Client Secret, code and tokens are not written to diagnostic/event logs.

## 3. Select the demo account and load prices

1. Click **Load demo accounts**.
2. Select the account labelled **Spotware**, checking its displayed account login against cTrader Desktop.
3. Click **Connect data**.

The app obtains the internal API account ID from cTrader. Do not type the desktop account login into an API account-ID field: they are different identifiers. Live accounts are not accepted by this demo-only version.

A single authenticated connection supplies Indices, Forex and Shares. During startup, each row shows its progress while the app discovers symbols and loads at least 100 completed five-minute candles. Independently ready instruments can scan while other rows warm up.

The connection uses encrypted, certificate-verified TLS to `demo.ctraderapi.com` on TCP port **5035**. Authorization uses `openapi.ctrader.com` over HTTPS. If a firewall blocks these destinations, permit the official services; do not turn off certificate verification.

## 4. Check instrument matches

Open the instrument-mapping controls in Connection. Check the actual cTrader symbol, its description and its trading schedule against the instrument shown in Olymp Trade.

- The screenshot-supported starting matches are S&P 500 / US 500, Dow Jones / US 30, Apple, Caterpillar, Mastercard, Boeing, Exxon Mobil, Walmart and Goldman Sachs.
- For **NASDAQ / US TECH 100**, confirm in Olymp Trade's asset information that its benchmark is **Nasdaq-100**.
- The ten Forex pairs shown in Spotware are available as candidates. Their availability in your Olymp Trade account must still be checked.
- Mark a pending row **Olymp match verified** only after checking the same underlying instrument. The app records this locally for the selected account/symbol mapping.

An unresolved, ambiguous or unverified instrument stays visible with an explanation and does not earn an actionable cross-platform rank. Adding a symbol to a cTrader watchlist alone does not establish that it also exists on Olymp Trade.

cTrader instruments may be broker CFDs with different prices, spreads, sessions and candle construction from Olymp Trade. The mapping identifies the intended underlying; it does not make the two prices identical. Check Olymp Trade's current availability when you trade there.

## 5. Read the dashboard

- **Indices** stay above the scrollable lower dashboard. **Forex** and **Shares** have their own independent rankings.
- Green **LONG** and red **SHORT** identify qualifying trends. The state column distinguishes **PROVISIONAL** from **CONFIRMED**.
- Ranking uses the **9 EMA angle captured at the qualifying EMA9/EMA21 crossover**. A stronger direction-aligned captured angle ranks first. Current angle is informative and does not change the captured score.
- A new trend requires an observed live crossover. Startup history alone does not invent one, even if EMA9 is already above or below EMA21.
- A provisional row confirms only after its crossing five-minute candle closes on the correct side with the correct EMA relationship.
- Confirmed trends survive wicks and exact EMA9 touches. A completed close across EMA9 or an opposing EMA crossover ends that trend.
- Grey rows explain waiting, closed markets, stale quotes, missing history or an unverified match. A quote older than 15 seconds is not actively ranked.

Use five-minute cTrader charts with EMA9 and EMA21 applied to the close to compare EMA values and completed candle times. The app uses the cTrader bid-price series. Its angle is measured on its own fixed reference chart geometry, so a differently zoomed chart can show a different visual slope.

Times are displayed in **IST**. Broker calendars control whether each instrument's market is open. The daily trend-membership reset defaults to **17:00 America/New_York**, with daylight-saving adjustment, so an IST midnight does not interrupt an active US session.

## 6. Remember, refresh or forget authorization

On Windows, **Remember credentials** uses DPAPI protection for the current Windows user. There is no plaintext fallback. Copying the app to another Windows user does not transfer usable saved credentials. On non-Windows development machines, credentials remain in memory only.

Access tokens expire. The app renews them using the refresh token when needed and retains the replacement securely if remembering is enabled. If renewal fails, generate fresh authorization. If the app reports that protected retention failed, the current memory session may still work, but the next startup can require authorization again.

Use **Forget credentials** to remove saved authorization. Settings and confirmed-trend state are separate from the credential file. App data lives in `%LOCALAPPDATA%\Trend_Chaser_Global\data`.

## Troubleshooting

| What you see | What to check |
|---|---|
| Application authorization rejected | API application activation, Client ID and Client Secret; generate fresh authorization after correcting them. |
| Redirect mismatch or missing code | Use the exact same registered URI, including slash/port/path; copy the final returned URL containing `code`. |
| No demo account | Authorize the cTrader ID and demo account shown in Desktop. The app cannot use a live account on the demo endpoint. |
| Symbol unavailable or ambiguous | Inspect the account's complete symbol catalog and choose/check the intended mapping. |
| History warming or recovery | Keep the connection open; inspect per-row reasons. Missing completed bars prevent a valid signal. |
| Grey stale row | Check market hours and network delivery. The app will not extend an old quote's freshness. |
| Certificate or connection failure | Check the device clock, trusted certificate configuration, firewall and official service access. Keep TLS verification enabled. |

The **Offline sample** is available without registration or credentials and uses fictional data. It demonstrates the interface, not an authenticated connection or trading results.
