# Contributing

This is a technical-community knowledge base about keeping out-of-warranty hardware in service. The
most valuable contributions are:

- **Confirmed hardware reports.** You ran the method on a board not yet listed: say which board, which
  BIOS version, which donor BIOS, which CPU, and what happened. A negative result is as useful as a
  positive one.
- **Safety fixes.** A wrong offset, a verifier check that passes when it should fail, a missing warning,
  a recovery step that does not work on some board. These get priority.
- **Corrections.** If something here is inaccurate, open an issue with a source.

Please keep contributions **vendor-neutral and reproducible**, and **never commit** vendor BIOS images,
microcode binaries, or any machine-identifying data (service tags, MAC addresses, serials, your own
SPI-dump hashes, hostnames, IP addresses, local file paths). The tools and docs here describe how to
obtain those from your own hardware and the vendor; they do not redistribute them.

By contributing you agree your contribution is licensed under this repo's terms (MIT for code, CC BY
4.0 for docs).
