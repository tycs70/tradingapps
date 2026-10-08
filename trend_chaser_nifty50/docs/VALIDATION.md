# Trend Chaser Nifty 50 validation

## Nifty 50 1.0.1 update — 8 October 2026

The reported Windows failure was reproduced with HTTP 200 returning an HTML page instead of the official CSV. Settings & Upstox now supports a browser download and validated same-day CSV import. Imported lists are revalidated, use the existing ISIN/active-option selection, show their import time, and expire in IST. Invalid replacements preserve the previous import; other index filenames are rejected. The filename and CSV checks cannot certify a manually supplied file's origin or download date: the user must download fresh from the official link. Imports are blocked during active/recovering sessions, and an imported-list session disconnects at day expiry.

Observed checks:

- Full Python suite: 146 tests, 145 passed and one native Windows DPAPI test skipped on Linux. All Tk tests ran on the offscreen display.
- Offline runtime/dependency/V3 decoder/EMA/Nifty 50/trend/demo/Tk verification passed for version 1.0.1.
- Synthetic worker benchmark: all 420 transitions for 210 stocks, p99 391.074 ms (excludes broker delivery and Windows rendering).
- PowerShell 7.5.3 filesystem tests passed for ownership, program replacement, rollback, preserved settings/encrypted-token fixture/trend state/logs and corrupted-package rejection. PowerShell was verified against its publisher checksum before execution.
- Independent review caught a list-change-during-feed-recovery issue; a reproducing test failed before the session guard and passed after it. A second review of recovery/IST-expiry behavior found no important issues; its focused 64-test run passed.
- The update retains the Nifty 50 install root, ownership marker, Desktop/Start Menu shortcuts, uninstall registry key and data directory. Only DisplayVersion becomes 1.0.1. Runtime, dependency pins, Windows wheels, strategy, indicators, history, trend ranking and original option-eligibility rules are unchanged.

Native Windows registry/shortcut creation, DPAPI and authenticated Upstox streaming still require checking on the target laptop. The installer runs its native offline security/Tk checks before swapping program files. Browser CSV import is the supported recovery path; this update does not claim the NSE website now accepts automated downloads.

The variant is based on the verified Trend Chase Version 1 1.0.1 layout update.
Only its Nifty 50 universe boundary and application identity change. The scanner,
strategy, trend lifecycle, indicators, history, models and existing option eligibility
module are retained. The dependency pins, wheel files and Windows runtime are unchanged.

## Checks

- Existing regression suite: scanner entries, completed-candle confirmations/removals,
  ranking, recovery, daily resets, logging, token handling and seven-row UI.
- New universe tests: exactly 50 official constituents, ISIN matching across renames,
  exclusion of outside symbols, expired options and missing contracts, BOM/quoted CSV,
  invalid/duplicate/missing rows, malformed CSV and network rejection without fallback.
- Separate settings and instance locks: the original app and Nifty 50 app can coexist.
- Installer ownership checks reject the original Trend Chase marker. Swaps preserve
  Nifty 50 data; failed swaps roll back; damaged package checksums are rejected.
- Source and packaged offline verification render the renamed Tk app and both tables.
- Release hashes and ZIP integrity are verified after packaging and delivery.

## Observed results (7 October 2026)

- Full suite: 127 tests, 126 passed, one native Windows DPAPI test skipped on Linux.
- Tk offline verifier passed, including the Nifty 50 universe boundary, identity,
  feed decoder, EMA and trend lifecycle checks.
- Both seventh rows and Entry IST cells fit in the 1200 x 680 main dashboard;
  the packaged sample preview also fits at 1200 x 800.
- PowerShell installer filesystem checks passed for ownership rejection, safe
  replacement, rollback, retained settings/token/trend state/logs and corruption.
- Synthetic unchanged-worker benchmark: 210 stocks, 420 transitions, p99 519.07 ms
  (excludes broker/network/Windows rendering).
- Core module byte comparison confirmed scanner, strategy, trend book, indicators,
  history, models and the original option-eligibility module are unchanged.

## Limits

This cloud environment runs Linux. Filesystem installer checks do not execute native
Windows registry/shortcut creation or DPAPI. The offline verifier exercises DPAPI on
Windows during installation. Authenticated Upstox streaming and a fresh official
Nifty 50 download have not been tested here; those hosts are blocked by this cloud's
network policy. Universe integration is tested using synthetic HTTP responses and
real parsing/filtering, without credentials or live orders.
