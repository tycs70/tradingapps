# Trend Chaser Global Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one independently installed Windows app with ranked Indices, Forex and Shares sections, an original icon, cTrader authorization help, and a verified downloadable ZIP.

**Architecture:** Adapt the uploaded Trend Chaser's pure EMA/trend logic into a separate source tree. A certificate-verified cTrader Protobuf client feeds a serialized scanner, and Tk renders immutable snapshots. Keep account authorization, instrument mapping, calendars, persistence, ranking and delivery independently testable.

**Tech Stack:** Python 3.12 x64, tkinter/ttk, requests, protobuf, verified stdlib TLS, Windows DPAPI, unittest, PowerShell installer, original generated PNG/ICO artwork.

**Spec:** `docs/superpowers/specs/2026-10-15-trend-chaser-global-design.md`

## Global Constraints

- Product name `Trend Chaser Global`, version `1.0.0`; Windows 10/11 x64.
- Work in `/workspace/tradingapps`; create new files under `trend_chaser_global/` and new planning documents only. Preserve existing scanner source, dependencies, installers and releases.
- Five-minute EMA9/EMA21; rank by captured qualifying-crossover EMA9 angle, not current angle. Reference defaults: 60 candles, 2:1 plot and a two-interval chord.
- Retain provisional confirmation, strict adverse EMA9 close removal, observed reversals, freshness of 15 seconds, confirmed-state backfill and no fabricated crossover on startup.
- Three independently ranked sections. Pin Indices above the scrollable Forex/Shares area; preserve row selection by instrument identity.
- One Spotware demo connection; user executes manually in Olymp Trade. No order messages.
- Use verified TLS and trusted dependency/runtime hashes. No plaintext credential persistence; no secrets or secret-bearing URLs in logs.
- Show IST timestamps; global daily-membership boundary defaults to 17:00 America/New_York with DST-aware conversion; actual quote sessions use broker metadata.
- Seed nine supported cross-platform name matches plus NASDAQ and ten Forex candidates with verification gates. Do not claim twelve confirmed non-Forex instruments.
- The original runtime may be reused only after validating the supplied ZIP's manifest; create a fresh package manifest, independent installer identity and checksum.
- A local file path is not proof of a working download. Verify the final delivery route and read-back hash; report any unresolved publication prerequisite explicitly.

## Review Focus

1. A broker's ask-only quote update must not make an old bid appear fresh; pin this in Task 4.
2. A selected stock changes rank while the user reads its details; selection must remain attached to that stock, tested in Task 5.
3. A token refresh succeeds but saving it fails; preserve the usable memory session, report retention failure safely and never retain plaintext, tested in Task 3.
4. Missing bars coincide with scheduled closure or DST; distinguish closed sessions from unverified open-session history, tested in Tasks 1 and 4.
5. A private-repository download works only when signed in; verify and disclose the access requirement, and never change repository visibility, tested during Task 7 delivery.

## File structure and shared contracts

All paths below are relative to `trend_chaser_global/` unless written as repository-root paths.

- `global_trend/models.py`, `indicators.py`, `trends.py`: adapted pure models, EMA geometry and observed trend lifecycle.
- `global_trend/catalog.py`, `calendar.py`: proposed asset identities, account-specific resolution and trading-time rules.
- `global_trend/protocol/`: pinned official schemas, generated message classes, license and provenance; `tools/generate_protocol.py` reproduces generation.
- `global_trend/transport.py`, `ctrader.py`: bounded TLS framing/request correlation and domain-level market-data operations.
- `global_trend/auth.py`, `credentials.py`, `storage.py`: browser/code authorization, Windows-protected secrets, settings and asynchronous logs/trend snapshots.
- `global_trend/engine.py`, `ranking.py`: serialized data processing and independent group snapshots.
- `global_trend/ui.py`, `ui_tables.py`, `ui_connection.py`, `demo.py`: presentation, scrolling tables, connection workflow and isolated samples.
- `run_app.pyw`, `verify_install.py`, `assets/`, `installer/`, `tools/build_release.py`, `tools/benchmark.py`, `docs/CONNECT_CTRADER.md`, `README.md`, `tests/`: entry point and deliverables.

