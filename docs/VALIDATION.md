# Validation status — 0.3.0

The software suite currently contains **46 tests**, using synthetic data, mocks
and real local subprocesses. No case targets a wireless network.

Coverage includes:

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

The installed command, wheel contents and zipapp entry point are checked during
release preparation. Software checks verify integration, not successful radio
operations or password/PIN recovery.

## Physical validation still pending

Record OS/kernel, adapter chipset/driver, backend versions, channel and interface
state before/after. Validate each WPA/WPS/PMKID/WEP workflow separately on a lab
network you control, along with cancellation, artifacts and interface restoration.
VMware USB passthrough, chipset compatibility, RF conditions, recovery outcomes
and a real Ollama model's quality have not been validated in the build environment.

The tagged baseline includes legacy WPA3/OWE selectors and an incomplete Evil Twin
placeholder. These do not establish implemented WPA3 recovery or an Evil Twin
workflow. Subsequent upstream beta additions are outside this pinned baseline.
