# Trend Chase Version 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Follow test-first steps and track results here.

**Goal:** Deliver a separate offline-installable Windows Trend Chase app and a sample demo sheet.
**Architecture:** Separate source at trend_chase/, seeded from verified 1.0.1 remote source; original scanner untouched. A pure trend registry consumes observed crosses and verified completed bars, with asynchronous persistent snapshots. UI consumes scanner snapshots with five rows per side.
**Tech Stack:** Python 3.12/Tk, existing pinned dependencies, Windows DPAPI, PowerShell per-user installer.
**Spec:** docs/superpowers/specs/2026-10-06-trend-chase-v1-design.md

## Global Constraints
- Name Trend Chase Version 1, version 1.0.0; Windows 10/11 Intel/AMD x64.
- Independent app in trend_chase/; original EMA app source/releases unchanged.
- Top five LONG and five SHORT, frozen crossover strength rank, current angle displayed separately.
- Close across EMA9 removes membership only; no trading actions; equality and wicks do not remove confirmed trends.
- Credential values never in tests/logs/demo/artifacts; user-scoped DPAPI, no plaintext fallback.
- Preserve TLS, runtime and artifact integrity checks; demo is explicitly sample data and cannot enter live state.

## Review Focus
- Recovery history contains an adverse close followed by recovery: never revive that candidate.
- Missing last-minute bars: history reconciliation must check completed candles, not silently skip confirmation.
- Same-day reconnect/new day: retain validated confirmed state only, never provisional or yesterday entries.
- Angle setting changes: frozen rank immutable; chart visibility has no computational effect.
- Demo and saved token interactions: no demo connection, token leak or persistence mutation.

### Task 1: Trend engine, recovery and persistence
Files: trend_chase/ema_scanner/trends.py, scanner.py, models.py, storage.py; tests/test_trends.py and tests/test_scanner.py.
Interfaces: TrendCandidate immutable record (key, symbol, side, crossover_time, crossover_angle, status, checked_through); TrendBook methods for observed crossover, verified candle/history, daily reset; scanner.snapshot() adds trends_long, trends_short (list of TrendRow with candidate + snapshot), trend_counts, and safe diagnostic status. Scanner accepts trend_store=None.
- [ ] Add failing tests for mirrored provisional add/confirm, equality/wick/close removal, immutable rank and top-five replacement.
- [ ] Implement pure registry and structured trend events with market details; preserve normal scanner.
- [ ] Add failing recovery tests for missing-minute/backfill confirmation, adverse intervening close, stale hiding and provisional loss on pause.
- [ ] Integrate with scanner serialized worker and all validated historical replacements; no new crosses from history.
- [ ] Add asynchronous atomic TrendStore confirmed-only persistence tests: same-day restore, invalid file, new day, no resurrection.
- [ ] Run full suite and benchmark; write report and commit task files.

### Task 2: Desktop tables, demo and app identity
Files: trend_chase/ema_scanner/ui.py, demo.py, __init__.py, credentials.py, storage.py identity, run_app.pyw, tests/test_ui.py, tests/test_demo.py, demo.html.
Consumes Task 1 scanner trend row interface.
- [ ] Add failing GUI tests for Top 5 per side, both angles, hidden chart toggle and token defaults/Forget Token.
- [ ] Build top trend tables above familiar normal scanner; update identity and independent paths; keep geometry.
- [ ] Add explicitly sample-only Demo tab with five rows per side and demo chart selection; never call broker or persist sample data.
- [ ] Wire entry point to asynchronous TrendStore; close threads and logger cleanly.
- [ ] Produce standalone demo.html using sample data matching UI; verify actual GUI rendering and capture demo screenshot.
- [ ] Run full GUI suite; write report and commit.

### Task 3: Independent Windows release and documentation
Files: trend_chase/installer/*, tools/build_release.py, verify_install.py, README.md, README_FIRST.txt; releases/Trend_Chase_V1_1.0.0_Windows_x64.zip and SHA256, Trend_Chase_V1_Demo.html and PNG.
- [ ] Verify existing 1.0.1 release SHA256/manifest and reuse trusted bundled runtime and wheels.
- [ ] Add package tests for independent names, icon, demo shortcut, retained data and complete required content.
- [ ] Change per-user installer/uninstaller branding/paths; add an app icon and Start Menu demo shortcut.
- [ ] Build new manifest/package, verify entire package and checksum; parse installer and run helper suite if supported.
- [ ] Run fresh full tests, offline GUI startup and benchmark; document actual counts and limitations.
- [ ] Perform independent whole-change review, address findings, rebuild changed package; deliver download links.
