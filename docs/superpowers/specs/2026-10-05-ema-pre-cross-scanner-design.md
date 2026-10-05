# EMA Pre-Cross Scanner — Windows application design

Date: 5 October 2026. Status: concrete design awaiting written-spec review.

## Purpose and agreed principles

Build a fresh, independently installable Windows desktop app for the user's laptop. It scans all currently option-eligible NSE stock underlyings (expected to be approximately 210), using five-minute Upstox candles and live prices. For bullish setups, warn slightly before EMA9 crosses EMA21 from below. For bearish setups, apply the exact mirror: warn slightly before EMA9 crosses EMA21 from above. Rank qualifying setups by EMA9's direction-aligned angle on a consistent chart view. No ATR normalization or old breakout/entry filters are carried into these new rules.

The app is a signal scanner. This first release places no orders and selects no option strikes. Prices and EMAs refer to the underlying shares. The user may uninstall all old apps; the new app must not depend on their files, Python environments, shortcuts, or data.

## Delivery and Windows installation

- Name: **EMA Pre-Cross Scanner**, fresh version **1.0.0**.
- Target: Windows 10/11, 64-bit Intel/AMD laptop, per-user installation without administrator rights.
- Deliver a downloadable ZIP containing the app, `INSTALL.bat`, PowerShell installer, uninstall support, and a bundled private Python/Tk runtime and dependency wheels.
- Double-click `INSTALL.bat`; installation verifies the bundled file hashes, installs into `%LOCALAPPDATA%\EMA_PreCross_Scanner`, runs offline startup checks, and creates Desktop and Start Menu shortcuts plus a Windows Installed Apps entry.
- Installation works without an existing Python installation. Internet is required for live Upstox data, but bundled installation should not need dependency downloads.
- The private runtime is CPython 3.12.15 from Astral's python-build-standalone Windows x86_64 distribution. The 22,011,023-byte runtime archive was downloaded with normal TLS verification and matched the SHA-256 in uv's authoritative runtime metadata: `6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402`. Inspection confirmed Python, pythonw, pip, `_tkinter.pyd`, Tcl, and Tk are included. No Windows binary has been executed in this Linux cloud environment.
- Pin dependencies and bundle compatible Windows wheels. Preserve TLS, package checksums, and runtime checksum validation.
- Re-running the installer preserves new-app settings and logs. It checks the instance lock and stages/validates replacement files before updating. It never uninstalls or edits old applications.
- The application launches through its private `pythonw.exe`, with no persistent console window. Installation errors remain visible and are recorded in a non-secret install log.

## Meaning of chart angle

An angle on a screen depends on horizontal zoom, vertical price scaling, and plot aspect ratio. It cannot be invariant while matching arbitrary external Upstox chart views. This release therefore includes its own **reference chart** and calculates angle from exactly the coordinate transformation used to draw EMA9 there.

Proposed defaults:

- Five-minute candles; last 60 candles visible, including the developing candle.
- Reference plot aspect ratio 2:1, retained when the window resizes.
- Price axis uses the visible candle/EMA range with 5% padding; the scale is held constant within a five-minute candle unless a price moves outside it. Re-scaling recalculates all displayed angles coherently.
- Measure EMA9's signed chord over the latest two candle intervals, ending at the developing candle's provisional EMA9 point. Angle = `degrees(atan2(upward_pixel_change, horizontal_pixel_change))`. Rising is positive and falling is negative.
- The table displays **EMA9 chart angle**, with an explanation of the 60-candle reference view. The selected stock's chart shows the two EMA lines and the measured slope segment.
- No ATR or frozen historical setup angle enters this metric or ranking. Arbitrarily zoomed Upstox charts can look different; matching an exact external view would require its same scale and aspect ratio. The reference view makes the app's number visually inspectable and repeatable.
- Flat/invalid price ranges yield a zero/invalid angle instead of division errors.

The angle window and standard reference view are configurable within documented limits. The scale definition is an explicit review point because the user's requested visual angle is not an intrinsic property of an EMA.

## Five-minute EMA calculation

