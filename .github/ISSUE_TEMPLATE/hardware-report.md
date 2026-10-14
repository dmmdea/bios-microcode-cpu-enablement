---
name: Hardware report (it worked / it didn't)
about: Tell others whether the method worked on a board, so the compatibility list grows
title: "[HW] <vendor> <model> + <CPU> — worked / failed"
labels: hardware-report
---

**A negative result is as useful as a positive one. Please do not include your service tag, MAC
address, SPI-dump hashes, hostnames, or local file paths.**

## The board
- Vendor / model / form factor (e.g. Dell OptiPlex 7060 SFF):
- Shipping BIOS version:
- Chipset (e.g. Q370):

## The donor microcode
- Which sibling board's BIOS you took the microcode from, and its version:
- CPUID / microcode revision added (e.g. 906ED rev 0x104):

## The CPU
- Model and sSpec on the lid (e.g. i7-9700T, SRG17):
- Retail (R0) or engineering/qualification sample:

## Write path
- Did your board need a service jumper? Which pins (from the board silkscreen/service manual)?
- Flashing tool and exact version (e.g. Intel FPT 12.0.49.1536):
- Any error codes you hit, and how you resolved them:

## Result
- [ ] Booted on the new CPU, verified CPUID/microcode revision
- [ ] Did not boot / other problem (describe)
- Did the pre-flash verifier pass? Any check it flagged?

## Anything else
Notes that would help the next person.
