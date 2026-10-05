# EMA Pre-Cross Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver an independent Windows installer and Desktop shortcut for the approved Upstox EMA9/EMA21 scanner.

**Architecture:** Pure indicator, geometry and signal-state modules feed a threaded scanner coordinator. One SDK V3 connection supplies quotes and minute candles; bounded, rate-limited REST workers warm and reconcile five-minute history. Tk renders immutable snapshots on its main thread. The installer stages a private Python/Tk runtime and bundled wheels before creating shortcuts.

**Tech Stack:** Python 3.12, tkinter, requests 2.32.5, upstox-python-sdk 2.23.0, stdlib unittest, PowerShell, bundled CPython 3.12.15 Windows x86_64.

**Spec:** `docs/superpowers/specs/2026-10-05-ema-pre-cross-scanner-design.md`

## Global Constraints

- EMA Pre-Cross Scanner 1.0.0; Windows 10/11 x86_64, per-user `%LOCALAPPDATA%\EMA_PreCross_Scanner`, no old-app dependencies.
- Five-minute underlying share EMA9/EMA21; every tick derives provisional EMAs from the last completed bar, never the last tick.
- Both LONG and SHORT; proximity 0.05%, angle chord two intervals, 60-bar reference, 2:1 aspect, 5% price padding; no ATR or old breakout filters.
- Only fresh ARMED ranks; quote age at most 15 seconds, future tolerance two seconds, normal NSE session; never invent startup or missed-feed crossings.
- No order APIs. Token remains in memory; no authorized URLs or token contents in logs/settings.
- Validate complete closed bars, independently pause affected symbols, recover gaps asynchronously, and never silently drop a queue-overflow crossing.
- Offline bundled install, verified hashes, Desktop/Start Menu shortcuts and uninstall entry, repeat-install preservation.
- Current cloud branch `work` is isolated; leave uploaded originals intact. Complete the already authorized build inline, with one fresh final review.

## Review Focus

1. Feed reconnect while history reloads: generation guards and quote-baseline resets must prevent stale jobs creating phantom crossings (Task 2/3 tests).
2. Broker minute rollover with absent or revised candles: never finalize incomplete history; recover before ranking (Task 2 tests).
3. Multi-day equity sessions and holiday/closed market: only completed regular-session bars seed EMAs; market closure clears actionable rows (Task 2/3 tests).
4. Windows paths containing spaces/non-ASCII, existing installation running, and corrupt runtime/package: installation must preserve user data or fail safely (Task 5 tests and PowerShell parse check; native execution limitation recorded).
5. Fast queues and GUI lag: snapshots/events remain consistent; overflow visibly pauses instead of fabricating continuity (Task 3/4 tests and 210-stock benchmark).

## File Structure

`ema_scanner/models.py` typed immutable records and settings; `indicators.py` EMA/reference geometry; `strategy.py` qualification/ranking/state transitions; `universe.py` eligible underlying mapping; `history.py` broker candles and minute assembly; `broker.py` REST/SDK boundary; `scanner.py` coordinator; `storage.py` non-secret settings/logging/instance lock; `ui.py` Tk board/chart. `run_app.pyw` entry point, `verify_install.py` offline installation self-check, `tools/build_release.py` reproducible package builder. Tests mirror behavior by component; `installer/` contains bootstrap/install/uninstall scripts.

### Task 1: EMA, reference chart and mirrored strategy

**Files:** `ema_scanner/{__init__,models,indicators,strategy}.py`, `tests/{__init__,test_strategy}.py`.

**Interfaces:** Produces `Candle`, `Instrument`, `Settings`, `Snapshot`, `Event`; `EMAHistory(candles).snapshot(price, quote_time, settings) -> Snapshot`; `qualification(snapshot, settings) -> str | None`; `SignalMachine.observe(snapshot, initial=False) -> list[Event]`, `.closed(snapshot)`, `.pause(reason)`; `rank_armed(snapshots) -> list[Snapshot]`.

- [x] Write tests for exact EMA recursion and repeat ticks; rendered chord geometry and scale hold/reset; bullish/bearish mirroring; proximity/convergence/equality; crossing, reversal, confirmation, cancellation and startup deduplication.
- [x] Run `python3 -m unittest tests.test_strategy -v`. Expected: missing-module FAIL before implementation.
- [x] Implement the interfaces above. Keep completed EMA series separate from provisional values, reference mapping identical for calculation/rendering, and all state changes explicit.
- [x] Run `python3 -m unittest tests.test_strategy -v`. Expected: all PASS.
- [x] Commit `feat: implement mirrored EMA pre-cross signals and chart geometry`.

### Task 2: Upstox boundary, eligible universe and candle continuity

**Files:** `ema_scanner/{universe,history,broker}.py`, `requirements.txt`, `tests/test_data.py`.

