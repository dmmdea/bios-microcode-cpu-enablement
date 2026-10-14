# FAQ

Short answers to what people ask first. Each links to the doc with the detail.

Evidence words (verified on the reference build, reported, inferred, unconfirmed) are defined in [03-how-it-works.md](03-how-it-works.md#how-to-read-the-evidence). Forum posts are paraphrased here, carry the post date and leave the poster unnamed; none was read word for word, so re-read the cited post before you rely on a detail. Quotations from Intel, Libreboot and the Intel microcode README were checked against the page.

## Warranty, law and what the repo ships

### Will this void my warranty?

No, because the hardware this targets has none left. The method is for end-of-life boards whose vendor has stopped issuing BIOS updates; the last BIOS for the reference model is 1.32.0. If the machine is leased, employer-managed or under a service contract, ask the owner first, and expect a vendor to decline support for a machine whose firmware you changed.

The procedure starts with two identical full dumps of the flash chip, and any rollback is built from them. No rollback was needed on the reference build, so treat that path as untested ([05-safety-and-recovery.md](05-safety-and-recovery.md)).

### Is this legal?

For hardware you own, in most places, yes. This is not legal advice.

The repo redistributes nothing. The files you handle do carry licenses. Intel's microcode license allows redistribution and use "in binary form, without modification" and says "No reverse engineering, decompilation, or disassembly of this software is permitted." The method copies one patch byte for byte and never edits or disassembles it. Your vendor's BIOS download has its own terms, which this project has not reviewed ([09-sourcing-and-licensing.md](09-sourcing-and-licensing.md)).

The one lock you get past, the flash write protection, is lifted by a jumper the vendor put on the board and labelled Service Mode. Boot Guard stays in force. Sharing is where the footing is less clear, so do not publish modified images, dumps or vendor files.

### Why does the repo ship no vendor BIOS, microcode or flashing tool?

The vendor's BIOS is the vendor's work, under the vendor's terms. Intel's microcode license allows only unmodified binary redistribution with notices, and FPT, Intel's flasher, is an OEM tool with no official public download that this project could find.

The third reason is safety. The [Win-Raid thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937) for this model offers a prebuilt microcode blob made for BIOS 1.4.2. Its author warned against using it on any other BIOS version, saying the Boot Policy address changed in newer versions. Owners reported dead boards (amber LED blinking, no POST) after writing it on BIOS 1.9.1 (post of 2021-03-23) and 1.18.0 (post of 2022-06-12), unconfirmed. A repo that builds from your own dump cannot hand you a blob for the wrong BIOS.

This is not a lockout. [04-procedure.md](04-procedure.md) has the command lines, and the programs in [tools/](../tools/) work on files you extract yourself.

## Why not an easier way

### Can I just update the BIOS instead?

Only if the vendor's newest BIOS already carries your CPU's microcode. Run MCExtractor on it and look for your CPU's CPUID in the table it prints ([08-glossary.md](08-glossary.md) explains the numbers). If it is there, update the normal way and stop.

On the reference model it is not. Dell's last BIOS for the OptiPlex 7060 (1.32.0) holds 906EA and 906EB, both 8th generation (verified on the reference build). The sibling OptiPlex 7070 ships 906EA, 906EB, 906EC and 906ED in BIOS 1.35.0 (reported, unconfirmed: the donor image was not retained). Both are 300-series boards, so the 9th-generation CPU runs electrically; the 7060 BIOS has nothing to load for it. The method copies the single 906ED patch from the sibling's BIOS into the 7060's own image. It does not flash the sibling's BIOS, which was built for a different board.

Loading microcode from the operating system does not help, because the CPU has to start first. Intel's microcode [README](https://raw.githubusercontent.com/intel/Intel-Linux-Processor-Microcode-Data-Files/main/README.md) says "Certain MCUs must only be applied from the BIOS."

### How is this different from CoffeeTime, UBU and the forum "mod BIOS" files?

| Approach | What it does | Why it is not this repo |
|---|---|---|
| Prebuilt blob (7060 threads) | A ready-made file for the microcode region, written with FPT | Built for BIOS 1.4.2 only; see the previous section. |
| UBU with MMTool | Replaces microcode inside an AMI BIOS and outputs a whole image | Whole-image output, and this project found no Boot Guard check in it. A post of 2024-08-20 says flashing a full UBU-modified BIOS went badly and needed a programmer to unbrick a couple of times (unconfirmed). |
| CoffeeTime (`AllinOne.exe`) | Automates a Coffee Lake mod for 100/200-series boards: microcode, a descriptor change, graphics firmware | Older chipsets, consumer boards ([Win-Raid thread](https://winraid.level1techs.com/t/tool-easy-automated-mod-tool-for-coffee-lake-bios/32795), 2018). |

This repo builds the payload from your own dump and a donor from the vendor's own BIOS, swaps a same-size slot so the FIT stays byte-identical, checks the Boot Guard digest, and writes only the microcode volume.

Writing a whole volume replaces the FIT and, a post of 2020-05-26 says, the startup module that follows the microcode (unconfirmed; on BIOS 1.32.0 the startup ACM lies outside the volume, see [03](03-how-it-works.md#8-where-this-argument-stops)). A blob swaps in another BIOS version's copies; a payload cut from your own dump writes back the bytes already there. Whether stale pointers explain the dead boards is a hypothesis, and nobody has published a teardown.

## Security

### Does this weaken Boot Guard or security?

No. The method changes nothing Boot Guard checks, and the verifier tests that on your image before anything is written.

Boot Guard makes the CPU run an Intel-signed module first. It checks a signed Key Manifest and Boot Policy Manifest, hashes the initial boot block (IBB), and compares the result with a SHA-256 digest in the signed policy. On a board set to enforce, a mismatch powers the machine off before any BIOS code runs ([Ermolov, ZeroNights 2016](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf); [Matrosov, Black Hat USA 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf)), and only an external programmer recovers it.

On the reference BIOS the method touches one firmware volume (offsets 0xD20000 to 0xE10000 of the BIOS region, holding the FIT and the microcode) and, inside it, one same-size slot. The lowest IBB byte is at 0xF00000, 960 KB higher. The FIT, including the entries that point at the two manifests, stays byte-identical. The fuses, the manifests and the IBB are untouched, and Secure Boot, a later UEFI stage, is not involved.

The verifier ([tools/](../tools/)) recomputes the IBB digest from your image, requires it to match the digest stored in the Boot Policy Manifest, requires it unchanged after the edit, and requires that no changed byte lies in an IBB segment. Any failed check prints "DO NOT FLASH" and exits with an error. If the manifest cannot be parsed, the verifier fails that gate by default; an override flag exists, [the tools README](../tools/README.md) describes it, and Gate 2 in [04](04-procedure.md) does not accept it. On the reference BIOS the digest recomputed from the pre-change dump equals the stored one (verified on the reference build).

Limits:

- "Outside the IBB" describes one BIOS, not a rule. coreboot's documentation says "The IBB might overlap with microcode" ([coreboot](https://doc.coreboot.org/security/intel/txt_ibb.html)), and some AMI-based BIOSes add their own firmware-volume hash check on top of Boot Guard (Matrosov, above). Compute the layout for your image, and boot the old CPU after the write, before any swap.
- Why vendors leave microcode outside the hashed area is undocumented. That the CPU authenticates microcode itself is a guess.
- The reference board's Boot Guard profile (profile 5, FVME) comes from a forum post of 2020-05-04, not from a measurement here. The digest check does not depend on it.
- The write lock is lifted only by the jumper, which means opening the case, so the method adds no software route around the lock. While the jumper is set the Management Engine is off; remove it afterward.
- Any firmware change alters TPM measurements (PCR0). Suspend BitLocker and keep your recovery key first. The reference machine had it off.

## Hardware

### Can I do it without opening the case?

No. Two steps are physical: the service jumper, a header on the motherboard, and the CPU swap. Everything else can run remotely. On the reference build the owner read the CPU lid, moved the service jumper on and off, swapped the CPU and thermal pad, and removed the case mesh screens; everything else was done remotely over SSH by an AI agent.

The jumper matters because the write fails without it: FPT returns Error 167 ("Protected Range Registers are currently set by BIOS") and writes nothing. With the jumper set, the write passed on the first attempt and the readback matched the payload (reported; the matching hashes are in the build's file records). Dell does not document why the jumper helps, so treat the observed result as the whole fact.

Pin pairs differ between boards:

- Reference SFF board: header JMP1, silkscreen "SERVICE MODE 3-4 SHORT: ME DISABLE" (reported, from the board's silkscreen as recorded by the owner). Pins 5-6 are PSWD and ship shorted; removing that cap clears the BIOS password (reported).
- Forum posts for the SFF (2020-05-29 and 2024-05-01) put service mode on the middle pins, near the front centre of the board under the DVD drive (unconfirmed). On a six-pin header laid out as three pairs, the middle pair is 3-4.
- You will see 5-6 quoted for this model. The reference record attributes that pair to the 7060 Micro (not independently verified).
- Read your own board's legend, photograph it before and after, and prove the effect before you write: a POST banner reading "Alert! Service Mode jumper is set", and the Intel Management Engine Interface gone from Device Manager.

Turn off chassis-intrusion detection in BIOS setup first. An armed switch halts POST with no video once the case is open (reported).

Newer Dell models are reported to have no service jumper. A post of 2021-04-09 about the OptiPlex 7080 MFF says Dell seems to have eliminated the service mode jumper in that generation ([thread](https://winraid.level1techs.com/t/dell-7080-mff-unlock-intel-amt-thread/36932)), and a post of 2022-03-12 about the 3090 MFF says it has no RTC reset, password reset or service mode jumper ([thread](https://winraid.level1techs.com/t/request-dell-optiplex-3090-mff-with-enabled-me-vpro/40053)); both unconfirmed. Those owners turned to an external programmer, which also means opening the case.

### What if my CPU is an engineering sample?

Do not use it. Engineering and qualification samples are a hard stop.

The original mod's author wrote on 2020-05-28 that the 7060 BIOS blocks every CPU of stepping P0 (CPUID 0x906EC) and that the block sits in a hashed volume protected by Boot Guard, the area this method leaves alone ([thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937); unconfirmed). Samples reported dead (unconfirmed):

- 2020-05-28: an i9-9900T ES (QQZ6) that did not boot after a successful flash.
- 2024-01-21: an i7-8700 ES (QN8H) on a 7060 SFF: it did not light up, the fan ran wildly and the power indicator flashed two or three times.
- 2024-07-26: an i9-9900T in a 3070 that also did not boot.

Read the lid before you buy or flash. The retail i7-9700T on the reference build reads SRG17 (stepping R0, CPUID 906ED). A Q-prefixed code such as QQZ6 or QRNL, the words "INTEL CONFIDENTIAL", or a lid you cannot identify means stop. Check the CPUID of the exact part, not its marketing name.

### Does a 9th-generation i3 or i5 need this at all?

Maybe not; this is unconfirmed. The final 7060 BIOS already carries 906EA and 906EB, and some 9th-generation i3 and i5 parts may report those signatures. An owner of an HP EliteDesk 800 G4 mini wrote on 2025-02-05 that it runs 9th-generation i5 CPUs but not 9th-generation i7 (bios-mods.com forum thread "Request: Bios upgrade of an HP Elitedesk 800 G4 mini to support i7 9700T"; unconfirmed). Neither that report nor the CPUID mapping is confirmed for the 7060. Look up your CPU's CPUID in Intel's specification update, run MCExtractor on your BIOS image, and continue only if that CPUID is missing.

### Does this work on HP, Lenovo, other vendors, laptops or AMD?

Only the Dell OptiPlex 7060 SFF is proven. [02-does-my-hardware-qualify.md](02-does-my-hardware-qualify.md) has the decision tree.

| Platform | Status |
|---|---|
| Dell OptiPlex 5060 and 3060 | Candidates, untested. A 2022 Win-Raid post reports that inserting microcode into a 3060 Mini Tower image succeeded; no CPU boot is reported (source thread not recorded; unconfirmed). |
| HP EliteDesk 800 G4 | Right chipset (a poster notes the G4 uses Q370, [Win-Raid](https://winraid.level1techs.com/t/89291), 2022-09-01) and a likely donor: 906ED is missing from one firmware and present in another, which the poster identifies as the G4 mini and the G5 mini (2025-02-05, bios-mods.com forum thread "Request: Bios upgrade of an HP Elitedesk 800 G4 mini to support i7 9700T"). The same poster pasted FPT Error 167. No service jumper is documented that this project could find, and Sure Start is reported on an HP laptop to restore a stock BIOS even after a modified one is programmed in ([Win-Raid](https://winraid.level1techs.com/t/rollback-hp-elite-dragonfly-bios-and-intel-me/35122), 2020-06-01). All of it unconfirmed. Research grade, so there is no recipe here. |
| Lenovo ThinkCentre M720 and M920 | Lenovo's spec sheets for the [M920 SFF](https://psrefstuff.lenovo.com/syspool/Sys/PDF/ThinkCentre/ThinkCentre_M920_SFF/ThinkCentre_M920_SFF_Spec.html) and the [M720 Tower](https://psref.lenovo.com/syspool/Sys/PDF/ThinkCentre/ThinkCentre_M720_Tower/ThinkCentre_M720_Tower_Spec.html) list 9th-generation Core processors, i9-9900 included. Update the BIOS instead. The Tiny models (M720q) were not checked. |
| 100/200-series boards (Skylake, Kaby Lake) | A different problem, Coffee Lake on an older chipset. Out of scope. |
| AMD, and laptops with soldered CPUs | Out of scope: different firmware, or no swappable CPU. |

### Will the board power and cool the CPU I want to fit?

Microcode only lets the CPU start. Whether the voltage regulators and the cooler can sustain it is a separate question. The reference build went from a 65 W 6-core i5-8500 to a 35 W 8-core i7-9700T and passed closed-case thermal soaks. The BIOS on that board has no power-limit controls (reported), so a higher-wattage 8-core part has less margin and no setting to cap it. One post of 2021-02-23 describes a 65 W i7-9700 that started and then tripped the board's protection, with the indicator flashing orange and the board turning off (unconfirmed). Check your cooler and power supply first.

## After the flash

### Will Windows or Linux see the new CPU automatically?

Yes, once the machine starts. To the OS it is an ordinary CPU and needs no driver. What the OS reports does not prove the BIOS carries the patch, though, because an OS can load its own microcode and report that revision. The proof is that the board starts with the new CPU, plus MCExtractor on a fresh dump of the flash.

Windows (PowerShell):

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, ProcessorId
Get-ItemPropertyValue 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0' -Name 'Update Revision' |
  ForEach-Object { '{0:X2}' -f $_ }
```

Linux:

```sh
grep -E -m2 '^(model name|microcode)' /proc/cpuinfo
dmesg | grep -i microcode    # typically shows whether the kernel replaced the BIOS's revision
```

On the reference build a live check read the processor ID BFEBFBFF000906ED and the revision bytes 04 01 00 00, which is 0x104 little-endian (reported). Treat the registry value as a hint, since other systems may lay it out differently. While the service jumper is set, the Intel Management Engine Interface is absent and the remote-management ports are quiet (reported: live checks over SSH). Remove the jumper before the machine returns to service, then check that the device is back.

### What does the modified BIOS give up, and what if I update it later?

Two things.

First, the swapped-out patch is gone from the image. The reference swap overwrote the 906EB slot, so a CPU with that signature (the 8th-generation 4-core parts) no longer has a patch in this BIOS. Intel's FIT specification says "A microcode update must exist for every processor stepping supported by the platform" (section 2), so expect a 906EB part to stop booting. That was not tested. The reference build's resident CPU, an i5-8500, is a 906EA part, and its patch is untouched. Check which signature your resident CPU needs before you choose a slot.

Second, a BIOS update, a downgrade, a vendor recovery image or a firmware capsule writes the vendor's microcode volume back, and that volume has no patch for the new CPU. It then stops booting. This follows from what the flash contains and was not tested on the reference build. Keep the old CPU, or repeat the procedure on the new image and derive every offset again, because none carry over between BIOS versions.

### What if it goes wrong?

Where it breaks decides how you recover.

| What you see | Likely cause | Way back |
|---|---|---|
| New CPU will not start; old CPU boots normally | A microcode or CPU problem; the BIOS itself is fine | Refit the old CPU and remove the jumper. The reference swap left the old CPU's patch in place (verified). Dell's LED list has 3,7 for "BIOS/CPU failure" ([KB 000132453](https://www.dell.com/support/kbdoc/en-us/000132453)); the reference build never produced one, so what an unsupported CPU shows on your board is unknown. |
| Amber LED blinking, no normal start, with the old CPU fitted | Damaged BIOS region. Dell lists 3,6 as BIOS corruption that recovery should fix. | Dell's USB recovery (Ctrl+Esc at power-on, described in the same KB) is the first thing to try. Two of the three reported 7060 failures mention an external programmer as the way back, so plan for one. |
| Brief flicker, immediate power-off, no video | The boot block or FIT no longer matches the Boot Guard policy (the expected failure from the reference record; not observed, because the reference build never failed) | External SPI programmer and your off-box dump; per the reference plan, nothing else restores it. |

Have a programmer, a clip that fits your chip's package, and two identical off-box dumps before the first write. Avoid the CH341A as commonly sold ([05](05-safety-and-recovery.md), rung 4, says what makes one acceptable): Libreboot's documentation says it "can have 5V logic levels on data lines, which can damage your SPI flash and also the southbridge that it's connected to", and that many newer flash chips run at 1.8 V ([Libreboot](https://libreboot.org/docs/install/spi.html); more in [09-sourcing-and-licensing.md](09-sourcing-and-licensing.md)). The full recovery ladder is in [05-safety-and-recovery.md](05-safety-and-recovery.md).

## Process

### Can an AI agent do the firmware analysis?

Yes. On the reference build the owner read the CPU lid, moved the service jumper on and off, swapped the CPU and thermal pad, and removed the case mesh screens; everything else was done remotely over SSH by an AI agent: the audit, two pre-write dumps, parsing the flash descriptor, FIT and Boot Guard manifests, locating the microcode volume, building and verifying the payload, running the write and reading it back.

Rules for an agent, from the reference build and its lessons:

- Every gate prints PASS or FAIL, and the write waits for an explicit human go.
- A claim marked unverified cannot justify a write.
- Run the write detached from the SSH session. OpenSSH on Windows ends child processes when the session drops, so the reference build started the write through `Invoke-CimMethod -ClassName Win32_Process -MethodName Create` and polled its log.
- Never run the vendor's BIOS installer remotely. On the reference build one attempt killed the SSH session and rebooted the PC ([05](05-safety-and-recovery.md#5-do-not-do-this)).

If an answer here is wrong or out of date, open an issue with a source. See [SECURITY.md](../SECURITY.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).
