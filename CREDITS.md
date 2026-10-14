# Source provenance and licensing

HIFI is an independent derivative project by D3FAULTH. It is not an official
upstream release and does not claim authorship of the upstream engine.

The bundled `hifi/engine` source derives from **Wifite2**, originally by derv82,
maintained by kimocoder and its contributors:

- Repository: https://github.com/kimocoder/wifite2
- Tagged baseline: **2.8.2**
- Pinned commit: `d88ed4a5a1764fab93c60b51c7d9baa186bc8757`
- License: **GNU GPL version 2**; this distribution uses `GPL-2.0-only`.
- File mapping and original Git blob IDs: `hifi/engine/UPSTREAM.json`.

The combined HIFI distribution is provided under the GPL in [LICENSE](LICENSE).
The original MIT notice for HIFI's workbench code is retained in
[LICENSES/HIFI-MIT.txt](LICENSES/HIFI-MIT.txt). Source archives include the
corresponding engine source, modification notices and license texts. Dependencies
remain under their respective licenses.

## Modifications by D3FAULTH, 2026-10-14 UTC

- Integrate all 47 Python modules from the tagged engine under `hifi.engine`;
  rename its entry module to `core.py` and apply HIFI's banner and runtime wording.
- Launch the bundled engine from installed packages, source checkouts and
  zipapps, including when the working directory is outside the checkout.
- Connect terminal menus, editable commands, private workspaces, reports and
  session history. Migrate prior session settings without altering old evidence.
- Preserve argument-parser failures and other nonzero exit statuses during
  cleanup. Permit saved-result viewing without radio dependencies or root.
- Load the database updater only for its explicit command.
- Correct argument-list execution, remove shell evaluation in the synchronous
  engine helper and packet-forging call, use direct sysfs writing for the existing
  ICNSS2 mode operation, and drain subprocess pipes while waiting.
- Replace a private Python REPL import with the supported builtin input function.

The full tagged command-line surface is retained: **113 option names and aliases**.
This baseline does not include subsequent upstream beta additions. Some legacy
flags are selectors or incomplete placeholders: WPA3/OWE selectors do not imply
general password recovery; the tagged Evil Twin code is an unimplemented
placeholder. HIFI does not advertise those as working recovery capabilities.

The upstream sample dictionary and IEEE database are not bundled. Supply a
dictionary with `--dict`; install `ieee-data` or explicitly run the database
updater for vendor lookups. This does not remove their command-line features.

## Other projects

HIFI uses separately installed Aircrack-ng tools, Wireshark/TShark, Linux wireless
tools, Reaver/Bully, hcxtools, Hashcat/John and optional Ollama. Python dependencies
include chardet and Requests. Their projects retain their own authorship,
trademarks and licenses. Runtime branding does not change these attributions.

HIFI 0.4.1 uses an original D3FAULTH/HIFI menu layout and wordmark.
The numbered terminal, privilege guidance and selected-device recovery UI are
HIFI additions; inherited engine provenance and notices remain unchanged.
