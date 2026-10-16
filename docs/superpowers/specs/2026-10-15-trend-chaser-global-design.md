# Trend Chaser Global 1.0.0 — design for review

Date: 15 October 2026. The user approved the conversational design and requested a new icon, an interesting display and instructions for connecting to cTrader. This written specification awaits review. Application implementation has not started.

## Purpose and delivery

Build one independent Windows 10/11 x64 desktop app that follows indices, Forex and shares using the user's Spotware cTrader demo account. Calculate signals locally and let the user place trades manually on Olymp Trade. Preserve the trading rules of the supplied Nifty Next 50 Trend Chaser 1.0.2, including ranking by the **9 EMA angle captured at a qualifying crossover**. Current angle remains a separate value.

Use the working name **Trend Chaser Global**, version 1.0.0. Deliver source, an offline Windows installation ZIP and SHA-256 file, an original application icon, an offline visual demo, validation results and a practical cTrader connection guide. Install separately from all previous scanners with its own data, credentials, shortcuts and uninstall entry. Do not modify the existing scanner or the uploaded archive.

Work in the existing isolated checkout at `/workspace/tradingapps`; no additional Git worktree is needed. Put the new app in a separate `trend_chaser_global/` source tree. Keep existing root application files, tests, requirements, installers and releases intact.

## Dashboard

Use one window with three distinct sections in this order:

1. **Indices:** pinned above the lower dashboard. Rank its qualifying trends independently.
2. **Forex:** independently ranked currency pairs below the index section.
3. **Shares:** independently ranked shares below Forex.

Keep the index section visible while scrolling the lower area. Each asset table supports scrolling and retains its strongest qualifying rows at the top. Size the layout for a typical 1366 × 768 Windows laptop and support a larger resizable window. The lower dashboard scrolls when needed; the design does not require every instrument to fit simultaneously. Retain selection by instrument identity during ranking changes.

Within each group, combine bullish and bearish candidates in one ranked table. Green tint plus a LONG label identifies bullish signals; red tint plus SHORT identifies bearish signals. Neutral, closed, unavailable, unverified and stale rows remain visible in grey below qualifying candidates, with a specific status. A row's direction must not depend on color alone. Historical EMA alignment alone must not be labelled a newly observed qualifying crossover.

Show rank, asset, direction, provisional/confirmed status, captured 9 EMA angle, current 9 EMA angle, cTrader price and crossover time. Put additional EMA values, distance from EMA9 and quote time in the selected-row details/reference chart. Display times in IST. Label the source prominently as **cTrader · Spotware Demo**, and distinguish it from the separate **OFFLINE SAMPLE** mode.

Use a dark navy background, clearly separated panels, teal/cyan accents, readable typography, prominent rank numbers and restrained row highlights. Refresh snapshots about once per second without recreating the whole interface. Keep the optional reference chart outside the main ranking area. Provide Connection, Events, Diagnostics and Help views, plus an offline sample that never uses credentials or saves live trend membership.

Create an original icon: a compact orbital/globe motif with an ascending EMA curve, readable at small sizes. Avoid reproducing cTrader or Olymp Trade branding. Supply a transparent PNG master and a multi-resolution Windows ICO, and apply the icon to the app and shortcuts.

## Trend rules and ranking

Retain these semantics from the supplied source:

- Use five-minute candles and EMA9/EMA21. Derive each tick's provisional EMA from the last completed EMA; repeated ticks do not advance the completed series.
- A LONG candidate requires an actually observed EMA9 crossover above EMA21, positive 9 EMA angle and price above EMA9. SHORT mirrors those conditions.
- Capture the signed EMA9 angle at that qualifying crossover. Preserve the reference geometry: 60 candles by default, 2:1 plot, padded held price scale and a two-interval EMA9 chord.
- New candidates are PROVISIONAL. Confirm only when the crossing candle has completed with the correct EMA relationship and its close strictly on the qualifying side of EMA9. A live crossover reversal removes an opposing candidate.
- A confirmed LONG remains until a completed candle closes strictly below EMA9; SHORT remains until a completed close strictly above EMA9. An opposite EMA crossover also ends the old candidate. Wicks and exact touches do not remove confirmed membership.
- A removed candidate needs another observed qualifying crossover to rejoin. Startup, reconnect and historical data must not invent a crossover.

Define ranking strength as the captured angle for LONG and the negative of the captured angle for SHORT. Sort each section by strength descending, crossover time ascending and instrument identity as a stable final tie-break. For example, +40° LONG and −40° SHORT have equal direction-adjusted strength; both outrank a 20° qualifying move. Provisional and confirmed candidates use the same strength metric and show their state explicitly. Current angle and percentage price change do not replace the captured ranking score.

Only candidates with fresh quotes, validated history and complete revalidation are actively ranked. Preserve confirmed candidates internally through temporary disconnection, but check every completed candle since capture before restoring them. Discard provisional candidates after continuity loss. Missing or stale data must never continue to look actionable.