Preserve the supplied pure `Candle`, `Instrument`, `Settings`, `Snapshot`, `TrendCandidate` and `TrendRow` field semantics. Add market/group metadata through explicit catalog types rather than coupling indicators to transport.

Public interfaces used across tasks:

- `CatalogEntry(key, group, olymp_name, ctrader_name, verified)` and `ResolvedAsset(entry, symbol_id, digits, schedule)`; group is `Indices`, `Forex` or `Shares`.
- `trading_day(when: datetime, boundary: str = '17:00', zone: str = 'America/New_York') -> date`.
- `MarketCalendar.is_open(when: datetime) -> bool` and `expected_buckets(start, end) -> tuple[datetime, ...]`.
- `rank_group(candidates: Sequence[TrendRow]) -> tuple[TrendRow, ...]`, sorted by direction-adjusted frozen strength, capture time and identity.
- `ProtoClient.request(message, timeout: float = 10.0) -> Message`, `subscribe(callback)`, `close()`; transport callbacks enqueue work and never touch widgets.
- `OAuthSession.authorization_url() -> str`, `exchange(code) -> TokenBundle`, `refresh(tokens) -> TokenBundle`; token objects exclude secrets from `repr`.
- `CTraderClient.accounts(tokens)`, `authorize(account_id, tokens)`, `catalog()`, `history(asset, start, end)`, `subscribe_assets(assets, callback)` and `close()`.
- `Engine.connect(client, assets)`, `disconnect()`, `snapshot() -> DashboardState`, `close()`; `DashboardState` contains grouped rows, connection/coverage state, events and diagnostics.
- `App(root, engine, settings_store, credential_store, demo=False)` and `App.close()`; demo snapshots implement the same view contract without broker access.

### Task 1: Preserve trend rules and define the watchlist/calendar

**Files:** Create `global_trend/{__init__,models,indicators,trends,catalog,calendar,ranking}.py`, `tests/{__init__,test_trends,test_calendar,test_catalog}.py`.

**Interfaces:** Produce the pure models, catalog types, calendar functions and `rank_group` above. Adapt the reference archive as source material; do not change the old checkout's package.

- [ ] Write failing tests for mirrored crossover capture, frozen scores after current-angle changes, candle-close confirmation, wick/touch retention, strict adverse closes, removal/re-entry, reconnect continuity and day rollover. Assert that +40° LONG and −40° SHORT tie in strength and both outrank 20°; ties resolve by capture time then identity.
- [ ] Add calendar/catalog tests: `assert trading_day(IST_midnight) == trading_day(just_before_IST_midnight)` for the same US session; verify both DST transitions, broker holidays/closed gaps, 20 seeded candidates, nine supported matches and unresolved/ambiguous mappings remaining explicit.
- [ ] Run `python -m unittest tests.test_trends tests.test_calendar tests.test_catalog -v` from the new source directory; confirm the intended missing-code failures.
- [ ] Adapt the reference pure logic, replace its IST-date membership test with `trading_day`, implement independent frozen-strength sorting and explicit verified mappings. Keep the original EMA/reference-geometry formulas.
- [ ] Re-run these suites; expected: every test executes and passes. Commit the independently testable core.

### Task 2: Implement the cTrader protocol and verified transport

**Files:** Create `global_trend/protocol/`, `global_trend/{transport,ctrader}.py`, `tools/generate_protocol.py`, `tests/test_protocol.py`, `tests/test_transport.py`, new runtime/development lockfiles.

**Interfaces:** Consume `ResolvedAsset` and `Candle`. Produce `ProtoClient` and `CTraderClient`. Decode server account IDs independently of displayed account login numbers.

- [ ] Write failing round-trip tests using the official message definitions: application/account authentication, account lists, symbols, spot events, M5 history, and market schedules. Assert OHLC delta decoding, UTC-minute timestamps and price scaling by 100000.
- [ ] Add framed-stream tests for split/coalesced frames, oversized lengths, EOF, response correlation, timeout and cancelled requests. Use a local TLS fixture to prove trusted connections succeed while untrusted certificates and wrong hostnames fail.
- [ ] Run `python -m unittest tests.test_protocol tests.test_transport -v`; verify the expected failures.
- [ ] Pin official schemas and licenses, generate compatible message classes, implement four-byte network-order framing, verified TLS, bounded pending requests and non-logging heartbeats. Implement catalog/history/subscription operations and a conservative historical request queue of at most two per second.
- [ ] Re-run transport/protocol suites and dependency compatibility checks; preserve all trust checks. Commit transport and its protocol provenance together.