- Warm each stock using validated completed Upstox five-minute candles from prior sessions and the current session. Seed EMA9 and EMA21 from closes using standard EMA recursion.
- For every fresh price update, recompute the developing candle's provisional EMA from the **previous completed candle's EMA** with the latest price as provisional close. Do not repeatedly advance a five-minute EMA for each tick.
- Both EMAs therefore move during the forming candle. Closed-candle values and provisional values stay distinct.
- Form five-minute candles from valid one-minute broker feed candles. Require contiguous minute coverage before finalizing a bar; use broker candle backfill to recover gaps or correct inconsistencies.
- History loading/reconciliation runs outside the GUI and signal-processing path. A stock with incomplete or stale data is marked PAUSED and is excluded from actionable ranking until recovered. Independently ready stocks continue scanning.
- Startup/reconnect snapshots are marked as initial observations. They are not reported as crossings that occurred after connection.

## Bullish ARMED rule

A stock is ARMED when all these conditions hold with fresh data:

1. Its live five-minute EMA9 is strictly below EMA21.
2. EMA9 is rising relative to the previous completed EMA9, and its reference-chart angle is positive.
3. The positive EMA gap is smaller than the gap at the previous completed candle: EMA9 is converging toward EMA21 from below.
4. Gap percentage, `100 * (EMA21 - EMA9) / latest_stock_price`, is at or below **0.05% by default**. This is a proximity setting, not ATR normalization. It is adjustable in Settings and visibly stated on the board.

The proposed 0.05% default gives “very close” a measurable definition; it is a starting rule to validate against the user's examples, not a claim of an optimal threshold.

No previous-candle breakout, 0.10 ATR buffer, EMA9 8-degree floor, EMA21 angle tolerance, or old direct/reentry cycle logic is applied. This is the user's new pre-crossover rule.

## Bearish ARMED rule

A stock is ARMED SHORT when all these conditions hold with fresh data:

1. Its live five-minute EMA9 is strictly above EMA21.
2. EMA9 is falling relative to the previous completed EMA9, and its reference-chart angle is negative.
3. The positive EMA gap, EMA9 minus EMA21, is smaller than at the previous completed candle: EMA9 is converging toward EMA21 from above.
4. Gap percentage, `100 * (EMA9 - EMA21) / latest_stock_price`, is at or below the same adjustable **0.05% default**.

The bearish rule uses identical history/readiness checks, chart geometry, settings, provisional updates, and cancellation behavior. A symbol cannot be ARMED LONG and ARMED SHORT simultaneously. At exact EMA equality, neither pre-crossover direction is ARMED; a crossing is recognized when the EMA relationship moves to the opposite side.

## States and ranking for both directions

- **WATCHING**: ready but neither direction's ARMED conditions are all satisfied.
- **ARMED**: the conditions above currently hold; signal is explicitly labelled provisional/pre-crossover.
- **CROSSED**: EMA9 crosses above EMA21 for LONG, or below EMA21 for SHORT, during a live candle. The previous relationship must have been observed. This is a live crossover, not a fill or closed-candle confirmation.
- **CONFIRMED**: the completed five-minute candle closes with EMA9 above EMA21 for LONG, or below EMA21 for SHORT.
- **CANCELLED/REVERSED**: an armed setup loses its direction/convergence/proximity conditions, or a live crossover reverses before candle close. For LONG, rising EMA9 is required; for SHORT, falling EMA9 is required.
- **PAUSED**: missing history, invalid/out-of-order quotes, stale feed, closed market, or recovery.

A price jump can cross the EMAs without a received quote satisfying the proximity rule first. Log that crossover as observed without an earlier ARMED warning; do not invent a warning time or promise advance notice for every crossover. A first connection observation that is already crossed is not a newly observed crossover.

Rank only fresh ARMED candidates by direction-aligned EMA9 chart-angle strength, descending: positive angle for LONG, negative angle multiplied by minus one for SHORT. Retain the signed angle in the display. Separate Bullish and Bearish views use the same rule; a combined view sorts by direction-aligned magnitude. Break equal-strength ties by smaller gap percentage, then symbol. Show crossing events separately so historical crossings cannot dominate the ARMED opportunity list.

The ranked list can contain every qualifying stock; no old Top 7/Top 8 restriction is inherited. The table refreshes at most once per second while quote evaluation remains event-driven. Emit an event on state transition and avoid duplicate alert sounds for unchanged states. Initial observations are clearly labelled, with crossing times recorded only when actually observed.

Both LONG and SHORT rules require fresh valid quotes. Initially use a 15-second freshness ceiling, reject quotes more than two seconds ahead of local/server time or arriving out of order, and gate live signals on the broker's normal NSE equity trading-session status. These operational checks are distinct from angle/proximity qualification. Retain quotes/history for diagnosis but label non-ready rows PAUSED.

## Stock universe and data access

