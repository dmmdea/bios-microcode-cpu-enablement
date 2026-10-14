# Safety and scope

This project documents an **owner-side modification of your own, out-of-warranty computer**. It is
not a security exploit and it has no "vulnerability" to report. It targets hardware the manufacturer
has stopped supporting, so there is no vendor to disclose to and no third party at risk.

## What this is

- A method and two **offline tools** for adding a CPU microcode patch, taken from the same vendor's BIOS
  for a sibling model, to an OEM board whose final BIOS lacks it, so that a newer CPU the board can
  already run electrically will also boot.
- The method leaves every region Intel Boot Guard verifies unchanged and keeps the original CPU's
  microcode as a fallback. The verifier prints `DO NOT FLASH` and exits non-zero when an image breaks
  any of those rules. The tools never write to hardware: holding back the write when the verifier
  fails is your job.

## What this is not

- Not a way to run code on hardware you do not own.
- Not a way to bypass a firmware password, disk encryption, or anyone else's security control.
- Not malware, persistence or evasion. The tools operate only on firmware image files **you** supply
  from **your own** machine, and the repo ships no vendor BIOS and no microcode binaries.

## The real risk is to your own board

Writing a motherboard's SPI flash can permanently disable ("brick") the board if done wrong. This repo
exists to make that outcome **much less likely** than the ad-hoc guides it is based on, but the risk is
never zero. Read `docs/05-safety-and-recovery.md` before doing anything, keep the pre-modification
backup the procedure makes, and have a hardware recovery path (an external SPI programmer) in mind
before you start. You accept that risk; see the MIT no-warranty clause.

## Reporting a problem with the repo

If a **tool or document here is wrong** in a way that could get someone's board bricked (a bad offset,
a check that passes when it should fail, a missing warning), please open an issue. That is a safety bug
in the documentation, and it is the kind of report this project wants.
