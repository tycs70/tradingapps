# Trend Chaser Nifty 50 validation

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
