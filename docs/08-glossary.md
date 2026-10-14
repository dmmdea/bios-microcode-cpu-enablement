# Glossary

Plain definitions of the terms the other docs use. Numbers marked "reference" come from the Dell OptiPlex 7060 SFF (BIOS 1.32.0) this method was developed on. They belong to that BIOS, so derive your own. The evidence words (verified on the reference build, reported, inferred, unconfirmed) are defined in [03](03-how-it-works.md#how-to-read-the-evidence).

Groups: [Identifying the CPU](#identifying-the-cpu) · [Inside the flash chip](#inside-the-flash-chip) · [What protects the flash](#what-protects-the-flash) · [Tools](#tools) · [Words this repo uses](#words-this-repo-uses)

## Identifying the CPU

**Microcode.** A patch the CPU applies to itself early in every boot. It fixes defects and, for a given CPU signature, it is what lets a BIOS start that CPU at all. The BIOS carries one patch per signature it supports, and when several match, the CPU loads the one with the highest revision ([Intel FIT specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf), section 4.3). The specification also says the BIOS must not compress, encode or encrypt it. If the BIOS has no patch for your CPU's signature, the board does not start. An operating system can load a newer patch later, but only on a CPU that already boots.

**CPUID (processor signature).** A 32-bit value the CPU reports, encoding family, model and stepping. Microcode is matched against it. 0x906ED means family 6, model 0x9E, stepping 0xD, which is why Intel's microcode repository names the file `06-9e-0d`. These docs write a CPUID without the prefix: 906ED.

**Stepping.** A revision of a CPU's silicon design, named like U0, B0, P0 or R0. Each stepping of a model has its own CPUID. The Coffee Lake family this method deals with:

| CPUID | Stepping | Parts | Source |
|---|---|---|---|
| 906EA | U0 | 8th-generation 6-core (the reference build's original i5-8500) | reference build |
| 906EB | B0 | 8th-generation 4-core | reference build |
| 906EC | P0 | first 9th-generation 8-core parts, and engineering and qualification samples | reference build; [Win-Raid](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937) |
| 906ED | R0 | retail 9th-generation 8-core parts (i7-9700T is SRG17, i9-9900T is SRG1B) | reference build; Win-Raid |

Whether 9th-generation i3 and i5 parts reuse 906EA and 906EB is unconfirmed.

**sSpec (S-spec).** The five-character code printed on the CPU lid, such as SRG17. It names the exact product and stepping, and you look it up on Intel's ARK or in the specification update. Read it before you buy or fit anything.

**Retail, ES and QS.** Retail parts are the ones Intel sold to the public. Engineering samples (ES) and qualification samples (QS) are pre-release parts handed to partners. Their lids carry Q-prefixed codes (QQZ6 and QRNL appear on pre-production lids) or the words "INTEL CONFIDENTIAL", and their steppings often differ from retail. A BIOS can refuse them even with the right microcode, so this method treats them as a hard stop.

**Revision.** The version number inside a microcode patch. The CPU keeps the highest one it is offered. The donor's 906ED patch is revision 0x104. The revision an operating system reports is what the CPU is running now, which the OS may have raised itself, so it does not show what the BIOS holds.

**Platform ID.** A 3-bit value the CPU exposes in MSR 0x17 that separates variants sharing one CPUID. Each microcode patch carries an 8-bit mask saying which platform IDs it serves, and the CPU uses a patch only if the mask includes its own ([Intel README](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/README.md)). The reference donor patch has mask 0x22 (bits 1 and 5). MCExtractor prints the mask; confirm it covers your CPU before you trust a donor.

**300-series, Coffee Lake, Coffee Lake Refresh.** The 300-series is the Intel chipset generation (H310, B360, B365, H370, Q370, Z370, Z390) for LGA1151 version 2 boards. Coffee Lake is the 8th-generation Core family and Coffee Lake Refresh the 9th. They share the socket and the chipsets, so an 8th-generation board can drive a 9th-generation CPU electrically. What it may lack is the microcode.

## Inside the flash chip

**SPI flash.** The chip on the motherboard that holds the platform's firmware. The reference board has one 32 MB part (JEDEC ID 0xC22019). A full dump is a copy of the whole chip, and it contains data that identifies your board, so never publish one.

**Flash descriptor.** The first 4 KB of the chip. It records where each region starts and ends and which masters (the host CPU, the ME, the Ethernet controller) may read or write each one. On the reference board the descriptor already lets the host write the BIOS region, so the write block came from the Protected Range Registers, not from here (verified on the reference build).

**Region.** A slice of the flash that the descriptor defines. Reference layout: descriptor 0x0 to 0xFFF, Ethernet (GbE) 0x1000 to 0x2FFF, ME 0x3000 to 0xFFFFFF, BIOS 0x1000000 to 0x1FFFFFF. The GbE region holds the Ethernet MAC address.

**BIOS region.** The region that holds the UEFI firmware: the firmware volumes and the NVRAM. Offsets in these docs are relative to the start of this region unless a doc says "absolute". Absolute is region base plus offset. On the reference board 0x1000000 + 0xD20000 = 0x1D20000, the address FPT's `-a` option takes.

**Firmware volume (FV).** A UEFI container: a header followed by firmware modules. The BIOS region is a series of them. On the reference BIOS the FIT and the microcode live in one FV that starts at offset 0xD20000 and is 0xF0000 (983,040) bytes long. The method writes exactly that FV and nothing else.

**NVRAM.** The part of the BIOS region where settings, boot entries and some board data are stored. It changes from boot to boot, which is why two dumps of the same board can differ even when nothing was flashed.

**FIT (Firmware Interface Table).** A table Intel CPUs read at reset, before the first BIOS instruction runs. A pointer at physical address 0xFFFFFFC0 (4 GB minus 0x40) leads to it. It starts with the signature `_FIT_` and holds 16-byte entries, each with a type. The types that matter here: 0x01 microcode patch, 0x02 startup ACM, 0x0B Key Manifest, 0x0C Boot Policy Manifest ([Intel FIT specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf), Table 2). The reference FIT sits at offset 0xD20100 with six entries (types 0, 1, 1, 2, 0x0B, 0x0C). Type 0x07, the BIOS startup module, is the legacy TXT boot entry and is not used on the reference build.

**Microcode slot.** The space for one patch, which a type 0x01 FIT entry points at. An unused slot starts with 0xFFFFFFFF, and a patch the FIT points at must be 16-byte aligned (both from the FIT specification).

**Same-size swap, append.** The two ways to add a patch. A swap writes the new patch into an existing slot of exactly the same size, so the FIT does not change by a byte. An append adds a new slot and a new FIT entry, which makes the table grow and carries more risk. The method prefers a swap. On the reference build the 906EB slot (0x1A000 bytes at offset 0xD3A000) received the 906ED patch, which is also 0x1A000 bytes. The 906EA patch was left alone, so the original CPU still boots. The price of a swap is that the replaced patch is gone: a CPU that needed the 906EB patch no longer has one in that image ([FAQ](07-faq.md)).

**Payload.** The bytes that get written: the rebuilt microcode volume, exactly as long as the range FPT is told to write (983,040 bytes on the reference build).

**Dump and readback.** A dump is a tool's copy of the chip's contents. A readback is reading a range you just wrote and comparing it with what you meant to write. Two dumps taken back to back must be byte-identical. A dump taken with the service jumper set (ME off) differs from one taken without it in ME and NVRAM blocks only, so compare the descriptor, the microcode volume and the IBB rather than whole-image hashes (verified on the reference build).

## What protects the flash

**Protected Range Registers (PR0 to PR4).** Chipset registers that make ranges of the flash read-only to the host. The BIOS programs them at every boot and then sets the FLOCKDN bit, which freezes them until the next hardware reset ([coreboot documentation](https://doc.coreboot.org/mainboard/lenovo/ivb_internal_flashing.html), written for Ivy Bridge ThinkPads; the Error 167 below shows the same mechanism on the 300-series reference board). While they cover the BIOS region, FPT's writes fail with Error 167: "Protected Range Registers are currently set by BIOS". On the reference board the Dell service jumper made the write pass. Why is undocumented, and flashrom's mailing list says the descriptor-override strap alone does not lift these ranges ([2016 post](https://www.flashrom.org/pipermail/flashrom/2016-February/014391.html)). Two related locks, BLE and SMM_BWP in the BIOS_CNTL register, can also block writes. On Linux, `chipsec_main -m common.spi_lock` and `chipsec_main -m common.bios_wp` read all of these without changing anything.

**Service jumper (Dell "Service Mode").** A header on the motherboard. With the cap on the right pins the BIOS leaves the flash writable and the Management Engine is off: the Intel Management Engine Interface disappears from Windows and POST shows "Alert! Service Mode jumper is set" (reported). On the reference SFF board the header is JMP1 and the silkscreen reads "SERVICE MODE 3-4 SHORT: ME DISABLE", with pins 5-6 labelled PSWD and shorted at the factory (reported, from the silkscreen as recorded by the owner). Other boards differ. Read yours.

**Boot Guard.** Intel's hardware-rooted boot check, configured by the OEM at manufacturing. At reset the CPU runs an Intel-signed module (the ACM) that verifies the OEM's Key Manifest and Boot Policy Manifest and then the initial boot block against the digest in that policy. Depending on the profile it verifies, measures into the TPM, or both, and it either shuts the machine down on failure or carries on ([Ermolov 2016](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf); [Matrosov 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf)). It is not UEFI Secure Boot, which acts later, and not BIOS Guard (PFAT), a different Intel feature with a similar name.

**ACM (Authenticated Code Module).** The Intel-signed code the CPU loads first under Boot Guard. A FIT entry of type 0x02 points at it.

**IBB (initial boot block).** The earliest part of the BIOS (its SEC and PEI phases) and the part Boot Guard hashes. The Boot Policy Manifest lists the IBB's segments and the SHA-256 of them. On an enforcing board, one changed byte inside a segment stops the machine before any BIOS code runs. The reference IBB has four segments, and the lowest starts at BIOS-region offset 0xF00000.

**KM and BPM (Key Manifest, Boot Policy Manifest).** Two signed structures in the flash. The KM, signed with the OEM's root key, names the key that signs the BPM. The BPM carries the IBB segment list and digest. FIT entries 0x0B (KM) and 0x0C (BPM) point at them. In a dump they show up with the markers `__KEYM__` (KM) and `__ACBP__`, `__IBBS__` and `__PMSG__` (BPM header, IBB element, signature).

**FPF (field programmable fuses).** One-time fuses in the chipset. They hold the hash of the OEM's root key and the Boot Guard settings, and no flash write can change them. What a firmware image shows about them is unreliable (reported); the real state is read from the running machine with Intel's MEInfo tool.

**ME (Management Engine, CSME).** A small separate processor in the chipset that runs its own firmware, stored in the ME region of the flash, and takes part in platform start-up. Windows shows it as "Intel Management Engine Interface". On business PCs it can also provide remote management (AMT). Intel's flash tools have to match its major version: the reference board's 300-series chipset uses CSME 12, so it takes the "v12" tool builds.

**HP Sure Start.** HP's runtime firmware protection. It keeps a protected copy of the BIOS and is reported to restore it over a modified one, even after an external-programmer write ([Win-Raid](https://winraid.level1techs.com/t/rollback-hp-elite-dragonfly-bios-and-intel-me/35122), on an HP laptop; desktop behavior is unconfirmed). One reason HP boards are not proven here.

**Brick.** A board that no longer starts. Two kinds matter. If the BIOS region is damaged but the boot block still runs, vendor recovery may revive it. If the boot block no longer matches the signed Boot Guard policy, the machine powers off at once and only an external programmer helps.

## Tools

**FPT (Flash Programming Tool).** Intel's command-line flash tool from the CSME System Tools (`fptw64.exe` on 64-bit Windows). Intel supplies it to OEMs and partners; this project found no official public download ([09-sourcing-and-licensing.md](09-sourcing-and-licensing.md)). The forms used in these docs:

```text
fptw64 -i                                          flash geometry, chip ID, descriptor access
fptw64 -d out.bin -bios                            dump the BIOS region
fptw64 -d out.bin                                  dump the whole chip
fptw64 -f payload.bin -a <absolute> -l <length>    write one range
```

Three rules from the reference record (not from Intel's manual, so check your version's help): always give both `-a` and `-l`, because leaving out `-l` writes from the address to the end of the flash; never pass `-y` or the no-verify option; and do not combine `-a` with `-bios`.

The build matters. Under the service jumper on the reference board one v12 build started and others failed or refused, and Error 620 followed from Error 51 there, so the usual forum advice to install the ME driver would have sent you the wrong way (reported, unconfirmed; the table is in [06](06-reference-build.md#flash-tool-builds-the-one-that-worked-and-the-ones-that-did-not)).

**MCExtractor.** An open-source Python tool by platomav (BSD-2-Clause-Patent) that lists every microcode patch in a file with its CPUID, platform mask, revision, date, size and checksum. `python MCE.py image.bin` is the basic call. Use it to see whether your CPUID is in a BIOS, to inspect a donor, and to check a readback.

**UEFITool.** LongSoft's open-source browser for UEFI images (BSD-2-Clause, per its GitHub page). It lays out firmware volumes and files, and its "NE" builds colour the regions Boot Guard protects. A forum post of 2020-05-04 puts the rule as: edit only the areas that are not coloured when the BIOS is opened in UEFITool NE Alpha 51 or above (unconfirmed). Used here to look at layout, not to edit.

**flashrom and chipsec.** Open-source tools. flashrom reads and writes flash chips, either internally on Linux (`-p internal`) or through an external programmer. chipsec reports lock state. flashrom was planned as a fallback on the reference build and never used.

**External SPI programmer.** A hardware reader and writer you clip onto the flash chip with the board unpowered, for example an XGecu T48 or a Raspberry Pi Pico running flashing firmware. Check the chip package first: a 16-leg SOP16 takes a clip, while an 8-pad WSON-8 has no legs to grip and Libreboot calls a clip on it "extremely unreliable". Check the voltage too. The reference chip is believed to be a 3.3 V part (unconfirmed against a datasheet), but some newer flash chips run at 1.8 V. The common CH341A is the one to avoid unless its 5 V data lines are fixed or metered ([05](05-safety-and-recovery.md), rung 4): Libreboot's documentation says it "can have 5V logic levels on data lines, which can damage your SPI flash and also the southbridge that it's connected to" ([Libreboot](https://libreboot.org/docs/install/spi.html)).

**Authenticode.** Microsoft's code-signing scheme for Windows executables. A valid signature from "Intel Corporation" shows a file was signed with Intel's key and has not changed since. It does not show that it is the build you need, or that whoever hosts it may distribute it.

**MMTool, UBU, CoffeeTime.** Community tools that older guides lean on. MMTool is AMI's utility for inserting and replacing modules, microcode included, in AMI Aptio BIOS images. UBU (UEFI BIOS Updater) automates microcode replacement through MMTool. CoffeeTime (`AllinOne.exe`) is an automated Coffee Lake mod for 100/200-series boards. None is used here; the [FAQ](07-faq.md) explains how they differ.

## Words this repo uses

**Reference build.** The Dell OptiPlex 7060 SFF (BIOS 1.32.0) on which the method was developed, running an i7-9700T on the modified BIOS since August 2026. See [06-reference-build.md](06-reference-build.md).

**Donor.** The vendor BIOS image of a related model that already carries the microcode you need. Reference donor: OptiPlex 7070 BIOS 1.35.0.

**Gate.** A check with a PASS or FAIL result that has to pass before the next step. A FAIL, or a parser that cannot finish, is a stop.

**Verifier and builder.** The two scripts in [tools/](../tools/). The builder makes the payload from your dump and the donor. The verifier checks the result against your dump before anything is written.
