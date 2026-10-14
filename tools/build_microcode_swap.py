#!/usr/bin/env python3
"""Same-size microcode swap for a BIOS image. Offline: it reads files and writes files, nothing else.

You give it your own dump (TARGET), a donor that carries the microcode of the CPU you want to add
(DONOR) and that CPU's CPUID. It overwrites ONE existing microcode update in TARGET with the donor's,
leaves the FIT byte-identical, keeps the fallback CPU's microcode, and writes three files to --out-dir:

  modified_full.bin  the whole image with that one slot replaced (same size as TARGET)
  ucode_fv_mod.bin   the microcode firmware volume alone: the file a flash tool would be given
  report.txt         the checks, the layout it derived and every changed byte range

It refuses, and writes nothing, on any layout surprise: a FIT pointer that does not land on the FIT, the
target CPUID already present, a fallback CPUID missing, a slot whose size differs from the donor update, a
donor update that fails Intel's checksum, an FFS file that carries a data checksum, or any gate of
verify_microcode_mod.py failing on the finished image (those gates run on the result in memory first).
You name the slot to overwrite with --replace-cpuid; the tool never picks one for you.

DONOR is a BIOS image (full SPI dump or BIOS-region dump, the default) or, with --donor-kind microcode, a
file holding one or more bare microcode updates, such as the files of Intel's public microcode repository.

It never writes to hardware and never flashes anything. Flashing is a separate manual step with the
flash tool your vendor or Intel supplies; see the README next to this file.

Exit status: 0 built (or dry run succeeded), 1 refused, 2 bad command line.

Example (file names, CPUIDs and the directory are placeholders):
  python -I build_microcode_swap.py dump_before.bin donor_bios_region.bin 906ED --replace-cpuid 906EB --fallback-cpuid 906EA --out-dir out
"""

# ======================================================================================
# SHARED CORE. This block is identical in verify_microcode_mod.py and build_microcode_swap.py.
# `python -I` keeps the script directory off sys.path, so one tool cannot import the other;
# the copy is deliberate and a test compares the two copies byte for byte.
# ======================================================================================

import collections
import hashlib
import os
import random
import struct
import sys

TOP = 1 << 32
MASK32 = 0xFFFFFFFF
FIT_SIG = b'_FIT_   '
FIT_ENTRY = 16
FIT_WINDOW = 16 << 20          # the CPU only looks for the FIT in the top 16 MiB below 4 GiB
T_HEADER, T_UCODE, T_ACM, T_DIAG_ACM, T_BIOS_STARTUP = 0x00, 0x01, 0x02, 0x03, 0x07
T_KEY_MANIFEST = 0x0B          # Intel FIT specification (document 599500), Table 2
T_BOOT_POLICY = 0x0C           # same table
FLVALSIG = 0x0FF0A55A          # flash descriptor signature, found at offset 0x10 of a full SPI image
FFS_ATTR_LARGE = 0x01
FFS_ATTR_CHECKSUM = 0x40       # the file carries a data checksum (UEFI PI specification)
UCODE_MAX = 4 << 20
MAX_IMAGE = 256 << 20
SECTOR = 0x1000


class FwError(Exception):
    """The input is not something these tools can reason about safely."""


def hx(n):
    return '0x%X' % n


def span(a, b):
    """Inclusive-end text for the half-open range [a, b)."""
    return '%s-%s' % (hx(a), hx(b - 1))


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def u64(b, o):
    return struct.unpack_from('<Q', b, o)[0]


def rev_signed(rev):
    return rev - (1 << 32) if rev & 0x80000000 else rev


def bcd_date(d):
    return '%04X-%02X-%02X' % (d & 0xFFFF, (d >> 24) & 0xFF, (d >> 16) & 0xFF)


def parse_cpuid(text):
    """'906ED', '0x906ED', or Intel's file-name form 'family-model-stepping' such as '06-9e-0d'."""
    t = text.strip().lower().replace(':', '-')
    if '-' in t:
        parts = t.split('-')
        if len(parts) != 3:
            raise ValueError('expected family-model-stepping, for example 06-9e-0d')
        fam, model, step = [int(p, 16) for p in parts]
        if fam > 0x0F or model > 0xFF or step > 0x0F:
            raise ValueError('family-model-stepping out of range (family must be <= 0x0F)')
        return ((model >> 4) << 16) | (fam << 8) | ((model & 0xF) << 4) | step
    v = int(t, 16)
    if not 0 < v <= MASK32:
        raise ValueError('CPUID out of range')
    return v


def parse_hex(text):
    return int(text.strip(), 16)


def guid_bytes(text):
    """Canonical dashed GUID text to the 16 bytes stored in firmware (first three fields little-endian)."""
    a, b, c, d, e = text.split('-')
    return struct.pack('<IHH', int(a, 16), int(b, 16), int(c, 16)) + bytes.fromhex(d + e)


def read_file(path):
    try:
        size = os.path.getsize(path)
        if size == 0 or size > MAX_IMAGE:
            raise FwError('%s: size %d bytes is outside the supported range (1 byte to %d MiB)'
                          % (os.path.basename(path), size, MAX_IMAGE >> 20))
        with open(path, 'rb') as f:
            return f.read()
    except OSError as e:
        raise FwError('cannot read %s: %s' % (os.path.basename(path), e.strerror or e))


# --------------------------------------------------------------------------- images

class Image(object):
    """A flash image and the BIOS-region view that every offset in these tools is relative to.

    A full SPI dump carries a flash descriptor (signature 0x0FF0A55A at offset 0x10); the BIOS region
    is then the span FLREG1 names. Anything else is taken to be a BIOS-region dump. In both cases the
    last byte of the region is decoded at 4 GiB - 1, which is how the FIT pointer and every FIT address
    turn into offsets.
    """

    def __init__(self, raw):
        self.raw = raw
        self.kind = 'bios-region'
        self.base = 0
        self.size = len(raw)
        if len(raw) >= SECTOR and u32(raw, 0x10) == FLVALSIG:
            frba = ((u32(raw, 0x14) >> 16) & 0xFF) << 4
            if frba + 8 > len(raw):
                raise FwError('flash descriptor: the region table is outside the file')
            flreg1 = u32(raw, frba + 4)
            base = (flreg1 & 0x7FFF) << 12
            limit = (((flreg1 >> 16) & 0x7FFF) << 12) | 0xFFF
            if base > limit or limit >= len(raw):
                raise FwError('flash descriptor: BIOS region (FLREG1 = %s) is empty or runs past the end '
                              'of the file' % hx(flreg1))
            self.kind = 'full-spi'
            self.base = base
            self.size = limit + 1 - base
        self.data = raw[self.base:self.base + self.size] if self.kind == 'full-spi' else raw

    def off(self, addr):
        """Region offset of a 32-bit address, or None if it is not inside the region."""
        o = addr - (TOP - self.size)
        return o if 0 <= o < self.size else None

    def describe(self):
        if self.kind == 'full-spi':
            return 'full SPI image, BIOS region %s (%s bytes)' % (span(self.base, self.base + self.size), hx(self.size))
        return 'BIOS-region image (%s bytes)' % hx(self.size)


# --------------------------------------------------------------------------- FIT

FitEntry = collections.namedtuple('FitEntry', 'idx type addr size version cv checksum raw')


class Fit(object):
    def __init__(self, ptr, off, entries, raw):
        self.ptr, self.off, self.entries, self.raw = ptr, off, entries, raw


def parse_fit(img):
    """Locate the FIT through the pointer at 4 GiB - 0x40 and read its entries."""
    d, L = img.data, img.size
    hint = ('Accepted inputs are a full SPI dump with a flash descriptor, or a BIOS-region dump whose last '
            'byte is the byte decoded at 4 GiB - 1. A bare firmware volume cut out with a UEFI editor is '
            'not either of those.')
    if L < 0x1000:
        raise FwError('image too small to be a BIOS region. ' + hint)
    ptr = u64(d, L - 0x40)
    if ptr >> 32 or ptr < TOP - min(L, FIT_WINDOW) or ptr > TOP - 0x40 - FIT_ENTRY:
        raise FwError('the FIT pointer at region end - 0x40 reads %s, which is not an address in the top '
                      '16 MiB below 4 GiB. %s' % (hx(ptr), hint))
    off = ptr - (TOP - L)
    if d[off:off + 8] != FIT_SIG:
        raise FwError('no "_FIT_" signature at region+%s, where the FIT pointer points. %s' % (hx(off), hint))
    n = d[off + 8] | d[off + 9] << 8 | d[off + 10] << 16
    if n < 1 or n > 4096 or off + n * FIT_ENTRY > L or ptr + n * FIT_ENTRY > TOP - 0x40:
        raise FwError('FIT header says %d entries, which does not fit below the FIT pointer' % n)
    entries = []
    for i in range(n):
        e = bytes(d[off + i * FIT_ENTRY: off + (i + 1) * FIT_ENTRY])
        entries.append(FitEntry(i, e[14] & 0x7F, u64(e, 0), e[8] | e[9] << 8 | e[10] << 16,
                                u16(e, 12), e[14] >> 7, e[15], e))
    return Fit(ptr, off, entries, bytes(d[off:off + n * FIT_ENTRY]))


# --------------------------------------------------------------------------- microcode

Slot = collections.namedtuple('Slot', 'idx addr off kind info aligned')


