# Tools

Two Python scripts that work on firmware image files you supply. One builds a modified image, the other decides whether that image is fit to flash. Neither touches hardware, and both need nothing beyond the Python 3 standard library.

| Script | Reads | Writes | Purpose |
|---|---|---|---|
| [`build_microcode_swap.py`](build_microcode_swap.py) | your dump, a donor | `modified_full.bin`, `ucode_fv_mod.bin`, `report.txt` in the directory you name | Overwrites one existing microcode update with the donor's, same size, FIT untouched |
| [`verify_microcode_mod.py`](verify_microcode_mod.py) | your dump, the modified image, optionally the payload | nothing | Prints PASS or FAIL per check, exits 1 and prints `DO NOT FLASH` if any check fails |

The builder runs the verifier's checks on its own output before it writes anything, so it cannot hand you an image the verifier would reject. Run the verifier on the files you are about to use anyway. It takes about a third of a second on a 32 MB image (measured on the reference build's dump).

## What they never do

- They open the files you name on the command line and nothing else: no flash device, no driver, no network socket.
- The verifier writes no file. The builder writes only into `--out-dir`, refuses to overwrite an existing file unless you pass `--force`, and refuses to write over either of its inputs.
- They do not flash. Writing the payload to the chip is a separate manual step with Intel's own flash tool (FPT), which comes from Intel's OEM tool packages and is not redistributed here. The procedure and the recovery plan are in [../docs/04-procedure.md](../docs/04-procedure.md) and [../docs/05-safety-and-recovery.md](../docs/05-safety-and-recovery.md).
- They write no UEFI variables either. The method only ever changes the microcode volume.

A script that cannot reach hardware cannot damage it, so you can run these on any machine, on a dump copied from anywhere, as often as you like. The write is the one step where a mistake costs a board, so it stays a deliberate action in which you read the address and the length yourself.

## Requirements

Python 3.8 or newer is the intent. It has been developed and run on 3.14 only and has not been tried on older versions. No packages to install.

Run both with `python -I`. Isolated mode keeps Python from importing anything out of the current directory or from environment variables. Firmware dumps arrive from forums and mirrors, and the folder you work in may hold anything.

## Inputs

