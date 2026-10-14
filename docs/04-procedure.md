# The procedure, step by step

This is the runbook for one change. You copy a CPU's microcode out of the vendor's own newer BIOS, put it into an unused slot of the same size in your BIOS image, and prove offline that nothing Intel Boot Guard checks has moved. Then you write only the microcode volume to the flash chip and change the CPU. It is an owner modifying their own out-of-warranty machine with publicly documented techniques and a jumper the manufacturer put on the board for servicing. There are six phases, numbered 0 to 5, and each ends in a gate. If you cannot pass a gate, you stop.

> **Risk.** Phase 4 erases and reprograms the chip that holds your firmware. A write interrupted at the wrong moment can leave a board that does not start, and the way back may be an external programmer. Phases 0 to 3 exist to make that unlikely. Phase 5 is ordered so that a bad write shows itself before the new CPU is involved.

Phases: [0 Preparation and backups](#phase-0-preparation-and-backups) (dumps, donor); [1 Build](#phase-1-build-the-modified-image) (offline); [2 Verify](#phase-2-verify) (offline); [3 Lift write protection](#phase-3-lift-write-protection) (at the machine); [4 Write](#phase-4-write-only-the-microcode-volume); [5 Restore, test, swap](#phase-5-restore-test-on-the-old-cpu-swap-confirm). What each gate requires is in its checklist.

## Before you start

Read [02](02-does-my-hardware-qualify.md), [03](03-how-it-works.md) and [05](05-safety-and-recovery.md) first. This page does not repeat their reasoning, and several steps below fail in ways only 05 explains.

On the reference build the owner read the CPU lid, moved the service jumper on and off, swapped the CPU and thermal pad, and removed the case mesh screens; everything else was done remotely over SSH by an AI agent. You can work the same way if the write in Phase 4 is launched so that a dropped connection cannot kill it (4.3).

### How to read this page

- **Evidence words** (verified on the reference build, reported, inferred, unconfirmed) are defined once, in [03](03-how-it-works.md#how-to-read-the-evidence). A link is an outside source.
- **Reference build** call-outs give the values from the board this method was proven on (Dell OptiPlex 7060 SFF, BIOS 1.32.0, i5-8500 replaced by an i7-9700T, microcode from OptiPlex 7070 BIOS 1.35.0). Use them to check your reading of a step. Do not type them in for another board.
- **Commands** run elevated in a short work folder without spaces, written `C:\fw`, which holds FPT, MC Extractor and this repo's tools. FPT commands start with `.\` so that they run in PowerShell and cmd.exe alike. The tools and the [helper scripts](../tools/README.md#helper-scripts-for-the-procedure) run as `python -I`, so Python imports nothing from a folder that also holds downloaded tools.
- **No hashes are printed here.** A dump's hash identifies the unit it came from; compare your own outputs with each other and keep them private.

### Values you carry through the phases

| Name | What it is | Where it comes from | Reference build |
|---|---|---|---|
| `<BIOS_BASE>` | Where the BIOS region starts on the chip | `-i` output, BIOS region Base | `0x1000000` (Limit `0x1FFFFFF`) |
| `<BIOS_SIZE>` | Size of the BIOS region | Limit + 1 - Base | `0x1000000` (16 MB) |
| `<FV_OFFSET>` | Start of the microcode volume inside the BIOS region | The builder's `report.txt`, "Write window"; the verifier prints the same as an `[info]` line | `0xD20000` |
| `<FV_LEN>` | Length of that volume, and of the payload | Same | `0xF0000` (983,040 bytes) |
| `<ABS_ADDR>` | The address FPT is given | The same lines, for a full dump ("absolute SPI address of the window"). Cross-check: `<BIOS_BASE>` + `<FV_OFFSET>` | `0x1D20000` |
| Target CPUID | The CPU you are adding | Lid sSpec, then MC Extractor on the donor | 906ED (retail R0; the i7-9700T is SRG17) |
| Resident CPUID | The installed CPU, whose microcode must stay | `Win32_Processor.ProcessorId` | 906EA (i5-8500) |
| Slot given up | The existing entry the donor microcode overwrites | Your FIT and MC Extractor | 906EB, `0x1A000` bytes at region offset `0xD3A000` |
| `<N>` | Platform ID of the CPU you will install (0 to 7) | `rdmsr 0x17`, bits 52:50, on a machine already running that CPU ([03](03-how-it-works.md), section 6) | Not recorded. The donor's mask is `0x22`, which covers IDs 1 and 5 |

### The repo's tools

The builder and the verifier are `build_microcode_swap.py` and `verify_microcode_mod.py` in [tools/](../tools/); [tools/README.md](../tools/README.md) lists their options and what each check and refusal means. They read the IBB segment list from the Boot Policy Manifest in your image and derive the microcode volume from your FIT, so nothing in them is tied to one board. Both accept a full SPI dump or a BIOS-region dump and print offsets relative to the BIOS region.

### If an agent is driving

Run Phases 0 to 2 and the read-only steps of Phase 3 on your own, and print every gate's output as it comes. Stop for a person at each hands-on step (reading the lid, moving the jumper, swapping the CPU), before the Phase 4 write, and whenever an output differs from what this page says to expect. The write needs an explicit go from someone who has seen the verifier output; before it, restate the address, the length, and the payload's size and hash. After a failed write, change nothing until a person has read 4.7. A claim tagged *inferred* or *unconfirmed* never justifies a write.

### Not covered here

- **Append mode**, where the FIT has to grow because no same-size slot exists. It carries more risk. Start from [03](03-how-it-works.md), section 6.
- **Other vendors' write-enable.** Phase 3 is proven on one Dell board only ([02](02-does-my-hardware-qualify.md)).
- **An external programmer.** [05](05-safety-and-recovery.md) covers it as a recovery path; the reference build never used one.
- **Linux, UEFI-shell and flashrom routes.** The write on the reference build was run with Windows FPT; a UEFI-shell build was staged and there is no record it was used.

## Phase 0: Preparation and backups

Nothing in this phase changes the machine. Everything after it assumes you did it, including the parts that feel like paperwork.

### 0.1 Settle your recovery path

Read 05. A write that breaks the boot path can be recovered only by programming the chip directly; Phase 2 tests for the Boot Guard failure, but a design is not a guarantee on your board. Find out which package your flash chip uses (16 legs is SOP16 and takes a clip; 8 leadless pads is WSON-8 and does not) and whether you have, or will buy, a programmer that is safe at 3.3 V. If you go ahead without one, make that decision now, not after a failed write.

### 0.2 Record the machine

Write these down. You need the CPU and the microcode revision again in Phase 5. The Linux equivalents are in [02](02-does-my-hardware-qualify.md), step 1.

```powershell
Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product
Get-CimInstance Win32_BIOS      | Select-Object SMBIOSBIOSVersion, ReleaseDate
Get-CimInstance Win32_Processor | Select-Object Name, ProcessorId
$k = 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0'
'0x{0:X}' -f [BitConverter]::ToUInt32((Get-ItemPropertyValue $k -Name 'Update Revision'), 0)
manage-bde -status
```

`ProcessorId` ends in the CPUID: `BFEBFBFF000906EA` is CPUID 906EA. The fifth line prints the microcode revision the CPU is running now. If yours prints `0x0`, change the final `0` to `4` (inferred; not seen). Then deal with the things that bite halfway through:

- **BitLocker.** If protection is on, suspend it or turn it off, and save the recovery key: the TPM measures firmware, so a changed image or Management Engine state can trigger a recovery prompt. It was off on the reference build.
- **Sleep and updates.** Pause Windows Update, disable sleep and hibernate, and stop any vendor firmware-update agent. Each can interrupt a read or a write.
- **Chassis intrusion.** On Dell, switch intrusion detection off in BIOS setup before you open the case; an armed switch halts POST with no video once the case has been opened (reported).
- **Vendor installers.** Do not run the vendor's BIOS installer on this machine at any point (troubleshooting table).

### 0.3 Read the CPU lid

Read the sSpec printed on the lid of the CPU you plan to install, before you buy if you can. Only retail parts work. A lid marked INTEL CONFIDENTIAL, a Q-prefixed sSpec, or any engineering or qualification sample is a hard stop: the 8-core samples on record use CPUID 906EC (stepping P0), which the 7060 BIOS is reported to block with code inside a volume that Boot Guard hashes, so no microcode edit helps ([02](02-does-my-hardware-qualify.md), "Why engineering and qualification samples fail").

### 0.4 Work folder and tools

Make `C:\fw` and collect in it: Intel FPT (`FPTW64.exe`, from the CSME System Tools), [MC Extractor](https://github.com/platomav/MCExtractor) (`MCE.py`, lists the microcode in an image), [BIOSUtilities](https://github.com/platomav/BIOSUtilities) (unpacks a vendor package), optionally [UEFITool NE](https://github.com/LongSoft/UEFITool), and Python 3 for this repo's tools. MC Extractor needs two packages:

```
pip install colorama pltable
```

FPT is not in this repo and will not be: Intel supplies it to OEMs and partners, and no official public download was found. [09](09-sourcing-and-licensing.md), section 6, covers where copies circulate and the licence question; read it first. The major version has to match the Management Engine generation of your chipset (v12 for 300-series boards like the reference one), and the minor build matters, because only some builds start once the service-mode jumper is set (Phase 3 and the troubleshooting table). Collect two or three v12 builds ([06](06-reference-build.md) has the table of which ones started on the reference board). Keep each build in its own folder with every file it shipped with, since builds ship different DLLs and drivers. FPT loads a kernel driver and runs as administrator, so check the file before you run it:

```powershell
Get-AuthenticodeSignature .\FPTW64.exe |
  Select-Object Status, @{ n = 'Signer'; e = { $_.SignerCertificate.Subject } }
```

You want `Valid` and a signer that reads Intel Corporation. Anything else is a stop. A valid signature shows the file is unchanged and came from Intel's key; it does not show that it is the build you need. Record where each copy came from and its SHA-256 in your own notes, not in the repo.

### 0.5 Read the flash, twice

```
.\FPTW64.exe -i
```

`-i` prints the flash geometry. Write down the total size, the chip ID, the BIOS region Base and Limit, whether the descriptor is valid, and the BIOS master's read and write access. Base is your `<BIOS_BASE>`; Limit + 1 - Base is your `<BIOS_SIZE>`.

```
.\FPTW64.exe -d full_1.bin
.\FPTW64.exe -d full_2.bin
.\FPTW64.exe -desc -d desc.bin
```

```powershell
(Get-FileHash full_1.bin).Hash -eq (Get-FileHash full_2.bin).Hash      # must be True
(Get-Item full_1.bin).Length                                           # must equal the flash size from -i
```

Both files must be exactly the flash size `-i` reported, and the two hashes must match. If they do not, retake both after closing everything that could touch firmware. Do not work from a read you cannot repeat. This whole-chip pair, with no `-bios` switch, is your backup: a `-bios` dump has no descriptor, GbE or ME region and cannot restore a board ([05](05-safety-and-recovery.md), section 1). Copy `full_1.bin`, `full_2.bin` and `desc.bin` off the machine now, to storage you control, and keep them private. A dump carries the network adapter's MAC address and the service tag (verified on the reference build), and the NVRAM area and ME region hold asset and ownership data and possibly other secrets (reported, unconfirmed). Never post a dump or its hash.

> **Reference build.** `-i` reported one 32768 KB component, chip ID `0xC22019` (a 32 MB Macronix part), BIOS region Base `0x01000000` and Limit `0x01FFFFFF`, a valid descriptor, and BIOS master Read `0x0F` and Write `0x0A` (reported; the descriptor in the dump agrees, verified). The two dumps hashed identically (verified).

### 0.6 Cut out your BIOS region and see what it holds

Both tools take the full dump (`full_1.bin`) directly, and a BIOS-region dump as well. Cut the region anyway: MC Extractor and UEFITool read it more simply, and the rung 2 restore in 05 writes it. Use the [`cut.py` helper](../tools/README.md#helper-scripts-for-the-procedure), then list the microcode:

```
python -I cut.py full_1.bin <BIOS_BASE> <BIOS_SIZE> own_region.bin
python MCE.py own_region.bin
```

MC Extractor prints each entry with its CPUID, platform mask, revision, date and checksum status. Check that the CPUID of the CPU you have installed is listed and the target CPUID is not. If the target is already there, you do not need this project: update the BIOS from the vendor.

### 0.7 Get the donor BIOS and your own stock BIOS

The donor is the vendor's BIOS for a sibling board that officially supports your target CPU ([02](02-does-my-hardware-qualify.md), step 4). Take the newest release, since microcode revisions rise from one BIOS version to the next. Also download your own board's BIOS package, in the version installed now; Phase 1 uses it to prove your offsets.

Unpack each download. Do not run it. A vendor BIOS package is a flasher, and the one time the reference build ran one, over SSH, it dropped the session and rebooted the PC (troubleshooting table). For Dell packages, BIOSUtilities includes a Dell PFS Update Extractor (older releases: `python Dell_PFS_Extract.py <package>.exe`, per a public [guide](https://github.com/dreamwhite/bios-extraction-guide/blob/master/Dell/README.md); current releases are packaged differently, see the [PyPI page](https://pypi.org/project/biosutilities)). The reference build did not record which extractor it used. It writes a folder of `.bin` files; the BIOS image is usually the largest (unconfirmed: same guide). Name the donor's image `donor_region.bin` and your own board's stock image `stock_region.bin`, then check the donor:

```
python MCE.py donor_region.bin
```

The target CPUID has to be listed with a valid checksum, at the highest revision you can find ([Intel's release notes](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files) list the revisions; a byte-for-byte comparison with Intel's file has not been tried). The reference donor's contents are in [06](06-reference-build.md).

### Gate 0

- [ ] Two full dumps with identical hashes, copied off the machine.
- [ ] CPU, CPUID, BIOS version and microcode revision written down; BitLocker handled.
- [ ] The new CPU's lid is read and it is a retail part.
- [ ] `own_region.bin` lists the installed CPU's CPUID and not the target's.
- [ ] `donor_region.bin` lists the target CPUID with a valid checksum.
- [ ] Your recovery path is decided.

## Phase 1: Build the modified image

### 1.1 What the builder does, and what it assumes

It reads your dump and the donor's image, copies the donor's microcode for the target CPUID over one existing slot of exactly the same size, and changes nothing else. The FIT is not edited, so it stays byte-identical, and the installed CPU's microcode stays in place as the fallback. It writes `modified_full.bin` (the whole image, the same size as your dump), `ucode_fv_mod.bin` (the payload, the microcode volume alone) and `report.txt`, after running the verifier's checks on the result in memory. If any of its checks does not hold for your images it prints `REFUSED: <reason>` and `Nothing was written.` (causes: [tools/README.md](../tools/README.md#what-it-does-in-order)).

**It derives the layout from your image.** It finds the FIT, the microcode volume and the IBB segment list (from the Boot Policy Manifest) itself. Do not use `--fit-offset`, `--fv-base` or `--fv-len` to force a layout, and do not use `--accept-no-bpm-check`, which turns a missing or unreadable Boot Policy Manifest into a pass with warnings (Gate 2 does not accept it). If the builder cannot parse your manifest, your board is outside what this method has been shown to cover. Stop; do not loosen a check to get past it.

**A slot is given up.** Swap mode overwrites an existing entry, so the CPUID that lived there is no longer in the BIOS. A CPU that needs it will stop booting, for the same reason your target CPU does not boot on the stock BIOS (inferred). `--replace-cpuid` is required because the builder never chooses which microcode to destroy. Check that the slot does not belong to the CPU you have installed, or to any CPU you may want to run later. If no slot of the right size exists, stop: that is append mode, which this page does not cover.

### 1.2 Run the builder

Dry run first. It runs every check and writes nothing:

```
python -I build_microcode_swap.py full_1.bin donor_region.bin 906ED --replace-cpuid 906EB --fallback-cpuid 906EA --platform-id <N> --out-dir out --dry-run
```

The CPUIDs are the reference build's (target, slot given up, resident); use your own from the table above. Pass `--platform-id` whenever you can read `<N>`: the builder then checks that the donor's platform mask includes your CPU's platform ID. Without it the builder only prints the mask and a warning. If you cannot read `<N>` because no machine you have runs that CPU yet, the reference build was in the same position (its `<N>` was not recorded) and relied on the donor being the vendor's own image for a board that officially ships that CPU (inferred; [03](03-how-it-works.md), section 6). When the dry run ends without a refusal, run the same line without `--dry-run`. It writes `out\modified_full.bin`, `out\ucode_fv_mod.bin` and `out\report.txt`, and prints its checks and then, among others, these lines (the format is the tool's; the values are the reference build's, yours will differ):

```
== Write window (nothing is written by this tool) ==
  microcode FV = write window: region+0xD20000, length 0xF0000
  this is a full SPI image: BIOS region starts at 0x1000000, so the absolute SPI address of the window is 0x1D20000
BUILT. Files in out:
```

Copy `<FV_OFFSET>`, `<FV_LEN>` and `<ABS_ADDR>` from those lines into your notes. `report.txt` also holds "What this changes" (CPUID, revision, date and platform mask of the removed and the added update) and every changed byte range. Given a BIOS-region dump, the tool cannot print the absolute address (the base is not in the file) and says so: add `<BIOS_BASE>` from 0.5. A wrong absolute address is a documented way to brick a board, so never take it from a forum post. The tool then prints the verifier command to run next, with your paths.

> **Reference build.** The payload file was exactly 983,040 bytes (`0xF0000`) and the changed bytes run from `0xD3A004` to `0xD53FFF`, 105,698 of them, all inside the 906EB slot (verified: recomputed from the reference build's pre-write dump, payload and modified image; the builder's own August output was not retained). The first four bytes of a microcode header, the header version, are the same in both entries, which is why the span starts at +4 (inferred from the range).

### 1.3 Cut the rollback slice and prove your offsets

```
python -I cut.py own_region.bin <FV_OFFSET> <FV_LEN> ucode_fv_orig.bin
python -I cut.py stock_region.bin <FV_OFFSET> <FV_LEN> ucode_fv_stock.bin
```

```powershell
(Get-FileHash ucode_fv_orig.bin).Hash -eq (Get-FileHash ucode_fv_stock.bin).Hash      # must be True
```

The builder does not write `ucode_fv_orig.bin`, so this step makes it. It is your rollback payload; keep it with the dumps. The comparison proves two things at once: the volume the builder works on is where the vendor's own image keeps it, and your flash holds the vendor's stock microcode volume, with no earlier modification. If the hashes differ, stop.

### Gate 1

- [ ] The builder finished without refusing (`BUILT.`), and its output says the FIT is byte-identical.
- [ ] `out\ucode_fv_mod.bin` is exactly `<FV_LEN>` bytes, and the Write window in `report.txt` matches your notes.
- [ ] The slot given up does not belong to a CPU you want to keep.
- [ ] `ucode_fv_orig.bin` matches the vendor's stock slice.

## Phase 2: Verify

### 2.1 Run the verifier

```
python -I verify_microcode_mod.py full_1.bin out\modified_full.bin out\ucode_fv_mod.bin --target-cpuid 906ED --fallback-cpuid 906EA --replace-cpuid 906EB
```

It opens the three files and nothing else. It prints one `[PASS]` or `[FAIL]` line per check under `== headings ==` and ends with a RESULT line: `RESULT: ALL CHECKS PASSED`, or `RESULT: n CHECK(S) FAILED -- DO NOT FLASH` with exit status 1. Add `--list-ranges` to print every changed byte range. Lines tagged `[info]`, such as the write window, are not warnings. Lines tagged `[WARN]` are.

> [!CAUTION]
> **Do not proceed unless Gate 2 passes.** One FAIL, a traceback, or a missing line means stop. Never change what a check tests in order to make it pass, and never reach for an override flag to turn a FAIL into a pass. The check named `IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM` has no override flag. If it fails on your own dump, take a fresh dump; if it still fails, open an issue with the BPM bytes and no other data. A FAIL there means the tool could not reproduce your board's own policy, not that the check is too strict.

A pass means the offline gates passed. The flash gates are Phases 3 and 4.

### 2.2 What the verifier checks

[tools/README.md](../tools/README.md#what-it-checks) lists every group of checks and what each is for. Four matter most, each printed by this name:

- `IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM`: SHA-256 over the IBB segments, read from your own image, equals the digest in the signed Boot Policy Manifest. It proves the segment list is complete; if it fails, the next check means nothing.
- `IBB digest UNCHANGED in the modified image`: the same digest on the modified image equals the original's. This is the check that prevents the expensive brick.
- `zero bytes changed outside the microcode FV`: every differing byte lies inside the microcode volume. On the reference board that volume ends 960 KB below the first IBB byte.
- `payload identical to the modified image at that offset`: what you flash is what you verified.

The IBB digest carries the weight: one changed byte in the Initial Boot Block, on a board that enforces Boot Guard, shuts the machine down before any BIOS code runs, and only an external programmer brings it back ([03](03-how-it-works.md), section 4).

### 2.3 What the verifier does not check

- **That the donor is genuine vendor firmware.** Get it from the vendor's site and compare its revision with Intel's notes.
- **That the donor's platform-ID mask covers your CPU.** The builder checks it when you pass `--platform-id`; the verifier does not.
- **Extra checks some BIOSes add on top of Boot Guard,** such as a firmware-volume hash in AMI-based images ([Black Hat USA 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf)). The only test is whether the board boots after the write, which is why Phase 5 boots the original CPU first.
- **Your flash chip, your power supply, and your jumper.**

### 2.4 Optional second look

Open `full_1.bin` and `out\modified_full.bin` in UEFITool NE. The microcode volume should be the only place they differ. Treat its Boot Guard colouring as a hint and the digest check as the test (unconfirmed: Win-Raid thread, page 1).

### 2.5 Freeze the payload

Write down the size of `ucode_fv_mod.bin` and its hash in your own notes. The readback in Phase 4 has to match it. If you rebuild for any reason, run Phase 2 again from the top.

### Gate 2

- [ ] The verifier's RESULT line says `RESULT: ALL CHECKS PASSED` with no "(n warning(s) above)" after it, there is no `[WARN]` or `[FAIL]` line anywhere in its output, and there is no traceback.
- [ ] None of the override flags was used: on the verifier `--accept-no-bpm-check`, `--ucode-window`, `--payload-offset`; on the builder `--accept-no-bpm-check`, `--fv-base`, `--fv-len`, `--force`. Each turns a failed or skipped check into a pass, narrows what is checked, or (`--force`) overwrites an earlier build's outputs. If you used one, rebuild into a fresh directory without it.
- [ ] `IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM` and `IBB digest UNCHANGED in the modified image` both printed `[PASS]`, by those names.
- [ ] The verifier was given the payload file, and `payload identical to the modified image at that offset` printed `[PASS]`.
- [ ] The payload's size and hash are in your notes.

## Phase 3: Lift write protection

Until now you have only read. Writing the flash needs the BIOS to stop blocking it. On a Dell business desktop of this era that is what the service-mode jumper is for. This phase holds the only steps that need hands inside the case.

### 3.1 Why a plain write fails

Point FPT's write at a range the BIOS has protected and it refuses:

```
Error 167: Protected Range Registers are currently set by BIOS, preventing flash access.
Please contact the target system BIOS vendor for an option to disable Protected Range Registers.
FPT Operation Failed.
```

That text is Intel's, and it turns up on other makers' boards too ([Alienware](https://winraid.level1techs.com/t/error-167-protected-range-registers-are-currently-set-by-bios-in-alienware-m15r2-bios/88096), [Vostro](https://winraid.level1techs.com/t/problem-unlocking-fd-on-dell-vostro-3670/98074)). It is the Protected Range Registers layer of the write protection the BIOS sets at every boot ([03](03-how-it-works.md), section 2).

### 3.2 What the service-mode jumper does

It is a header the manufacturer put on the board for servicing, and the BIOS reads it during POST. While it is set, POST shows `Alert! Service Mode jumper is set`, the Management Engine is disabled (its interface vanishes from the OS), and writes that returned Error 167 pass (reported; why is not documented, see [06](06-reference-build.md#making-the-flash-writable-the-service-jumper)). Two properties matter for safety. It needs the case open and the machine powered down to set, so nobody can turn it on remotely. And it leaves the board in a non-production state: no ME, no remote management, a banner at every boot. Keep it set for as long as you need and no longer.

### 3.3 Prove the board is locked

Do this before you touch the jumper. It tests your tools as well as the board (FPT starts, your write command is well formed, and what a refusal looks like) on a write that changes nothing.

Pick a target inside the volume you will write, in space that is blank in your dump: 4 KB that is entirely `0xFF`, starting on a 4 KB boundary (protected ranges are per range, so probe inside the volume). The helper lists the 64 KB blocks that are entirely blank, and the first 4 KB of such a block is the safest choice, because even a coarse erase then touches nothing live:

```
python -I blank.py own_region.bin <FV_OFFSET> <FV_LEN>
```

Take one block offset it prints as `<PROBE_OFF>`. The address FPT needs is `<PROBE_ABS>`, which is `<BIOS_BASE>` + `<PROBE_OFF>`. Make a 4 KB file of `0xFF` and write it over that spot:

```powershell
[IO.File]::WriteAllBytes("$PWD\ff4k.bin", [byte[]](,0xFF * 4096))
.\FPTW64.exe -f ff4k.bin -a <PROBE_ABS> -l 0x1000
```

With the jumper not set, the expected result is Error 167 and nothing written.

> **Reference build.** The probe went to `0x1D85000` (region offset `0xD85000`, all `0xFF` in the dump, inside the volume) and returned Error 167 with nothing written (reported; the console log was not retained, the blank range verified). That address is 4 KB-aligned but not 64 KB-aligned, and whether the rest of its 64 KB block is blank was not recorded; the start of a block that `blank.py` lists is the cleaner choice.

If FPT reports `FPT Operation Passed` instead, the BIOS has not protected that range. That would be unusual on a retail OEM board, and it is not what the reference board did. Probe a second blank block near the other end of the volume. If both pass, the jumper may not be needed for this volume: skip 3.4 and the jumper checks in 3.5, but still take the second dump pair (3.5) and run the write, readback and compare rehearsal (3.6) with the FPT build you will write with, since neither needs the jumper. In Gate 3, mark the banner and Management Engine bullet not applicable. If only one probe passes, stop and open an issue. If FPT will not start at all, try another v12 build; the troubleshooting table has the details.

### 3.4 Set the jumper

1. Shut the machine down fully (not hibernate, not restart), unplug the power cord, and hold the power button for several seconds to drain the board.
2. Touch bare chassis metal, open the case, and photograph the area around the header before you touch anything.
3. Find the header from the silkscreen printed on your own board and, where one exists, the service manual for your exact model and form factor. Not every manual documents the service-mode jumper, so the silkscreen is the authority.
4. Put a spare jumper cap across the service-mode pair. Do not take the cap from another pair. Removing the cap from a password pair clears the BIOS password (reported).
5. Reconnect power and boot.

> **Reference build: header JMP1, six pins in three pairs.** The silkscreen reads `SERVICE MODE 3-4 SHORT: ME DISABLE`. Service mode is **pins 3-4**: open is normal, shorted is service mode. Pins 5-6 are PSWD and ship shorted. Leave that pair alone. (Reported, from the board's silkscreen as recorded by the owner.) Which cap sat on 3-4 was not recorded.

> [!WARNING]
> **Pins differ by model and by form factor. Do not copy another model's.** The pins widely quoted for the OptiPlex 7060 are 5-6. By the record of this build that belongs to the 7060 Micro (unconfirmed), and on the SFF board 5-6 is the password pair. Forum posters describe the SFF header as the middle pins, which fits 3-4 on a six-pin header (unconfirmed: [Win-Raid thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937), pages 4 and 9). The Micro and the tower are not independently verified, and older boards differ again ([a 2016 flashrom report](https://www.flashrom.org/pipermail/flashrom/2016-February/014391.html) on a 3010 moves its ME-clear jumper from 2-3 to 1-2). Identify your header from the legend on your own board or the manual for your exact model. If the legend is unreadable or no manual covers your board, stop and open an issue with a photo that does not show the service tag.

### 3.5 Confirm it took, then dump twice more

On the first boot expect the banner `Alert! Service Mode jumper is set`. It may wait for a keypress, so be at the machine for this boot (the Dasharo documentation for the OptiPlex 7010 and 9010 describes the same banner waiting for F1: [docs.dasharo.com](https://docs.dasharo.com/variants/dell_optiplex/initial-deployment/)). On the reference build the banner appeared and the OS booted; whether a key was pressed was not recorded. In the OS, confirm the Management Engine is down:

```powershell
Get-PnpDevice | Where-Object FriendlyName -like '*Management Engine Interface*'
```

The device should be absent or show `Unknown`. If it is still present and `OK`, the jumper is doing nothing: power down and recheck the pins. Now start FPT with the build you intend to write with:

```
.\FPTW64.exe -i
```

It has to print the same geometry as in Phase 0. If it fails to initialise, that build is out for this jumper state. Try the next one and read the troubleshooting table (Errors 51, 620 and 621). Repeat until one starts. Then dump twice more with that exact build and compare:

```
.\FPTW64.exe -d jumper_full_1.bin
.\FPTW64.exe -d jumper_full_2.bin
```

```powershell
(Get-FileHash jumper_full_1.bin).Hash -eq (Get-FileHash jumper_full_2.bin).Hash      # must be True
```

```
python -I diffranges.py full_1.bin jumper_full_1.bin
```

The two new hashes must match each other. They will not match the Phase 0 pair, because the ME region and the NVRAM area change between boots and with the jumper set. The last command shows where the first pair and the second differ: the differences should sit below `<BIOS_BASE>` (the ME region) and in the first part of the BIOS region (the NVRAM area). If a range touches the descriptor or GbE (flash offsets below `0x3000`), the microcode volume (`<ABS_ADDR>` up to `<ABS_ADDR>` + `<FV_LEN>`), or the Boot Guard area (your lowest IBB byte upward, `0xF00000` into the region on the reference board), stop: something rewrote firmware between your dumps. Copy the new pair off the machine too.

### 3.6 Probe again, under the jumper

```
.\FPTW64.exe -f ff4k.bin -a <PROBE_ABS> -l 0x1000
.\FPTW64.exe -d probe_back.bin -a <PROBE_ABS> -l 0x1000
```

```powershell
(Get-FileHash ff4k.bin).Hash -eq (Get-FileHash probe_back.bin).Hash      # must be True
```

Expect `FPT Operation Passed` from the write and `True` from the compare. This write changed nothing, and it rehearsed the three things Phase 4 depends on: the write command, the ranged readback and the compare. Your build's own help (`.\FPTW64.exe -h`) is the authority on `-A` (flash address) and `-L` (length).

### Gate 3

- [ ] The probe failed with Error 167 before the jumper (or passed, and you followed 3.3).
- [ ] After the jumper: the banner was seen, the Management Engine device is gone, and FPT starts. (If 3.3 showed no jumper is needed, only FPT starting applies.)
- [ ] The second dump pair is identical, and its differences from the first pair are limited to the ME region and the NVRAM area.
- [ ] The same probe passes (under the jumper if you needed one) and reads back blank.
- [ ] You know which FPT build you will write with.

## Phase 4: Write only the microcode volume

You are about to erase and reprogram `<FV_LEN>` bytes on the flash chip. Of everything in this runbook it is the step that can do the most damage, so the preconditions come first.

### 4.1 What the window contains

The window is the whole microcode volume, and on the reference board the FIT sits inside it. It is 15 erase blocks of 64 KB, all of it erased and reprogrammed, including the parts whose bytes do not change, so a write interrupted between erase and program can leave a board that cannot start, recoverable only with a programmer (inferred from the layout; not tested). That is the reason for 4.2 and 4.3, and the reason not to narrow the window yourself: a narrower write was not tried on the reference build. Propose one in an issue ([CONTRIBUTING](../CONTRIBUTING.md)); do not change it mid-run.

### 4.2 Preconditions

- [ ] Mains power is stable. A UPS is better. The reference build had none and accepted the risk, which is a record, not a recommendation.
- [ ] Sleep, hibernate and updates are off, and nothing else is using the flash.
- [ ] BitLocker is off or suspended and the recovery key is saved.
- [ ] The jumper is still set (unless 3.3 showed you do not need it) and FPT still starts.
- [ ] Gate 2 passed on the files you are about to write, and `ucode_fv_mod.bin` is that file, with length `<FV_LEN>`.
- [ ] `<ABS_ADDR>` equals what the tools printed in the Write window and `<BIOS_BASE>` + `<FV_OFFSET>`, checked against your notes.
- [ ] `<ABS_ADDR>` and `<FV_LEN>` are both multiples of `0x10000` (64 KB). They are on the reference build. If yours are not, stop: an unaligned window has not been tried here, and a window that cuts an erase block may make the tool rewrite that block's neighbours (inferred).
- [ ] If you are remote, the detached launch has been proven (4.3).
- [ ] `ucode_fv_mod.bin` and `ucode_fv_orig.bin` are in `C:\fw` on the target machine, next to FPT. Copy them over if you built elsewhere, then compare their size and hash with your notes.

### 4.3 If you are remote, prove the detach first

> **Never start the write from an SSH prompt.** Windows OpenSSH ends the processes of a connection that drops (reported), and a write killed halfway risks a brick. Launch it as a separate process that does not belong to your session, and watch its log.

Prove the mechanism first, with a command that cannot hurt:

```powershell
$p = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine      = 'cmd.exe /c "ping -n 30 127.0.0.1 > C:\fw\probe.log 2>&1"'
  CurrentDirectory = 'C:\fw'
}
$p.ReturnValue          # 0 means the process was created
```

Now close the SSH session, reconnect, and read the log:

```powershell
Get-Content C:\fw\probe.log -Tail 3
```

You want the finished ping statistics, written after you disconnected. If you do not get them, do not launch the write remotely. Do it at the console.

### 4.4 The write

Write only the volume, with an explicit address and length, and nothing else. If you can sit at the machine, do the write there, from an elevated prompt in `C:\fw`:

```
.\FPTW64.exe -f ucode_fv_mod.bin -a <ABS_ADDR> -l <FV_LEN>
```

Remote, detached:

```powershell
$fw  = 'C:\fw'
$cmd = "$fw\FPTW64.exe -f $fw\ucode_fv_mod.bin -a <ABS_ADDR> -l <FV_LEN>"
$p = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine      = "cmd.exe /c `"$cmd > $fw\flash.log 2>&1`""
  CurrentDirectory = $fw
}
$p.ReturnValue          # 0 means the process was created
```

Rules for the command:

- Always give both `-a` and `-l`. The reference record warns that leaving out `-l` makes the write run from the address toward the end of the flash, and that `-a` and `-bios` do not combine (reported, unconfirmed; not tested).
- The payload's length must equal `-l` exactly.
- Do not add `-y` or `NOVERIFY`. FPT's help describes `-Y` as suppressing the prompt when a warning occurs and `-NOVERIFY` as disabling the automatic verify after flashing a new file (check your build's help). The prompt and the automatic verify are part of the safety net.
- One FPT process at a time. Do not start a second one, and do not shut down, sleep or log off while it runs.

The command is not the safe part: forum guides use the same `-a` and `-l` form with a prebuilt blob, and the documented dead boards came from such blobs written onto other BIOS versions ([05](05-safety-and-recovery.md), section 2.3). What this runbook changes is where the payload comes from (your own dump) and what Phase 2 proved about it.

> **Reference build.** The recorded command used the BIOS region Base `0x1000000` plus the volume offset `0xD20000`, and the volume length. It ran detached, from FPT 12.0.49.1536 with the jumper set, and passed on the first attempt (reported; the readback was verified). The exact launch line and log name were not retained.
>
> ```
> FPTW64.exe -f ucode_fv_mod.bin -a 0x1D20000 -l 0xF0000
> ```

### 4.5 Watch it

```powershell
while (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue) { Start-Sleep 2 }
Get-Content C:\fw\flash.log
```

If you lost the process id, look for the process by name with `Get-Process FPTW64 -ErrorAction SilentlyContinue`. The log should end with `FPT Operation Passed`. While it runs, do nothing else.

### 4.6 Read it back before you reboot

```
.\FPTW64.exe -d readback.bin -a <ABS_ADDR> -l <FV_LEN>
python MCE.py readback.bin
```

```powershell
(Get-FileHash readback.bin).Hash -eq (Get-FileHash ucode_fv_mod.bin).Hash      # must be True
```

Expect `True`, and MC Extractor listing both the resident CPUID and the target CPUID. Then take a full dump and check that nothing else moved:

```
.\FPTW64.exe -d dump_after.bin
python -I diffranges.py jumper_full_1.bin dump_after.bin
```

The only difference of substance should be the changed range inside the volume. Small differences in the NVRAM area are normal. Anything else: stop. The reference run compared the written range only; the full-dump comparison is an extra check this runbook adds.

### 4.7 If the write fails

If the log ends in anything other than `FPT Operation Passed`, or the readback differs, do not reboot yet. Find out what the flash holds:

```
.\FPTW64.exe -d readback.bin -a <ABS_ADDR> -l <FV_LEN>
```

```powershell
(Get-FileHash readback.bin).Hash -eq (Get-FileHash ucode_fv_orig.bin).Hash
(Get-FileHash readback.bin).Hash -eq (Get-FileHash ucode_fv_mod.bin).Hash
```

- **Equal to `ucode_fv_orig.bin`:** nothing was written. That is the usual result of Error 167 or a driver error. Fix the cause (Phase 3, the troubleshooting table) and repeat the write.
- **Equal to `ucode_fv_mod.bin`:** the write took and the log is the odd part. Carry on from 4.6.
- **Equal to neither:** the volume is partly written. Do not reboot and do not power off. Repeat the same write command once. If it passes and the readback matches, carry on. If it fails again, write `ucode_fv_orig.bin` the same way and check the readback against it, then go to [05](05-safety-and-recovery.md).
- **FPT no longer starts, or the machine has stopped responding:** go to 05 straight away.

### Gate 4

- [ ] The log ends with `FPT Operation Passed`.
- [ ] The ranged readback equals the payload.
- [ ] MC Extractor on the readback lists the resident and the target CPUID.
- [ ] The full-dump comparison shows no change outside the volume apart from NVRAM.

## Phase 5: Restore, test on the old CPU, swap, confirm

The order is deliberate. You test the board on the CPU it already knows before you add a second variable.

### 5.1 Reboot once with the jumper still set

Shut down fully, wait ten seconds, and power on, with the original CPU still in. If the banner waited for a key in 3.5, have someone at the keyboard. This is the first boot that reads the volume you wrote, so it is where a bad write shows itself. With the jumper still set, if the OS comes up you can still fix things from inside it: rewriting the rollback slice is one command away. When the OS is up, check that the CPU is the original and the microcode revision matches what you recorded in 0.2 (the original CPU's entry was never touched), and that FPT still starts and the volume still reads back equal to the payload:

```
.\FPTW64.exe -d readback2.bin -a <ABS_ADDR> -l <FV_LEN>
```

```powershell
(Get-FileHash readback2.bin).Hash -eq (Get-FileHash ucode_fv_mod.bin).Hash      # must be True
```

That compare proves the write survived a power cycle. If the machine does not reach the OS, go to 05.

### 5.2 Restore write protection

Shut down fully and unplug. Take the cap off the service-mode pair, photograph the header, and close the case. Re-arm chassis intrusion detection if you switched it off. With the jumper gone the BIOS programs the protected ranges again, as it did before you started (inferred). If you want proof, run the 3.3 probe again with a build that starts in normal mode; Error 167 means the protection is back.

### 5.3 Boot normally on the original CPU

Expect no service-mode banner, an OS that boots, the Management Engine Interface device back (and, where AMT is enabled, ports 623 and 16992 listening again), the BIOS version unchanged, and temperatures where they were. This is the production-state check. If something differs, power down and compare the header with your photo before going further. If the board will not boot, go to 05. This runbook asks for the boots in 5.1 and 5.3 because they are the cheapest way to tell "the write is bad" from "the new CPU is the problem"; no record shows the reference build made them ([06](06-reference-build.md), limits of the evidence).

### 5.4 Swap the CPU

Power off, unplug, and press the power button once to drain the board. Then:

1. Remove the cooler. Release the socket lever and lift the old CPU out by its edges. Do not touch the socket pins: a bent LGA pin is a dead board.
2. Seat the new CPU by its two alignment notches, not by feel, then close the retention plate and the lever.
3. Clean both contact surfaces, renew the thermal interface, and mount the cooler evenly.
4. Check the new CPU's power against what the board, the power supply and the cooler were designed for (criterion C9 in [02](02-does-my-hardware-qualify.md)).

### 5.5 First boot on the new CPU

Power on with the jumper off. If there is no video, the fans ramp and fall, or an LED or beep pattern appears that you do not recognise, power off, unplug, put the original CPU back, and confirm the board boots. Then go to 05. Do not repeat the swap until you know why it failed.

### 5.6 Confirm

Run the 0.2 commands again. On Linux, the revision is on the `microcode` line of `/proc/cpuinfo`:

```sh
grep -m1 microcode /proc/cpuinfo
```

`ProcessorId` should end in the target CPUID, and the revision should be the donor's. If the revision line prints `0x0`, see 0.2.

> **Reference build.** `ProcessorId` read `BFEBFBFF000906ED`, and `Update Revision` read `04 01 00 00`, which is 0x104 (reported; read live on 11 October 2026).

The OS's own microcode loader can supply the revision it reports, so by itself it does not prove the BIOS image carries the new entry (inferred); the Phase 4 readback with MC Extractor does.

### 5.7 Soak it

Run a sustained all-core load for 30 to 60 minutes with the case in its normal configuration, and watch temperatures and clocks. The reference build was checked with a 75-second all-core load, a 30-minute CPU-heavy LLM inference run and a 54-minute 4K NVDEC-to-NVENC transcode, with no throttling, hangs or errors (reported). The same visit also changed the thermal pad and removed the case's mesh screens, so those results do not isolate the CPU.

### 5.8 Put things back, and keep what you need

- Turn BitLocker back on, re-arm chassis intrusion, and resume Windows Update. Keep automatic BIOS updates off: vendor update utilities, Windows Update and fwupd can all deliver BIOS updates.
- Keep the original dumps, the rollback slice, the verified payload and your notes in a private place.
- A vendor BIOS update, downgrade or recovery writes the stock microcode volume back, and the new CPU will stop booting (inferred from what the flash holds; not tested). To move to a newer BIOS, repeat this procedure against that version's image, and derive every offset again.
- If you ran this on a board that is not listed in 02, report it with the [hardware report template](../.github/ISSUE_TEMPLATE/hardware-report.md). A failure is as useful as a success.

### Gate 5

- [ ] The original CPU booted with the jumper set, and the volume read back equal after that boot.
- [ ] The original CPU booted normally with the jumper off, and the Management Engine is back.
- [ ] The new CPU boots, and `ProcessorId` and the microcode revision are what you expect.
- [ ] A sustained load ran without throttling or hangs.

## Troubleshooting

Codes not listed here were not met on the reference build. The evidence behind each row (all reported or unconfirmed; no console logs were kept) is in [06](06-reference-build.md), "Flash tool builds" and "What went wrong along the way".

| What you see | What to do |
|---|---|
| `Error 167: Protected Range Registers are currently set by BIOS...` on a write with the jumper not set | The BIOS has made the range read-only to the host: Phase 3. If it still appears with the jumper confirmed active, stop; the next route is an external programmer ([05](05-safety-and-recovery.md)). |
| `Error 51`, then `Error 620` (also with `-DRVLESS`, which adds `Error 640`), from FPT 12.0.85.1919 with the jumper set; the same build ran normally with the jumper off | This build could not reach PCI configuration space. Try another build of the same major version (12.0.49.1536 worked) and drop `-DRVLESS`. The usual advice for 620, to install the ME driver, does not fit a board whose ME interface the jumper switched off on purpose ([Win-Raid](https://winraid.level1techs.com/t/how-to-fix-this-error/94081)). |
| `Error 621`, from FPT 13.50, 14.0.20 and 15.0, which printed `HW: Cannonlake Platform` before stopping | Read by the owner as a version refusal (unconfirmed). Use a v12 build. |
| `Unrecognized option` from the vendor's BIOS installer (`/writehdrfile /writeromfile`), after which the SSH session died and the PC rebooted | Never run a vendor BIOS installer on a machine you are modifying, and never remotely; unpack it instead. If one has run, take a fresh dump and compare it with `diffranges.py`. Dell's article ([000130691](https://www.dell.com/support/kbdoc/en-us/000130691)) is reported to list these switches for this model. |

The service-mode banner at POST, no video after opening the case (chassis intrusion), and a new CPU that does not POST are covered in [05](05-safety-and-recovery.md), rung 0. If the write passed but the new CPU does not POST, put the original CPU back before you troubleshoot anything else, then check the lid, the readback, seating, cooler and power.

## If anything looks wrong, stop

> [!CAUTION]
> **Stop and go to [05-safety-and-recovery.md](05-safety-and-recovery.md) if:**
>
> - a verifier line says FAIL, prints a traceback, or is missing
> - two dumps do not hash the same
> - a probe write fails with the jumper set
> - the log does not end in `FPT Operation Passed`, or the readback differs from the payload
> - the connection dropped, the power flickered, or the machine rebooted during the write
> - the board does not POST, shows an LED or beep pattern you do not recognise, or powers off by itself
>
> Do not reboot a machine whose last write you have not verified. Do not stack a second fix on the first. Put the original CPU back before you troubleshoot anything with the new one.
