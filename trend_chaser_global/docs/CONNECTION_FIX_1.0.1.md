# Connection repair — 1.0.1

The user confirmed successful Windows authorization, demo-account discovery and
live quotes in 1.0.0, then supplied diagnostics showing repeated connection
interruptions. No user credentials or authorization codes were used in cloud tests.

The 1.0.0 reader sent keepalives only after a socket receive timeout. A busy quote
stream can prevent that timeout indefinitely. A verified local TLS fixture reproduced
the missing heartbeat against the original 1.0.0 source with a heartbeat already
25 seconds overdue. The fix checks the outgoing deadline on every receive-loop
iteration and sends a keepalive after ten seconds without an outgoing message.

Recovery now reauthenticates the same selected demo account in a background worker.
The scanner discards provisional continuity, preserves confirmed membership for
revalidation, reloads authoritative history and subscribes to fresh quotes before
ranking again. Backoff increases from 2 to 60 seconds and respects longer broker
cooldowns. Manual disconnection and credential removal cancel queued/in-flight
recovery. Invalid/revoked authorization stops retries and requests fresh authorization.

Only controlled reason categories reach diagnostics: remote close, network socket,
TLS, protocol, processing, broker session end or authorization end. Broker response
bodies, credentials and URLs are not logged. Cancel controls remain available while
connection work is pending. Dashboard refresh retains one timer and cancels it on close.

Validation includes failing regressions followed by passing checks for busy-stream
heartbeat starvation, automatic recovery/backoff, manual cancellation, refresh after
manual disconnect, UI cancellation/timer cleanup and matching package version. A
35-second continuous-stream TLS run received 3,432 quotes and all three scheduled
heartbeats without a disconnect. A real Engine/controller recovery fixture checked
an adverse missed candle before allowing any restored rank. Synthetic I/O does not
verify the user's network or native Windows behavior of this update.

The independent review found recovery edge cases which were reproduced and fixed:
token renewal preserves broker cooldowns; Disconnect retains a successfully rotated
token without restarting data; Forget and changed credentials discard late renewal
results; history authorization failures stop retries. A successful renewal also
handles cTrader's expected invalidation of the old token before reconnecting.

Final automated run: **148 tests, 147 passed, 1 Windows-only DPAPI test skipped**.
The twelve real Tk8.6 dashboard tests, offline verifier and PowerShell filesystem /
parser checks passed. The synthetic benchmark processed all 210 instruments and
420 transitions at 353.692 ms p99, excluding broker/network and Windows rendering.

Close 1.0.0 and run the new extracted INSTALL.bat to update in place. Saved DPAPI
authorization, mappings and preferences remain under the existing app data directory.