def parse_ucode(buf, off):
    """Classify the bytes at buf[off:]. Returns (kind, info) with kind 'empty', 'ucode' or 'bad'.

    Layout and checksum rule: Intel SDM volume 3A, "Microcode Update Facilities". A DataSize of 0 means
    2000 and a TotalSize of 0 means 2048. The sum of every dword of the update, extended signature table
    included, must be zero.
    """
    if off < 0 or off + 4 > len(buf):
        return 'bad', {'why': 'address is outside the image'}
    if u32(buf, off) == MASK32:
        return 'empty', {}
    if off + 48 > len(buf):
        return 'bad', {'why': 'header runs past the end of the image'}
    hv, rev, date, sig, _ck, lv, pf, ds, ts = struct.unpack_from('<9I', buf, off)
    data_size, total = ds or 2000, ts or 2048
    why = []
    if hv != 1:
        why.append('header version %s (expected 1)' % hx(hv))
    if lv != 1:
        why.append('loader revision %s (expected 1)' % hx(lv))
    if total % 4 or data_size % 4 or total < 48 + data_size or total > UCODE_MAX:
        why.append('implausible sizes (data %s, total %s)' % (hx(data_size), hx(total)))
    elif off + total > len(buf):
        why.append('update (%s bytes) runs past the end of the image' % hx(total))
    if why:
        return 'bad', {'why': '; '.join(why), 'cpuid': sig}
    total_sum = sum(struct.unpack_from('<%dI' % (total // 4), buf, off)) & MASK32
    info = {'cpuid': sig, 'rev': rev, 'date': date, 'pf': pf, 'data_size': data_size, 'total': total,
            'sum_ok': total_sum == 0, 'ext_bad': None, 'ext_warn': None}
    ext = total - 48 - data_size
    if ext:
        # Extended signature table: 20-byte header (count, checksum, 12 reserved) + 12 bytes per entry.
        if ext < 20 or (ext - 20) % 12:
            info['ext_bad'] = 'extended table size %s does not fit the 20 + 12*n layout' % hx(ext)
        else:
            tab = off + 48 + data_size
            count = u32(buf, tab)
            if 20 + 12 * count != ext:
                info['ext_bad'] = 'extended table says %d entries but occupies %s bytes' % (count, hx(ext))
            else:
                # Written from the SDM description. No real blob with an extended table has been run
                # through this yet, so a mismatch is only a warning; the whole-update sum above already
                # covers these bytes and is the check that can fail.
                ext_sum = sum(struct.unpack_from('<%dI' % (ext // 4), buf, tab)) & MASK32
                hdr_triple = (sig + pf + u32(buf, off + 16)) & MASK32
                bad = ext_sum != 0
                for i in range(count):
                    s_i, p_i, c_i = struct.unpack_from('<3I', buf, tab + 20 + 12 * i)
                    bad = bad or ((s_i + p_i + c_i) & MASK32) != hdr_triple
                if bad:
                    info['ext_warn'] = 'extended signature table checksums do not follow the SDM rule'
    info['ok'] = info['sum_ok'] and info['ext_bad'] is None
    return 'ucode', info


def ucode_blob(img, slot):
    return bytes(img.data[slot.off:slot.off + slot.info['total']])


def fit_ucode_slots(img, fit):
    out = []
    for e in fit.entries:
        if e.type != T_UCODE:
            continue
        off = img.off(e.addr)
        if off is None:
            kind, info = 'bad', {'why': 'address %s is outside the BIOS region' % hx(e.addr)}
        else:
            kind, info = parse_ucode(img.data, off)
        out.append(Slot(e.idx, e.addr, off, kind, info, e.addr % 16 == 0))
    return out


def slot_text(s):
    if s.kind == 'ucode':
        i = s.info
        return 'CPUID %s rev %s (%s) platform mask %s, %s bytes @ region+%s' % (
            hx(i['cpuid']), hx(i['rev']), bcd_date(i['date']), hx(i['pf']), hx(i['total']), hx(s.off))
    if s.kind == 'empty':
        return 'empty slot @ region+%s' % hx(s.off)
    return 'unreadable (%s)' % s.info.get('why', '?')


# --------------------------------------------------------------------------- firmware volumes

FV = collections.namedtuple('FV', 'start length hdrlen erased')
FfsFile = collections.namedtuple('FfsFile', 'off hdrsize size ftype attr guid')


def find_fvs(data):
    """Every EFI firmware volume header (signature _FVH, header words summing to zero) in `data`."""
    out, pos = [], 0
    while True:
        p = data.find(b'_FVH', pos)
        if p < 0:
            return out
        pos = p + 1
        start = p - 40
        if start < 0 or start + 0x38 > len(data):
            continue
        length, attrs, hdrlen = u64(data, start + 32), u32(data, start + 44), u16(data, start + 48)
        if hdrlen < 0x38 or hdrlen % 2 or hdrlen > SECTOR or length < hdrlen or start + length > len(data):
            continue
        if sum(struct.unpack_from('<%dH' % (hdrlen // 2), data, start)) & 0xFFFF:
            continue
        out.append(FV(start, length, hdrlen, 0xFF if attrs & 0x800 else 0x00))


def enclosing_fv(fvs, off):
    """The innermost volume that contains `off`: a volume nested inside a larger one wins."""
    best = None
    for fv in fvs:
        if fv.start <= off < fv.start + fv.length and (best is None or fv.length < best.length):
            best = fv
    return best


def derive_ucode_fv(img, slots):
    """The single EFI firmware volume that holds every microcode slot the FIT points at."""
    if not slots:
        raise FwError('the FIT has no microcode (type 0x01) entries')
    fvs = find_fvs(img.data)
    owners = set()
    for s in slots:
        if s.off is None:
            raise FwError('FIT entry %d points outside the BIOS region (%s)' % (s.idx, hx(s.addr)))
        owner = enclosing_fv(fvs, s.off)
        if owner is None:
            raise FwError('FIT entry %d (region+%s) is not inside any EFI firmware volume; pass the '
                          'write window explicitly if this board keeps microcode in a raw region'
                          % (s.idx, hx(s.off)))
        owners.add(owner)
    if len(owners) != 1:
        raise FwError('the FIT microcode entries are spread over %d firmware volumes' % len(owners))
    return owners.pop()


def ffs_files(data, fv):
    """The FFS files of a volume, in order. Stops at free space; raises FwError on a corrupt chain."""
    end = fv.start + fv.length
    pos = fv.start + fv.hdrlen
    ext = u16(data, fv.start + 52)
    if ext:
        if fv.start + ext + 20 > end:
            raise FwError('firmware volume extended header is out of range')
        pos = fv.start + ext + u32(data, fv.start + ext + 16)
    files = []
    while True:
        pos = fv.start + (((pos - fv.start) + 7) & ~7)
        if pos + 24 > end:
            return files
        hdr = bytes(data[pos:pos + 24])
        if hdr == bytes([fv.erased]) * 24:
            return files
        attr = hdr[19]
        if attr & FFS_ATTR_LARGE:
            hsz = 32
            if pos + 32 > end:
                raise FwError('FFS file header at region+%s is cut off by the end of the volume' % hx(pos))
            size = u64(data, pos + 24)
        else:
            hsz = 24
            size = hdr[20] | hdr[21] << 8 | hdr[22] << 16
        if size < hsz or pos + size > end:
            raise FwError('FFS file at region+%s has an impossible size %s' % (hx(pos), hx(size)))
        files.append(FfsFile(pos, hsz, size, hdr[18], attr, hdr[:16]))
        pos += size


def ffs_owner(data, fv, a, b):
    """The FFS file whose data area contains [a, b), or None."""
    for f in ffs_files(data, fv):
        if f.off + f.hdrsize <= a and b <= f.off + f.size:
            return f
    return None


def guid_text(g):
    return '%08X-%04X-%04X-%s-%s' % (struct.unpack_from('<IHH', g, 0) + (g[8:10].hex().upper(), g[10:16].hex().upper()))


# --------------------------------------------------------------------------- Boot Guard

Bpm = collections.namedtuple('Bpm', 'off size ibbs digest segments')   # segments: (flags, base, size, off)
BootObj = collections.namedtuple('BootObj', 'name idx start end problem')


class BpmNotParsed(Exception):
    """No BPM was found, or it is not in the one layout this parser has been checked against."""


def parse_bpm(img, fit):
    """Read the IBB digest and segment list from the Boot Policy Manifest the FIT points at.

    The layout below has been checked on one BPM only: the one in the reference build (Dell OptiPlex
    7060 SFF, BIOS 1.32.0), structure version 0x10. '__ACBP__' header of 16 bytes, '__IBBS__' element
    right behind it; inside that element the hash structure (u16 algorithm, u16 size, digest) sits at
    +0x60, the segment count at +0x84 and the segments (u16 reserved, u16 flags, u32 base, u32 size)
    from +0x85. Any other version raises BpmNotParsed; nothing is guessed. The caller recomputes the
    digest, which is the real test.
    """
    ents = [e for e in fit.entries if e.type == T_BOOT_POLICY]
    if not ents:
        raise BpmNotParsed('the FIT has no Boot Policy Manifest entry (type 0x0C)')
    e = ents[0]                       # Intel FIT specification 4.11: the ACM uses the first one only
    d = img.data
    off = img.off(e.addr)
    if off is None or e.size < 0x100 or off + e.size > img.size:
        raise BpmNotParsed('the FIT BPM entry (%s, size %s) does not describe a range inside the BIOS region'
                           % (hx(e.addr), hx(e.size)))
    end = off + e.size
    if d[off:off + 8] != b'__ACBP__':
        raise BpmNotParsed('no "__ACBP__" structure at region+%s, where the FIT BPM entry points' % hx(off))
    if d[off + 8] != 0x10:
        raise BpmNotParsed('BPM structure version %s; only 0x10 has been checked' % hx(d[off + 8]))
    ibbs = off + 0x10
    if d[ibbs:ibbs + 8] != b'__IBBS__' or d[ibbs + 8] != 0x10:
        raise BpmNotParsed('the IBB element is missing or is not structure version 0x10')
    if ibbs + 0x85 > end:
        raise BpmNotParsed('the IBB element runs past the end of the BPM')
    alg, dsz = struct.unpack_from('<HH', d, ibbs + 0x60)
    if alg != 0x000B or dsz != 32:
        raise BpmNotParsed('IBB hash algorithm id %s with size %d; only SHA-256 (0x0B, 32 bytes) is supported'
                           % (hx(alg), dsz))
    digest = bytes(d[ibbs + 0x64:ibbs + 0x84])
    n = d[ibbs + 0x84]
    if not 1 <= n <= 32 or ibbs + 0x85 + 12 * n > end:
        raise BpmNotParsed('IBB segment count %d does not fit inside the BPM' % n)
    segs = []
    for i in range(n):
        _res, flags, base, size = struct.unpack_from('<HHII', d, ibbs + 0x85 + 12 * i)
        so = img.off(base)
        if so is None or size == 0 or so + size > img.size:
            raise BpmNotParsed('IBB segment %d (%s, length %s) is not inside the BIOS region'
                               % (i, hx(base), hx(size)))
        segs.append((flags, base, size, so))
    return Bpm(off, e.size, ibbs, digest, segs)


def ibb_digest(img, bpm):
    """SHA-256 over every listed segment, in the listed order.

    The per-segment flags field is not interpreted. The stored digest is the oracle: if it is not
    reproduced the callers stop, so a wrong reading of the flags cannot pass quietly.
    """
    h = hashlib.sha256()
    for _flags, _base, size, so in bpm.segments:
        h.update(img.data[so:so + size])
    return h.digest()


def acm_extent(img, off):
    d = img.data
    if off is None or off + 28 > img.size or u16(d, off) != 2 or u32(d, off + 16) != 0x8086:
        return None
    size = u32(d, off + 24) * 4                 # ACM header: Size field, in dwords, at +0x18
    if size == 0 or size > (4 << 20) or off + size > img.size:
        return None
    return off + size


def boot_objects(img, fit):
    """Region ranges of the boot-chain objects the FIT names: ACM, BIOS startup modules, KM, BPM."""
    names = {T_ACM: 'Startup ACM', T_DIAG_ACM: 'Diagnostic ACM', T_BIOS_STARTUP: 'BIOS startup module',
             T_KEY_MANIFEST: 'Key Manifest', T_BOOT_POLICY: 'Boot Policy Manifest'}
    out = []
    for e in fit.entries:
        if e.type not in names:
            continue
        off = img.off(e.addr)
        if off is None:
            out.append(BootObj(names[e.type], e.idx, None, None, 'address %s is outside the BIOS region' % hx(e.addr)))
        elif e.type in (T_ACM, T_DIAG_ACM):
            end = acm_extent(img, off)
            out.append(BootObj(names[e.type], e.idx, off, end, None if end else 'no ACM header at the FIT address'))
        else:
            size = e.size * 16 if e.type == T_BIOS_STARTUP else e.size
            ok = 0 < size and off + size <= img.size
            out.append(BootObj(names[e.type], e.idx, off, off + size if ok else None,
                               None if ok else 'FIT size field %s does not fit the region' % hx(e.size)))
    return out


# --------------------------------------------------------------------------- byte ranges

def diff_runs(a, b, chunk=65536):
    """Exact changed-byte ranges [start, end) between two equal-length byte strings."""
    runs, start, n = [], None, len(a)
    for base in range(0, n, chunk):
        end = min(base + chunk, n)
        if a[base:end] == b[base:end]:
            if start is not None:
                runs.append((start, base))
                start = None
            continue
        ca, cb = a[base:end], b[base:end]
        for i in range(end - base):
            if ca[i] != cb[i]:
                if start is None:
                    start = base + i
            elif start is not None:
                runs.append((start, base + i))
                start = None
    if start is not None:
        runs.append((start, n))
    return runs


def coalesce(runs, gap):
    out = []
    for a, b in runs:
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def split_runs(runs, lo, hi):
    """(parts inside [lo, hi), parts outside it)."""
    inside, outside = [], []
    for a, b in runs:
        if a < lo:
            outside.append((a, min(b, lo)))
        if b > hi:
            outside.append((max(a, hi), b))
        ia, ib = max(a, lo), min(b, hi)
        if ia < ib:
            inside.append((ia, ib))
    return inside, outside


def run_bytes(runs):
    return sum(b - a for a, b in runs)


def overlap(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


# --------------------------------------------------------------------------- reporting

class Report(object):
    def __init__(self, echo=True):
        self.echo, self.lines, self.fails, self.warns = echo, [], [], []

    def _put(self, line):
        self.lines.append(line)
        if self.echo:
            print(line)

    def heading(self, text):
        self._put('')
        self._put('== %s ==' % text)

    def check(self, name, ok, detail=''):
        self._put('  [%s] %s%s' % ('PASS' if ok else 'FAIL', name, ('  -- ' + detail) if detail else ''))
        if not ok:
            self.fails.append(name)
        return ok

    def warn(self, text):
        self.warns.append(text)
        self._put('  [WARN] ' + text)

    def skip(self, name, why):
        self._put('  [SKIP] %s  -- %s' % (name, why))

    def info(self, text):
        self._put('  [info] ' + text)

    def say(self, text=''):
        self._put(text)


class Opts(object):
    def __init__(self, target=None, fallbacks=(), replace=None, window=None, payload_offset=None,
                 accept_no_bpm=False):
        self.target, self.fallbacks, self.replace = target, list(fallbacks), replace
        self.window, self.payload_offset, self.accept_no_bpm = window, payload_offset, accept_no_bpm


def parse_window(text):
    """'OFFSET:LENGTH', both hex, both relative to the BIOS region."""
    a, _, b = text.partition(':')
    return parse_hex(a), parse_hex(b)


class Ctx(object):
    pass


def slot_bytes(img, s):
    if s.off is None:
        return b''
    n = s.info['total'] if s.kind == 'ucode' else 48
    return bytes(img.data[s.off:s.off + n])


def slot_changed(c, a, b):
    if a.kind != b.kind or a.off != b.off:
        return True
    if a.off is None:
        return False
    n = max(len(slot_bytes(c.io, a)), len(slot_bytes(c.im, b)))
    return c.io.data[a.off:a.off + n] != c.im.data[b.off:b.off + n]


# --------------------------------------------------------------------------- the gates

def step_geometry(c):
    """Image geometry"""
    rep = c.rep
    same = len(c.orig_raw) == len(c.mod_raw)
    rep.check('images are the same size', same, '%s vs %s bytes' % (hx(len(c.orig_raw)), hx(len(c.mod_raw))))
    if not same:
        rep.info('every other check compares offsets, so none of them would mean anything; stopping')
        return False
    c.io, c.im = Image(c.orig_raw), Image(c.mod_raw)
    rep.check('BIOS region found at the same place in both images',
              (c.io.kind, c.io.base, c.io.size) == (c.im.kind, c.im.base, c.im.size), c.io.describe())
    return True


def step_fit(c):
    """Firmware Interface Table"""
    rep = c.rep
    c.fo = parse_fit(c.io)
    rep.check('FIT found through the pointer at 4 GiB - 0x40 (original)', True,
              'region+%s, %d entries' % (hx(c.fo.off), len(c.fo.entries)))
    try:
        c.fm = parse_fit(c.im)
    except FwError as e:
        rep.check('FIT found through the pointer at 4 GiB - 0x40 (modified)', False, str(e))
        return False
    rep.check('FIT found through the pointer at 4 GiB - 0x40 (modified)', True,
              'region+%s, %d entries' % (hx(c.fm.off), len(c.fm.entries)))
    c.fit_same = c.fo.raw == c.fm.raw and c.fo.ptr == c.fm.ptr
    detail = 'whole table and pointer unchanged'
    if not c.fit_same:
        diff = [i for i in range(min(len(c.fo.entries), len(c.fm.entries)))
                if c.fo.entries[i].raw != c.fm.entries[i].raw]
        detail = ('this tool set only supports a same-size swap that leaves the FIT alone; entries differing: %s, '
                  'entry counts %d vs %d' % (diff or 'none', len(c.fo.entries), len(c.fm.entries)))
    rep.check('FIT byte-identical to the original', c.fit_same, detail)
    loc = lambda f: sorted(e.raw for e in f.entries if e.type in (T_KEY_MANIFEST, T_BOOT_POLICY))
    n_km = len([e for e in c.fo.entries if e.type == T_KEY_MANIFEST])
    n_bpm = len([e for e in c.fo.entries if e.type == T_BOOT_POLICY])
    rep.check('Key Manifest (0x0B) and Boot Policy Manifest (0x0C) FIT entries bit-identical',
              loc(c.fo) == loc(c.fm), 'original has %d KM and %d BPM entries' % (n_km, n_bpm))
    if c.fm.entries[0].cv:
        rep.check('FIT checksum (header C_V bit is set)', sum(c.fm.raw) & 0xFF == 0)
    return True


def step_window(c):
    """Microcode firmware volume"""
    rep, o = c.rep, c.opts
    c.so = fit_ucode_slots(c.io, c.fo)
    c.sm = fit_ucode_slots(c.im, c.fm)
    c.fv = None
    if o.window:
        start, length = o.window
        ok = 0 <= start and 0 < length and start + length <= c.io.size
        rep.check('explicit microcode window lies inside the BIOS region', ok,
                  'region+%s, length %s' % (hx(start), hx(length)))
        if ok:
            c.fv = FV(start, length, 0, 0xFF)
    else:
        try:
            c.fv = derive_ucode_fv(c.io, c.so)
            rep.check('microcode firmware volume identified from the FIT', True,
                      'region+%s, length %s, an EFI volume that holds all %d microcode entries'
                      % (hx(c.fv.start), hx(c.fv.length), len(c.so)))
        except FwError as e:
            rep.check('microcode firmware volume identified from the FIT', False, str(e))
    if c.fv is None:
        return True
    end = c.fv.start + c.fv.length
    rep.check('microcode FV is 4 KiB aligned (flash sector size)',
              c.fv.start % SECTOR == 0 and c.fv.length % SECTOR == 0,
              '%s-%s' % (hx(c.fv.start), hx(end - 1)))
    stray = [s for s in c.so if s.kind == 'ucode' and s.off + s.info['total'] > end]
    rep.check('every FIT microcode slot lies completely inside that volume', not stray)
    return True


def step_diff(c):
    """Changed bytes"""
    rep = c.rep
    c.runs = diff_runs(c.orig_raw, c.mod_raw)
    lo, hi = c.io.base, c.io.base + c.io.size
    inside, c.out_img = split_runs(c.runs, lo, hi)
    c.rel = [(a - lo, b - lo) for a, b in inside]
    total = run_bytes(c.runs)
    if not rep.check('at least one byte changed', total > 0, '%d bytes in %d ranges' % (total, len(c.runs))):
        rep.info('the two files are identical, so there is nothing to flash')
        return False
    if c.fv is None:
        rep.check('zero bytes changed outside the microcode FV', False, 'the volume is unknown, so this cannot be judged')
    else:
        _inside, outside = split_runs(c.rel, c.fv.start, c.fv.start + c.fv.length)
        n_out = run_bytes(outside) + run_bytes(c.out_img)
        if n_out:
            first = (outside[0][0] if outside else None)
            where = ('first at region+%s' % hx(first)) if first is not None else \
                    ('first at image offset %s, outside the BIOS region' % hx(c.out_img[0][0]))
            detail = '%d bytes changed outside region+%s; %s' % (n_out, span(c.fv.start, c.fv.start + c.fv.length), where)
        else:
            detail = 'all %d changed bytes are inside region+%s' % (total, span(c.fv.start, c.fv.start + c.fv.length))
        rep.check('zero bytes changed outside the microcode FV', n_out == 0, detail)
    spans = coalesce(c.rel, 256)
    if spans:
        rep.info('changed spans in the BIOS region (gaps of up to 256 unchanged bytes merged): %d' % len(spans))
        for a, b in spans[:6]:
            rep.info('  region+%s  (%s bytes)' % (span(a, b), hx(b - a)))
        if len(spans) > 6:
            rep.info('  ... %d more' % (len(spans) - 6))
    return True


def step_swap(c):
    """Swap contract"""
    rep = c.rep
    c.changed_slot = None
    if not c.fit_same or len(c.so) != len(c.sm):
        rep.skip('exactly one FIT microcode slot changed', 'needs an identical FIT')
        return True
    changed = [(a, b) for a, b in zip(c.so, c.sm) if slot_changed(c, a, b)]
    ok = len(changed) == 1
    if ok:
        a, b = changed[0]
        ok = a.kind == 'ucode' and b.kind == 'ucode' and a.off == b.off and a.info['total'] == b.info['total']
    detail = '%d slot(s) changed' % len(changed)
    if ok:
        c.changed_slot = changed[0]
        a, b = changed[0]
        detail = 'FIT entry %d, region+%s, %s bytes' % (a.idx, hx(a.off), hx(a.info['total']))
    rep.check('exactly one FIT microcode slot changed, at the same offset and with the same size', ok, detail)
    if not ok:
        return True
    old, new = c.changed_slot
    rep.info('slot: CPUID %s rev %s  ->  CPUID %s rev %s' % (hx(old.info['cpuid']), hx(old.info['rev']),
                                                            hx(new.info['cpuid']), hx(new.info['rev'])))
    lo, hi = old.off, old.off + old.info['total']
    inside = all(lo <= a and b <= hi for a, b in c.rel) and not c.out_img
    rep.check('every changed byte lies inside that slot', inside, 'slot is region+%s' % span(lo, hi))
    if c.opts.window:
        rep.skip('slot sits in the data area of one FFS file without a data checksum',
                 'explicit window given, volume structure not parsed')
    elif c.fv is not None:
        try:
            f = ffs_owner(c.io.data, c.fv, lo, hi)
        except FwError as e:
            rep.check('slot sits in the data area of one FFS file without a data checksum', False, str(e))
            return True
        good = f is not None and not (f.attr & FFS_ATTR_CHECKSUM)
        if f is None:
            detail = 'no single FFS file contains the slot'
        else:
            detail = 'file %s, attributes %s, data checksum attribute %s' % (
                guid_text(f.guid), hx(f.attr), 'SET (this tool does not recompute it)' if f.attr & FFS_ATTR_CHECKSUM else 'clear')
        rep.check('slot sits in the data area of one FFS file without a data checksum', good, detail)
    return True


def step_ucode(c):
    """Microcode referenced by the FIT (modified image)"""
    rep = c.rep
    for s in c.sm:
        if s.kind == 'empty':
            rep.info('FIT entry %d: empty slot at region+%s (first dword 0xFFFFFFFF, allowed by the FIT specification)'
                     % (s.idx, hx(s.off)))
        elif s.kind == 'bad':
            rep.check('FIT entry %d: microcode header valid' % s.idx, False, s.info['why'])
        else:
            i = s.info
            detail = 'rev %s (%s), platform mask %s, %s bytes @ region+%s' % (
                hx(i['rev']), bcd_date(i['date']), hx(i['pf']), hx(i['total']), hx(s.off))
            if i['ext_bad']:
                detail += '; ' + i['ext_bad']
            rep.check('microcode CPUID %s: Intel checksum valid' % hx(i['cpuid']), i['ok'], detail)
            if i['ext_warn']:
                rep.warn('CPUID %s: %s' % (hx(i['cpuid']), i['ext_warn']))
    rep.check('all FIT microcode addresses are 16-byte aligned (FIT specification 4.3)',
              all(s.aligned for s in c.sm))
    return True


def step_cpuids(c):
    """CPUID checks"""
    rep, o = c.rep, c.opts
    if not o.fallbacks:
        rep.check('fallback microcode still present', False,
                  'no --fallback-cpuid given: the tool cannot know which CPU you want to keep bootable')
    for f in o.fallbacks:
        a = [s for s in c.so if s.kind == 'ucode' and s.info['cpuid'] == f]
        b = [s for s in c.sm if s.kind == 'ucode' and s.info['cpuid'] == f]
        if not a:
            ok, detail = False, 'CPUID not in the original FIT; check the value'
        elif not b:
            ok, detail = False, 'missing from the modified image'
        else:
            ok = all(any(ucode_blob(c.io, x) == ucode_blob(c.im, y) for y in b) for x in a) and all(y.info['ok'] for y in b)
            detail = 'byte-identical to the original, checksum valid' if ok else 'bytes differ from the original or checksum bad'
        rep.check('fallback CPUID %s still present, unchanged and valid' % hx(f), ok, detail)
    if o.target is None:
        rep.check('target microcode present', False, 'no --target-cpuid given')
    else:
        m = [s for s in c.sm if s.kind == 'ucode' and s.info['cpuid'] == o.target]
        ok = bool(m) and all(s.info['ok'] for s in m)
        detail = ('rev %s at region+%s' % (hx(m[0].info['rev']), hx(m[0].off))) if m else 'no FIT microcode entry has this CPUID'
        rep.check('target CPUID %s present with a valid checksum' % hx(o.target), ok, detail)
        if any(s.kind == 'ucode' and s.info['cpuid'] == o.target for s in c.so):
            rep.warn('the original already contains CPUID %s, so this is a replacement of existing '
                     'microcode, not an enablement' % hx(o.target))
        if c.changed_slot is not None:
            rep.check('the changed slot now holds the target CPUID', c.changed_slot[1].info['cpuid'] == o.target,
                      'slot now holds %s' % hx(c.changed_slot[1].info['cpuid']))
    if o.replace is not None:
        if c.changed_slot is None:
            rep.skip('replaced CPUID matches --replace-cpuid', 'needs exactly one changed slot (see the swap contract)')
        else:
            got = c.changed_slot[0].info['cpuid']
            rep.check('replaced CPUID matches --replace-cpuid', got == o.replace,
                      'the overwritten slot held %s, you named %s' % (hx(got), hx(o.replace)))
    cp_o = set(s.info['cpuid'] for s in c.so if s.kind == 'ucode')
    cp_m = set(s.info['cpuid'] for s in c.sm if s.kind == 'ucode')
    rep.info('CPUIDs removed: %s; added: %s; unchanged: %d' % (
        ', '.join(hx(x) for x in sorted(cp_o - cp_m)) or 'none',
        ', '.join(hx(x) for x in sorted(cp_m - cp_o)) or 'none', len(cp_o & cp_m)))
    return True


def step_bootguard(c):
    """Boot Guard chain"""
    rep = c.rep
    c.objs = boot_objects(c.io, c.fo)
    seen = set()
    for ob in c.objs:
        if ob.problem:
            rep.check('%s (FIT entry %d): extent can be determined' % (ob.name, ob.idx), False, ob.problem)
            continue
        seen.add(ob.name)
        same = c.io.data[ob.start:ob.end] == c.im.data[ob.start:ob.end]
        rep.check('%s (FIT entry %d) byte-identical' % (ob.name, ob.idx), same, 'region+%s' % span(ob.start, ob.end))
    for need in ('Startup ACM', 'Key Manifest', 'Boot Policy Manifest'):
        if need not in seen:
            rep.warn('the FIT has no usable %s entry, so that object cannot be compared' % need)
    if c.fv is not None:
        hits = ['%s (region+%s)' % (ob.name, span(ob.start, ob.end)) for ob in c.objs
                if ob.end is not None and overlap(c.fv.start, c.fv.start + c.fv.length, ob.start, ob.end)]
        rep.check('microcode FV does not overlap the ACM, Key Manifest, Boot Policy Manifest or startup modules',
                  not hits, ', '.join(hits))
    return True


def step_ibb(c):
    """IBB digest (Boot Guard)"""
    rep, o = c.rep, c.opts
    c.bpm = None
    try:
        c.bpm = parse_bpm(c.io, c.fo)
    except BpmNotParsed as e:
        why = str(e)
    if c.bpm is not None:
        b = c.bpm
        flags = sorted(set(s[0] for s in b.segments))
        rep.check('Boot Policy Manifest parsed from the image', True,
                  'region+%s, %d IBB segment(s), %s bytes hashed, SHA-256' % (
                      hx(b.off), len(b.segments), hx(sum(s[2] for s in b.segments))))
        d_o, d_m = ibb_digest(c.io, b), ibb_digest(c.im, b)
        note = '' if flags == [0] else ' (segment flags seen: %s; this parser does not interpret them)' % \
            ', '.join(hx(f) for f in flags)
        rep.check('IBB digest recomputed from the ORIGINAL equals the digest stored in its BPM', d_o == b.digest,
                  ('recomputed %s... stored %s...%s' % (d_o.hex()[:8], b.digest.hex()[:8], note)) if d_o != b.digest else 'match')
        rep.check('IBB digest UNCHANGED in the modified image', d_m == d_o,
                  ('original %s... modified %s...' % (d_o.hex()[:8], d_m.hex()[:8])) if d_m != d_o else 'match')
        rep.check('modified image still matches the digest stored in the BPM', d_m == b.digest)
        if c.fv is not None:
            hits = [span(s[3], s[3] + s[2]) for s in b.segments
                    if overlap(c.fv.start, c.fv.start + c.fv.length, s[3], s[3] + s[2])]
            rep.check('microcode FV does not overlap any IBB segment', not hits,
                      'overlaps region+%s' % ', '.join(hits) if hits else '')
        touched = [span(s[3], s[3] + s[2]) for s in b.segments
                   if any(overlap(a, z, s[3], s[3] + s[2]) for a, z in c.rel)]
        rep.check('no changed byte lies inside an IBB segment', not touched,
                  'touched: region+%s' % ', '.join(touched) if touched else '')
    else:
        rep.warn('Boot Policy Manifest not usable: %s' % why)
        rep.warn('the IBB digest cannot be checked. The only evidence left is that no byte outside the microcode '
                 'FV changed. That does NOT prove the FV is outside the IBB; if your platform hashes the microcode '
                 'volume, the board will not start after the flash.')
        for name in ('IBB digest of the original equals the digest in its BPM', 'IBB digest unchanged',
                     'microcode FV does not overlap any IBB segment'):
            rep.skip(name, 'needs a parsed BPM')
        rep.check('flash anyway without the IBB digest check (--accept-no-bpm-check)', o.accept_no_bpm,
                  'accepted by the user' if o.accept_no_bpm else 'not accepted; read the warning above, then decide')
    return True


def step_payload(c):
    """Payload file"""
    rep, p = c.rep, c.payload
    if p is None:
        return True
    if c.fv is None:
        rep.check('payload can be placed', False, 'the microcode FV is unknown')
        return True
    fv_end = c.fv.start + c.fv.length
    if len(p) == c.fv.length:
        off = c.fv.start
    elif c.opts.payload_offset is not None:
        off = c.opts.payload_offset
    else:
        rep.check('payload is as long as the microcode FV', False,
                  'payload is %s bytes, the FV is %s; pass --payload-offset only if you mean a partial write'
                  % (hx(len(p)), hx(c.fv.length)))
        return True
    end = off + len(p)
    rep.check('payload lies inside the microcode FV', c.fv.start <= off and end <= fv_end,
              'payload region+%s, FV region+%s' % (span(off, end), span(c.fv.start, fv_end)))
    rep.check('payload offset and length are 4 KiB aligned', off % SECTOR == 0 and len(p) % SECTOR == 0)
    rep.check('payload identical to the modified image at that offset', end <= c.im.size and p == c.im.data[off:end])
    rep.check('payload covers every changed byte', all(off <= a and b <= end for a, b in c.rel) and not c.out_img)
    guarded = [(ob.name, ob.start, ob.end) for ob in c.objs if ob.end is not None]
    if c.bpm is not None:
        guarded += [('IBB segment', s[3], s[3] + s[2]) for s in c.bpm.segments]
    hits = ['%s (region+%s)' % (n, span(a, z)) for n, a, z in guarded if overlap(off, end, a, z)]
    rep.check('payload does not overlap Boot Guard objects or IBB segments', not hits, ', '.join(hits))
    return True


STEPS = (step_geometry, step_fit, step_window, step_diff, step_swap, step_ucode, step_cpuids,
         step_bootguard, step_ibb, step_payload)


def evaluate(orig_raw, mod_raw, payload, opts, rep):
    """Run every gate. Returns (all_passed, context); the context carries what the gates derived."""
    c = Ctx()
    c.orig_raw, c.mod_raw, c.payload, c.opts, c.rep = orig_raw, mod_raw, payload, opts, rep
    for step in STEPS:
        rep.heading(step.__doc__.strip())
        try:
            if step(c) is False:
                break
        except FwError as e:
            rep.check(step.__doc__.strip() + ': could be evaluated', False, str(e))
            break
    return not rep.fails, c


def flash_window_text(c):
    """The write window the microcode FV defines, in region terms and (if known) SPI terms."""
    if c.fv is None:
        return None
    lines = ['microcode FV = write window: region+%s, length %s' % (hx(c.fv.start), hx(c.fv.length))]
    if c.io.kind == 'full-spi':
        lines.append('this is a full SPI image: BIOS region starts at %s, so the absolute SPI address of the window is %s'
                     % (hx(c.io.base), hx(c.io.base + c.fv.start)))
    else:
        lines.append('this file is a BIOS-region image: the absolute SPI address is the BIOS region base plus %s; the '
                     'base is not in this file, read it from your flash tool or the flash descriptor' % hx(c.fv.start))
    return lines


# --------------------------------------------------------------------------- synthetic images (self-test only)
# Everything below is generated from a seeded random stream; no vendor firmware is embedded anywhere.
# The geometry copies the reference build (Dell OptiPlex 7060 SFF, BIOS 1.32.0), whose layout was read
# from a dump taken from that machine: 16 MiB BIOS region, microcode volume at region+0xD20000 (length
# 0xF0000) holding two microcode updates, FIT at +0xD20100 with six entries, Boot Policy Manifest at
# +0xFC0080, Key Manifest at +0xFC1100, startup ACM at +0xFD0000, and four IBB segments. Only the
# structure is reproduced; every byte of content is random.

SYN_R = 0x1000000
SYN_FV, SYN_FVLEN, SYN_FIT = 0xD20000, 0xF0000, 0xD20100
SYN_ACM, SYN_ACM_LEN, SYN_KM, SYN_KM_LEN, SYN_BPM, SYN_BPM_LEN = 0xFD0000, 0x8000, 0xFC1100, 0x241, 0xFC0080, 0x2DF
SYN_IBB = ((0xF00000, 0xC0080), (0xFC1080, 0x80), (0xFC2100, 0xDF00), (0xFD8000, 0x28000))
SYN_UCODES = ((0x906EA, 0xF8, 0x22, 0x19C00, 0x02012024), (0x906EB, 0xF6, 0x02, 0x1A000, 0x02012024))
FFS2_GUID = guid_bytes('8C8CE578-8A3D-4F1C-9935-896185C32DD3')       # EFI_FIRMWARE_FILE_SYSTEM2_GUID


def syn_bytes(rng, n):
    return rng.getrandbits(8 * n).to_bytes(n, 'little') if n else b''


def syn_ucode(cpuid, rev, pf, total, date, rng):
    b = bytearray(total)
    struct.pack_into('<9I', b, 0, 1, rev, date, cpuid, 0, 1, pf, total - 48, total)
    b[48:] = syn_bytes(rng, total - 48)
    s = sum(struct.unpack('<%dI' % (total // 4), bytes(b))) & MASK32
    struct.pack_into('<I', b, 16, (-s) & MASK32)
    return bytes(b)


def syn_ffs(guid, ftype, attr, data):
    h = bytearray(24)
    h[0:16] = guid
    h[18], h[19] = ftype, attr
    h[20:23] = (24 + len(data)).to_bytes(3, 'little')
    h[16] = (-sum(h)) & 0xFF
    h[17] = ((-sum(data)) & 0xFF) if attr & FFS_ATTR_CHECKSUM else 0xAA
    h[23] = 0xF8
    return bytes(h) + bytes(data)


def syn_fv(length, files):
    h = bytearray(0x48)
    h[16:32] = FFS2_GUID
    struct.pack_into('<Q', h, 32, length)
    h[40:44] = b'_FVH'
    struct.pack_into('<I', h, 44, 0x000CFEFF)
    struct.pack_into('<H', h, 48, 0x48)
    h[55] = 2
    struct.pack_into('<II', h, 56, length // SECTOR, SECTOR)
    struct.pack_into('<H', h, 50, (-sum(struct.unpack('<36H', bytes(h)))) & 0xFFFF)
    out = bytearray(b'\xFF' * length)
    out[0:0x48] = h
    pos = 0x48
    for f in files:
        pos = (pos + 7) & ~7
        out[pos:pos + len(f)] = f
        pos += len(f)
    return out


def syn_fit_entry(addr, size, typ):
    e = bytearray(16)
    struct.pack_into('<Q', e, 0, addr)
    e[8:11] = size.to_bytes(3, 'little')
    struct.pack_into('<H', e, 12, 0x0100)
    e[14] = typ
    return bytes(e)


def syn_region(seed=1, ucodes=SYN_UCODES, with_bpm=True, ffs_attr=0x0C):
    """A 16 MiB BIOS region with the reference geometry. Returns (bytearray, layout dict)."""
    rng = random.Random(seed)
    img = bytearray(b'\xFF' * SYN_R)
    img[0x100000:0x180000] = syn_bytes(rng, 0x80000)          # BIOS code outside the microcode volume and the IBB
    img[0xF00000:SYN_R] = syn_bytes(rng, SYN_R - 0xF00000)    # the IBB area
    data, slots, pos = bytearray(), [], 0x400
    for spec in ucodes:
        if slots:
            pos = (pos + SECTOR - 1) & ~(SECTOR - 1)
        data += b'\xFF' * (pos - 0x400 - len(data))
        blob = syn_ucode(spec[0], spec[1], spec[2], spec[3], spec[4], rng)
        data += blob
        slots.append((spec[0], SYN_FV + pos, len(blob)))
        pos += len(blob)
    base = TOP - SYN_R
    ents = [syn_fit_entry(base + off, 0, T_UCODE) for _c, off, _t in slots]
    ents.append(syn_fit_entry(base + SYN_ACM, 0, T_ACM))
    ents.append(syn_fit_entry(base + SYN_KM, SYN_KM_LEN, T_KEY_MANIFEST))
    if with_bpm:
        ents.append(syn_fit_entry(base + SYN_BPM, SYN_BPM_LEN, T_BOOT_POLICY))
    hdr = bytearray(16)
    hdr[0:8] = FIT_SIG
    hdr[8:11] = (len(ents) + 1).to_bytes(3, 'little')
    struct.pack_into('<H', hdr, 12, 0x0100)
    fit_bytes = bytes(hdr) + b''.join(ents)
    fit_file = syn_ffs(guid_bytes('33221100-5544-7766-8899-AABBCCDDEEFF'), 1, 0x10,
                       fit_bytes + b'\xFF' * (0x180 - len(fit_bytes)))
    files = [syn_ffs(b'\xFF' * 16, 0xF0, 0, b'\xFF' * (0xA0 - 24)),
             fit_file,
             syn_ffs(b'\xFF' * 16, 0xF0, 0, b'\xFF' * (0x168 - 24)),
             syn_ffs(guid_bytes('FFEEDDCC-BBAA-9988-7766-554433221100'), 1, ffs_attr, bytes(data))]
    img[SYN_FV:SYN_FV + SYN_FVLEN] = syn_fv(SYN_FVLEN, files)
    struct.pack_into('<Q', img, SYN_R - 0x40, base + SYN_FIT)
    acm = bytearray(syn_bytes(rng, SYN_ACM_LEN))
    struct.pack_into('<HHIIHHIII', acm, 0, 2, 3, 0xA1, 0, 0, 0, 0x8086, 0x20170209, SYN_ACM_LEN // 4)
    img[SYN_ACM:SYN_ACM + SYN_ACM_LEN] = acm
    img[SYN_KM:SYN_KM + SYN_KM_LEN] = b'__KEYM__\x10' + syn_bytes(rng, SYN_KM_LEN - 9)
    if with_bpm:
        h = hashlib.sha256()
        for b, n in SYN_IBB:
            h.update(bytes(img[b:b + n]))
        ibbs = bytearray(0x85 + 12 * len(SYN_IBB))
        ibbs[0:8] = b'__IBBS__'
        ibbs[8] = 0x10
        struct.pack_into('<HH', ibbs, 0x60, 0x000B, 32)
        ibbs[0x64:0x84] = h.digest()
        ibbs[0x84] = len(SYN_IBB)
        for i, (b, n) in enumerate(SYN_IBB):
            struct.pack_into('<HHII', ibbs, 0x85 + 12 * i, 0, 0, base + b, n)
        bpm = b'__ACBP__' + bytes([0x10, 0x01, 0x10, 0, 0, 0, 0x80, 0]) + bytes(ibbs)
        bpm += b'__PMSG__' + syn_bytes(rng, SYN_BPM_LEN - len(bpm) - 8)
        img[SYN_BPM:SYN_BPM + SYN_BPM_LEN] = bpm
    return img, {'slots': slots}


def syn_spi(region, seed=2):
    """Wrap a BIOS region into a full SPI image: 4 KiB descriptor, a filler region, then the BIOS region last."""
    rng = random.Random(seed)
    n = len(region)
    out = bytearray(b'\xFF' * (2 * n))
    out[0x1000:0x20000] = syn_bytes(rng, 0x1F000)
    struct.pack_into('<I', out, 0x10, FLVALSIG)
    struct.pack_into('<I', out, 0x14, 0x04 << 16)                      # FRBA = 0x40
    struct.pack_into('<5I', out, 0x40, 0, ((2 * n >> 12) - 1) << 16 | (n >> 12), 0x0FFF0003, 0x00020001, 0x7FFF)
    out[n:] = region
    return out


def syn_replace(raw, base, off, blob):
    out = bytearray(raw)
    out[base + off:base + off + len(blob)] = blob
    return out


# ======================================================================================
# END OF SHARED CORE. Everything below belongs to build_microcode_swap.py only.
# ======================================================================================

import argparse


class Refuse(Exception):
    """A preflight or post-build gate failed; nothing is written."""


class Params(object):
    def __init__(self, target_cpuid, replace_cpuid, fallbacks, donor_kind='image', platform_id=None,
                 fv_base=None, fv_len=None, fit_offset=None, accept_no_bpm=False):
        self.target_cpuid, self.replace_cpuid, self.fallbacks = target_cpuid, replace_cpuid, list(fallbacks)
        self.donor_kind, self.platform_id = donor_kind, platform_id
        self.fv_base, self.fv_len, self.fit_offset, self.accept_no_bpm = fv_base, fv_len, fit_offset, accept_no_bpm


class Plan(object):
    pass


def need(rep, name, ok, fail='', info=''):
    """A preflight gate: print PASS (with `info`) or FAIL (with `fail`) and stop at the first FAIL."""
    rep.check(name, ok, info if ok else fail)
    if not ok:
        raise Refuse('%s%s' % (name, (' -- ' + fail) if fail else ''))


def scan_ucode(data):
    """Every valid microcode update in `data` at 16-byte alignment, referenced by the FIT or not."""
    out, pat, hits = [], b'\x01\x00\x00\x00', 0
    p = data.find(pat)
    while p >= 0:
        hits += 1
        if hits > 2000000:
            raise Refuse('the raw microcode scan gave up after 2 million candidate headers; the image is damaged or not firmware')
        if p % 16 == 0 and data[p + 20:p + 24] == pat:
            kind, info = parse_ucode(data, p)
            if kind == 'ucode' and info['ok']:
                out.append((p, info))
        p = data.find(pat, p + 1)
    return out


def donor_updates(donor_raw, p, rep):
    """All (info, blob) updates the donor offers."""
    found = []
    if p.donor_kind == 'image':
        try:
            di = Image(donor_raw)
            dfit = parse_fit(di)
        except FwError as e:
            raise Refuse('donor image: %s' % e)
        rep.info('donor: %s' % di.describe())
        for s in fit_ucode_slots(di, dfit):
            if s.kind == 'ucode':
                found.append((s.info, ucode_blob(di, s)))
    else:
        pos = 0
        while pos < len(donor_raw):
            kind, info = parse_ucode(donor_raw, pos)
            if kind != 'ucode':
                if set(donor_raw[pos:]) <= set([0xFF]):          # erased padding after the last update
                    break
                raise Refuse('donor file: the bytes at offset %s are not a microcode update (%s)'
                             % (hx(pos), info.get('why', 'empty')))
            found.append((info, bytes(donor_raw[pos:pos + info['total']])))
            pos += info['total']
        rep.info('donor: bare microcode file holding %d update(s)' % len(found))
    return found


def plan_swap(tgt_raw, donor_raw, p, rep):
    """Every preflight gate, then the swap in memory and the full verifier gate set on the result."""
    rep.heading('Target image')
    try:
        tgt = Image(tgt_raw)
        fit = parse_fit(tgt)
    except FwError as e:
        raise Refuse(str(e))
    rep.info('target: %s' % tgt.describe())
    need(rep, 'FIT found through the pointer at 4 GiB - 0x40', True, info='region+%s, %d entries' % (hx(fit.off), len(fit.entries)))
    if p.fit_offset is not None:
        need(rep, '--fit-offset agrees with the FIT pointer', p.fit_offset == fit.off,
             'the pointer gives region+%s, you gave %s' % (hx(fit.off), hx(p.fit_offset)))
    slots = fit_ucode_slots(tgt, fit)
    need(rep, 'the FIT lists microcode', bool(slots))
    for s in slots:
        rep.info('FIT entry %d: %s' % (s.idx, slot_text(s)))
    broken = [s.idx for s in slots if s.kind == 'bad' or (s.kind == 'ucode' and not s.info['ok']) or not s.aligned]
    need(rep, 'every FIT microcode entry is readable, 16-byte aligned and passes its checksum', not broken,
         'FIT entries %s are not' % broken)
    need(rep, 'at least one --fallback-cpuid is given', bool(p.fallbacks),
         'name the CPU you are keeping, normally the one installed now')
    for f in p.fallbacks:
        need(rep, 'fallback CPUID %s is in the FIT with a valid checksum' % hx(f),
             any(s.kind == 'ucode' and s.info['cpuid'] == f for s in slots))
    need(rep, '--replace-cpuid is not one of the fallbacks', p.replace_cpuid not in p.fallbacks)
    need(rep, '--replace-cpuid is not the target', p.replace_cpuid != p.target_cpuid)
    need(rep, 'target CPUID %s is not already in the FIT' % hx(p.target_cpuid),
         not any(s.kind == 'ucode' and s.info['cpuid'] == p.target_cpuid for s in slots),
         'the FIT already carries microcode for it, so there is nothing to add; if the board still refuses the CPU, '
         'missing microcode is not the cause')
    scanned = scan_ucode(tgt.data)
    stray = [o for o, i in scanned if i['cpuid'] == p.target_cpuid]
    need(rep, 'target CPUID is nowhere in the image (raw scan, copies the FIT does not reference included)', not stray,
         'found at region+%s' % ', '.join(hx(o) for o in stray))
    referenced = set(s.off for s in slots)
    copies = [o for o, i in scanned if i['cpuid'] == p.replace_cpuid and o not in referenced]
    if copies:
        rep.warn('microcode for CPUID %s also exists at region+%s, not referenced by the FIT; that copy stays '
                 'as it is' % (hx(p.replace_cpuid), ', '.join(hx(o) for o in copies)))

    rep.heading('Donor microcode')
    found = donor_updates(donor_raw, p, rep)
    mine = [(i, b) for i, b in found if i['cpuid'] == p.target_cpuid]
    need(rep, 'donor offers microcode for CPUID %s' % hx(p.target_cpuid), bool(mine),
         'it holds CPUIDs: %s' % (', '.join(sorted(set(hx(i['cpuid']) for i, _ in found))) or 'none'),
         info='%d update(s)' % len(mine))
    if p.platform_id is not None:
        mine = [(i, b) for i, b in mine if i['pf'] & (1 << p.platform_id)]
        need(rep, 'donor offers an update whose platform mask includes platform id %d' % p.platform_id, bool(mine))
    best = max(rev_signed(i['rev']) for i, _ in mine)
    for i, _b in mine:
        if rev_signed(i['rev']) < best:
            rep.info('older donor revision %s ignored' % hx(i['rev']))
    top = [(i, b) for i, b in mine if rev_signed(i['rev']) == best]
    need(rep, 'one unambiguous donor update at the highest revision', len(set(b for _i, b in top)) == 1,
         'several different updates share the highest revision (platform masks %s); choose with --platform-id'
         % ', '.join(sorted(set(hx(i['pf']) for i, _ in top))), info='revision %s' % hx(top[0][0]['rev']))
    dinfo, dblob = top[0]
    need(rep, 'donor update passes Intel checksum', dinfo['ok'],
         dinfo['ext_bad'] or 'the sum of its dwords is not zero')
    ids = [n for n in range(8) if dinfo['pf'] & (1 << n)]
    rep.info('donor update: CPUID %s rev %s (%s), %s bytes, platform mask %s = platform id(s) %s'
             % (hx(dinfo['cpuid']), hx(dinfo['rev']), bcd_date(dinfo['date']), hx(dinfo['total']), hx(dinfo['pf']),
                ', '.join(str(n) for n in ids) or 'none'))
    if p.platform_id is None:
        rep.warn('platform id not asserted. Pass --platform-id N (IA32_PLATFORM_ID, MSR 0x17 bits 52:50, of the CPU '
                 'you will install) to make the tool check the donor mask against it.')
    if dinfo['ext_warn']:
        rep.warn(dinfo['ext_warn'])

    rep.heading('Slot to overwrite')
    same_size = [s for s in slots if s.kind == 'ucode' and s.info['total'] == dinfo['total']
                 and s.info['cpuid'] not in p.fallbacks and s.info['cpuid'] != p.target_cpuid]
    rep.info('slots with exactly the donor size (%s bytes) that are not fallbacks: %s'
             % (hx(dinfo['total']), ', '.join('CPUID %s @ region+%s' % (hx(s.info['cpuid']), hx(s.off)) for s in same_size) or 'none'))
    named = [s for s in slots if s.kind == 'ucode' and s.info['cpuid'] == p.replace_cpuid]
    need(rep, '--replace-cpuid %s names a microcode slot in the FIT' % hx(p.replace_cpuid), bool(named))
    chosen = [s for s in named if s in same_size]
    need(rep, 'that slot has exactly the size of the donor update', bool(chosen),
         'slot is %s bytes, donor update is %s bytes; this tool never resizes or moves anything'
         % (hx(named[0].info['total']), hx(dinfo['total'])), info='both %s bytes' % hx(dinfo['total']))
    need(rep, 'exactly one slot holds that CPUID', len(chosen) == 1,
         '%d slots do; this tool will not guess between them' % len(chosen))
    slot = chosen[0]
    need(rep, 'the slot is referenced by exactly one FIT entry', len([e for e in fit.entries if e.type == T_UCODE and e.addr == slot.addr]) == 1)

    rep.heading('Layout')
    window = None
    try:
        fv = derive_ucode_fv(tgt, slots)
        derived = True
    except FwError as e:
        derived = False
        need(rep, 'microcode firmware volume found', p.fv_base is not None and p.fv_len is not None,
             '%s. If this board keeps microcode in a raw region, pass --fv-base and --fv-len (hex, relative to the BIOS region).' % e)
        fv = FV(p.fv_base, p.fv_len, 0, 0xFF)
        window = (p.fv_base, p.fv_len)
        rep.warn('using the write window you gave; the FFS file checks cannot run without an EFI volume')
    if derived:
        rep.check('microcode firmware volume found', True, 'region+%s, length %s' % (hx(fv.start), hx(fv.length)))
        if p.fv_base is not None:
            need(rep, '--fv-base agrees with the volume found', p.fv_base == fv.start, 'found %s, you gave %s' % (hx(fv.start), hx(p.fv_base)))
        if p.fv_len is not None:
            need(rep, '--fv-len agrees with the volume found', p.fv_len == fv.length, 'found %s, you gave %s' % (hx(fv.length), hx(p.fv_len)))
    need(rep, 'the volume is 4 KiB aligned (flash sector size)', fv.start % SECTOR == 0 and fv.length % SECTOR == 0)
    need(rep, 'the slot lies inside the volume', fv.start <= slot.off and slot.off + dinfo['total'] <= fv.start + fv.length)
    if derived:
        try:
            f = ffs_owner(tgt.data, fv, slot.off, slot.off + dinfo['total'])
        except FwError as e:
            raise Refuse('walking the FFS files of the volume failed: %s' % e)
        need(rep, 'the slot sits in the data area of one FFS file', f is not None)
        need(rep, 'that FFS file has no data checksum (attribute 0x40 clear)', not (f.attr & FFS_ATTR_CHECKSUM),
             'this tool does not recompute FFS checksums')

    mod = bytearray(tgt_raw)
    mod[tgt.base + slot.off:tgt.base + slot.off + len(dblob)] = dblob
    mod = bytes(mod)
    payload = mod[tgt.base + fv.start:tgt.base + fv.start + fv.length]

    rep.heading('Verifier gates on the finished image (the same code as verify_microcode_mod.py)')
    opts = Opts(p.target_cpuid, p.fallbacks, p.replace_cpuid, window, None, p.accept_no_bpm)
    n_before = len(rep.fails)
    ok, ctx = evaluate(tgt_raw, mod, payload, opts, rep)
    if not ok:
        raise Refuse('%d verifier gate(s) failed on the finished image: %s' % (len(rep.fails) - n_before, '; '.join(rep.fails[n_before:])))
    plan = Plan()
    plan.tgt, plan.mod, plan.payload, plan.fv, plan.slot, plan.dinfo, plan.ctx = tgt, mod, payload, fv, slot, dinfo, ctx
    return plan


# --------------------------------------------------------------------------- command line

def cpuid_arg(text):
    try:
        return parse_cpuid(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError('%r: %s' % (text, e))


def hex_arg(text):
    try:
        return parse_hex(text)
    except ValueError:
        raise argparse.ArgumentTypeError('%r is not a hexadecimal number' % text)


def platform_arg(text):
    try:
        v = int(text, 10)
    except ValueError:
        v = -1
    if not 0 <= v <= 7:
        raise argparse.ArgumentTypeError('%r: the platform id is a number from 0 to 7' % text)
    return v


def build_parser():
    p = argparse.ArgumentParser(
        prog='build_microcode_swap.py',
        usage='%(prog)s TARGET DONOR TARGET_CPUID --replace-cpuid CPUID --fallback-cpuid CPUID --out-dir DIR [options]\n'
              '       %(prog)s --self-test',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)
    p.add_argument('target', nargs='?', help='your own dump (full SPI dump or BIOS-region dump); never modified')
    p.add_argument('donor', nargs='?', help='BIOS image carrying the microcode (or a bare microcode file, see --donor-kind); never modified')
    p.add_argument('target_cpuid', nargs='?', type=cpuid_arg, metavar='TARGET_CPUID',
                   help='CPUID of the CPU you want to add, for example 906ED or 06-9e-0d')
    p.add_argument('--replace-cpuid', type=cpuid_arg, metavar='CPUID',
                   help='the CPUID whose microcode slot gets overwritten; required, never guessed')
    p.add_argument('--fallback-cpuid', type=cpuid_arg, action='append', default=[], metavar='CPUID',
                   help='a CPUID that must keep its microcode, normally the CPU installed now; required, repeatable')
    p.add_argument('--out-dir', metavar='DIR', help='where the three output files go (required unless --dry-run)')
    p.add_argument('--donor-kind', choices=('image', 'microcode'), default='image',
                   help='image: DONOR is a BIOS image (default). microcode: DONOR holds bare microcode updates')
    p.add_argument('--platform-id', type=platform_arg, metavar='N',
                   help='0-7, IA32_PLATFORM_ID (MSR 0x17 bits 52:50) of the CPU you will install; the donor mask must include it')
    p.add_argument('--fit-offset', type=hex_arg, metavar='OFF', help='hex, relative to the BIOS region; must equal what the FIT pointer gives')
    p.add_argument('--fv-base', type=hex_arg, metavar='OFF', help='hex, relative to the BIOS region; must equal the volume found (or define it if none is found)')
    p.add_argument('--fv-len', type=hex_arg, metavar='LEN', help='hex; same rule as --fv-base')
    p.add_argument('--accept-no-bpm-check', action='store_true',
                   help='proceed although no usable Boot Policy Manifest was found; the IBB digest then goes unchecked')
    p.add_argument('--force', action='store_true', help='overwrite output files that already exist')
    p.add_argument('--dry-run', action='store_true', help='run every check, write nothing')
    p.add_argument('--self-test', action='store_true', help='run the built-in tests on synthetic images and exit; needs no files')
    return p


def write_atomic(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.target and args.donor and args.target_cpuid is not None):
        parser.error('TARGET, DONOR and TARGET_CPUID are required (or use --self-test)')
    if args.replace_cpuid is None:
        parser.error('--replace-cpuid is required: this tool never chooses which microcode to destroy')
    if not args.out_dir and not args.dry_run:
        parser.error('--out-dir is required unless --dry-run is given')
    names = ('modified_full.bin', 'ucode_fv_mod.bin', 'report.txt')
    paths = [os.path.join(args.out_dir, n) for n in names] if args.out_dir else []
    print('build_microcode_swap.py: offline. It reads the files you name and writes only into --out-dir. It never '
          'opens a device, a driver or the network, and it never flashes anything.')
    rep = Report()
    try:
        for path in paths:
            for src in (args.target, args.donor):
                if os.path.realpath(path) == os.path.realpath(src):
                    raise Refuse('output %s would overwrite an input file' % path)
            if os.path.exists(path) and not args.force:
                raise Refuse('%s already exists; remove it or pass --force' % path)
        try:
            tgt_raw, donor_raw = read_file(args.target), read_file(args.donor)
        except FwError as e:
            raise Refuse(str(e))
        params = Params(args.target_cpuid, args.replace_cpuid, args.fallback_cpuid, args.donor_kind, args.platform_id,
                        args.fv_base, args.fv_len, args.fit_offset, args.accept_no_bpm_check)
        plan = plan_swap(tgt_raw, donor_raw, params, rep)
    except Refuse as e:
        print('')
        print('REFUSED: %s' % e)
        print('Nothing was written.')
        return 1
    except Exception as e:                      # fail closed
        print('')
        print('REFUSED: unexpected %s: %s' % (type(e).__name__, e))
        print('Nothing was written.')
        return 1

    c, old, fv = plan.ctx, plan.slot, plan.fv
    rep.heading('What this changes')
    rep.say('  Overwrites the BIOS microcode for CPUID %s (rev %s, %s, platform mask %s) with CPUID %s (rev %s, %s, platform mask %s).'
            % (hx(old.info['cpuid']), hx(old.info['rev']), bcd_date(old.info['date']), hx(old.info['pf']),
               hx(plan.dinfo['cpuid']), hx(plan.dinfo['rev']), bcd_date(plan.dinfo['date']), hx(plan.dinfo['pf'])))
    rep.say('  After a flash, a CPU with signature %s no longer gets a BIOS microcode update at reset. Whether it still '
            'starts is not guaranteed; keep such a CPU out of this board.' % hx(old.info['cpuid']))
    rep.say('  Kept untouched: %s. The FIT is byte-identical, so no table the Boot Guard ACM reads was edited.'
            % ', '.join('CPUID ' + hx(f) for f in params.fallbacks))
    rep.say('  Changed bytes: %d in %d ranges, all inside region+%s.' % (run_bytes(c.rel), len(c.rel), span(old.off, old.off + old.info['total'])))
    lo, hi = c.rel[0][0], c.rel[-1][1]
    rep.say('  Smallest 4 KiB-aligned span that covers every change: region+%s. The reference procedure writes the whole '
            'volume instead.' % span(lo & ~(SECTOR - 1), (hi + SECTOR - 1) & ~(SECTOR - 1)))
    rep.heading('Write window (nothing is written by this tool)')
    for line in flash_window_text(c):
        rep.say('  ' + line)
    rep.say('  payload file: ucode_fv_mod.bin, %s bytes. A flash tool takes an absolute start address and a length; for '
            "Intel's FPT those are -a and -l, and both must be given." % hx(len(plan.payload)))
    rep.say('  A wrong absolute address is a documented way to brick a board: take the BIOS region base from your own '
            'flash tool or from the flash descriptor of your dump, never from a forum post.')

    report = list(rep.lines)
    report += ['', '== Exact changed byte ranges (BIOS region offsets, half-open) ==']
    report += ['  %s  (%d bytes)' % (span(a, b), b - a) for a, b in c.rel]
    report += ['', 'Nothing was written to hardware by this tool.']
    text = ('\n'.join(report) + '\n').encode('ascii', 'replace')
    if args.dry_run:
        print('')
        print('DRY RUN: every check passed; nothing was written.')
        return 0
    try:
        os.makedirs(args.out_dir, exist_ok=True)
        write_atomic(paths[0], plan.mod)
        write_atomic(paths[1], plan.payload)
        write_atomic(paths[2], text)
    except OSError as e:
        print('')
        print('ERROR: could not write the outputs: %s' % e)
        return 1
    print('')
    print('BUILT. Files in %s:' % args.out_dir)
    print('  %-18s %s bytes   whole image, same size as TARGET' % (names[0], hx(len(plan.mod))))
    print('  %-18s %s bytes   microcode volume only' % (names[1], hx(len(plan.payload))))
    print('  %-18s %d changed ranges listed' % (names[2], len(c.rel)))
    print('')
    print('Next: re-check the result with the independent verifier before any write:')
    print('  python -I verify_microcode_mod.py "%s" "%s" "%s" --target-cpuid %s %s --replace-cpuid %s'
          % (args.target, paths[0], paths[1], hx(params.target_cpuid),
             ' '.join('--fallback-cpuid ' + hx(f) for f in params.fallbacks), hx(params.replace_cpuid)))
    print('Writing the payload is a separate manual step with the vendor or Intel flash tool; see the README.')
    return 0


# --------------------------------------------------------------------------- self-test

def self_test():
    donor_specs = ((0x906EA, 0xFA, 0x22, 0x19C00, 0x01012024), (0x906EB, 0xF7, 0x02, 0x1A000, 0x01012024),
                   (0x906EC, 0xF8, 0x22, 0x1A000, 0x01012024), (0x906ED, 0x100, 0x22, 0x1A000, 0x10012024),
                   (0x906ED, 0x104, 0x22, 0x1A000, 0x11142024))
    treg, tlay = syn_region(seed=1)
    treg = bytes(treg)
    dimg, _ = syn_region(seed=5, ucodes=donor_specs)
    dimg = bytes(dimg)
    dslots = fit_ucode_slots(Image(dimg), parse_fit(Image(dimg)))
    d104 = [ucode_blob(Image(dimg), s) for s in dslots if s.info['cpuid'] == 0x906ED and s.info['rev'] == 0x104][0]
    slot_off = tlay['slots'][1][1]
    expected = bytes(syn_replace(treg, 0, slot_off, d104))
    base = dict(target_cpuid=0x906ED, replace_cpuid=0x906EB, fallbacks=[0x906EA])
    results = []

    def run(label, tgt=treg, donor=dimg, expect=None, want_mod=None, **over):
        kw = dict(base, **over)
        try:
            plan = plan_swap(tgt, donor, Params(**kw), Report(echo=False))
            got = ('built', plan)
        except Refuse as e:
            got = ('refused', str(e))
        except Exception as e:                       # a crash is a test failure
            got = ('crash', '%s: %s' % (type(e).__name__, e))
        if expect is None:
            ok = got[0] == 'built' and (want_mod is None or got[1].mod == want_mod)
            note = '' if ok else (' -> ' + got[1] if got[0] != 'built' else ' -> output differs from the expected image')
        else:
            ok = got[0] == 'refused' and expect in got[1]
            note = '' if ok else (' -> ' + (got[1] if got[0] != 'built' else 'built, but a refusal was expected'))
        results.append(ok)
        print('  [%s] %s%s' % ('ok' if ok else 'WRONG', label, note[:200]))

    run('BIOS-region target, image donor (picks revision 0x104 of two)', want_mod=expected)
    spi = bytes(syn_spi(treg))
    run('full SPI target, image donor', tgt=spi, want_mod=bytes(syn_replace(spi, SYN_R, slot_off, d104)))
    run('bare microcode donor file', donor=d104, donor_kind='microcode', want_mod=expected)
    other = syn_ucode(0x906EC, 0xF8, 0x22, 0x1A000, 0x01012024, random.Random(11))
    run('bare donor file with two updates and erased padding', donor=other + d104 + b'\xFF' * 512, donor_kind='microcode', want_mod=expected)
    run('platform id 5 is in the donor mask', platform_id=5, want_mod=expected)
    run('explicit --fv-base/--fv-len/--fit-offset that agree', fv_base=SYN_FV, fv_len=SYN_FVLEN, fit_offset=SYN_FIT, want_mod=expected)
    short = syn_ucode(0x906ED, 0x104, 0x22, 0x19400, 0x11142024, random.Random(13))
    run('donor update of a different size', donor=short, donor_kind='microcode', expect='exactly the size of the donor')
    run('target CPUID already in the FIT', target_cpuid=0x906EA, expect='not already in the FIT')
    run('fallback not in the FIT', fallbacks=[0x906EC], expect='is in the FIT')
    run('no fallback given', fallbacks=[], expect='fallback-cpuid is given')
    run('replace CPUID equals a fallback', replace_cpuid=0x906EA, fallbacks=[0x906EA], expect='not one of the fallbacks')
    run('replace CPUID not in the FIT', replace_cpuid=0x906EC, expect='names a microcode slot')
    run('platform id 0 is not in the donor mask', platform_id=0, expect='platform id 0')
    run('--fv-base disagrees with the volume found', fv_base=SYN_FV + SYN_FVLEN, expect='--fv-base')
    run('--fit-offset disagrees with the FIT pointer', fit_offset=SYN_FIT + 16, expect='--fit-offset')
    bad = bytearray(d104)
    bad[0x2000] ^= 0xA5
    run('donor update fails its checksum', donor=bytes(bad), donor_kind='microcode', expect='checksum')
    ptr = bytearray(treg)
    struct.pack_into('<Q', ptr, SYN_R - 0x40, 0)
    run('FIT pointer destroyed', tgt=bytes(ptr), expect='FIT pointer')
    ffs_img, _ = syn_region(seed=1, ffs_attr=0x4C)
    run('microcode FFS file carries a data checksum', tgt=bytes(ffs_img), expect='no data checksum')
    nobpm, _ = syn_region(seed=1, with_bpm=False)
    run('no BPM, flag absent', tgt=bytes(nobpm), expect='flash anyway')
    nobpm_exp = bytes(syn_replace(bytes(nobpm), 0, slot_off, d104))
    run('no BPM, flag given', tgt=bytes(nobpm), accept_no_bpm=True, want_mod=nobpm_exp)
    hidden = bytearray(treg)
    hidden[0x300000:0x300000 + len(d104)] = d104
    run('target microcode hidden elsewhere in the image', tgt=bytes(hidden), expect='nowhere in the image')
    run('donor image is not firmware', donor=b'\x00' * 65536, expect='donor image')
    run('donor file with garbage after the update', donor=d104 + b'garbage' * 10, donor_kind='microcode', expect='not a microcode update')
    vols = [FV(0, 0x100000, 0x48, 0xFF), FV(0x1000, 0x20000, 0x48, 0xFF), FV(0x400000, 0x1000, 0x48, 0xFF)]
    nested_ok = (enclosing_fv(vols, 0x2000) == vols[1] and enclosing_fv(vols, 0x500) == vols[0]
                 and enclosing_fv(vols, 0x400000) == vols[2] and enclosing_fv(vols, 0x300000) is None)
    results.append(nested_ok)
    print('  [%s] innermost firmware volume wins when volumes are nested' % ('ok' if nested_ok else 'WRONG'))
    print('')
    bad_n = results.count(False)
    if bad_n:
        print('SELF-TEST: %d of %d cases did not behave as expected' % (bad_n, len(results)))
        return 1
    print('SELF-TEST: all %d cases behaved as expected' % len(results))
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
