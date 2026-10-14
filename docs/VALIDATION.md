# Validation status — 0.4.3

The software suite currently contains **75 tests**, using synthetic data, mocks
and real local subprocesses. No case targets a wireless network.

Install the development dependencies with `python -m pip install '.[test]'`,
then run `python -m unittest discover -s tests -v`. The discovery terminal check
uses a VT screen model so curses' incremental redraws are interpreted correctly.

Coverage includes:

- Hidden AP detection, later observed-name updates, comma-containing names, unknown signal, partial CSV rows, client association and stable discovery ordering.
- Real fixture subprocesses writing changing scan CSV data, exiting with errors, producing an empty header, or producing no CSV; no radio hardware is involved.
- Direct scan entry, hidden-row selection, rescan and options in a real terminal, preserving HIFI's frame and saving the selected BSSID/channel.
- An optional real `airodump-ng` check reads a locally generated synthetic beacon PCAP into the CSV parser. CI installs aircrack-ng for Python 3.12; other matrix jobs skip this case. It opens no wireless interface.
- Unknown-channel APs stay visible; stale adapter names are refreshed at scan start. Empty/failed scans clear old network results and preserve private diagnostic evidence.
- Temporary monitor-mode cancellation, half-completed setup recovery, NetworkManager ownership restoration, adapter locking and visible recovery failures.
- Summary exports omit network names, BSSIDs and observed client data; full exports retain them.

- Privilege checks before process handoff; unprivileged recovery cannot change interfaces.
- Selected-interface recovery, disappearance, cancellation, failed mode changes, final-state verification and summary redaction.
- A separate rendered PTY check for two-digit menu navigation, demo recovery, resizing, and all eight main entries visible at 80×24, consistent `00 Back`, and `00 Exit`.

- Workbench command editing, scope controls and demo behavior.
- Private atomic persistence, old-session migration and summary privacy.
- Bounded process cancellation, descendants, output limits and HTML escaping.
- Real pseudoterminal input, Ctrl+C, resizing, exit status, working directories,
  file permissions, cancellation, terminal restoration and return to menus.
- Bundled engine help from an unrelated working directory with no engine or
  radio binaries on PATH; no previous product name in help output.
- Retention of all 113 baseline option names and aliases and import of all engine modules.
- Parser errors retaining exit code 2 and stored-result viewing without backends.
- Engine argv preservation and subprocess pipe draining with large outputs.

The installed command is checked from outside the checkout. This focused update
does not publish a new source ZIP or zipapp. Software checks verify integration, not successful radio
operations or password/PIN recovery.

## Physical validation still pending

For discovery, verify the user's RTL8814AU adapter passed through to Kali:
select the adapter, scan a lab AP with hidden SSID, verify BSSID/channel/signal,
connect a lab client normally and check whether the name becomes observable,
then select/stop and inspect adapter mode and NetworkManager ownership. Also
check unplugging the adapter and stopping a scan. No SSID recovery is guaranteed.
This update covers 2.4/5 GHz passive discovery only; no 6 GHz profile or new
disruptive, Bluetooth or MITM operation has been added.

The inherited explicit-interface (`-i`) engine path assumes an already prepared
interface. Automatic adapter selection handles monitor setup; the explicit path
has not been corrected in this terminal/recovery update. Select an existing
monitor interface for bounded engine capture profiles.

Record OS/kernel, adapter chipset/driver, backend versions, channel and interface
state before/after. Validate each WPA/WPS/PMKID/WEP workflow separately on a lab
network you control, along with cancellation, artifacts and interface restoration.
VMware USB passthrough, chipset compatibility, RF conditions, recovery outcomes
and a real Ollama model's quality have not been validated in the build environment.

The tagged baseline includes legacy WPA3/OWE selectors and an incomplete Evil Twin
placeholder. These do not establish implemented WPA3 recovery or an Evil Twin
workflow. Subsequent upstream beta additions are outside this pinned baseline.