## Instruments and evidence

Discover the selected account's complete symbol catalog through Open API. Broker symbol IDs are account/server-specific: never hardcode them or assume a displayed login number is the internal account ID. Match normalized names and descriptions through an explicit mapping, and show ambiguous or missing symbols instead of silently substituting a different instrument.

The screenshot-supported starting catalog is:

| Group | Olymp Trade name | cTrader display name | Evidence status |
|---|---|---|---|
| Index | S&P 500 | US 500 | Name/benchmark mapping supported by screenshots |
| Index | Dow Jones | US 30 | Name/benchmark mapping supported by screenshots |
| Index | NASDAQ | US TECH 100 | Verify that Olymp Trade's benchmark is Nasdaq-100 |
| Share | Apple | APPLE | Company name shown on both platforms |
| Share | Caterpillar | CATERPILLAR | Company name shown on both platforms |
| Share | MasterCard | MASTERCARD | Company name shown on both platforms |
| Share | Boeing | BOEING | Company name shown on both platforms |
| Share | Exxon Mobil | EXXON | Company name shown on both platforms |
| Share | Walmart | WAL-MART | Company name shown on both platforms |
| Share | Goldman Sachs | GOLDMAN SACHS | Company name shown on both platforms |

The ten Forex candidates shown in cTrader are EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD, EUR/JPY, GBP/JPY and EUR/GBP. Their Olymp Trade availability has not been established by the supplied screenshots.

This supplies 20 candidate rows across the three sections, not proof of 20 common instruments. The nine supported name matches still require successful cTrader catalog resolution at connection. NASDAQ and the Forex candidates retain a visible **Olymp match unverified** status until their matching instruments are checked. Do not invent additional matches to reach a stated asset count. The layout and watchlist configuration support future verified additions without a code change.

Show quotes/details for catalog-resolved pending candidates, but keep them out of the cross-platform actionable ranking until the user verifies their Olymp Trade match in the mapping settings. Persist that verification locally with the account/symbol mapping. User confirmation attests instrument identity, not identical prices or permanent trading availability. cTrader prices, sessions and candle boundaries may differ from Olymp Trade's; the app cannot certify Olymp Trade's current availability without an Olymp feed.

## cTrader connection and data flow

Use a single connection for all three asset classes, with a background network worker and a serialized scanner queue. GUI widget operations stay on Tk's main thread. Keep authentication, transport, symbol mapping, market calendars, candle history, trend state and rendering as separate components.

Use Spotware's official Open API protocol definitions for application authentication, account discovery/authentication, symbol discovery, quote subscriptions, historical trendbars and live trendbar subscriptions. Use the Protobuf endpoint `demo.ctraderapi.com:5035` with certificate and hostname verification. Generate compatible Python message classes from pinned official protocol definitions and retain provenance/license information; use a dedicated framed TLS transport rather than relying on unexamined SDK TLS defaults. The documented outer framing is a four-byte length followed by the Protobuf message envelope. Bound message size, request lifetime and queue length. No order-placement messages are part of this app.

Authenticate the registered API application, retrieve authorized accounts with the access token, select the Spotware demo account and authenticate that account. Verify that the selected account is a demo account before connecting to the demo endpoint. Subscribe only to selected resolved symbols. Correlate responses with request IDs, send protocol heartbeats, honor throttling/backoff responses and cancel obsolete work on disconnect. Queue historical requests conservatively, no faster than two per second.

Decode prices with the protocol's 1/100000 scaling and symbol display precision. Decode trendbar OHLC from low plus delta fields and timestamps from UTC minutes. Use the same cTrader bid-price basis for historical candles and provisional calculations; an ask-only update must not fabricate a new bid observation or freshness time. Keep source timestamps separate from local receipt times.

Load at least 100 completed five-minute candles for EMA warm-up. Subscribe to quotes and live bars, reconcile completed candles against authoritative history, and use complete backfill after reconnect. Detect revisions, out-of-order data, missing coverage, stale quotes and queue overflow. A newly subscribed snapshot establishes the initial relationship rather than earning a crossover.

Replace NSE-only hours and constituent/option-eligibility filtering with broker symbol schedules, holidays and time zones. Keep internal timestamps aware and use UTC for transport. Trading sessions follow each symbol's broker metadata. For the scanner's daily membership reset, use a configurable global trading-day boundary, default 17:00 America/New_York, so an IST midnight does not reset an active US session. Display this choice in settings/help and test daylight-saving changes. Retain the original 15-second quote freshness requirement.

## Authorization and credential handling

