# Sourcing and licensing

This repo is text and scripts, and it is meant to stay that way. Every firmware input comes from you, from your vendor, from Intel or from an open-source project. None of them is in the repo. This page says where each one comes from, on what terms, and why nothing is bundled.

Links were checked in October 2026. Vendors move pages and revise tools, so re-check a URL or a version number before relying on it. Evidence words (verified on the reference build, reported, inferred, unconfirmed) are defined in [03](03-how-it-works.md#how-to-read-the-evidence).

## The inputs at a glance

| Input | Where it comes from | Terms | In this repo? |
|---|---|---|---|
| SPI dump of your board | Your own hardware | Yours, but it contains vendor code and your board's identifiers | No. The `.gitignore` blocks the usual file types |
| Donor BIOS (a sibling model's) | Your vendor's support site | The vendor's download terms | No |
| Intel microcode | Inside the donor BIOS, or Intel's public microcode repository | Intel's license: unmodified binary redistribution with notices, no reverse engineering | No |
| MCExtractor | [github.com/platomav/MCExtractor](https://github.com/platomav/MCExtractor) | BSD-2-Clause-Patent | No, link only |
| UEFITool | [github.com/LongSoft/UEFITool](https://github.com/LongSoft/UEFITool) | BSD-2-Clause | No, link only |
| Dell PFS extractor | [platomav/BIOSUtilities](https://github.com/platomav/BIOSUtilities) | Not named on its GitHub page; read the repository | No, link only |
| Intel FPT | Intel supplies it to OEMs and partners; third-party copies exist | No official public download found; terms unknown to this project | No |
| flashrom, chipsec | [flashrom.org](https://www.flashrom.org/), [github.com/chipsec/chipsec](https://github.com/chipsec/chipsec) | chipsec: GPL-2.0 (GitHub page). flashrom: read its license | No, link only |
| Verifier and builder | [tools/](../tools/) | MIT | Yes |

## 1. Your own SPI dump

This is the one input that has to come from your machine. It is a copy of the flash chip on your board, so it is yours to make.

Three ways to take it:

- Intel FPT on Windows: `fptw64 -d dump.bin` for the whole chip, which is the pre-write backup. Adding `-bios` reads the BIOS region only; use that for listing, since it cannot restore a board.
- flashrom on Linux with `-p internal` (see section 7; it was planned as a fallback on the reference build and never run).
- An external programmer clipped to the chip.

Take two dumps, compare them, and store both off the machine before anything else. The procedure is in [04-procedure.md](04-procedure.md).

A dump holds the vendor's firmware, which belongs to the vendor, plus data that is yours alone: the Ethernet MAC address (GbE region), the service tag and asset or ownership data (ME region and NVRAM), and possibly password hashes. Some boards also keep a Windows OEM key in the firmware as an ACPI MSDM table. The reference board's flash had none; yours might.

- Never commit, attach or paste a dump.
- Do not publish its hash either. A hash of a full dump identifies one unit, because the dump includes per-unit data. This repo prints no example hashes for the same reason.
- Share what you derived instead: the CPUID table MCExtractor prints, offsets, and tool output with identifiers removed.

Two dumps of the same board, one taken with the ME running and one with the service jumper set, differ in ME and NVRAM blocks only (verified on the reference build). Compare the descriptor, the microcode volume and the IBB, not whole-file hashes.

## 2. The donor BIOS from your vendor

Download the BIOS update for the sibling model from the vendor's own support site. For the reference build that is Dell's support page for the OptiPlex 7070, BIOS 1.35.0. Dell delivers it as a Windows installer around a PFS update image, so extract the firmware before MCExtractor or UEFITool can read it. The Dell PFS Update Extractor in [platomav/BIOSUtilities](https://github.com/platomav/BIOSUtilities) "parses Dell PFS Update images and extracts their Firmware (e.g. SPI, BIOS/UEFI, EC, ME etc) and Utilities (e.g. Flasher etc) component sections" and needs Python 3.10 to 3.13, per its README. The reference build also used Dell PFS extraction, but the tool and version were not recorded.

Extract the package. Do not run it: on the reference build one attempt to run Dell's installer remotely killed the SSH session and rebooted the PC ([06](06-reference-build.md#what-went-wrong-along-the-way)), and an installer's job is to flash a BIOS.

Pick a donor that meets all three conditions:

1. Same vendor and same chipset family as your board.
2. MCExtractor shows your CPU's CPUID in it.
3. The patch's platform mask includes your CPU's platform ID ([08-glossary.md](08-glossary.md) explains the mask).

The proven pairing is OptiPlex 7060 from OptiPlex 7070. HP EliteDesk 800 G4 from G5 has been suggested and is unproven ([02-does-my-hardware-qualify.md](02-does-my-hardware-qualify.md)). The 906ED patch in the 7070's BIOS 1.35.0 is revision 0x104, dated 2024-11-14 (reported, unconfirmed; the donor package was not retained).

The vendor's terms of use for BIOS downloads were not reviewed for this project. Read them. They do not bind this repo, which redistributes nothing, but they may bind you.

## 3. Intel microcode

Two routes, in order of preference.

**Route A: the donor BIOS.** This is the reference route. The patch inside is the one the vendor validated and shipped for its own board.

**Route B: Intel's public repository.** [Intel-Linux-Processor-Microcode-Data-Files](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files) names its files by family, model and stepping, so 906ED is `06-9e-0d`. Its [release notes](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/releasenote.md) list the signature as `06-9e-0d/22` with revision 00000104 in release microcode-20250512 (previous revision 00000102), labelled `CFL-H` and `Core Gen9 Mobile`. That is the same revision number and platform mask as the Dell donor. The desktop i7-9700T runs on that signature and mask on the reference build, but the mobile label is one more reason to compare Intel's file with the donor's patch before trusting it. Byte-for-byte equality was not checked.

Route B is unproven for this method. Whether a vendor BIOS accepts a patch that did not come from its own image is an open question, and so is whether the platform mask in Intel's file matches the vendor's copy. The repository also may not hold what a BIOS needs. Its [README](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/README.md) says "MCUs are best loaded from the BIOS" and "Certain MCUs must only be applied from the BIOS. Such MCUs are never packaged in this package since they are not appropriate for OS distribution." That is why the vendor BIOS is the preferred source.

### Intel's license, in summary

This is a summary of the [`license` file](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/license), with the operative sentences quoted. Read the file.

- "Redistribution and use in binary form, without modification, are permitted, provided that the following conditions are met."
- Redistributions must reproduce Intel's copyright notice and the disclaimer.
- Intel's name may not be used to endorse or promote products derived from the software without written permission.
- "No reverse engineering, decompilation, or disassembly of this software is permitted."
- The software is provided "as is".

Debian ships the package in its non-free section, and its [copyright file](https://metadata.security.debian.org/changelogs/non-free/i/intel-microcode/oldoldstable_copyright) reproduces the same license text.

### What that means here

- The repo commits no microcode, so it redistributes none, modified or not.
- The method moves Intel's bytes into your own firmware image without editing them. That fits "without modification" for the patch itself, but the license is written about redistribution. Whether building a modified BIOS image for your own machine falls inside its terms is for Intel or a lawyer to say, and this project does not claim to know.
- Every tool here identifies a patch by reading its header fields: CPUID, revision, date, checksum, platform mask. This project treats that as inspection, not reverse engineering, and nothing here disassembles or decompiles microcode. The license does not define the term, and nobody involved is a lawyer.
- Do not share the modified image or the extracted patch. Distribution is the thing the license controls tightly.

## 4. MCExtractor

Open source (BSD-2-Clause-Patent, per its [GitHub page](https://github.com/platomav/MCExtractor)). It needs Python 3.7 or newer and the `colorama` and `pltable` modules. A release is two files, the script `MCE.py` and its database `MCE.db`, and the README says the database "is required for the program to run".

```sh
pip3 install colorama pltable
python MCE.py path/to/image.bin
```

The README describes dragging files onto the script; passing the path as an argument, as above, is the usual equivalent. For use from a command prompt it names the `-skip` parameter, and `python MCE.py -?` shows the help screen. The output is one row per patch found: CPUID, platform mask, revision, date, size and checksum.

Run it three times: on your own dump (which CPUIDs does my BIOS carry?), on the donor (does it carry mine?), and on a readback of the flash after the write (is the new patch really in the chip?). [A Win-Raid thread](https://winraid.level1techs.com/t/how-to-extract-a-list-of-supported-cpus-from-a-bios/32414) from 2018 points to it for exactly this check.

## 5. UEFITool

[UEFITool](https://github.com/LongSoft/UEFITool) by LongSoft is open source (BSD-2-Clause, per its GitHub page). Use the NE ("new engine") release. Open a dump of your BIOS region to see the volume layout, the FIT and the regions Boot Guard protects. This project uses it to read, not to edit. The forum rule it shares is a post of 2020-05-04 in the 7060 thread: edit only the areas that are not coloured when the BIOS is opened in UEFITool NE Alpha 51 or above (unconfirmed). Leave the coloured areas alone.

## 6. Intel FPT

Intel's Flash Programming Tool is part of the CSME System Tools, which Intel supplies to OEMs and partners. This project found no official public download and does not know what license terms Intel attaches to the tool. The copies in circulation come from third parties: forum collections (the Win-Raid forum's Intel ME tools threads are the usual starting point) and GitHub mirrors. The reference build's FPT 12.0.85.1919 came from one of the mirrors. This project does not host, link to or vouch for any of them, and whether a given mirror has Intel's permission is an open question.

### Picking a build

Match the tool's major version to the ME firmware's major version. 300-series boards run CSME 12, so they take the v12 builds (unconfirmed, Win-Raid). The minor build matters too. On the reference board, under the Dell service jumper, 12.0.49.1536 started and the dumps and the write passed; 12.0.85.1919 failed to start its driver; and 13.50, 14.0.20 and 15.0 started but refused on a version check. The table, with the error texts, is in [06](06-reference-build.md#flash-tool-builds-the-one-that-worked-and-the-ones-that-did-not) (reported, unconfirmed; no console log was kept, and the driver-stack explanation there is the reference record's). No public documentation was found for Errors 51 and 621 (searched October 2026), and the usual public advice for Error 620 (install the ME driver) pointed the wrong way here.

The 7060 thread's advice, in a post of 2020-05-25, is to download Intel CSME System Tools v12 r23 (2020-05-03), because v12 is the correct major version for the 7060 board and no other major version should be used (unconfirmed). That agrees with the reference build as far as it goes: v12 worked, and v13 to v15 refused. It is incomplete, because a v12 build (12.0.85.1919) also failed. The r23 build was not tested on the reference build.

### The Authenticode check

FPT loads a kernel driver and runs as administrator, and you will probably get it from a third party. Check the signature before you run it:

```powershell
Get-AuthenticodeSignature .\FPTW64.exe |
  Select-Object Status, @{ n = 'Signer'; e = { $_.SignerCertificate.Subject } }
```

You want Status `Valid` and a signer that reads Intel Corporation. The 12.0.85.1919 build passed that check on the reference build. The signature of 12.0.49.1536, the build that worked, was never recorded, so run the check on your own copy and treat anything unsigned, invalid or signed by someone else as a stop.

A valid signature shows the file came from Intel's signing key and has not changed. It does not show that this is the build you need, or that the site hosting it may distribute it.

If you would rather not depend on FPT, an external programmer works at every stage and needs no Intel tool. On the reference build, FPT under the jumper was the path that worked.

## 7. flashrom, a programmer and chipsec

- **flashrom** ([flashrom.org](https://www.flashrom.org/), also packaged by Linux distributions). `-p internal` is Linux only. Support for the 300-series flash controller was not confirmed for this project, and its behavior under the Dell jumper is untested.
- **External programmers.** Libreboot's [SPI flashing guide](https://libreboot.org/docs/install/spi.html) is blunt about the CH341A: it "can have 5V logic levels on data lines, which can damage your SPI flash and also the southbridge that it's connected to", "DO NOT use it unless you have fixed the issue", and "Clip-based flashing (ISP / in-system programming) is, specifically, what we advise against using the CH341a for." It recommends a Raspberry Pi Pico instead. The same guide warns "Do NOT assume that the voltage is 3.3v on what you're flashing. Lots of modern flash chips today are 1.8v on a lot of newer systems", and "Do not connect the power source until your chip is otherwise properly wired. For instance, do not connect a test clip that has power attached." It names the Pomona 5250 (SOIC8) and 5252 (SOIC16) test clips. An XGecu T48 is sold with 3.3 V and 1.8 V adapters and a separate clip (vendor listings); its suitability for in-circuit use on these boards is unconfirmed, and the reference record calls in-circuit programming on Dell boards unreliable. Check your chip's package (SOP16 takes a clip, WSON-8 does not) and its voltage before buying anything. [05-safety-and-recovery.md](05-safety-and-recovery.md) covers recovery.
- **chipsec** ([github.com/chipsec/chipsec](https://github.com/chipsec/chipsec)). Open source, with read-only modules that report the flash lock state.

## Why the repo ships no vendor BIOS, no microcode and no flashing tool

Three reasons.

1. **Vendor BIOS images** are the vendor's work, offered under the vendor's own terms. The repo has no right to redistribute them and does not need to, because they are a free download from the vendor.
2. **Intel's microcode and FPT.** The microcode license allows unmodified binary redistribution with notices and forbids reverse engineering. For FPT, this project found no official public download at all, so a copy in this repo would be one more mirror of uncertain standing.
3. **Safety.** The [Win-Raid thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937) for this model offers a prebuilt microcode blob made for BIOS 1.4.2. Its author warned against using it on any other BIOS version, saying the Boot Policy address changed in newer versions. Owners reported dead boards after writing it on BIOS 1.9.1 (post of 2021-03-23) and 1.18.0 (post of 2022-06-12) (reported, unconfirmed). Any file this repo shipped would be bound to one BIOS version at one moment and would invite the same mistake. Building from your own dump means the payload always matches the firmware it replaces.

This is not a safety lockout. The procedure, with exact command lines, is in [04-procedure.md](04-procedure.md), and the verifier and builder in [tools/](../tools/) do everything that can be done without third-party binaries. What is missing is only files that belong to other people.

## What you can share

| Fine to share | Never share |
|---|---|
| The CPUID table MCExtractor prints | Dumps, BIOS images, extracted microcode, FPT binaries |
| Offsets and layout facts for a named BIOS version | A hash of your own dump |
| Verifier output with identifiers removed | Service tags, MAC addresses, serial numbers |
| Which tool build worked, and which error codes you met | Hostnames, IP addresses and local file paths left in logs |

[CONTRIBUTING.md](../CONTRIBUTING.md) has the same rule for issues and pull requests.

## Keep a provenance record

The reference build did not record where its working FPT build came from, and the gap could not be filled afterwards. For every input and tool you use, keep a record in your own notes, not in the repo:

```text
item:       <donor BIOS | FPT build | MCExtractor release | ...>
version:    <vendor version or tool build>
obtained:   <date> from <URL, or "own hardware">
sha-256:    <hash, kept private>
signature:  <Authenticode status and signer, or vendor signature>
```

## Reading list

- Intel, [Firmware Interface Table BIOS Specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf) (document 599500, rev 1.2.1, October 2016).
- Ermolov, [Safeguarding rootkits: Intel BootGuard](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf), ZeroNights 2016.
- Matrosov, [Betraying the BIOS](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf), Black Hat USA 2017.
- coreboot, [on the IBB](https://doc.coreboot.org/security/intel/txt_ibb.html).
- Libreboot, [SPI flashing guide](https://libreboot.org/docs/install/spi.html).
- Win-Raid, [the OptiPlex 7060 microcode thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937).