### Task 3: Add authorization, protected retention and connection instructions

**Files:** Create `global_trend/{auth,credentials,storage}.py`, `tests/test_auth.py`, `tests/test_storage.py`, `docs/CONNECT_CTRADER.md`.

**Interfaces:** Produce `TokenBundle`, `OAuthSession`, protected `CredentialStore`, `SettingsStore`, `TrendStore` and `EventLogger`. Task 4 consumes the stores; Task 5 consumes the authorization and account-selection workflow.

- [ ] Write failing tests asserting authorization uses `scope=accounts`, redirect URIs encode correctly, code exchange/refresh keep TLS verification, expiry/rotation is tracked, and errors never expose codes, secrets, tokens or request URLs.
- [ ] Test DPAPI through an injected protector, non-Windows memory-only behavior, corrupt retained data, atomic replacement and Forget Credentials. Simulate refresh-success/save-failure and assert the memory token survives with a safe retention warning and no plaintext file.
- [ ] Run `python -m unittest tests.test_auth tests.test_storage -v`; confirm meaningful failures.
- [ ] Implement the official authorization/token endpoint workflow and exact manual-code handoff. Add per-app settings/confirmed-state persistence and asynchronous logs outside the signal path. Write the step-by-step guide with dummy examples only, including app registration/activation, redirect code, selected internal demo account, token renewal, symbol verification and chart comparison.
- [ ] Re-run both suites; verify the guide against the implemented control names. Commit this user-facing connection capability.

### Task 4: Build the serialized live scanner and recovery

**Files:** Create `global_trend/engine.py`, `tests/test_engine.py`, `tools/benchmark.py`.

**Interfaces:** Consume Tasks 1–3; produce `Engine` and immutable `DashboardState`. Use an injectable clock and broker interface so the real processing path is tested without real credentials.

- [ ] Write failing end-to-end tests from seeded history through quote input to three independent rankings. Assert initial alignment creates no crossover, only verified matches become actionable, and provisional/confirmed rows use captured scores.
- [ ] Add tests for ask-only updates preserving bid age, incomplete current-bar history, late corrections, stale/future quotes, generation/epoch rejection, disconnect, overflow and confirmed-state backfill across every missed candle. Cover closure gaps and DST explicitly.
- [ ] Run `python -m unittest tests.test_engine -v`; confirm the missing implementation fails.
- [ ] Implement the bounded serialized queue, account/catalog preparation, 100-completed-candle warm-up, provisional bid snapshots, authoritative closed-candle reconciliation and safe recovery. Gate each symbol independently; preserve inactive/unverified rows and their reasons. Never use offline sample prices after a connection failure.
- [ ] Re-run all core/engine suites. Run the synthetic benchmark through this engine and assert the exact expected transition count and processing p99 below 1000 ms. Commit the complete data-to-ranking workflow.

### Task 5: Build the dashboard, original icon and offline demo

**Files:** Create `global_trend/{ui,ui_tables,ui_connection,demo}.py`, `run_app.pyw`, `assets/icon.png`, `assets/icon.ico`, `tests/test_ui.py`, `tests/test_demo.py`.

**Interfaces:** Consume `DashboardState`, authorization and stores; produce the standalone `App` and demo using the identical presentation contract.

- [ ] Write failing GUI tests for the three sections, pinned index area, scrolling, mixed-direction independent rankings, grey inactive rows, state labels and selected-row identity after reordering. Test real callback cleanup, offline isolation, masked credentials and safe errors.
- [ ] Run the UI tests on the existing Xorg dummy display from the new app directory; confirm expected failures.
- [ ] Implement the dark navy/teal dashboard, readable ranking columns, details/chart views, connection wizard, mapping verification and Help. All broker calls stay off Tk's main thread. Apply stable widget identities and refresh snapshots without rebuilding the full layout.
- [ ] Generate the requested original transparent globe/EMA icon using image generation. Convert it to multi-resolution ICO for Windows packaging; preserve the original PNG. Apply iconography and clearly label fictional offline samples. Do not use third-party broker logos.
- [ ] Re-run all GUI/demo suites and the actual entry point, including connected-fixture and disconnected startup/close. Capture a screenshot and standalone offline preview; commit the complete interface and assets.

