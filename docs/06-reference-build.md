# Reference build: a 9th-gen CPU in an OptiPlex 7060 SFF

In August 2026 a Dell OptiPlex 7060 SFF (a 2018 small-form-factor office PC) on its final BIOS,
1.32.0, had one microcode entry replaced and its Core i5-8500 swapped for a Core i7-9700T. Stock
1.32.0 carries microcode for 8th-generation CPUs only (CPUIDs 906EA and 906EB). The i7-9700T is
CPUID 906ED. Its microcode, revision 0x104, was copied unmodified from Dell's own OptiPlex 7070
BIOS 1.35.0, a sibling model that Dell lists with 9th-generation CPUs.

The motive was heat: the owner chose the 35 W i7-9700T over the 65 W, 6-core i5-8500 it replaced, on
thermal grounds. The i7-9700T is a 35 W, 8-core part: a rating 30 W lower, and two more cores. The
machine has run on it since 20 August 2026 and passed closed-case thermal soaks. The same visit also
changed the thermal pad and removed the case's mesh screens, so the soaks do not isolate the CPU.

The owner read the CPU lid, moved the service jumper on and off, swapped the CPU and thermal pad, and
removed the case mesh screens; everything else was done remotely over SSH by an AI agent: audit,
dumps, analysis, payload build, write and readback. No external programmer and no live USB stick
were used.

This is one machine on one BIOS build. Offsets, jumper pins and the Boot Guard layout will differ on
yours, so read the numbers below as a worked example, not as values to copy. The general method is in
[04-procedure.md](04-procedure.md). What bricks a board, and how to get one back, is in
[05-safety-and-recovery.md](05-safety-and-recovery.md); read that before you write to a flash chip.

Nothing here defeats Boot Guard: the edit stays outside every byte it covers. The one protection that
does block the write, the BIOS's flash write protection, is lifted by the board's own service-mode
jumper.

## Before and after

| | Before | After | Basis |
|---|---|---|---|
| CPU | Core i5-8500 | Core i7-9700T | reported |
| Cores / threads | 6 / 6 | 8 / 8 | published Intel specifications |
| TDP rating | 65 W | 35 W | published Intel specifications |
| CPUID | 906EA | 906ED (R0 stepping, sSpec SRG17) | reported |
| Microcode entries in the BIOS image | 906EA rev 0xF8, 906EB rev 0xF6 | 906EA rev 0xF8, 906ED rev 0x104 | verified: recomputed from the dump, the payload and the modified image; the readback equals the payload |
| Microcode dropped from the BIOS image | n/a | 906EB (the 8th-gen 4-core stepping); its slot now holds 906ED | by construction, see "The edit" |
| Revision the OS reports | 0xF8 | 0x104 | reported |
| BIOS version string | 1.32.0 | 1.32.0 | reported |
| IBB (Boot Guard-covered) bytes in the write window | n/a | none | verified, by arithmetic on the dump |
| FIT (Firmware Interface Table) | 6 entries | the same 6 entries, byte-identical | verified (FIT identical in the dump and the modified image) |
| Sustained load in the closed case | not recorded | soaks passed (the pad and mesh screens also changed) | reported |

## How to read the evidence tags