| File | What it is | Where it comes from |
|---|---|---|
| `TARGET` / `ORIGINAL` | your own dump, taken before any change | a full SPI dump, or the BIOS-region dump, from your flash tool. Take two and confirm they are identical before trusting either |
| `DONOR` | a BIOS image that carries the microcode you want, from the same vendor's sibling model | extracted from the vendor's BIOS update, see [../docs/09-sourcing-and-licensing.md](../docs/09-sourcing-and-licensing.md). Or, with `--donor-kind microcode`, a file of bare microcode updates such as those in [Intel's public microcode repository](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files) |

Two image shapes are accepted: a full SPI dump with a flash descriptor, or a BIOS-region dump whose last byte is the byte decoded at 4 GiB - 1. A firmware volume cut out with a UEFI editor is neither, and the tools say so instead of guessing. Every offset the tools print is relative to the BIOS region.

CPUIDs can be written `906ED`, `0x906ED` or in Intel's file-name form `06-9e-0d`.

## verify_microcode_mod.py

```
python -I verify_microcode_mod.py ORIGINAL MODIFIED [PAYLOAD] --target-cpuid CPUID --fallback-cpuid CPUID [options]
```

| Option | Meaning |
|---|---|
| `--target-cpuid` | the CPUID whose microcode you are adding |
| `--fallback-cpuid` | a CPUID that must stay bootable, normally the CPU installed now. Repeat for several. Leaving it out is a FAIL, because the tool cannot know which CPU you want to keep |
| `--replace-cpuid` | optional assertion: the CPUID whose slot was overwritten |
| `--ucode-window OFF:LEN` | hex, relative to the BIOS region. Use it instead of finding the EFI volume from the FIT. Skips the FFS file check |
| `--payload-offset OFF` | hex. Where `PAYLOAD` belongs when it is not the whole microcode volume |
| `--accept-no-bpm-check` | see [When the Boot Policy Manifest cannot be parsed](#when-the-boot-policy-manifest-cannot-be-parsed) |
| `--list-ranges` | print every exact changed byte range after the checks |
| `--self-test` | run the built-in cases on synthetic images, no files needed |

Exit status: 0 all checks passed, 1 a check failed or an input could not be read, 2 bad command line. An unexpected error counts as a failure, never as a pass.

### What it checks

The contract is a same-size swap of one microcode update and nothing else. An image made any other way (microcode appended, FIT edited, whole image rebuilt) fails by design.

| Group | Checks | Why |
|---|---|---|
| Geometry | files have the same size; the BIOS region is found the same way in both | every later check compares offsets |
| FIT | the pointer at 4 GiB - 0x40 lands on `_FIT_`; the whole table is byte-identical; the Key Manifest (type 0x0B) and Boot Policy Manifest (type 0x0C) entries are bit-identical | the CPU and the Boot Guard ACM find the signed policy through these entries. Type numbers are from Table 2 of [Intel's FIT specification](https://www.intel.pl/content/dam/develop/external/us/en/documents/firmware-interface-table-bios-specification-r1p2p1.pdf) |
| Microcode volume | the one EFI firmware volume that holds every FIT microcode entry is found; it is 4 KiB aligned; every microcode slot lies inside it | this volume is the write window |
| Changed bytes | at least one byte changed; none outside the volume; exactly one FIT microcode slot changed, same offset, same size; every changed byte inside that slot; the slot sits in an FFS file whose data-checksum attribute (0x40) is clear | the swap contract. A file that carries a data checksum would need a header edit, which this toolset refuses |
| Microcode | every update the FIT points at passes Intel's checksum (the sum of all dwords is zero) and is 16-byte aligned; an empty slot (first dword 0xFFFFFFFF) is allowed | [Intel SDM vol. 3A](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html), FIT specification section 4.3 |
| CPUIDs | each fallback is present, byte-identical to the original, checksum valid; the target is present with a valid checksum and sits in the changed slot | your current CPU keeps working, the new one gets its update |
| Boot Guard objects | the startup ACM, Key Manifest and Boot Policy Manifest (and any BIOS startup module) are byte-identical; the microcode volume overlaps none of them | these sit in the gaps between IBB segments on the reference build, so the IBB digest alone would not notice a change there |
| IBB digest | the BPM is parsed from the image; the SHA-256 over its segment list equals the digest stored in the ORIGINAL's BPM, is unchanged in MODIFIED, no segment overlaps the volume and no changed byte falls in a segment | if the IBB changes, the Boot Guard ACM refuses to start the platform before any BIOS code runs. Background: [Ermolov, ZeroNights 2016](https://papers.put.as/papers/firmware/2016/Intel_BootGuard_final.pdf), [Matrosov, Black Hat USA 2017](https://www.blackhat.com/docs/us-17/wednesday/us-17-Matrosov-Betraying-The-BIOS-Where-The-Guardians-Of-The-BIOS-Are-Failing.pdf) |
| Payload (if given) | length equals the volume, or `--payload-offset` is given; it lies inside the volume, is 4 KiB aligned, equals the matching slice of MODIFIED, covers every changed byte and overlaps no Boot Guard object | the file you flash is the file you checked |

The IBB segment list is read from the BPM in the image. Nothing is hard-coded to one board.

### Sample output

Abridged, from synthetic images (see [Self-test](#self-test)); the numbers differ on real firmware. The first run is a good pair, the second has one byte flipped inside an IBB segment.

```
== Changed bytes ==
  [PASS] at least one byte changed  -- 106037 bytes in 426 ranges
  [PASS] zero bytes changed outside the microcode FV  -- all 106037 changed bytes are inside region+0xD20000-0xE0FFFF
== Swap contract ==
  [PASS] exactly one FIT microcode slot changed, at the same offset and with the same size  -- FIT entry 2, region+0xD3A000, 0x1A000 bytes
  [info] slot: CPUID 0x906EB rev 0xF6  ->  CPUID 0x906ED rev 0x104
== IBB digest (Boot Guard) ==
  [PASS] IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM  -- match
  [PASS] IBB digest UNCHANGED in the modified image  -- match
RESULT: ALL CHECKS PASSED
```

```
  [FAIL] zero bytes changed outside the microcode FV  -- 1 bytes changed outside region+0xD20000-0xE0FFFF; first at region+0xF10000
  [FAIL] IBB digest UNCHANGED in the modified image  -- original <8 hex>... modified <8 hex>...
  [FAIL] no changed byte lies inside an IBB segment  -- touched: region+0xF00000-0xFC007F
RESULT: 6 CHECK(S) FAILED -- DO NOT FLASH
```

### When a check fails

| Failed check | What it means | What to do |
|---|---|---|
| zero bytes changed outside the microcode FV | something besides the microcode volume differs from your dump | rebuild from the pristine dump; do not flash |
| IBB digest UNCHANGED / no changed byte lies inside an IBB segment | a byte the Boot Guard ACM hashes changed. On a board that enforces Boot Guard this powers the machine off before any BIOS code runs, and only an external SPI programmer recovers it (the reference build's recovery notes) | do not flash |
| FIT byte-identical | the table was edited | rebuild with `build_microcode_swap.py` |
| fallback CPUID ... still present | the CPU you run today would lose its microcode | stop; check the CPUID with a microcode lister such as [MCExtractor](https://github.com/platomav/MCExtractor) |
| slot sits in the data area of one FFS file without a data checksum | the board checksums the file that holds the microcode, and this toolset does not recompute that checksum | stop; it is a different layout from the reference build |
| IBB digest recomputed from the ORIGINAL ... | the BPM parsed, but its stored digest is not reproduced from your dump. A damaged dump, a different layout than the parser knows, or a board that already fails its own check | there is no flag for this one. Take a fresh dump; if it persists, open an issue with the BPM bytes (no other data) |
| flash anyway without the IBB digest check | no usable BPM, see below | read the next section |

### When the Boot Policy Manifest cannot be parsed

The parser knows one layout: BPM structure version 0x10 with a SHA-256 IBB hash, which is the layout of the reference build. If the FIT has no type 0x0C entry, or the BPM is any other version or hash, the verifier prints WARN lines and fails the check named `flash anyway without the IBB digest check`. It does not guess a layout.

`--accept-no-bpm-check` turns that failure into a pass with warnings. After that, the only evidence the IBB is intact is that no byte outside the microcode volume changed. That does not show the volume itself lies outside the IBB. coreboot's [IBB documentation](https://doc.coreboot.org/security/intel/txt_ibb.html) says the IBB "might overlap with microcode" (quoted from a digest of that page, not re-read), and on a platform that hashes its microcode the swap breaks Boot Guard at the next power-on. Use the flag only if you can establish the IBB layout some other way, for example with UEFITool's FIT view.

## build_microcode_swap.py

```
python -I build_microcode_swap.py TARGET DONOR TARGET_CPUID --replace-cpuid CPUID --fallback-cpuid CPUID --out-dir DIR [options]
```

Example (file names, CPUIDs and directory are placeholders):

```
python -I build_microcode_swap.py dump_before.bin donor_bios_region.bin 906ED --replace-cpuid 906EB --fallback-cpuid 906EA --platform-id <N> --out-dir out
```

| Option | Meaning |
|---|---|
| `--replace-cpuid` | required. The CPUID whose slot is overwritten. The tool never picks a victim; it lists the same-size, unprotected slots and refuses if you name another |
| `--fallback-cpuid` | required, repeatable. CPUIDs that must keep their microcode, normally the CPU installed now |
| `--out-dir` | where the three files go. Required unless `--dry-run` |
| `--donor-kind image\|microcode` | `image` (default): `DONOR` is a BIOS image. `microcode`: `DONOR` holds one or more bare updates, optionally followed by 0xFF padding |
| `--platform-id N` | 0 to 7, the platform ID of the CPU you will install (IA32_PLATFORM_ID, MSR 0x17 bits 52:50). The donor's platform mask must include it. Without it the tool prints the mask and a warning |
| `--fit-offset`, `--fv-base`, `--fv-len` | hex, relative to the BIOS region. They must agree with what the tool derives, or it refuses. If no EFI volume is found, `--fv-base` and `--fv-len` define the write window instead, and the FFS file check cannot run |
| `--accept-no-bpm-check` | same meaning as in the verifier |
| `--force`, `--dry-run`, `--self-test` | overwrite existing outputs; run every check and write nothing; run the built-in cases |

Exit status: 0 built (or dry run succeeded), 1 refused, 2 bad command line.

### What it does, in order

1. Finds the BIOS region and the FIT from the pointer at 4 GiB - 0x40.
2. Reads every microcode the FIT references and requires a valid checksum and 16-byte alignment on each.
3. Requires the fallback CPUIDs to be present and the target CPUID to be absent, both from the FIT and from a raw scan of the whole image for unreferenced copies.
4. Takes the donor update for the target CPUID, the highest revision if there are several, and requires it to be unambiguous and to pass Intel's checksum.
5. Requires the slot named by `--replace-cpuid` to have exactly the donor's size and to be referenced by exactly one FIT entry.
6. Derives the microcode volume and requires the slot to sit in an FFS file without a data checksum.
7. Copies the donor bytes over the slot, in memory, and runs the verifier's full gate set on the result.
8. Only if everything passed, writes the three files.

Any failure stops the run with `REFUSED: <reason>` and `Nothing was written.` Refusal causes: FIT pointer that does not land on `_FIT_`; a FIT microcode entry that is unreadable, misaligned or fails its checksum; target CPUID already present anywhere; fallback missing; replace CPUID equal to a fallback or to the target; donor update missing, ambiguous or failing its checksum; slot size different from the donor's; two slots with the same CPUID; no single EFI volume holding the microcode; an FFS data checksum; any failed verifier gate.

The donor's size has to match exactly. A smaller update would fit a larger slot in principle, since the FIT carries no slot sizes, but this tool does not do it and it has not been tried on a board.

### What it changes, and what that costs

One microcode update is overwritten. A CPU whose signature matches the removed update no longer gets a BIOS-supplied microcode update at reset. Whether such a CPU still starts is not guaranteed, so keep it out of the board. The report states the CPUID, revision, date and platform mask of both the removed and the added update. On the reference build the removed slot held a stepping the board never used (per that build's notes), and the CPU installed at the time kept its own update, so it remained a working fallback.

### Outputs

| File | Content |
|---|---|
| `modified_full.bin` | the whole image with the one slot replaced, the same size as `TARGET` |
| `ucode_fv_mod.bin` | the microcode firmware volume alone, the file a flash tool is given (0xF0000 bytes on the reference build) |
| `report.txt` | every check, the derived layout, the write window, and the exact changed byte ranges (no file paths, no hashes) |

### The write window

The report and the console print the window the payload covers: a BIOS-region offset and a length. For a full SPI dump the tool adds the absolute SPI address, the BIOS region base from the descriptor plus the offset. For a BIOS-region dump it cannot, and says so: read the base from your flash tool or the flash descriptor.

On the reference build (OptiPlex 7060 SFF, BIOS 1.32.0) the window is offset 0xD20000, length 0xF0000, absolute address 0x1D20000, and the write that worked there used `-a 0x1D20000 -l 0xF0000` with FPT (reported; the readback was verified). The same record says to always pass both `-a` and `-l` and never to disable the tool's verification (reported; check your own tool's documentation). Absolute addresses differ between boards. A forum poster reported a base of 0x1D50000 for a Vostro 3670 (reported, unconfirmed: [Win-Raid thread](https://winraid.level1techs.com/t/help-adding-cpu-microcode-to-dell-7060-bios/34937)), which is why the address is derived from your dump and never copied.

## What has and has not been checked

Checked against the reference build's dump (OptiPlex 7060 SFF, BIOS 1.32.0), opened read-only:

- the FIT, firmware volumes, FFS files, ACM, Key Manifest and Boot Policy Manifest parse as described;
- the IBB digest recomputed from the BPM's segment list equals the digest stored in the BPM;
- the builder's output equals an independent byte splice of the same donor bytes, and the verifier passes it. The donor in those runs was a synthetic update with a valid checksum, not a vendor image;
- a dozen single-byte and structural mutations of that real pair (inside an IBB segment, the ACM, the Key Manifest, the BPM, the flash descriptor, the new microcode, the FIT, a truncated file, a short payload) were each rejected;
- on synthetic images, 1,500 single-byte changes to a good modified image, with the structure headers targeted, were all rejected, and 500 corrupted targets produced only builds that re-verified or clean refusals, never a crash;
- both scripts pass their `--self-test`.

Not checked:

- Other BPM structure versions and hash algorithms. They are reported as "not usable" and need the flag.
- Microcode with an extended signature table. The rule is written from the SDM; no real sample was available. A mismatch there is a warning, not a failure. The whole-update checksum, which covers those bytes, is the hard check.
- Any board other than the reference build, and any vendor other than Dell. Failures to parse end in FAIL or REFUSED, not in PASS.
- Firmware that hashes the microcode volume with its own scheme on top of Boot Guard. The Black Hat 2017 deck linked in the checks table describes AMI-style firmware-volume hashes of this kind. These tools cannot see one. The first boot on the old CPU after the flash is the test.
- A real vendor donor. The donor-side logic was exercised with synthetic images and with a real Windows microcode blob, which the builder correctly refused on size.

A PASS means the files are consistent with the contract. It says nothing about the write path, the power supply, your recovery programmer, or TPM-bound keys: a changed BIOS volume may change measured-boot values, so have your BitLocker recovery key at hand (recorded as a risk in the reference record).

## Self-test

```
python -I verify_microcode_mod.py --self-test
python -I build_microcode_swap.py --self-test
```

The verifier runs 31 cases and the builder 24, on images generated from a seeded random stream. No vendor firmware is embedded in either script. The geometry copies the reference build's layout (volume at 0xD20000, FIT at 0xD20100, BPM at 0xFC0080 and so on); the content is random. Each mutation case asserts that the mutation changed something, and each negative case names the check that has to fail, so a case passes only when that check, not just some check, fails.

## Helper scripts for the procedure

[04-procedure.md](../docs/04-procedure.md) uses three small helpers besides the two tools. They are plain Python 3 with no dependencies, run as `python -I`, and are not part of the checked toolset. `cut.py` writes one output file; the other two only read. They were run against a synthetic image built to the reference layout, not against real firmware. Save each under the file name in its first comment.

`cut.py` cuts a range out of a file and refuses to run past the end of it:

```python
# cut.py  usage: python -I cut.py <in.bin> <offset> <length> <out.bin>
import sys

src, off, length, dst = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0), sys.argv[4]
data = open(src, "rb").read()
if off + length > len(data):
    sys.exit(f"refusing: 0x{off:X}+0x{length:X} runs past the end of {src} (0x{len(data):X} bytes)")
open(dst, "wb").write(data[off:off + length])
print(f"{dst}: 0x{length:X} bytes ({length}) taken from 0x{off:X}")
```

`blank.py` lists 64 KB-aligned blocks inside the microcode volume that are entirely `0xFF`, which are safe places for the probe write:

```python
# blank.py  usage: python -I blank.py <bios_region.bin> <fv_offset> <fv_length>
import sys

img, off, length = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
data = open(img, "rb").read()
blank = b"\xff" * 0x10000
first = (off + 0xFFFF) & ~0xFFFF          # first 64 KB boundary inside the volume
found = [a for a in range(first, off + length - 0xFFFF, 0x10000) if data[a:a + 0x10000] == blank]
for a in found[:4]:
    print(f"blank 64 KB block at region offset 0x{a:X}")
print(f"{len(found)} blank 64 KB block(s) inside 0x{off:X}..0x{off + length:X}")
```

`diffranges.py` prints each contiguous range where two equal-sized files differ. Offsets are file offsets, so on a full dump they are flash addresses:

```python
# diffranges.py  usage: python -I diffranges.py <a.bin> <b.bin>
import sys

a, b = open(sys.argv[1], "rb").read(), open(sys.argv[2], "rb").read()
if len(a) != len(b):
    sys.exit(f"sizes differ: {len(a)} vs {len(b)}")
STEP, start, last = 0x1000, None, None
for base in range(0, len(a), STEP):
    if a[base:base + STEP] == b[base:base + STEP]:
        continue
    for i in range(base, min(base + STEP, len(a))):
        if a[i] != b[i]:
            if start is None:
                start = i
            elif i - last > 0x100:               # a gap of 256+ equal bytes closes the range
                print(f"0x{start:X}-0x{last:X}  (span {last - start + 1} bytes)")
                start = i
            last = i
if start is not None:
    print(f"0x{start:X}-0x{last:X}  (span {last - start + 1} bytes)")
else:
    print("identical")
```

## Keeping the two copies in sync

`python -I` leaves the script's directory off `sys.path`, so one script cannot import the other. The parsing and gate code is therefore copied into both, between the `SHARED CORE` and `END OF SHARED CORE` comments. If you change one copy, change the other. This prints `True` when they match:

```
python -I -c "import re;f=lambda n:re.search(r'# SHARED CORE.*?# END OF SHARED CORE',open(n).read(),re.S).group(0);print(f('verify_microcode_mod.py')==f('build_microcode_swap.py'))"
```

Safety bugs (a check that passes when it should fail, a wrong offset, a missing warning) get priority; see [../CONTRIBUTING.md](../CONTRIBUTING.md).
