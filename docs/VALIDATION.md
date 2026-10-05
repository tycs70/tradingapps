# Release validation — 5 October 2026

Release: EMA Pre-Cross Scanner 1.0.0, Windows 10/11 Intel/AMD x64.

The 46 automated Python checks cover provisional EMA recursion, chart geometry, mirrored bullish/bearish arming, ranking, equality, cancellation, observed crosses and confirmations, initial/reconnect semantics, stock-option eligibility, minute gaps/corrections, historical coverage, timestamp rejection, independent readiness, queue overflow, memory-only token handling, settings and instance locks. Actual Tk widgets were exercised on a Linux Xorg dummy display, including filters, chart rendering and close cleanup. PowerShell 7.5.3 parsed all installer scripts and exercised real filesystem helpers for quoted/Unicode paths, ownership, safe swapping, failed-swap rollback, retained settings and checksum rejection; these are cross-platform checks, not a Windows installation run.

Synthetic queue benchmark: 210 stocks and 420 expected ARMED/crossover transitions, with no missing transitions; cloud quote-to-event p99 235.042 ms on the initial measured run. This is processing latency and excludes broker delivery, network and Windows UI latency. The screen refreshes once per second.

Bundled runtime: CPython 3.12.15 Windows x86_64 from Astral python-build-standalone, 20261003 release. Original runtime SHA-256 verified against uv download metadata: `6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402`. Package verification checks every bundled file and all twelve pinned wheel hashes; the installer rechecks them, stages offline dependency installation and performs a Python/Tk/decode/EMA self-check before applying files.

The SDK's stock WebSocket helper disables TLS verification. This application uses its own certificate-verified websocket-client transport with the SDK protobuf decoder instead. REST requests retain normal TLS verification. Authorized WebSocket URLs, error response bodies and tokens never enter diagnostic/event logs.

Native Windows installation/shortcut/uninstall behavior, authenticated Upstox V3 subscription coverage, exchange-holiday status, and end-to-end laptop alert timing have not been verified here. No token was requested in chat. The Windows installer performs local startup checks, but these do not establish live trading readiness. Compare selected EMA values and quote times with five-minute Upstox equity charts and examine all coverage counts before using alerts.