**Interfaces:** Consumes Task 1 records. Produces `eligible_stocks(master, today) -> (list[Instrument], list[str])`; `parse_candles(rows, now) -> list[Candle]`; `MinuteBook.update(rows, current_bucket) -> (list[Candle], bool)`; `Broker(token).universe()`, `.history(key, now)`, `.stream(keys, message, status)`, `.disconnect()`; `parse_feed(message) -> (quotes, minutes, market_status)`.

- [x] Write tests for CE/PE eligibility, expired/index/unmapped exclusions; malformed/non-finite candles; contiguous minute aggregation and revisions/gaps; initial feed nesting, timestamp and market status; rate limiting and token normalization without logging.
- [x] Run `python3 -m unittest tests.test_data -v`. Expected: missing-module FAIL.
- [x] Implement one V3 stream and rate-limited bounded requests with TLS verification. Historical five-minute data covers prior/current sessions and excludes forming candles. Reject irregular or incomplete current-session coverage.
- [x] Run `python3 -m unittest tests.test_data -v`. Expected: all PASS.
- [x] Commit `feat: add Upstox data adapter and validated option stock universe`.

### Task 3: Scanner orchestration and safe persistence

**Files:** `ema_scanner/{scanner,storage}.py`, `tests/test_scanner.py`, `tools/benchmark.py`.

**Interfaces:** Consumes Tasks 1/2. Produces `Scanner(settings, broker_factory=Broker).connect(token)`, `.disconnect()`, `.snapshot() -> dict`, `.set_settings(settings)`, `.close()`. Worker and callback generation guards protect reconnects; UI sees copied immutable rows/events. `SettingsStore(path).load()/save(settings)` and `InstanceLock(path)` are independent of old apps.

- [x] Write tests with fake broker/clock for stale/future/out-of-order quotes; reconnect, overflow, initial observation, history failures; closed market; independent symbol recovery; all 210 candidates and ordered transition events. Settings tests reject saved tokens and corrupt values.
- [x] Run `python3 -m unittest tests.test_scanner -v`. Expected: missing-module FAIL.
- [x] Implement coordinator with one processing thread, at most four history workers, bounded event queue, stale-data checks, and asynchronous event logging. A paused symbol resets its observation baseline when recovered.
- [x] Run `python3 -m unittest tests.test_scanner -v` and `python3 tools/benchmark.py`. Expected: all PASS; 210-stock quote-to-event processing p99 below one second without dropped transitions on this cloud host.
- [x] Commit `feat: coordinate streaming signals with explicit data readiness`.

### Task 4: Windows desktop board and inspectable chart

**Files:** `ema_scanner/ui.py`, `run_app.pyw`, `verify_install.py`, `tests/test_ui.py`.

**Interfaces:** Consumes `Scanner.snapshot()` and Task 1 chart geometry. Produces `App(root, scanner, store)`, masked token connection, ranking filters, selected-stock chart, events, settings and diagnostics. Entry point manages instance lock and startup errors without token exposure.

- [x] Write a UI smoke test using an injected fake scanner: both-direction rows, filter, exact chord endpoints/aspect, closure clears rows, setting validation, close/disconnect. Add offline import/installation check.
- [x] Run `python3 -m unittest tests.test_ui -v`. Expected: missing-module FAIL; use an offscreen display for actual widgets if available.
- [x] Implement Tk UI on the main thread, snapshots refreshed once per second, coherent reference plot, all stocks/reasons visible in Diagnostics, no network until Connect.
- [x] Run full unittest suite and offscreen UI smoke, plus `python3 verify_install.py --no-display`. Expected: PASS; record any unavailable native Windows checks.
- [x] Commit `feat: add Windows desktop scanner board and reference chart`.

### Task 5: Offline installer and downloadable release

**Files:** `installer/{INSTALL.bat,install.ps1,uninstall.ps1}`, `tools/build_release.py`, `tests/test_package.py`, `README.md`, `README_FIRST.txt`, `docs/VALIDATION.md`.

**Interfaces:** Consumes complete app and verified runtime archive. Produces `dist/EMA_PreCross_Scanner_1.0.0_Windows_x64.zip`, fully bundled pinned Windows wheels and checksummed release tree.

- [x] Write package-verifier tests for unsafe paths, altered/missing files, wheel/runtime completeness and source-only token exclusion. Exercise installer syntax with PowerShell when available.
- [x] Run `python3 -m unittest tests.test_package -v`. Expected: missing-module FAIL.
- [x] Bundle Windows-compatible wheels, convert verified private runtime to ZIP, build SHA-256 manifest. Installer verifies all content, stages offline pip install/startup checks, preserves own data, refuses running instance, atomically swaps with rollback, and creates both shortcuts/uninstall registration. Uninstall affects only owned path.
- [x] Run full suite, 210-stock benchmark, package integrity verification, PowerShell parse check and offscreen desktop startup. Expected: PASS; native Windows and authenticated Upstox tests explicitly unverified unless an execution route is available.
- [x] Commit `build: package independent offline Windows installer`.
- [x] Run one fresh whole-branch code review against the spec and Review Focus; fix important findings with a failing regression test and full green suite. Deliver ZIP, digest, brief installation steps and honest validation limits.
