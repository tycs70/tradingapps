# Validation and release evidence

This is an independent application under `trend_chaser_global/`. The original
scanner source and its release remain unchanged. Linux automated checks establish
development and offline package readiness; they do not establish a native Windows
install or authenticated cTrader service readiness.

## Executed checks

- New application: **126 tests run, 125 passed, 1 skipped** (native Windows DPAPI),
  full suite with a display, including strategy, captured-angle
  ranking, transport/TLS, OAuth/refresh, retention failures, account-scoped mappings,
  history recovery and widgets.
- Original application: 52 tests run, 51 passed; one optional original release
  wheel-cache test skipped. Original tracked files are unchanged.
- Real Tk8.6 on system Python 3.13: ten dashboard tests passed; screenshot
  captured at 1366 × 768 with original icon and native font/image rendering.
  The primary Python 3.12 cloud Tk9 renderer substitutes fixed fonts/images;
  it is used for behavioral tests, not the delivered visual evidence.
- Real entry point: demo and disconnected startup, then graceful timed shutdown.
- Real Engine + broker fixture: fresh LONG appears green, then STALE appears grey.
- Offline installation verifier: dependencies, cTrader messages, EMA recursion,
  global time zones and real Tk startup passed.
- Synthetic benchmark: 210 instruments, 420 expected transitions; measured
  processing p99 365.718 ms (target below 1,000 ms). Excludes network/broker and
  native Windows rendering.
- Portable PowerShell 7.5.3 on Linux: installer helper checks passed for quoted /
  Unicode paths, ownership refusal, staging, swap rollback, data preservation and
  corrupted packages. All installer scripts parsed successfully.
- All 71 uploaded reference files matched their manifest. The entire uploaded ZIP
  and reusable Windows runtime have independently pinned SHA-256 values.
- Seven Windows/universal wheels matched the trusted dependency lock. A corrupted
  wheel is rejected. Licenses remain inside runtime/wheel archives.
- Release ZIP CRC, safe paths, extracted file manifest and SHA-256 checked. Final
  deterministic-build and hosted-download hashes are recorded with the release.

## Not executed

- Windows 10/11 installation, shortcuts, registry integration and native DPAPI.
- Real Spotware application registration/approval, OAuth credentials or demo
  market streaming. These require the user's registered Open API application.
- Current Olymp Trade availability and identical cross-platform prices. The app
  starts with nine supported name matches, one conditional NASDAQ benchmark match
  and ten Forex candidates needing explicit Olymp match verification.

## Implementation decisions

1. Use the existing isolated cloud checkout, as approved, with a separate app
   directory. Cost if wrong: source must be moved; original files stay untouched.
2. Remote skill helper resources were unavailable, so execution used a manual
   ledger and test logs. Cost if wrong: additional bookkeeping; no product impact.
3. Move persistence tests from the pure-core task to the storage task, where their
   dependency exists. Cost if wrong: none; the original cases were retained.
4. Add optional broker-calendar coverage to history revalidation so scheduled
   closures do not look like missing candles. Cost if wrong: incorrect metadata
   could hide a gap; full history, open-session hole and DST tests guard this.
5. Native Windows/DPAPI and authenticated streaming could not be judged in this
   Linux environment without the user's application authorization. Ship the
   independently verified offline package with explicit prerequisites. Cost if
   wrong: platform or broker-specific defects may remain until tested on Windows.

## Fresh-context review and fixes

An independent reviewer inspected the complete implementation. Four Important
findings were reproduced and fixed; an installer rollback finding was raised to
Important because it could overwrite existing user integration files. Each fix
had a failing regression followed by a passing check and the final green suite:

- History is revalidated when its queued result is consumed, so a response cannot
  claim coverage of a candle that closed after background validation.
- Mapping editors bind the original account/session and reject changes before
  saving. Another account cannot inherit verified mappings from an open editor.
- Candle coverage includes partial broker sessions and holiday/DST transitions,
  while still rejecting missing bars during tradable intervals.
- Structured `BLOCKED_PAYLOAD_TYPE` / `retryAfter` metadata gates every request of
  that type on the connection; the engine defers history retries accordingly.
- Installer helpers back up/restore integration files, reject unrelated existing
  shortcuts, back up Windows uninstall registration and retain recovery backups
  if rollback itself fails. Registry/COM execution still requires native Windows.

No Critical findings or deferred Minor findings remain. The author's fix pass was
verified by regression tests; a second reviewer pass was not performed.

## Connection and use

Read [CONNECT_CTRADER.md](CONNECT_CTRADER.md). Create/activate an application in
the official cTrader Open API portal, enter its Client ID/Secret and exact redirect
URI in the app, authorize the **accounts** scope, exchange the returned code,
load/select the Spotware demo account and connect. Verify the instrument mappings,
wait for history and fresh quotes, then compare EMAs against cTrader. Any trade on
Olymp Trade is placed manually after checking its own chart and session.
