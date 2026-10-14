# Why this is worth doing in 2026

A 2018 office PC usually still works. It counts as old because the vendor stopped validating new CPUs
for it, Windows 10 reached end of support, and new machines are what the industry sells. This page gives
the numbers behind spending an afternoon and the price of a used CPU instead of buying a new machine.

## Memory and silicon got expensive, fast

AI datacenter demand pulled the memory industry into a shortage that hit ordinary PCs hard.

- Standard (non-AI) DRAM contract prices rose **93-98% in a single quarter** (Q1 2026); the memory
  industry booked about **$97 billion** of revenue that quarter, up 81% in three months.
  [TrendForce, 2026-06-01](https://www.trendforce.com/presscenter/news/20260601-13070.html)
- Gartner expects **2026 PC prices up about 17%**, with memory rising to **23% of a PC's bill of
  materials** (16% in 2025).
  [Gartner, 2026-02-26](https://gcom.pdo.aws.gartner.com/en/newsroom/press-releases/2026-02-26-gartner-says-surging-memory-costs-will-reduce-global-pc-and-smartphone-shipments-in-2026)
- Intel's CEO, on the 2026-07-23 earnings call, called it *"one of the most severe supply constraints in
  [the industry's] history… These shortages will persist for the foreseeable future."*
  [Intel Q2 2026 call](https://download.intel.com/newsroom/2026/earnings/Intel-Q22026-Earnings-Call.pdf)
- IDC does not expect the memory shortage to ease **until early 2028**.
  [IDC, 2026-07-08](https://www.idc.com/resource-center/press-releases/2q26-pc-top5/)

When new hardware is scarce and expensive, the cheapest real upgrade is often the one you already own.
Gartner expects buyers to respond by keeping PCs longer: **about 15% longer for business** by the end of
2026 (same Gartner release).

## Windows 10 ended support, and a lot of PCs got stranded

Windows 10 reached end of support on **2025-10-14**. Microsoft now sells consumer security updates for
**$30, running to 2027-10-12**
([Microsoft](https://support.microsoft.com/en-us/windows/windows-10-consumer-extended-security-updates-esu-program-33e17de9-36b3-43bb-874d-6c53d2e4bf42)).
Dell's COO said around **a billion PCs were still on Windows 10** at the deadline, roughly half of them
without the hardware to move to Windows 11
([reported via Pureinfotech](https://pureinfotech.com/billion-pcs-stuck-windows-10-dell/)).

A faster, more efficient CPU does not make an unsupported PC supported. A machine that is quick enough
for another three or four years is one you do not have to replace while prices are high, and Linux or a
self-hosted workload runs on it regardless of Microsoft's support calendar.

## Most of the carbon is spent before the PC is switched on

In the makers' own life-cycle studies, manufacturing is roughly **70-80%** of a computer's lifetime
emissions: Apple reports **71%** for a 2025 MacBook Air
([Apple PER](https://apple.com/environment/pdf/products/notebooks/M4_MacBook_Air_PER_March2025.pdf)),
and Dell and TCO Certified studies land in the same 73-80% range. Keeping a working PC in service for a
few more years avoids paying that manufacturing cost again.

The world produced **62 million tonnes of e-waste in 2022, and formally recycled under a quarter of it**
([UN Global E-waste Monitor 2024](https://www.itu.int/en/ITU-D/Environment/Pages/Publications/The-Global-E-Waste-Monitor-2024.aspx)).

## Where a CPU swap fits

This project removes one specific limit: an OEM board whose chipset supports a newer CPU, but whose final
BIOS lacks that CPU's microcode (forum reports say such a CPU will not POST; the reference build did not
test the stock BIOS with it). The missing piece is a few kilobytes of Intel-signed data, taken from the
same vendor's BIOS for a sibling model. On the reference build it took the rated CPU power from 65 W to
35 W while adding two cores. Closed-case soaks passed afterwards; the same visit also changed the thermal
pad and removed the case mesh screens, so the cooler running is not down to the CPU alone.

The rest of these docs cover how to do it without bricking the board.

---

*Figures here are dated and linked; a few rest on secondary reporting, which is noted at each source.
Re-check any number before quoting it elsewhere. The memory market in particular moves monthly.*