The connection screen guides the user through creating/approving an Open API application, supplying its Client ID, Client Secret and exact registered redirect URI, opening the authorization page with the **accounts** read-only scope, and entering the returned authorization code in the app. Use an explicit manual code handoff for this version; do not require a browser extension, a public callback service or cTrader Algo to remain running. Explain how to obtain the code from the redirect URL and avoid treating a redirect-page error as token rejection without checking the actual code exchange.

Use the current official authorization/token endpoints, `https://openapi.ctrader.com/apps/auth` and `https://openapi.ctrader.com/apps/token`. Apply timeouts and safe errors to exchanges. Store access-token expiry and refresh tokens; rotate refreshed credentials atomically, since refresh tokens are single-use. Read-only account authorization is sufficient; this is a scanner with manual execution elsewhere.

Keep sensitive inputs masked and out of logs, saved URLs, screenshots and demo data. Use Windows user-scoped DPAPI for optional remembered credentials, with no plaintext fallback. On non-Windows development machines, retain them only in memory. Save this app's preferences and confirmed trend snapshots separately under `%LOCALAPPDATA%\Trend_Chaser_Global\data`. Include Forget Credentials. Error messages identify the failed stage without dumping response bodies, tokens, authorization URLs or secret-bearing token request URLs.

## Installer and connection guide

Reuse the supplied Windows Python/Tk runtime only after its archive and bundled manifest checks pass. Rebuild this app's dependency wheel set with pinned versions, trusted hashes and retained licenses. Installation remains offline, per-user and without an existing Python requirement. Preserve this app's settings on reinstall, refuse an unrelated installation root and retain rollback/instance-lock protections. Use independent Desktop/Start Menu shortcuts, ownership marker and uninstall registration named for Trend Chaser Global.

Provide `CONNECT_CTRADER.md` and an in-app Help walkthrough covering:

1. A cTrader ID and the Spotware demo account.
2. Registering and activating an Open API application in the official portal; possible external approval is a prerequisite, not an app failure.
3. Where Client ID, Client Secret and redirect URI go in the app, with no request for secret values in chat.
4. Opening read-only authorization, obtaining the authorization code and exchanging it for tokens.
5. Selecting the returned demo account and resolving/checking asset mappings.
6. Waiting for history, confirming fresh quotes and comparing selected five-minute EMA values with the cTrader chart.
7. Reading ranking/state colors, refreshing expired authorization and forgetting credentials.
8. Placing any trade manually in Olymp Trade after checking its own instrument, session and price.

Supply an offline demo and screenshot so the layout and icon are reviewable without credentials. Sample prices and events must be clearly fictional and must not pollute saved live state.

## Validation and acceptance

Run meaningful tests for the preserved EMA recursion, reference geometry, observed-crossover lifecycle, frozen scoring, mixed-direction per-section ranking, provisional confirmation, wick/touch retention, adverse closes and restart/backfill recovery. Test trading-day/DST handling, per-symbol schedules, stale gating, data revisions, quote side handling, symbol ambiguity, malformed protocol frames, request timeouts, authentication state, refresh rotation and cleanup. Test secret redaction and demo isolation.

Exercise real Tk widgets on the cloud's offscreen display: all three groups, independent scrolling/ranking, pinned index area, row colors and state labels, stable selection, connection controls, safe errors, sample mode and graceful shutdown. Run the real entry point and the offline installation verifier. Run a representative synthetic processing benchmark, verify expected transitions and keep the inherited sub-one-second p99 processing target. Check this app's package manifest, dependency hashes, ZIP checksum and installer helper behavior when the required tooling is available.

Verify that original tracked application files remain unchanged except for new design/planning documents and the separate new app tree. Report passing, failing, skipped and unrun checks distinctly. An offline demo or simulated protocol test does not establish authenticated cTrader readiness. Native Windows installation, DPAPI behavior and actual authenticated streaming must be reported as unverified unless genuinely exercised.

The build is acceptable when its source, offline demo, package and available automated checks are complete, with clear external prerequisites for live use. Do not claim that all requested common assets, a native Windows install, or a live account connection have been verified without corresponding evidence.

## Reference sources inspected

- Uploaded `Nifty_Next50_1.0.2_Windows.zip`: all 71 files matched its bundled manifest; its `trends.py`, indicators, UI, storage, installer and documentation establish the original behavior.
- Spotware protocol definitions: <https://github.com/spotware/openapi-proto-messages>.
- Current authentication endpoint constants: <https://github.com/spotware/OpenApiPy/blob/main/ctrader_open_api/endpoints.py>.
- Official authentication implementation and scope guidance: <https://github.com/spotware/OpenApiPy/blob/main/ctrader_open_api/auth.py> and <https://github.com/spotware/OpenApiPy/blob/main/docs/authentication.md>.
- Current-instance public documentation access to `openapi.ctrader.com` was blocked by the egress proxy; official GitHub sources and PyPI metadata were readable. No cTrader credentials are configured in this workspace. User authorization will occur in the delivered Windows app.
