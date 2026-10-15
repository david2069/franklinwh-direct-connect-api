# Persistent sessions — design

**Status: the recommendation in §3 (option B) shipped** — `DirectConnectTransport` holds
an `RLock` across `request()` and `login()`, and `DirectConnectClient` has
`connect()` / `close()` / `connected` / `ensure_session()` / `connects`
(`CHANGELOG.md` → Unreleased, #6). The **§6 open questions are still unmeasured**: nobody
has established whether the aGate closes an idle TCP/9000 session, or whether a held
login expires server-side. Written 2026-10-13; status updated 2026-10-15.

See [Held sessions and threads](USAGE.md#held-sessions-and-threads) for how to use what
shipped; this page is the reasoning behind it.

Problem brought by the bridge: every call opens a TCP connection **and performs a
login**, then closes it. The bridge's poller does that per gateway every 30 s, and it
has 31 call sites following the same `with client(...) as c: c.login()` pattern.

The fix belongs here, not in the bridge: the session, its lifetime and its safety are
properties of **the connection**, which this library owns. Solving it downstream would
leave the CLI, the emulator and every third party still paying connect-per-call.

---

## 1. The transport already supports this

Almost nothing needs building. `DirectConnectTransport` already does the hard parts:

| Behaviour | Where | Status |
| --- | --- | --- |
| `connect()` is idempotent — returns if `_sock` is live | `transport.connect` | ✅ |
| Reconnect resets framing state and re-logs-in | `transport._reconnect` | ✅ |
| `request()` reconnects when the socket is gone, and retries transient failures | `transport.request` | ✅ |
| `_logged_in` tracks whether a re-login is owed | `transport.__init__` | ✅ — comment literally says *"re-login after a transient reconnect"* |

That path was written for persistence and has **never been exercised**, because nothing
holds a connection long enough to need it.

**So sessions do not persist for one reason only: callers close them.**
`DirectConnectClient.__exit__` calls `transport.close()`, and every documented example
uses `with`.

---

## 2. The real blocker: the client is not thread-safe, and does not say so

**There is no locking anywhere in `transport.py` or `client.py` — zero occurrences.** A
transport carries shared mutable state across a call:

* `_sock` — the socket
* `_stream` — the `FrameStream` reassembly buffer
* `_pending` — frames read but not yet matched
* `_snno` — the sequence number
* `_logged_in` / `_login_data_area`

Today that is harmless: every caller constructs its own client, so there is one user per
transport. The moment a client is held and shared — exactly what persistence invites —
two concurrent `request()` calls interleave on one socket.

**Measured, 2026-10-13, 6 threads x 12 calls on one held client against the emulator:**

| | connects |
| --- | ---: |
| with the lock | **1** |
| without | **5** |

**The failure mode is not corrupted data**, which is what this section first assumed.
Unlocked, each caller's frames time out, `request()` reconnects and retries, and the
results still come back correct — paid for in reconnect storms and latency. The retry
machinery masks the race.

That makes it *worse* to find, not better: the obvious tests (no exceptions, well-formed
responses) pass either way. **The connect count is the only signal that discriminates**,
and nothing was counting connects until this work added a counter.

**Nothing in the docs mentions threads at all.** A consumer has no way to know.

This is the decision this document exists to make. Persistence without an answer here is
a trap, not a feature.

---

## 3. Options

**A. Document "not thread-safe; one client per thread."**
Cheapest, honest, and pushes the problem to every consumer — each inventing its own lock,
differently. The bridge would need one immediately.

**B. Lock inside the transport.** A single `threading.RLock` around `request()` and
`login()`. A held client becomes safe to share; concurrent callers queue.

**C. A `Session` / pool abstraction in the library.**
More surface, more to get wrong, and it duplicates what a lock plus a held client gives.

**Recommendation: B, plus documentation.** It makes the obvious usage correct rather than
merely documented, and it costs one lock on a path already bounded by device latency.

**Why serialising is right rather than a limitation:** the device is the scarce resource.
The aGate's concurrent-connection behaviour is unmeasured and probably small, and the
Modbus Bridge reached the same conclusion from the other side. Queueing two callers on
one socket is correct; opening a second socket to avoid queueing is the failure mode.

---

## 4. Shape

* **`DirectConnectTransport` gains an internal `RLock`**, held across `request()` and
  `login()` — the whole send-plus-receive pair, since the hazard is interleaving, not
  either half alone. `RLock` because `request()` can re-enter via `_reconnect` →
  `_do_login`.
* **`DirectConnectClient` gains an explicit lifecycle** that does not require `with`:
  `connect()` / `close()`, with `with` still closing as it does today. Nothing existing
  changes behaviour.
* **An idle policy is the CONSUMER's**, not the library's. The library should not decide
  when a socket has been held too long; it should make holding and closing cheap and let
  the bridge, CLI and emulator choose. The bridge's figure is 10 minutes.
* **Diagnostics:** expose how many real connects a transport has made. Without it,
  "persistence is working" is unverifiable — and the bridge measured 38 TIME_WAIT
  sockets a minute precisely because nobody was counting.

---

## 5. What must not change

* **`with` keeps closing.** Existing code and every documented example rely on it.
* **No implicit global pool.** Keyed caches of connections hide lifetime from the caller;
  the consumer should decide what it holds and for how long.
* **Retry semantics stay as they are.** `request()` already documents that aGate requests
  are idempotent set-to-value operations, so a retry cannot double-apply. That reasoning
  is unaffected by persistence and should not be revisited casually.

---

## 6. Open questions

1. **Does the aGate close an idle TCP/9000 session, and after how long?** Unmeasured. It
   decides whether an idle-close policy is a courtesy or a necessity. The bridge is
   stopped for a Modbus correlation run tonight; a parallel local-channel measurement
   would answer it cheaply.
2. **Does a held login expire server-side?** `_logged_in` assumes a re-login is needed
   only after a reconnect. If the device expires sessions, a long-held client would start
   failing in a way the current code reads as a transport fault.
3. **Should `login()` be lazy?** Today callers call it explicitly. With persistence, a
   held client could log in on first use and re-login transparently — tidier, but it
   changes a documented pattern and is not required for the win.

Questions 1 and 2 are measurements, not opinions, and should be answered before the
idle policy is fixed.