Evidence words (verified on the reference build, reported, inferred, unconfirmed) are defined once, in
[03-how-it-works.md](03-how-it-works.md#how-to-read-the-evidence). A URL is an outside source. Where a
note and a measurement disagree, the measurement wins and the text says so.

## The machine and why it changed

The audit was read-only and ran on the evening of 19 August 2026.

| Item | Value | Basis |
|---|---|---|
| System | OptiPlex 7060 SFF, Intel Q370 chipset | reported |
| BIOS | 1.32.0, the last release for this model | reported |
| CPU | Core i5-8500, CPUID 906EA, microcode revision 0xF8 loaded | reported |
| Microcode in the BIOS image | 906EA rev 0xF8 and 906EB rev 0xF6. A scan of the whole 16 MB BIOS region finds no other valid microcode | verified |
| Management Engine firmware | CSME 12.0.95.2489 | reported |
| Disk encryption | BitLocker off | reported |
| Chassis intrusion detection | switched off in BIOS setup before the case was opened | reported |

BitLocker was off so that a changed firmware measurement could not trigger a recovery prompt. If
yours is on, suspend it and have the recovery key to hand. Chassis intrusion detection matters on Dell
business PCs: with it enabled, opening the case can halt POST with no video (reported).

**Why swap the CPU instead of tuning it.** The BIOS exposes no power-limit controls, software
undervolting is locked on this platform, and fan control is a single on/off override with no curve
(all reported). The remaining lever was a cooler part.

**Why not the supported i7-8700.** Dell lists the i7-8700 (6 cores, 12 threads, 65 W) for this
chassis ([specification sheet](https://dl.dell.com/topicspdf/optiplex-7060-desktop_specifications2_en-us.pdf);
reported). It needs no firmware work. In the reference record's pre-flash audit the i7-9700T came out
about 21% slower in multi-thread work and about 9% slower in single-thread (reported, unconfirmed: the
source of the comparison was not recorded). The 9700T was chosen for its 35 W rating, because heat was the
problem. If you want speed and not heat, buy the supported part and skip this page.

**Which 9th-gen part.** This method is for retail R0-stepping CPUs (CPUID 906ED), the 8-core parts.
9th-gen i3 and i5 models may reuse the 906EA and 906EB steppings the stock BIOS already carries
(unconfirmed), so check a candidate's CPUID against the BIOS's microcode list before you plan a mod.
Engineering and qualification samples are P0 (CPUID 906EC) and a hard stop; why is in
[02](02-does-my-hardware-qualify.md), "Why engineering and qualification samples fail". The owner read
the sSpec etched on the lid before installing the CPU: SRG17 is the retail i7-9700T R0 (reported).

## Where the microcode came from

The 7060 and the 7070 are the same platform family (reported). Dell sold the 7070 with 9th-generation
CPUs, so its BIOS 1.35.0 carries microcode that Dell validated for them.

| Image | Microcode entries | Basis |
|---|---|---|
| OptiPlex 7060 BIOS 1.32.0 (the target) | 906EA rev 0xF8; 906EB rev 0xF6 | verified |
| OptiPlex 7070 BIOS 1.35.0 (the donor) | 906EA rev 0xFA; 906EB rev 0xF6; 906EC rev 0xF8; 906ED rev 0x104 (dated 2024-11-14). Platform mask 0x22 on all four | reported. A forum poster also [found all four](https://winraid.level1techs.com/t/request-microcode-patch-for-dell-optiplex-7070-micro/115057) in both microcode sections of this BIOS |

Dell ships a BIOS update as a Windows executable that wraps a PFS-format image. Unwrap it, then list
the microcode in the image with [MC Extractor](https://github.com/platomav/MCExtractor):

```
python MCE.py <donor_image>
```

The record does not name the extractor that unwrapped Dell's package. The
[BIOSUtilities](https://github.com/platomav/BIOSUtilities) project includes a Dell PFS extractor.

The microcode is not edited. Its header carries Intel's revision, checksum and platform mask; the
builder checks the checksum and copies the blob as it is. Intel's public microcode repository lists
the same revision for CPUID 06-9E-0D (release 20250512, read from a summary of the
[release notes](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/releasenote.md);
reported). The reference build used Dell's copy, and an Intel-sourced blob is untested here. Neither
the BIOS nor the microcode is distributed by this repository: see
[09-sourcing-and-licensing.md](09-sourcing-and-licensing.md).

## Boot Guard analysis

Boot Guard checks a hash of the Initial Boot Block (IBB) before any BIOS code runs
([Ermolov, ZeroNights 2016](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf)).
If the board is fused for enforcement and one IBB byte has changed, the platform stops before BIOS
code runs, and the way back is an external programmer. [03-how-it-works.md](03-how-it-works.md)
explains the chain. This section covers what was verified on the reference image.

The first question was what the hash covers and whether the microcode volume is inside it. That has a
computed answer, so it should not come from a forum. The method:

1. Find the FIT. It lists where the Key Manifest (type 0x0B) and the Boot Policy Manifest, BPM (type
   0x0C), live ([Intel FIT specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf),
   table 2).
2. Read the IBB segment list and the digest from the BPM.
3. Recompute SHA-256 over the segments, in order, and compare.

On this BIOS the four segments are:

| # | Start | Length | End | Note |
|---|---|---|---|---|
| 1 | 0xF00000 | 0xC0080 | 0xFC0080 | ends where the BPM (`__ACBP__`) begins |
| 2 | 0xFC1080 | 0x80 | 0xFC1100 | ends where the Key Manifest (`__KEYM__`) begins |
| 3 | 0xFC2100 | 0xDF00 | 0xFD0000 | ends where the startup ACM begins (the FIT's type 2 entry points at 0xFD0000) |
| 4 | 0xFD8000 | 0x28000 | 0x1000000 | runs to the end of the region |

All offsets are inside the 16 MB BIOS region. Add 0x1000000 to get chip addresses on this 32 MB part.
The segments are those of BIOS 1.32.0 only, read from this BIOS's BPM. Another BIOS has its own list,
which the tools in this repo read from the image themselves.

The snippet in [03-how-it-works.md](03-how-it-works.md#the-offline-tests) (section 5) recomputes the
digest from these segments. On the reference image (verified): the digest over the four segments, in
this order, equals the one in the signed manifest; no segment overlaps the microcode volume (0xD20000
to 0xE10000); and the gap between the volume end and the lowest protected byte is 960 KB.

The BPM markers sit where the table says: `__ACBP__` at 0xFC0080, `__IBBS__` at 0xFC0090,
`__PMSG__` at 0xFC0145 and `__KEYM__` at 0xFC1100 (verified). The digest is stored at 0xFC00F4.

The equality is the part that matters. It proves the segment list you used is exactly the set of
bytes the manifest hashes. If your digest does not match the signed one, you missed a segment or
misread the layout. Stop, and do not write anything.

Three cautions on what this does and does not show:

- **Profile.** Forum threads describe the 7060 as running Boot Guard profile 5 (FVME: verified boot,
  measured boot, immediate shutdown on failure). The reference build never read the fuse state, so the
  profile is reported, unconfirmed. The digest check does not depend on it.
- **Why the microcode is outside.** No source consulted says why. A plausible reason is that the CPU
  authenticates each microcode update against Intel's signature itself, so Boot Guard has no need to
  hash it (unconfirmed). coreboot's documentation notes that on other platforms
  [the IBB may overlap microcode](https://doc.coreboot.org/security/intel/txt_ibb.html). This is a
  property of this BIOS. Compute it for yours.
- **Other hash checks.** Some AMI-based BIOSes add their own firmware-volume hash check on top of
  Boot Guard ([Matrosov, Black Hat 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf)).
  The microcode volume here evidently is not under one, because the machine runs on a modified
  volume. On a new BIOS you only learn that by booting, which is why the old-CPU boot gate exists.

## The edit: one slot, same size

The microcode firmware volume (FV) is 0xF0000 bytes at region offset 0xD20000, which is 15 erase
blocks of 64 KB. Walking the FIT (the snippet in [03](03-how-it-works.md#the-fit), section 3, plus a
read of each microcode header) shows what is in it. Output on the reference image (verified):

```
type 0x01  address 0xFFD20400  region offset 0xD20400
    microcode  cpuid 0x906EA  revision 0xF8  size 0x19C00
type 0x01  address 0xFFD3A000  region offset 0xD3A000
    microcode  cpuid 0x906EB  revision 0xF6  size 0x1A000
type 0x02  address 0xFFFD0000  region offset 0xFD0000
type 0x0B  address 0xFFFC1100  region offset 0xFC1100
type 0x0C  address 0xFFFC0080  region offset 0xFC0080
```

The table itself is at 0xD20100, inside the volume, and has six entries counting its header.

| Region offset | Size | Content |
|---|---|---|
| 0xD20000 | 0xF0000 | the microcode volume |
| 0xD20100 | 6 entries | the FIT: header, two microcode entries, startup ACM, Key Manifest, BPM |
| 0xD20400 | 0x19C00 | 906EA, revision 0xF8. Kept, as the fallback for the installed CPU |
| 0xD3A000 | 0x1A000 | 906EB, revision 0xF6. Replaced by 906ED, revision 0x104 |
| 0xD54000 to 0xE10000 | 0xBC000 | other volume contents: data that is not microcode, plus blank space. Rewritten with identical bytes |

A type 1 FIT entry points at a microcode header. The CPUID lives in that header, not in the entry
(verified on this image; Intel FIT specification, section 4.3). A blob for a different CPUID at the
same address therefore needs no FIT edit. Three facts made a swap possible instead of an append:

- The 906ED blob in the modified image is exactly 0x1A000 bytes, the size of the 906EB slot (verified;
  that it came unmodified from the donor is reported, and the builder refuses a swap that does not
  match exactly).
- The installed CPU (906EA) keeps its entry, so the old CPU stays a working fallback.
- Neither the installed CPU nor the target uses 906EB, so nothing in service loses its microcode.

The changed bytes lie between region offsets 0xD3A004 and 0xD53FFF, 105,698 of them, inside the old
906EB slot. The first four bytes of a microcode header, the header version, are the same in both
blobs, which is why the span starts at +4. The FIT is byte-identical. All of this is verified:
recomputed from the reference build's pre-write dump, payload and modified image (the builder's own
August output was not retained).

**The trade-off.** 906EB is the 8th-generation 4-core stepping. The 4-core i3 models on Dell's list
for this chassis are the CPUs that depended on it (inferred from the stepping; not tested). After the
swap this BIOS has no microcode for them. If you ever want to fit one, restore the original slice
first. A BIOS flash, downgrade or recovery from Dell's own packages writes Dell's stock volume back,
and the stock microcode with it, after which the i7-9700T would not start (inferred from what a
flash writes; not tested). Keep the rollback copy and the pre-write dumps off the machine.

If a target had no same-size slot, the builder also has an append mode that grows the FIT. It carries
more risk, and the reference build did not use it.

### What the verifier checks

The August 2026 run used reference scripts that have since been replaced by the tools in this
repository. What the current verifier checks is listed in
[tools/README.md](../tools/README.md#what-it-checks), and [04](04-procedure.md), 2.2, names the four
checks that matter most. In the 7060 image the platform mask is 0x22 on the installed 906EA entry and
was 0x02 on the old 906EB slot (verified); the donor 906ED blob carries 0x22 (reported). Whether the
mask covers the new CPU's platform ID was settled in practice, not by a check: the machine runs on
the CPU.

## Making the flash writable: the service jumper

Without the jumper every write fails. On the reference build a 4 KB write over blank space returned
the error below. It is FPT's standard message: the reference record has it, and it matches the public
reports linked after it (line breaks added here):

```
Error 167: Protected Range Registers are currently set by BIOS, preventing flash access.
Please contact the target system BIOS vendor for an option to disable Protected Range Registers.
FPT Operation Failed.
```

The console log of the attempt was not retained (reported). The same error shows up on
other vendors' machines: an [Alienware m15 R2](https://winraid.level1techs.com/t/error-167-protected-range-registers-are-currently-set-by-bios-in-alienware-m15r2-bios/88096)
and a [Vostro 3670](https://winraid.level1techs.com/t/problem-unlocking-fd-on-dell-vostro-3670/98074).
It means the BIOS programmed the chipset's write-protect ranges over the flash before handing off to
the OS. The flash descriptor was not the obstacle. The BIOS master already had write access to the
BIOS region (read 0x0F, write 0x0A in the descriptor of the dump; verified).

Dell puts a service-mode jumper on the board. With it set, the same class of write passed.

| Header | Pins | Silkscreen | Basis |
|---|---|---|---|
| JMP1 | 3-4 | "SERVICE MODE 3-4 SHORT: ME DISABLE" | reported |
| JMP1 | 5-6 | PSWD, shorted at the factory | reported |

While the jumper is set the Management Engine is disabled. The Management Engine Interface device
disappears from the OS, and POST shows "Alert! Service Mode jumper is set" (reported). Dasharo's
documentation for the OptiPlex 7010 and 9010 shows the same banner and says to press F1
([page](https://docs.dasharo.com/variants/dell_optiplex/initial-deployment/)). The record does not say
whether the 7060 waited for a key.

Rules for the header:

- **Read your own board.** The pin pair differs by model. A widely copied note gives 5-6 for the 7060
  Micro (reported, not checked here). The SFF board read 3-4, and the agent's first written plan had
  the pairs reversed. Photograph the legend before and after.
- **Leave the PSWD pair alone.** On Dell boards, removing the password jumper's cap clears the BIOS
  password (reported). Put a spare cap on the service pair. Which cap the reference build used on 3-4
  was not recorded.
- **Shut down fully and unplug the machine** before touching the header.

How the jumper lifts the protection is not established. Two flashrom mailing-list posts
([2011](https://www.flashrom.org/pipermail/flashrom/2011-September/007986.html),
[2016](https://www.flashrom.org/pipermail/flashrom/2016-February/014391.html)) say the descriptor
override strap does not lift protected-range restrictions. A working guess is that the Dell BIOS reads
the jumper at POST and skips programming the ranges (inferred). What is known is the observable:
no jumper gives Error 167, and with the jumper the write passes.

**Stop rule.** If a no-op write still returns Error 167 with the jumper set, stop. The only route
left is an external programmer.

## Flash tool builds: the one that worked and the ones that did not

Intel's Flash Programming Tool (FPT) ships in the CSME System Tools kit, one kit per Management
Engine generation. The Q370 pairs with CSME 12, so the v12 kit is the right major version. Forum
posters on this board say the same and warn against other major versions
([thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937)).
Intel supplies the kits to OEMs and partners, and no official public download was found. This
repository does not redistribute them.

The major version was not enough. The minor build mattered.

| Build | Package | Under the service jumper | Basis |
|---|---|---|---|
| 12.0.49.1536 (April 2020) | `FPTW64.exe` (about 1.3 MB) with `Pmxdll32e.dll`, `Idrvdll32e.dll`, `fparts.txt` | Starts. Dumps and writes work. The write passed on the first attempt | reported; the readback verified |
| 12.0.85.1919 | one `FPTW64.exe` (about 3.7 MB) | Error 51, "Failed to initialize driver for accessing PCI device", then Error 620, "Unknown hardware platform". The driverless option (`-DRVLESS`) gives Error 640 and 620 | reported |
| 13.50, 14.0.20, 15.0 | newer kits | start and report "HW: Cannonlake Platform", then refuse on version with Error 621 | reported, unconfirmed (no log kept) |

The order of events was this (reported). The first dumps and the write-protection probe were made
with 12.0.85.1919 while the jumper was off, and that build ran normally. As soon as the jumper was
set it stopped starting. 12.0.49.1536 was then staged and started cleanly.

Why is not established. The reference record attributes it to a change of driver stack between the
two builds (the older one loads `pmxdrv.sys`, the newer one `WNPDriver.sys`; reported). The file
layouts are consistent with that, but nothing proves it. The first written plan guessed the failure
was the missing Management Engine. Later entries in the record disagree: Error 620 followed Error 51 as a
downstream symptom.

Public threads answer Error 620 with advice to install the ME driver or to use a different tool for the chipset
([example](https://winraid.level1techs.com/t/how-to-fix-this-error/94081)). Under the jumper there is
no ME interface to install a driver for, and the tool was already the right major version. What fixed
it was an older minor build of the same kit.

**Provenance gap.** The source, hash and signature check of the 12.0.49.1536 files were not recorded
on the day. The failing 12.0.85.1919 build came from a public GitHub mirror of the System Tools and carried a
valid Intel signature when checked (reported). If you
use any FPT build, record where it came from, its SHA-256 and the output of
`Get-AuthenticodeSignature` before you run it.

## The sequence, stage by stage

Where the detail of a stage was not retained, the stage says so, and "Limits of this evidence" at the
end collects them.

| # | Stage | Where | Passes when |
|---|---|---|---|
| 1 | Audit the running system | remote | BIOS version, CPU, microcode revision and encryption state recorded |
| 2 | Dump the chip twice | remote | the two dumps hash identically and are copied off the machine |
| 3 | Parse the image | remote, offline | FIT walked; IBB digest equals the signed one; volume outside the IBB |
| 4 | Build and verify the payload | remote, offline | the verifier passes: only the microcode volume differs, FIT unchanged |
| 5 | Prove the flash is write-protected | remote | a 4 KB write fails with Error 167 |
| 6 | Set the service jumper | hands-on | POST banner shows; the Management Engine Interface is gone from the OS |
| 7 | Dump again, then write | remote | the tool starts under the jumper; the write reports success |
| 8 | Read back and compare | remote | the readback equals the payload; MC Extractor lists 906EA and 906ED |
| 9 | Boot on the old CPU | remote | normal boot with the original CPU still installed (not confirmed on the reference build) |
| 10 | Swap CPU and thermal interface | hands-on | the system boots on the new CPU |
| 11 | Confirm, then remove the jumper | remote, hands-on | CPUID 906ED; interface back; banner gone |

### 1. Audit the running system (remote)

```powershell
Get-CimInstance Win32_BIOS      | Select-Object SMBIOSBIOSVersion   # 1.32.0
Get-CimInstance Win32_Processor | Select-Object Name, ProcessorId   # ProcessorId ends in 000906EA
$k = 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0'
'0x{0:X}' -f [BitConverter]::ToUInt32((Get-ItemPropertyValue $k -Name 'Update Revision'), 0)   # 0xF8
manage-bde -status                                                   # BitLocker state
```

Also switch off chassis intrusion detection in BIOS setup before anyone opens the case.

### 2. Dump the chip twice (remote)

Measure the chip before you dump it:

```
fptw64 -i
```

On the reference build this reported one 32768 KB component (JEDEC ID 0xC22019, a Macronix part), a
BIOS region from 0x01000000 to 0x01FFFFFF, a valid flash descriptor, and BIOS master access of read
0x0F, write 0x0A (reported; the descriptor in the dump agrees, verified). The BIOS base turns a volume
offset into a chip address: 0x1000000 + 0xD20000 = 0x1D20000. Other Dell boards differ. A forum post
gives a different volume base on a Vostro 3670 ([thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937),
page 9). Measure yours, do not copy this one.

Then dump twice and compare:

```
fptw64 -d full_1.bin
fptw64 -d full_2.bin
fptw64 -desc -d desc.bin
```

```powershell
(Get-FileHash full_1.bin).Hash -eq (Get-FileHash full_2.bin).Hash      # must be True
```

Both reads hashed identically (verified). Copy both dumps and the descriptor off the machine before
doing anything else. A dump contains the service tag, the network MAC address and other identity data.
Keep it private and never commit it.

### 3. Parse the image (remote, offline)

Cut the BIOS region out of the dump (the tools in this repo also take the full dump), for MC Extractor
and the rollback slice:

```python
open('own_region.bin', 'wb').write(open('full_1.bin', 'rb').read()[0x1000000:])
```

Before you trust the address, compare the range at chip address 0x1D20000 with the same range of
Dell's shipped 1.32.0 image. They matched on the reference build (reported; recorded at the time, not
re-run for this page). The original slice staged as the rollback copy equals the same range of the
dump (verified).

### 4. Build and verify the payload (remote, offline)

Build from the machine's own dump plus the donor's BIOS region. Do not reuse a prebuilt blob: the
public reports of dead boards on this model come from such blobs written onto other BIOS versions
([05](05-safety-and-recovery.md), section 2.3).

As run in August 2026 with the reference scripts, since replaced by the tools in this repo:

```
python build_ucode_mod.py own_region.bin donor_region.bin out --mode swap
python verify_before_flash.py own_region.bin out/modified_full.bin out/ucode_fv_mod.bin
```

The current equivalent, with the tools in [tools/](../tools/) (arguments explained in
[04](04-procedure.md), 1.2 and 2.1):

```
python -I build_microcode_swap.py full_1.bin donor_region.bin 906ED --replace-cpuid 906EB --fallback-cpuid 906EA --platform-id <N> --out-dir out
python -I verify_microcode_mod.py full_1.bin out/modified_full.bin out/ucode_fv_mod.bin --target-cpuid 906ED --fallback-cpuid 906EA --replace-cpuid 906EB
```

The payload, `ucode_fv_mod.bin`, is exactly 983,040 bytes (0xF0000), the length of the volume. The
reference record reports that the verifier passed on the real payload; its August output was not
retained. Run today with the tools in this repo, on the reference build's pre-write dump and its
modified image and payload, the verifier ends in `RESULT: ALL CHECKS PASSED` (verified). Stage the
payload and the original slice (`ucode_fv_orig.bin`) on the target. The second is the one-command
rollback while the board still boots.

### 5. Prove the flash is write-protected (remote)

Write 4 KB of 0xFF over blank space inside the volume. Region offset 0xD85000 is all 0xFF in this
image (verified), so even a successful write changes nothing.

```powershell
[IO.File]::WriteAllBytes("$PWD\ff4k.bin", [byte[]](,0xFF * 4096))
fptw64 -f ff4k.bin -a 0x1D85000 -l 0x1000
```

The command form is reconstructed from the file names and the flash syntax in stage 7; the exact line
was not retained. Without the jumper the expected result is Error 167, as above. That error is a
useful result: it shows the tool reaches the chip and that the jumper is really needed. This probe
used FPT 12.0.85.1919; any build that starts without the jumper will do.

### 6. Set the service jumper (hands-on)

Shut the machine down, unplug it, and put a cap across JMP1 pins 3-4 on the SFF board (see the rules
above). Boot to the OS. POST showed "Alert! Service Mode jumper is set". From the remote side, confirm
that the Management Engine Interface device is gone before continuing:

```powershell
Get-PnpDevice | Where-Object FriendlyName -like '*Management Engine Interface*'
```

The record reports the device missing at this point. If you started with FPT 12.0.85.1919, expect it to
fail from here (Error 51, then 620). That is the signal to switch builds.

### 7. Dump again, then write (remote)

With FPT 12.0.49.1536 in a folder together with its DLLs, take two more dumps under the jumper:

```
FPTW64.exe -d jumper_full_1.bin
FPTW64.exe -d jumper_full_2.bin
```

Those two hashed identically (verified). They do not match the first pair, and that is expected. The
difference is confined to the Management Engine region and to the first 0x87000 bytes of the BIOS
region, which is NVRAM; the descriptor, GbE region, microcode volume, FIT and IBB were identical
(verified). Disabling the ME and rebooting changes ME state and NVRAM. When you compare
dumps taken in different modes, compare the regions that matter, not the whole-file hash. The
jumper-set dump is a valid pre-write image for this tool.

The planned last test is the 4 KB probe again, now expecting `FPT Operation Passed`. The probe file
was staged on the machine, but its result is not recorded (reported). The write then passed on the
first attempt.

> **Risk.** This is the step that can brick the board. The window is 15 erase blocks of 64 KB and
> includes the FIT, the table the CPU reads to find the startup ACM and the signed policy. A power cut
> in the middle of the write can leave it half-written. Treat that case as programmer-only recovery
> (not tested; see [05-safety-and-recovery.md](05-safety-and-recovery.md)). The reference build had
> no UPS and accepted that risk; you should not copy it.

The rules for the command (from the pre-flash plan; the one recorded command follows them):

- Pass both `-a` and `-l`. The plan says that without `-l` the tool writes from the address to the
  end of the flash (not tested here).
- Never combine `-a` with `-bios`.
- Do not pass `-y`, and do not use the no-verify option.
- The payload length must equal `-l` exactly. Both 0x1D20000 and 0xF0000 are 64 KB aligned.

Windows OpenSSH ends the processes of a connection that drops (reported), and a write killed halfway
risks a brick. Launch the write detached and poll a log. The agent proved the detached launch with a
harmless probe first (reported).

```powershell
$cmd = 'FPTW64.exe -f ucode_fv_mod.bin -a 0x1D20000 -l 0xF0000'
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine      = "cmd.exe /c `"$cmd`" > flash.log 2>&1"
    CurrentDirectory = (Get-Location).Path   # the folder with FPTW64.exe, its DLLs and the payload
}
Get-Content .\flash.log                      # poll until it ends with: FPT Operation Passed
```

This template is built from the recorded command (`FPTW64.exe -f ucode_fv_mod.bin -a 0x1D20000 -l
0xF0000`) and the recorded launch method. The exact launch line and log name were not retained.
Never run Dell's BIOS installer remotely; see "What went wrong".

### 8. Read back and compare (remote)

```
FPTW64.exe -d readback.bin -a 0x1D20000 -l 0xF0000
```

```powershell
(Get-FileHash readback.bin).Hash -eq (Get-FileHash ucode_fv_mod.bin).Hash   # must be True
python MCE.py readback.bin                       # lists 906EA rev F8 and 906ED rev 104
```

The readback hashed equal to the payload (verified from the surviving file list). MC Extractor on the
live readback listed 906EA rev F8 and 906ED rev 104 (reported). The readback line above is
reconstructed from the recorded file names. Check your FPT build's help output to confirm that `-d`
takes `-a` and `-l` before you rely on it.

### 9. Boot on the old CPU (remote)

The gate: after the write and before the case is opened, reboot with the original CPU still installed
and confirm a normal boot. It separates "the BIOS is broken" from "the new CPU is not accepted", and
it proves the fallback microcode still works, which is your way back if the new CPU fails.

**The reference record does not confirm this reboot was run.** The pre-flash plan lists it as a gate,
and no surviving note says it was executed. The record does show that the flash and the
readback were done from Windows on the old CPU, and that the machine started on the new CPU after
the swap. Do the reboot on yours.

### 10. Swap the CPU and thermal interface (hands-on)

Power off, unplug, swap the CPU. The owner used a phase-change pad instead of paste, and took the
case's mesh screens off in the same visit. The service jumper was still set during the swap and the
first boots on the new CPU. BIOS settings were intact afterwards (reported).

### 11. Confirm, then remove the jumper (remote, hands-on)

Rerun the audit commands from stage 1. On the reference build the live check of 11 October 2026 read
the CPU name `Intel(R) Core(TM) i7-9700T CPU @ 2.00GHz` and a ProcessorId ending in `000906ED`
(reported). The machine had already run its soaks on that CPU on the evening of the swap.

That evening the cap came off pins 3-4. Afterwards the Management Engine Interface device was back in
the OS and the POST banner was gone (reported). Until then the machine ran with its Management Engine
disabled, so do not leave the jumper in.

## What went wrong along the way

**Dell's installer, run over SSH.** The agent planned to build a Dell recovery image (`BIOS_IMG.rcv`)
as a safety net, using the switches Dell's knowledge base gives for the 7060
([KB 000130691](https://www.dell.com/support/kbdoc/en-us/000130691)):
`OptiPlex_7060_1.32.0.exe /writehdrfile /writeromfile`. The 1.32.0 package answered "Unrecognized
option", the SSH connection dropped, and the PC rebooted. The mechanism was not investigated. A dump
taken right after the reboot showed no change in the microcode volume, FIT, IBB segments or manifests
(reported), and the jumper-set dump taken later that morning agrees with the pre-incident dump in the
descriptor, GbE region, microcode volume, FIT and IBB (verified). Only ME-region blocks and NVRAM
differed. The lesson: do not run the vendor's installer remotely, and treat the knowledge-base
switches as unreliable per model. Recovery options are covered in
[05-safety-and-recovery.md](05-safety-and-recovery.md).

**The jumper pins in the written plan.** The first written plan named pins 5-6 as service mode, and
its password warning was attached to the wrong pair. The silkscreen on the board settled it: 3-4 is
service mode, and 5-6 is the password pair. That is why the rule above says to read your own board,
and why this page quotes pins only as the legend printed on one SFF board.

**The wrong FPT build and a wrong guess about it.** See the tool section. The first reading, that the
missing Management Engine was the cause, did not survive: an older build of the same kit worked with
the Management Engine still missing.

**A plan B that was never needed.** The plan also described writing with flashrom from a Linux
live USB. It was not run and is not validated for this board. Do not take it as a tested route.

## Result

A live check over SSH on 11 October 2026 read (reported; not re-run for this page): processor name
`Intel(R) Core(TM) i7-9700T CPU @ 2.00GHz`, ProcessorId ending in `000906ED`, BIOS version 1.32.0,
and `Update Revision` of `04 01 00 00` in the CentralProcessor registry key, which is 0x104.

One caution on that last value. It is the revision the CPU is running, and Windows can also apply
microcode itself, so by itself it does not prove the BIOS image carries 906ED. The proof is the
readback and MC Extractor in stage 8, plus the fact that the machine starts on that CPU. No test of
the stock BIOS with the 9700T was made, so "it will not start without the mod" rests on forum reports
and not on a test here.

Soaks on 20 August 2026, closed case (reported):

- A 75-second all-core busy loop held a flat 143.8 to 144.4% of the 2.0 GHz base clock, about
  2.9 GHz. No throttling.
- A 30-minute CPU-heavy LLM inference run and a 54-minute 4K NVDEC-to-NVENC transcode ran clean: no
  throttling, no hangs, no failures.

These describe the whole change. The same visit swapped the paste for a phase-change pad and removed
the case's mesh screens, so they do not isolate the effect of the CPU alone.

## Limits of this evidence

- **One board, one BIOS.** Only the SFF board on BIOS 1.32.0 was analysed. Other 7060 BIOS versions
  and form factors were not dumped.
- **The write time and launch line were not retained.** The command lines in stages 2, 5, 7 and 8,
  apart from the flash command itself, are reconstructed from the record, the surviving file names and
  the tool's syntax.
- **FPT provenance.** Source, hash and signature of the build that worked were not recorded.
- **The old-CPU reboot** (stage 9) is a gate in the pre-flash plan and is not confirmed for this build.
- **The under-jumper probe** result (stage 7) is not recorded.
- **No restore has ever been exercised.** The pre-write dumps exist and the old CPU's microcode was
  left in place, but a backup is not a restore until it has restored something. Whether an external
  programmer was on hand was not recorded.
- **Not recorded:** which cap went on pins 3-4, whether the banner waited for a keypress, and whether
  Windows Update was paused during the write.
- **Boot Guard fuse state** and profile were not measured.
- **Errors 621 and 640** have no public or vendor documentation that was found. The reading of 621 is
  the record's and is untested here.
- **The write window was the whole volume.** The FIT and the fallback microcode were erased and
  rewritten with identical bytes, along with the slot that changed. A narrower window was not tried,
  and one that does not line up with the flash's erase blocks brings its own risk.
- **Worth capturing next time.** The registry key from stage 1 also holds `Previous Update Revision`
  and `Patch Source` values on current Windows 11 builds. They may show whether the firmware or the
  OS supplied the microcode. Their semantics were not verified, and the reference record did not
  capture them.

## What is specific to this board

| Item | Reference value | Specific to |
|---|---|---|
| Microcode volume | region offset 0xD20000, length 0xF0000, found by walking the FIT | this BIOS build |
| FIT | at 0xD20100, 6 entries; the pointer at region end minus 0x40 holds 0xFFD20100 | this BIOS build (the pointer location is universal) |
| Swap slot | 906EB at 0xD3A000, size 0x1A000, platform mask 0x02 | this BIOS; the donor blob must match the size exactly |
| Boot Guard | digest at 0xFC00F4, segments as in the table, lowest protected byte 0xF00000 | this BIOS; read yours from its BPM |
| Flash | 32 MB, JEDEC ID 0xC22019, BIOS region 0x1000000 to 0x1FFFFFF | this board |
| Service jumper | JMP1 pins 3-4, PSWD on 5-6 | this board; the 7060 Micro and older models differ |
| FPT build | 12.0.49.1536 works under the jumper; 12.0.85.1919 does not | this board's jumper state; the kit's major version must match the chipset |
| Donor | OptiPlex 7070 BIOS 1.35.0 | this model pairing |
| Dell traps | POST banner, chassis intrusion halting POST | Dell business desktops |

What carries over: the order of the work (audit, two identical dumps, parse, prove the layout against
the vendor image, check Boot Guard before choosing what may change); preferring a same-size slot so
the FIT does not move; leaving the installed CPU's microcode in place; writing only the microcode
volume with an exact `-a` and `-l`; a readback compare; and booting the old CPU before the swap. The
qualifying checks are in [02-does-my-hardware-qualify.md](02-does-my-hardware-qualify.md), and the
terms are in [08-glossary.md](08-glossary.md).

## Sources

- Intel, [Firmware Interface Table BIOS Specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf), document 599500, revision 1.2.1, October 2016, sections 4.3, 4.10, 4.11 and table 2.
- Ermolov, ["Safeguarding rootkits: Intel BootGuard"](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf), ZeroNights 2016.
- Matrosov, ["Betraying the BIOS"](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf), Black Hat USA 2017.
- coreboot, [IBB documentation](https://doc.coreboot.org/security/intel/txt_ibb.html).
- Win-Raid, [microcode for the Dell 7060](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937) (long-running thread; pages 1, 3, 4, 7, 8 and 9 were used) and [the 7070 Micro request](https://winraid.level1techs.com/t/request-microcode-patch-for-dell-optiplex-7070-micro/115057).
- Win-Raid, Error 167: [Alienware m15 R2](https://winraid.level1techs.com/t/error-167-protected-range-registers-are-currently-set-by-bios-in-alienware-m15r2-bios/88096) and [Vostro 3670](https://winraid.level1techs.com/t/problem-unlocking-fd-on-dell-vostro-3670/98074). Error 620: [thread](https://winraid.level1techs.com/t/how-to-fix-this-error/94081).
- flashrom mailing list on protected ranges: [2011](https://www.flashrom.org/pipermail/flashrom/2011-September/007986.html) and [2016](https://www.flashrom.org/pipermail/flashrom/2016-February/014391.html).
- Dasharo, [OptiPlex initial deployment](https://docs.dasharo.com/variants/dell_optiplex/initial-deployment/) (service-mode banner on the 7010/9010).
- Dell, [OptiPlex 7060 specifications](https://dl.dell.com/topicspdf/optiplex-7060-desktop_specifications2_en-us.pdf), and knowledge-base article [000130691](https://www.dell.com/support/kbdoc/en-us/000130691) on creating a BIOS recovery file.
- Intel, [microcode release notes](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/releasenote.md).
- Tools: [MC Extractor](https://github.com/platomav/MCExtractor), [BIOSUtilities](https://github.com/platomav/BIOSUtilities).