### Task 6: Package the independent Windows application

**Files:** Create `installer/{INSTALL.bat,install.ps1,uninstall.ps1,common.ps1}`, `tools/build_release.py`, `verify_install.py`, `README.md`, `README_FIRST.txt`, `tests/test_package.py`, `tests/test_installer.ps1`.

**Interfaces:** Consume the new source, trusted wheel cache, icon and uploaded runtime; produce `dist/Trend_Chaser_Global_1.0.0_Windows_x64.zip` and matching `.sha256`.

- [ ] Write failing package tests for safe paths, file-manifest corruption, exact dependency hashes, offline installation settings, independent ownership/shortcut/uninstall identity, icon and guide inclusion, and preservation of only this app's data. Reuse the reference rollback/filesystem tests with the new identity.
- [ ] Run package tests and PowerShell helper checks where available; record the expected missing-package failures.
- [ ] Verify the uploaded base manifest before extracting reusable runtime files. Resolve and pin this app's dependencies and download checksum-verified Windows-compatible wheels. Implement a deterministic package builder, safe staged installer, pre-apply verifier, rollback and offline `--require-hashes` dependency installation.
- [ ] Run the offline installation verifier, package tests, build and manifest/checksum verification. Run PowerShell parsing/filesystem checks if available; explicitly retain native Windows execution as unverified when no Windows execution environment exists. Commit source/packaging changes and retain the ZIP as a delivery artifact.

### Task 7: Review, validate and deliver an actual download

**Files:** Create `docs/VALIDATION.md`; update the connection guide and README only to reflect actual results. Save evidence under ignored `build/` and final distributables under `dist/`.

**Interfaces:** Consume the packaged app; produce a reviewed implementation, accurate validation report and working download route.

- [ ] Run the complete new-app suite under a display; verify test counts and distinct skips. Run the real entry point, offline verifier, benchmark, wheel integrity and final ZIP checks. Run the original scanner suite once to establish it remains intact.
- [ ] Have a fresh reviewer inspect the whole implementation against the approved spec, emphasizing the five Review Focus cases. Address concrete findings, re-run affected checks and complete a final review of the fixes.
- [ ] Verify there are no changes to original scanner files and no credentials, connection codes, transient caches or secret-bearing logs in the package or Git changes. Commit the final validation documentation.
- [ ] Check supported downloadable file attachments first. If this environment cannot attach a binary, use a release asset in the existing `tycs70/tradingapps` repository after verifying API/network access and repository visibility. Preserve private visibility and explain any sign-in requirement. Do not publish to an unrelated service or fabricate an asset URL.
- [ ] Upload only the completed ZIP/checksum (and optional preview/guide), retrieve the asset through the actual download route, and assert its SHA-256 matches the local ZIP. Only then report that link as verified. If external access is blocked, finish all independent build work and report the exact access action needed; a workspace path must not be represented as a tested download.
- [ ] Deliver the ZIP link, checksum, preview and connection guide. Explain cTrader setup in concise user language, list required registration/authorization steps and clearly state which live/native checks remain unrun.

## Self-review and execution recommendation

Each spec requirement is assigned above: core/ranking/session behavior to Task 1; secure protocol to Task 2; credentials and guide to Task 3; live processing/recovery to Task 4; dashboard/icon/demo to Task 5; offline Windows delivery to Task 6; independent review, evidence and download usability to Task 7. Tests in Tasks 1, 3, 4 and 5 cover the five Review Focus inputs; Task 7 verifies access requirements for delivery.

Recommend **Native** execution: one implementer in this session follows these tightly coupled interfaces, then a fresh reviewer checks the whole branch. Subagent-driven execution is available if the user prefers per-task implementer/reviewer handoffs. Written-plan review and execution-method selection precede implementation.