- Download/cache Upstox's NSE instrument master; select currently listed stock-option contracts, resolve/deduplicate their NSE equity underlying instrument keys, and subscribe to the shares.
- Exclude index options, expired contracts, unresolved underlyings, and duplicate symbols. Check expiry dates in IST.
- Display eligible, subscribed, receiving-data, ready, and paused counts, plus per-stock exclusion/recovery reasons. The count follows current exchange eligibility and is not silently forced to 210.
- Use one Upstox V3 streaming connection and background REST requests for historical/backfill data with conservative bounded concurrency and rate limiting. Validate account/feed subscription limits during live Windows testing.
- Accept the user's Upstox access token in a masked input, normalize a pasted Bearer prefix, and retain it in memory only. Do not write tokens or authorized WebSocket URLs to settings, logs, test output, or diagnostic exports.
- No shared server, cloud account registration, or order API is required.

## Interface

- Main board: Connect/Disconnect, connection/market status, coverage counts, proximity threshold, and ranked ARMED candidates, with All/Bullish/Bearish views.
- Columns: rank, symbol, side (LONG/SHORT), state, signed EMA9 angle, EMA9, EMA21, gap %, latest stock price, last quote time, and armed time.
- Selected-stock reference chart: price candles, EMA9, EMA21, gap, angle measurement, and provisional/closed-bar distinction.
- Separate crossover/event log, Settings/token input, and Diagnostics tabs.
- Save only non-secret settings such as window size, threshold, and chart parameters. Keep new-app logs in its own data folder.
- A market-closed or disconnected screen never presents cached rows as fresh actionable signals.

## Architecture and source reuse

Use Python/Tkinter for a lightweight desktop interface, with the pinned Upstox Python SDK and requests. Reuse the reviewed apps' instrument mapping, network patterns, worker/queue separation, and Windows installation experience. Implement the newly agreed strategy and ranking as separate pure functions/state logic rather than carrying forward the old strategy filters.

Separate modules cover indicators/chart geometry, signal states, feed adaptation/history, scanner coordination, settings/logging, UI/chart rendering, and installation verification. GUI updates happen on the Tk main thread; feed/history processing runs in workers. Avoid synchronous file/network I/O in the alert path. Handle bounded-queue overflow by pausing/recovering affected data rather than silently losing quote crossings.

## Validation and acceptance

- Indicator fixtures verify completed EMA recursion and provisional EMA recomputation, including many ticks in one candle.
- Chart fixtures verify angle equals the rendered reference-chart slope, positive/negative/flat cases, consistent aspect ratio, and coherent re-scaling. No ATR input exists in ranking.
- Signal tests verify symmetric bullish/bearish pre-crossover arming, proximity edges, convergence, equality handling, cancellation, live crossing, close confirmation, reversal, duplicate suppression, and startup/reconnect semantics. Mirrored price fixtures must produce mirrored states and comparable ranking strengths.
- Universe tests exercise stock-option eligibility, expiry, equity mapping, missing keys, index exclusions, and counts.
- Feed tests use synthetic messages and mocked REST/SDK boundaries. They exercise stale/out-of-order data, missing minutes, disconnection, recovery, closed market, and independent stock readiness.
- A 210-stock synthetic load test measures quote-to-event/GUI-queue latency and validates no missing transitions. Target alert visibility within one second of a received qualifying quote; actual Windows UI/network latency requires a Windows run.
- GUI smoke checks verify connection controls, ranked rows, chart state, settings persistence, and close/disconnect cleanup using an offscreen display if available.
- Packaging verifies hashes, complete source/runtime/wheels, architecture checks, safe staging, independent install paths, shortcuts, uninstall metadata, and repeat-install preservation. Run a native Windows installation/startup check when a Windows execution route is available; do not claim that Linux checks validate native Windows behavior.
- Test authenticated streaming with a user-supplied token on Windows and compare selected EMA values against the user's five-minute Upstox chart before claiming live readiness. Tokens are never requested in chat.

## Scope limits and remaining review points

This first release implements both bullish and bearish pre-crossover setups. It is a scanner with no automatic/manual order placement, option selection, exits, profit/loss accounting, or backtest profitability claims.

The concrete defaults to review are the 0.05% proximity threshold, two-interval angle measurement, 60-candle reference chart, and 2:1 plot aspect ratio. The intended product principles, broker, timeframe, whole-universe scanning, independent Windows installation, and Desktop shortcut are established.

Next stage: review this written spec, then produce the implementation plan and select its execution method. No new application code has been written yet.
