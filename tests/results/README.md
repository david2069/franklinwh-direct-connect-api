# Live test and capture results

Required by Rule 6 of `hardware_test_protocol.md` in `franklinwh-gateway-emulator`, which
binds this repo (see `.agents/policies/SOURCES.md`).

**Every live test or capture against the owner's aGate gets a file here**, dated, recording:

- what was commanded, with the exact frame and `cmdType`;
- when, to the minute, with the timezone;
- the firmware version (`IBG_VER` from the login manifest) and which aGate;
- what **read back** — not the ack; an ack is not a result;
- what was **restored**, and the read-back proving the restore took;
- which other clients were running (the bridge, a scheduler, a capture), or that they were
  stopped and how that was confirmed — by counting sockets, not by trusting a switch.

## Two rules about what goes in here

**Serials and site data do not.** Captures holding serials stay outside git (the owner's
capture directory); the results file describes them and gives the path. Mask identifiers in
the file itself — `<SERIAL>`, `<AGATE_IP>`, `192.0.2.x`.

**Nothing here is cited as public evidence.** These files are gitignored history for the
next session, not a source a CHANGELOG, PR or issue may point at. Quote the relevant line
inline in the public text instead. See `CLAUDE.md`, "What evidence can be published".

## Status

**Empty as of 2026-10-31, and that is accurate.** This session has run no live test against
the reference aGate. The `1821` Debug Mode evidence this library documents is the **Direct
Connect Bridge session's**, recorded on that repository's issue #311 — it is cited as theirs,
not reproduced here.
