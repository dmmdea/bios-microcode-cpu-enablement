# Safety and recovery

Sources last checked 2026-10-11. Vendors rewrite their support pages, so re-read the Dell articles linked below before you rely on them.

The procedure in [04](04-procedure.md) erases and reprograms one firmware volume, 983,040 bytes (`0xF0000`) of the chip that holds your board's firmware. It is the one step in this project that can leave a board that does not start. A failed write you notice before rebooting can usually be undone from the running OS. After a reboot, the way back is the vendor's recovery procedure (a key combination at power-on and a USB stick) if the early boot code still runs, and an SPI programmer if it does not. Of the three dead-board reports for this class of mod, two mention a hardware programmer as the way back and the first and third show no result (reported, unconfirmed; section 2.3).

> [!IMPORTANT]
> **The backup you read before the first write is the most important file in this project.** Every recovery step except the vendor's stock-BIOS recovery restores from it, and nothing else can recreate your board's descriptor, MAC address, ME region and NVRAM. [Section 1](#1-the-backup-comes-first) says how to make it and how to know it is good.

> **Reference build.** The write passed on the first attempt and read back equal to the payload. Nothing failed, so no rung of the recovery ladder was run on that board, and no external programmer was used. The ladder below is assembled from Dell's documentation, forum recovery reports, the tools' own manuals and the reference record. Each rung says how far it has been tested.

Evidence words (verified on the reference build, reported, inferred, unconfirmed) are defined in [03](03-how-it-works.md#how-to-read-the-evidence). A link is an outside source.

**On this page:** [1 The backup](#1-the-backup-comes-first) · [2 How the operation bricks a board](#2-how-the-operation-bricks-a-board) · [3 Before you write](#3-before-you-write-the-verifier-must-pass) · [4 The recovery ladder](#4-the-recovery-ladder) · [5 Do not do this](#5-do-not-do-this) · [6 If it fails anyway](#6-if-it-fails-anyway-say-so) · [What is not established](#what-is-not-established) · [Sources](#sources)

## Terms used here

| Word | Meaning here |
|---|---|
| Volume | The firmware volume the procedure writes. On the reference BIOS it runs from region offset `0xD20000` to `0xE10000`, which is flash address `0x1D20000`, length `0xF0000`. It holds the microcode and the FIT. |
| FIT | The table the CPU reads at reset, before any BIOS code runs. It points at the microcode, the startup ACM and the two Boot Guard manifests (type `0x0B` Key Manifest, type `0x0C` Boot Policy Manifest). |
| IBB | The initial boot block: the boot code Boot Guard hashes before the BIOS runs. Four segments on the reference BIOS, the lowest at region offset `0xF00000`. |
| Region image | `own_region.bin`, the 16 MB BIOS region cut out of your pre-write full dump ([04](04-procedure.md), 0.6). |

Every offset on this page is the reference build's (BIOS 1.32.0). Yours differ ([03](03-how-it-works.md), section 9). The [glossary](08-glossary.md) has the rest.

## 1. The backup comes first

Rungs 1, 2 and 4 of the ladder write bytes from your own pre-write dump back to the chip. Rung 3, the vendor's recovery, installs a stock BIOS and not yours. The dump is the one thing that cannot be rebuilt after a failure, because it holds your board's identity: the descriptor, the GbE region with the MAC address, the ME region and the NVRAM.

A backup counts when it has all of these.

- **It is the whole chip.** `.\FPTW64.exe -d full_1.bin` with no region switch. The `-bios` form saves the BIOS region and nothing else. A poster in the 7060 thread who held only a `-bios` dump while waiting for a programmer was told to read the complete chip with the programmer, check its structure in UEFITool NE, and make at least two identical reads ([Win-Raid, page 8](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=8), 2022-06-12; reported, unconfirmed).
- **It was read twice and the two files are byte-identical.**

  ```
  .\FPTW64.exe -i
  .\FPTW64.exe -d full_1.bin
  .\FPTW64.exe -d full_2.bin
  ```

  ```powershell
  (Get-FileHash full_1.bin).Hash -eq (Get-FileHash full_2.bin).Hash      # must be True
  (Get-Item full_1.bin).Length                                           # must equal the flash size from -i
  ```

  If the pair differs, stop. The read path or the machine state is not stable (driver trouble, or something writing to NVRAM between reads), and a backup you cannot repeat is not a backup. The two dumps on the reference build, taken minutes apart, hashed identically (verified on the reference build).
- **Both reads were taken in the same machine state.** A dump taken with the service jumper set differs from one taken without it in the ME region and in the NVRAM area at the start of the BIOS region, and nowhere else. The descriptor, GbE region, microcode volume, FIT and IBB were identical (verified on the reference build). When states differ, compare ranges with `diffranges.py` ([tools/README.md](../tools/README.md#helper-scripts-for-the-procedure)) and not whole-file hashes.
- **It is stored in two places off the machine.** A dump on the machine's own disk is out of reach when the machine will not start.
- **It opens.** Load it once in [UEFITool NE](https://github.com/LongSoft/UEFITool). The descriptor, the BIOS region and the volume at the offset you expect should all appear. That separates a chip image from a truncated read.
- **It is private.** The image carries the MAC address and the service tag (verified on the reference build), and the NVRAM area and ME region may hold other ownership data (reported, unconfirmed). Never post it, its hash or a screenshot of it. This repo's `.gitignore` excludes `*.bin` for that reason.
- **It is never overwritten.** Later reads get new names.

A backup is not proven until it has restored something, and the reference build never restored one. If you own a programmer, read the chip with it before the first write (board unpowered, 3.3 V-safe programmer, steps in rung 4) and compare that read with the FPT dump using `diffranges.py`. They should agree on the descriptor, GbE region, microcode volume and IBB (inferred). One comparison shows that the clip fits, the chip identifies itself and your software handles its size, while nothing is at stake. The author of the popular 7060 blob gave the same advice: back up with a hardware programmer ([Win-Raid, page 7](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=7), 2020-09-18).

## 2. How the operation bricks a board

Five things have bricked boards of this kind, or are expected to. For each: what happens, what has been seen, and the rule or verifier check in this repo that avoids it. A sixth cannot be checked offline.

### 2.1 A changed byte inside the Boot Guard IBB

**What happens.** Boot Guard's startup code, a module Intel signs, hashes the IBB and compares the result with the SHA-256 stored in the signed Boot Policy Manifest, before any BIOS code runs ([Ermolov, ZeroNights 2016](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf); [Matrosov, Black Hat USA 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf)). On a board set to enforce, one changed byte inside the IBB makes the comparison fail and the machine powers off. The 7060 is reported to run profile 5, meaning verified-boot plus measured-boot with immediate shutdown on failure (reported, unconfirmed). The reference board's fuses were not read, and the mapping from the number to that name is inferred ([03](03-how-it-works.md), section 4).

**What it looks like.** A brief flicker, power-off, no video, and no answer to the Ctrl+Esc recovery combination, because no BIOS code has run that could answer. The reference record expected exactly this. It is expected and not observed, because the reference build never failed. Only a programmer brings the board back.

**How the method avoids it.**

- The write window is one volume. On the reference BIOS it ends at region offset `0xE10000` and the lowest IBB byte sits at `0xF00000`, so 960 KB (`0xF0000` bytes) of untouched flash lies between them (verified on the reference build).
- The verifier recomputes the IBB digest from your own image and requires it to equal the digest in the signed manifest (`IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM`), to stay unchanged in the modified image (`IBB digest UNCHANGED in the modified image`), and to show zero changed bytes outside the volume (`zero bytes changed outside the microcode FV`; all three in [04](04-procedure.md), 2.2).
- The first of those is the one to read first. Section 3 says why.

### 2.2 Moving the FIT, or the Key Manifest and Boot Policy Manifest entries

**What happens.** The CPU reads the FIT before the first BIOS instruction, and the startup code finds the signed manifests through the FIT's type `0x0B` and `0x0C` entries ([Intel FIT specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf), sections 4.10 and 4.11). The FIT lies outside the IBB hash, so an edit to those two entries passes the digest check and still breaks the chain ([03](03-how-it-works.md), section 5).

A missing or invalid table is handled by the platform. The specification says the result "depends on platform provisioning and will range from immediate unbreakable shutdown and up to fallback to time-limited legacy boot followed by a platform reset" (section 3.1, rule 3, as quoted in [03](03-how-it-works.md)). That a stale or moved pointer fails like a changed IBB is inferred from the verifier's rationale. Nobody has reproduced it.

**How the method avoids it.**

- Same-size slot swap. The donor microcode overwrites an existing slot of exactly its own size, so the FIT stays byte-identical. On the reference build the 906ED entry and the 906EB slot it replaced are both `0x1A000` bytes, and the changed bytes lie between `0xD3A004` and `0xD53FFF` (verified: recomputed from the reference build's dump, payload and modified image; the builder's own August output was not retained).
- The verifier requires the whole FIT to be byte-identical (`FIT byte-identical to the original`), which includes the type `0x0B` and `0x0C` entries (`Key Manifest (0x0B) and Boot Policy Manifest (0x0C) FIT entries bit-identical`).
- Append mode, where the FIT has to grow, is not what the reference build did. Treat it as expert-only ([04](04-procedure.md), "Not covered here"; [03](03-how-it-works.md), section 6).

### 2.3 A prebuilt blob written onto a different BIOS version

**What happens.** The forum files for this mod are ready-made replacements for the whole volume, built for one BIOS version. For the 7060 the popular one was made for BIOS 1.4.2. Its author warned against using it on any other BIOS version and attributed the problem to a Boot Policy address that changed in newer versions ([Win-Raid, page 7](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=7), 2021-03-23; unconfirmed). The same `-a` and `-l` command on a newer BIOS replaces the FIT and everything else in the window with the other version's bytes. The mechanism is the author's explanation. No teardown has been published, and the stale-pointer reading is inferred.

A 2020 post says the same window also overwrites the ACM (reported, unconfirmed). On BIOS 1.32.0 the ACM sits at region offset `0xFD0000`, outside the window (verified on the reference build), so either the layout changed between versions or the post was imprecise ([03](03-how-it-works.md), section 8). Another Dell board was reported with its volume at a different base, flash address `0x1D50000` (Vostro 3670, [Win-Raid, page 9](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=9), 2024-08-20; reported, unconfirmed).

**What has been seen.**

| Date | BIOS | What the poster reported | Way back reported | Source |
|---|---|---|---|---|
| 2020-09-19 | not known to the poster | Reported a bricked chip after the `fptw64` write, no backup | Another member offered a full dump of a 65 W 7060; whether it was written is not shown | [page 7](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=7) |
| 2021-03-23 | 1.9.1 | The board accepts the write, then shows a flashing amber light on the first reboot and is dead | A hardware programmer and an intact 7060 image | [page 7](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=7) |
| 2022-06-12 | 1.18.0 | The write finished without error. After a restart: no POST, amber blinking | A CH341A and the poster's own backup; the post ends before the result | [page 8](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=8) |

All three are reported, unconfirmed. The amber blinking in the last two is a different picture from the flicker-and-power-off the reference record expects from a Boot Guard shutdown, so the failure those boards hit may not be the one in 2.1.

**How the method avoids it.**

- The payload is built from your own dump and from a donor BIOS you downloaded from the vendor, never from someone else's file ([04](04-procedure.md), Phase 1).
- The verifier requires the payload to equal exactly that slice of the verified modified image (`payload identical to the modified image at that offset`) and to be exactly as long as the volume, unless you pass `--payload-offset`, which Gate 2 forbids.
- A payload belongs to one BIOS version. A BIOS update, even the vendor's own, means a new dump, a new build and a new verification ([04](04-procedure.md), 5.8).

### 2.4 An interrupted write

**What happens.** The volume holds the FIT as well as the microcode. The window is 15 erase blocks of 64 KB, and all of it is erased and reprogrammed, including bytes that do not change ([04](04-procedure.md), 4.1). A write that stops between erase and program can leave the board with no valid table for the CPU to read at reset, which is the situation the specification passage in 2.2 describes. Inferred from the layout, not tested.

The usual causes are a power cut, an SSH session that drops and takes FPT with it (Windows OpenSSH ends the processes of a connection that drops; reported, unconfirmed), sleep or an update restart in the middle of the write, and someone pulling the plug because nothing seems to be happening.

**How the method avoids it, and what it cannot.**

- It writes the volume and nothing else, with both `-a` and `-l`, a payload exactly as long as `-l`, no `-y` or `NOVERIFY`, and one FPT process at a time ([04](04-procedure.md), 4.4).
- If you are remote, FPT is launched through WMI as a separate process and its log is polled. The detach is proven first with a harmless command ([04](04-procedure.md), 4.3). On the reference build the owner read the CPU lid, moved the service jumper on and off, swapped the CPU and thermal pad, and removed the case mesh screens; everything else was done remotely over SSH by an AI agent, so a dropped session was a live risk there. Never start the write from an SSH prompt.
- Mains power should be stable, with sleep, hibernate and updates off. A UPS is better. The reference build had none and accepted the risk, which is a record and not a recommendation.
- If the log does not end in `FPT Operation Passed`, or the readback differs, do not reboot ([04](04-procedure.md), 4.7).

No software closes the gap left by a power cut during the erase and program cycle. That is why section 3 wants the programmer in your hands before the first write.

### 2.5 The wrong address or length

**What happens.** FPT takes an absolute flash address, which is the region base plus the offset inside the region. On the reference board that is `0x1000000` plus `0xD20000`, so `0x1D20000`. Pass the region offset by mistake and the payload lands 16 MB lower, in the ME region. The reference record also warns that leaving out `-l` makes FPT write from the address toward the end of the flash (reported, unconfirmed; not tested, and Intel's manual is not public). A window that cuts an erase block may make the tool rewrite that block's neighbours (inferred; [04](04-procedure.md), 4.2).

**How the method avoids it.**

- `<ABS_ADDR>` is computed as `<BIOS_BASE>` plus `<FV_OFFSET>`, with the base read from `-i` output ([04](04-procedure.md), "Values you carry through the phases"). Both `<ABS_ADDR>` and `<FV_LEN>` must be multiples of `0x10000`.
- Offsets are proved before anything is written: the volume cut from your region image must equal the same slice of the vendor's stock image ([04](04-procedure.md), 1.3).
- A 4 KB probe write of `0xFF` over blank space inside the volume must fail with Error 167 without the jumper and pass under it, with a blank readback ([04](04-procedure.md), 3.3 to 3.6).
- You never type another board's numbers. The reference values are examples.

### 2.6 A check you cannot run offline

Some AMI-based BIOSes add their own firmware-volume hash check on top of Boot Guard ([Matrosov, Black Hat USA 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf)). If one covered the microcode volume, the swap would trip it instead of the ACM, and the failure would be whatever the vendor coded. It would hit with either CPU, because the volume itself changed. Nothing in a dump shows it. On the reference build no such check fired: the board booted on the modified volume and has run since (reported, unconfirmed; [03](03-how-it-works.md), section 5). On any other board only a boot tells you, which is why the procedure boots the original CPU on the modified volume before the new CPU goes in ([04](04-procedure.md), Phase 5).

## 3. Before you write: the verifier must pass

No PASS, no write. Run the verifier from [`tools/`](../tools/) on the exact files you will write ([04](04-procedure.md), Phase 2), and hold it to Gate 2 in full: the RESULT line is `RESULT: ALL CHECKS PASSED` with no "(n warning(s) above)" after it and no `[WARN]` line anywhere; none of the override flags was used (verifier: `--accept-no-bpm-check`, `--ucode-window`, `--payload-offset`; builder: `--accept-no-bpm-check`, `--fv-base`, `--fv-len`, `--force`); and `IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM` and `IBB digest UNCHANGED in the modified image` both printed PASS by those names.

> [!CAUTION]
> **A FAIL is final for that image.** A traceback or a missing line counts as a FAIL. Never change what a check tests to make it pass, and never reach for an override flag until it agrees with you. If it disagrees with you, it is probably right.

Read `IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM` first. It recomputes SHA-256 over the IBB segments listed in the Boot Policy Manifest of your original image and compares the result with the digest stored in that manifest. That one line tells you whether the tool's reading of your manifest reproduces your board's own policy. The segment list comes from your image, not from values worked out for one BIOS ([04](04-procedure.md), "The repo's tools"). A FAIL there has no override flag: the dump is damaged, the layout is one the parser does not know, or the board already fails its own check. Take a fresh dump, and if it persists open an issue with the BPM bytes and no other data. `IBB digest UNCHANGED in the modified image`, which confirms the digest is unchanged, proves nothing when that first line failed. A PASS shows that the tool's reading of the manifest covers every segment.

A PASS does not show that the new CPU will boot. [04](04-procedure.md), 2.3, lists what the verifier does not check: donor provenance, the platform-ID mask (the builder checks it when given `--platform-id`), extra vendor hash checks, and your chip, power supply and jumper.

| Before the write | Pass condition | Why |
|---|---|---|
| Backup | Two full-chip reads, byte-identical, copied off the machine (section 1) | Rungs 1, 2 and 4 restore from it |
| Recovery hardware | Chip package identified (16 legs is SOP16 and takes a clip; 8 leadless pads is WSON-8 and does not), datasheet voltage read, a programmer checked at 3.3 V on its data lines, clip in hand | Finding out after the board is dead costs days of shipping. [03](03-how-it-works.md), section 7, and [02](02-does-my-hardware-qualify.md), C8, ask for this too |
| Recovery media | `BIOS_IMG.rcv` for your exact model, built on another PC and copied to a FAT32 stick; a wired USB keyboard to hand (rung 3) | The one attempt to build it on the target went wrong (rung 3) |
| Rollback slice | `ucode_fv_orig.bin` cut from your pre-write dump, equal to the vendor's stock slice, next to FPT on the target ([04](04-procedure.md), 1.3) | Rung 1 is one command only if the file is already there |
| Write path | The 4 KB probe fails with Error 167 without the jumper and passes under it. If it still fails with the jumper confirmed active, stop: the next route is a programmer | Tests the tool, the address arithmetic and the lock before the real write |
| FPT build | The build that passed the probe under the jumper is the build you write and roll back with | Builds differ in whether they start under the jumper. On the reference board 12.0.49.1536 did and 12.0.85.1919 did not, failing with Error 51 and then 620 (reported, unconfirmed) |
| Old CPU | The original CPU is fitted for the write. The new CPU stays in its box until the readback matches and the original CPU has booted on the modified volume | Separates a bad write from a CPU the board does not accept |
| Power and session | Stable mains, sleep, hibernate and updates off, detached launch proven if you are remote | Section 2.4 |
| BitLocker | Off, or suspended with the recovery key saved | The TPM measures firmware, so a changed image can trigger a recovery prompt ([04](04-procedure.md), 0.2). Dell's recovery can trigger one too. It was off on the reference build |
| Chassis intrusion (Dell) | Switched off in BIOS setup before you open the case | An armed switch is reported to halt POST with no video once the case has been opened (reported, unconfirmed). It looks like a brick |
| Jumper | Header identified from the legend printed on your own board, photographed before and after. The cap comes from a spare, not from another pair | Removing the cap from a password pair clears the BIOS password (reported). With the service jumper set the ME is off |

A no in any row is a stop.

## 4. The recovery ladder

Work down the ladder and stop at the first rung that works. Each rung is slower and more final than the one above it. Change one thing at a time and write down exactly what you see before you change anything: the LED pattern, whether the fans spin, whether there is video.

The ladder was written for the Dell desktop this method was proven on. Other vendors differ. HP Sure Start is reported to replace a modified BIOS with a stock one from its own protected copy, even after an external programmer wrote the modified one (a post about an HP laptop, [Win-Raid thread 35122](https://winraid.level1techs.com/t/rollback-hp-elite-dragonfly-bios-and-intel-me/35122); desktop behavior unconfirmed). Do not assume any rung holds there.

### Where to start

| What you see | Most likely | Start at |
|---|---|---|
| The write log does not end in `FPT Operation Passed`, or the readback differs, and the OS is still up | A partial write | Do not reboot. [04](04-procedure.md), 4.7, then rung 1 |
| New CPU fitted, no POST. With the original CPU fitted the board starts normally | Not a brick: the board does not accept the new CPU | Rung 0 |
| Original CPU fitted, no OS, repeating amber pattern such as 3,6 or 3,7 | BIOS region damaged, early boot code probably still runs (inferred) | Rung 3, then rung 4 |
| Original CPU fitted, a brief flicker and power-off, no video, no pattern, no answer to Ctrl+Esc | A Boot Guard shutdown (expected, not observed) | Rung 4 |
| Anything else | Unknown | Original CPU in, try rung 3 once. If no recovery screen appears, rung 4 |

### Rung 0: put the original CPU back

Power off, unplug, and refit the CPU that was in the board before. The swap never touched its microcode (by construction; [03](03-how-it-works.md), section 7), so it should start the board again (inferred; the reference record shows no boot on the original CPU between the write and the swap). Rungs 1 and 2 need the service jumper set. If you already removed it ([04](04-procedure.md), 5.2), set it again ([04](04-procedure.md), 3.4) before rung 1 or 2; if it is still set, leave it while you decide whether to roll the BIOS back. If you keep the modified BIOS, remove the jumper when you are done with FPT.

Some things look like a brick and are not.

| What you see | What it is | What to do |
|---|---|---|
| `Alert! Service Mode jumper is set` at POST, waiting for a key | Expected while the jumper is set (reported) | Press a key. Remove the jumper when you finish |
| No video, fans running, right after you reopened the case | Chassis intrusion detection halting POST on a Dell (reported, unconfirmed) | Close the case properly. Switch intrusion detection off in setup before the next opening |
| The board starts, then shuts off with an amber indicator flashing, with a 65 W CPU | One poster reported the board's protection tripping ([page 7](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=7), 2021-02-23; unconfirmed). The post does not say whether the cause was power or an early shutdown. The 7060 Micro comes in 35 W and 65 W board variants ([02](02-does-my-hardware-qualify.md), C9) | Refit the original CPU and check the board's design TDP. If the same thing happens with the original CPU fitted, it is not this row: see Where to start |
| A CPU other than the original will not start | The swap gave up that CPU's microcode ([03](03-how-it-works.md), "What the swap costs") | Use a CPU whose microcode is still in the image, or redo the swap against another slot |

### Rung 1: re-flash the microcode volume from your backup

**When.** The OS still runs. Typically the write failed or its readback differs, or the new CPU was rejected and you want the stock volume back. **Needs.** The jumper still set, the FPT build that passed the probe, and `ucode_fv_orig.bin` next to it.

First read what the flash holds and compare it with both files ([04](04-procedure.md), 4.7). If it equals neither, repeat the original write once. If that fails again, or you want the stock volume back, write the rollback slice the same way:

```
.\FPTW64.exe -f ucode_fv_orig.bin -a <ABS_ADDR> -l <FV_LEN>
.\FPTW64.exe -d readback.bin -a <ABS_ADDR> -l <FV_LEN>
```

```powershell
(Get-FileHash readback.bin).Hash -eq (Get-FileHash ucode_fv_orig.bin).Hash      # must be True
```

The reference values were `0x1D20000` and `0xF0000`. Use yours. The same rules apply as for the first write: detached if you are remote, no `-y`, stable power. This rung rewrites the same window as the write that failed, so it carries the same interruption risk. You are making the same bet a second time, which is worth it only because the alternative is a board that does not start. Do not reboot until the compare says `True`.

**Tested on the reference build?** No. The rollback slice was staged on the machine and, as far as the records show, never written. The command form is the one the reference build used for its write (reported, unconfirmed).

### Rung 2: restore the whole BIOS region

**When.** Rung 1's readback still does not match, or you suspect damage outside the volume: a mistaken address, or a full-dump comparison ([04](04-procedure.md), 4.6) that shows differences elsewhere. The OS must still run.

```
.\FPTW64.exe -bios -f own_region.bin
```

`own_region.bin` is the BIOS region cut from your pre-write dump. It should also restore the NVRAM as it stood at the time of that dump, so BIOS settings go back to that state (inferred). This writes 16 MB, IBB included. You are writing bytes that were there before, so Boot Guard is satisfied, but the window is much larger than rung 1's and so is the exposure to an interruption. The same conditions apply, and `-a` and `-bios` must not be combined (reported, unconfirmed).

Use a file of exactly the region's size. That is the form reported on the forum for a BIOS-region write: dump with `-bios -d`, edit, write back with `-f <file> -bios` ([Win-Raid, 7060 thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937), 2024-05-01; reported, unconfirmed). Check `-h` for your build. If FPT refuses the file, do not widen anything to get past the refusal. Go to rung 4.

**Tested on the reference build?** No. Read your build's help (`.\FPTW64.exe -h`) before you need this rung, not during.

If the OS no longer runs, rungs 1 and 2 are not available. The write on the reference build was run with Windows FPT; a UEFI-shell build was staged and there is no record it was used.

### Rung 3: the vendor's BIOS recovery (Dell)

Dell's recovery rewrites the BIOS region from a file on a USB stick. It needs the board's early boot code to be intact enough to start and look for the stick. Dell does not document that dependency, so the dependency is inferred. By the same reasoning, a Boot Guard shutdown never reaches the point where a recovery screen could appear (inferred).

**Prepare it on another PC, before you flash anything.** Download the BIOS package for your exact model from Dell. Taking the version your backup came from means a later redo starts from a stock image you have already analysed (inferred). Dell says the recovery works with any version ([KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453)). Then make the recovery file. Dell documents two routes:

- Run the package with `/writehdrfile /writeromfile` and rename the `.hdr` it produces to `BIOS_IMG.rcv`. [KB 000130691](https://www.dell.com/support/kbdoc/en-us/000130691) gives this route and lists the OptiPlex 7060 among the affected models. Close all work first and use a machine you can afford to reboot: on the reference build that exact command rebooted the PC (cause not established).
- Rename the downloaded file to `BIOS_IMG.rcv`, uppercase, with the underscore and the `.rcv` extension ([KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453)).

On the reference build the first route failed (section 5; reported). The second route, which runs no package, was not tried. So the knowledge-base switches are unreliable per model, and the rename route is unverified for this package.

> [!WARNING]
> **Build the recovery media on a different machine, before you flash anything. Never on the target, and never over a remote session.** Put the file in the root of a FAT32 stick. The file must match your exact model ([KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453)).

**Use it.**

1. Power off and unplug. Refit the original CPU. The stock image has microcode for it and not for the new one.
2. Plug in a wired USB keyboard. Dell says Bluetooth and wireless keyboards do not work. Insert the stick.
3. Power on and immediately press and hold Ctrl and Esc until the recovery screen appears. Choose the recover option. The machine restarts several times, which Dell calls normal. The flash itself is described as taking about a minute ([KB 000130691](https://www.dell.com/support/kbdoc/en-us/000130691)). Do not power off during it.
4. If the recovery screen does not appear, remove the power cord and the coin cell, wait about a minute, reseat both and try again ([KB 000130691](https://www.dell.com/support/kbdoc/en-us/000130691)).

**What it costs.**

- It installs Dell's stock image. The stock microcode comes back, so the new CPU will not boot until you repeat the procedure against that image (inferred from what the flash holds; not tested).
- BIOS settings return to defaults, and BitLocker may ask for its recovery key. Find the key before you start ([KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453)). The recovery touches the BIOS firmware only, and your data and Windows are left alone.
- Remove the service jumper afterwards if it is still set.

**What the LED patterns mean is not settled.** Repeating amber blinks on the power button are the board's way of saying something. Dell's own pages give the same patterns different meanings:

| Pattern | Recovery article ([KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453)) | Indicator guide, table for 2012 to 2020 ([KB 000126021](https://www.dell.com/support/kbdoc/en-us/000126021/a-reference-guide-to-the-dell-optiplex-diagnostic-indicators)) |
|---|---|---|
| 3,3 | Recovery image not found | No memory detected |
| 3,4 | Recovery image found but invalid | Storage subsystem failure |
| 3,6 | BIOS corruption, recovery should fix it | System board failure |
| 3,7 | BIOS or CPU failure, try BIOS recovery | Possible memory failure |

The 7060 dates from 2018, so the 2012 to 2020 table is the one that covers it (inferred). The indicator guide's 2020 to 2025 table gives still other meanings.

[KB 000130691](https://www.dell.com/support/kbdoc/en-us/000130691) names the OptiPlex 7060 and treats a repeating amber 3,6 or 3,7 with no POST as the case for USB recovery. So read a 3,6 or 3,7 after a flash as "no POST, firmware suspected" and nothing more. During a recovery attempt, 3,3 and 3,4 point at the stick or the file. The reference record expected a repeating 3,6 and a reachable Ctrl+Esc screen when the BIOS region is damaged but the boot block is intact. That was a prediction and not an observation.

Do not wait for beeps. Dell has dropped beep codes on every OptiPlex built since 2012 except the memory-failure code ([KB 000126021](https://www.dell.com/support/kbdoc/en-us/000126021/a-reference-guide-to-the-dell-optiplex-diagnostic-indicators)). A board that fails after a firmware write is silent.

**Tested on the reference build?** No. Nothing was recovered with it there.

### Rung 4: an external SPI programmer

This is the last rung and the only one that works on a board that does not start at all. The flash is a standard SPI NOR chip. Nothing about reading or writing it is Dell-specific. On the reference board `-i` reported one 32768 KB component with JEDEC ID `0xC22019`, a Macronix part (reported, unconfirmed). The package was not recorded. The reference build never used a programmer, so this rung comes from the tools' manuals and other people's reports.

**Identify the chip before you buy anything.**

- Read the part number printed on the chip and find its datasheet. Note the package and the supply voltage. The reference chip is believed to be a 3.3 V part, unconfirmed against a datasheet. Some boards carry 1.8 V flash, which a 3.3 V programmer can damage. That is general SPI NOR practice and not specific to this board, so check yours.
- Count the legs. 16 legs is SOP16 and takes a clip. 8 leadless pads is WSON-8, which a clip cannot grip ([02](02-does-my-hardware-qualify.md), C8). The reference record assumes SOP16 without recording a visual check. A pogo-pin adapter or lifting the chip is outside this repo.

**Choose a programmer that is safe at 3.3 V.** Check the voltage, not the colour of the board.

- A CH341A as commonly sold is reported to drive 5 V on its data lines. Libreboot's documentation says that level can damage the flash chip and the chipset it is wired to, and not to use the programmer until the problem is fixed ([Libreboot, SPI flashing guide](https://libreboot.org/docs/install/spi.html)).
- Forum posts describe cutting the trace that feeds the programmer's own controller chip from 5 V and wiring in 3.3 V. Others report using unmodified boards without trouble. Which revisions are affected is not settled ([Win-Raid CH341A guide](https://winraid.level1techs.com/t/guide-using-ch341a-based-programmer-to-flash-spi-eeprom/30834); reported, unconfirmed). Check the data-pin level with a meter before you connect it to a board (inferred), or buy a programmer that specifies 3.3 V I/O.
- The reference record prefers an XGecu T48. Its vendor lists 3.3 V and 1.8 V adapters (reported, unconfirmed), and its in-circuit behavior has not been checked.

**Prepare the board.** Shut down fully, unplug the power cord, hold the power button for several seconds to drain the board ([04](04-procedure.md), 3.4, does the same before the jumper) and take out the coin cell. The clip powers the chip, and nothing else on the board should be live. Programming in circuit is reported unreliable, because the programmer ends up powering part of the board and the results are unpredictable ([Win-Raid CH341A guide](https://winraid.level1techs.com/t/guide-using-ch341a-based-programmer-to-flash-spi-eeprom/30834); unconfirmed). The reference record says the same of Dell boards (reported, unconfirmed). If reads come back inconsistent, the more dependable fix is to remove the chip, and that is outside this repo. Match pin 1 on the clip to pin 1 on the chip.

**Read the chip ID first.** With no operation, flashrom only probes ([manual](https://man.archlinux.org/man/flashrom.8.en)). `ch341a_spi` below is a placeholder for the flashrom driver name of whatever programmer you have checked at 3.3 V; the commands are otherwise the same.

```
flashrom -p ch341a_spi
```

The output should name the chip and give its size, and both should match what `-i` reported when you made the backup (reference: 32768 KB, ID `0xC22019`). An ID of all zeros or all ones, or no chip found, is a contact problem: reseat the clip and probe again. Do not read or write until the probe identifies the chip. If it lists several matching definitions, add `-c "<name as printed>"` to every command below (the manual: `-c` probes only for the chip you name).

**Read twice, compare, then diff against your backup.**

```
flashrom -p ch341a_spi -r read_1.bin
flashrom -p ch341a_spi -r read_2.bin
```

```powershell
(Get-FileHash read_1.bin).Hash -eq (Get-FileHash read_2.bin).Hash      # must be True
```

```sh
sha256sum read_1.bin read_2.bin                                        # Linux: the two hashes must match
```

```
python -I diffranges.py full_1.bin read_1.bin
```

The two reads must match and must be the size of the chip. Against your pre-write dump, expect differences in the volume you wrote and in the NVRAM and ME blocks (inferred). Differences in the descriptor, the GbE region or the IBB mean either a bad read (reseat and repeat) or a failed write that reached further than planned. Either way you now know it. Open `read_1.bin` in UEFITool NE as well.

A 32 MB part needs 4-byte addressing in both the programmer and the software. The flashrom manual does not address it and the reference build never tested it (unconfirmed). Check that the probe reports the full size. A read whose second half is a copy of its first half is the sign of a tool that cannot address past 16 MB (inferred). Stop if you see it.

**Write the backup.**

```
flashrom -p ch341a_spi -w full_1.bin
```

`-w` erases the chip, writes the file and, unless you pass `-n`, reads the whole chip back and compares it ([manual](https://man.archlinux.org/man/flashrom.8.en)). Never pass `-n`. When it finishes, read twice more and compare both reads with `full_1.bin` (`sha256sum` on Linux, `Get-FileHash` on Windows).

**Put it back.** Remove the clip. Refit the coin cell and the power cord. Fit the original CPU, with the service jumper off, and power on. If the board starts, take two new dumps with FPT and compare them with the file you wrote before you do anything else. The restored board is back to your stock BIOS with the original CPU's microcode only. Whether to repeat the procedure is a separate decision.

**If you have no backup.** Another owner's image of the same model can start the board, but it carries their MAC address and service tag and other per-board data. On the reference image the MAC sits in the GbE region and the service tag in the NVRAM and ME regions (verified on the reference build). In 2020 a poster with a dead 7060 and no backup was offered a 65 W 7060 dump by another member ([Win-Raid, page 7](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=7); reported, unconfirmed). That is the price of skipping section 1.

**Tested on the reference build?** No. Nothing on that board needed it.

## 5. Do not do this

- **Do not flash a prebuilt blob.** That means any file someone else built: a microcode `.bin`, a "mod BIOS", a pre-patched image. It is made for their BIOS version, and writing it over yours is the documented cause of the dead boards in 2.3. Build from your own dump.
- **Do not run the vendor's Windows BIOS installer on this machine, least of all over a remote session.** On the reference build the 1.32.0 installer, started over SSH with the recovery-file switches, answered "Unrecognized option", the connection dropped and the PC rebooted. A dump taken afterwards showed no change to the volume, FIT, IBB or manifests (reported, unconfirmed). Why it rebooted was never established. An installer that does flash is a write you cannot watch from a session that can die, and a completed vendor flash puts the stock microcode back under the new CPU (inferred). Unpack packages with a tool, and build recovery media on another PC.
- **Do not use an engineering or qualification sample.** Read the sSpec on the lid. Anything marked INTEL CONFIDENTIAL, or a Q-prefixed sSpec, is a stop ([04](04-procedure.md), 0.3). The 7060 BIOS is reported to refuse stepping P0, CPUID 906EC, with code inside a volume that Boot Guard hashes, so microcode cannot fix it; an engineering-sample i9-9900T (QQZ6) took the mod and still did not boot ([Win-Raid, page 4](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937?page=4), 2020-05-28; unconfirmed).
  A refused CPU looks exactly like a bad flash, and you will be tempted to run recovery steps on a board that is fine. A model name does not settle the stepping, the sSpec does: R0 is 906ED, the CPUID this method adds.
- **Do not skip the two-dumps check.** A single read cannot tell you whether the read path is sound, and the rest of the ladder restores from it.
- **Do not write until the probe has passed, and never leave out `-a` or `-l`.** Do not add `-y` or `NOVERIFY`, and do not combine `-a` with `-bios` (the last is reported, unconfirmed). Do not start the write from an SSH prompt.
- **Do not carry numbers between BIOS versions or boards.** Offsets, constants and jumper pins belong to one image or one board. The pins widely quoted for the 7060 are reported to belong to the Micro, and on the reference SFF the same pair is the password pair ([04](04-procedure.md), 3.4).
- **Do not use a programmer you have not checked at 3.3 V.**
- **Do not touch the password pair, and do not leave the service jumper set.** Removing the cap from a password pair clears the BIOS password (reported). With the service jumper set, the ME is off and the flash is writable. Take it off when the work is done.
- **Do not make the verifier pass.** Fix the image honestly, or stop.

## 6. If it fails anyway, say so

A failure with a note is worth more than ten reports of success. Open an issue with the board, BIOS version, donor BIOS, CPU, FPT build, exactly what you saw (LED pattern, fans, video), and which rung brought it back, using the [hardware report template](../.github/ISSUE_TEMPLATE/hardware-report.md). Do not attach a dump, because it carries your MAC address and service tag. If something on this page led you into a board loss, that is a safety bug in the documentation, and [SECURITY.md](../SECURITY.md) asks for exactly that report.

## What is not established

- **No rung has been run on the reference board.** Every rung is assembled from documentation and other people's reports.
- **How a Boot Guard shutdown presents on a 7060.** The reference record expects a flicker and power-off. The reported dead boards show amber blinking. Which of Dell's LED tables applies is unconfirmed.
- **The mechanism behind the prebuilt-blob bricks.** The author blames a moved Boot Policy address. No teardown exists.
- **Whether Dell's recovery file can be made from the 1.32.0 package** by renaming it, and whether recovery is reachable after a bad volume write.
- **The reference board's Boot Guard profile.** Profile 5 is reported on a forum, and the fuses were not read.
- **Programmer details.** Which CH341A revisions drive 5 V, the XGecu T48 in circuit, the reference chip's voltage class from a datasheet, 4-byte addressing in cheap programmer software, and the reference chip's package.
- **FPT's behavior** with `-bios -f`, and with `-a` and no `-l`. Intel's manual is not public.

## Sources

Specifications and talks:

- Intel, [Firmware Interface Table BIOS Specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf), document 599500, revision 1.2.1, October 2016.
- Ermolov, [Safeguarding rootkits: Intel BootGuard](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf), ZeroNights 2016.
- Matrosov, [Betraying the BIOS](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf), Black Hat USA 2017.

Dell:

- [KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453), how to recover the BIOS after a boot or POST failure.
- [KB 000130691](https://www.dell.com/support/kbdoc/en-us/000130691), BIOS recovery for a no-POST issue, with the affected OptiPlex models.
- [KB 000126021](https://www.dell.com/support/kbdoc/en-us/000126021/a-reference-guide-to-the-dell-optiplex-diagnostic-indicators), the OptiPlex diagnostic indicator tables and beep codes.

Forum reports and tool documentation:

- Win-Raid, [Help adding CPU microcode to Dell 7060 BIOS](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937), pages 4, 7, 8 and 9.
- Win-Raid, [Using a CH341A-based programmer to flash SPI EEPROM](https://winraid.level1techs.com/t/guide-using-ch341a-based-programmer-to-flash-spi-eeprom/30834).
- Win-Raid, [Rollback HP Elite Dragonfly BIOS and Intel ME](https://winraid.level1techs.com/t/rollback-hp-elite-dragonfly-bios-and-intel-me/35122), on HP Sure Start.
- Libreboot, [SPI flashing guide](https://libreboot.org/docs/install/spi.html).
- [flashrom manual](https://man.archlinux.org/man/flashrom.8.en).
- [UEFITool](https://github.com/LongSoft/UEFITool) and [MCExtractor](https://github.com/platomav/MCExtractor).
