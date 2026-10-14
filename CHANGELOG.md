# Changelog

## 0.4.5 — reliability and evidence assessment

- Replace three stty size calls with terminal sizing that supports piped execution.
- Clean up descendants after parent exit so inherited pipes do not stall results.
- Add wide action panels, structured job status, elapsed time and expandable logs.
- Add selected-network evidence assessments and optional local Ollama explanations without raw logs or recovered credentials.
- Expose adapter recovery directly from network actions.
- Add regression coverage for non-TTY execution, dead-parent cleanup and assessment privacy/scope.

## 0.4.4 — selected-network WPA/WPS integration

- Open Network Actions after discovery selection; connect WPA/WPA2 wordlist and WPS PIN/Pixie-Dust workflows to that exact adapter, BSSID and channel.
- Prepare monitor mode for each attempt, stream output inside the D3FAULTH frame, and restore adapter state on completion/cancellation/failure.
- Add dependency/wordlist readiness, a reviewed command, configurable overall runtime and WPA client-disconnect behavior.
- Require fresh matching structured evidence before reporting a recovered password or PIN; distinguish PIN-only results, no recovery, errors and restoration problems.
- Keep recovered credentials, selected targets and wordlist paths out of summary exports.
- Verify selected workflow routing and terminal navigation with synthetic fixtures. Live Kali password/PIN recovery remains unverified.

## 0.4.3 — direct scanning and visible failures

- Make Scan Wi-Fi the first/default action; open the live table directly and select the sole connected adapter automatically.
- Add in-table rescan, optional settings and scanner details; retain numbered network selection and D3FAULTH framing.
- Treat nonzero scanner exits as failures, distinguish empty results, retain exit/error output and collect read-only adapter evidence before restoration.
- Explicitly run the CSV scanner in background mode; keep detected APs with unknown channels visible instead of discarding them.
- Report missing scan dependencies and timed-out adapter reads; clear stale observations after a new failed/empty scan.
- Add offline real-backend CSV verification in CI. Live RTL8814AU/VMware reception remains unverified.
- Keep the existing engine unchanged; this is a discovery/usability fix.

## 0.4.2 — passive hidden-network discovery

- Replace the Discovery menu's cached-network entry with a real selected-adapter scan.
- Show hidden access points, stable row numbers, BSSID, channel, raw signal, security and observed clients.
- Update a hidden name only when observed traffic reveals it; retain last-seen timestamps and detailed network/client views.
- Select a network directly to fill session BSSID/channel; add filtering, Stop, saved observations and scan band/time settings.
- Prepare temporary monitor mode and restore the previous selected-adapter state; report incomplete recovery and prevent competing HIFI scans on the same phy.
- Keep discovery observations out of summary exports; retain them in explicit full exports.
- Limit this update to discovery. The broader controller redesign, Bluetooth, MITM and jamming additions are not included. The existing engine is unchanged.
- Software fixtures and terminal checks do not constitute physical radio validation.

## 0.4.1 — compact terminal workflow

- Group the existing features into seven main sections and a visible `00 Exit`.
- Use `00 Back` in submenus, descriptive menu hints and consistent two-digit input.
- Put adapter recovery under `02`, editable command profiles under `05`, and saved evidence under `06`.
- Add session overview, keyboard/CLI help, and the agreed D3FAULTH terminal standard.
- Retain the repository's existing engine revision; this update changes the terminal, local adapter maintenance and documentation.
- Verify menu routing, simulated recovery, terminal resizing and explicit exit with real pseudoterminals. Hardware validation remains pending.

## 0.4.0 — D3FAULTH terminal and adapter recovery

- Replace the flat terminal layout with a bordered D3FAULTH/HIFI interface, numbered menus, two-column home screen and persistent privilege/adapter status.
- Add number-plus-Enter selection, responsive layout, resize guidance and an original direct-engine banner.
- Check privileges before command handoff and show the exact elevated launcher instead of a late engine failure.
- Add detected-adapter selection, selected-interface restart and managed-mode restoration with command previews, verification and best-effort link-up recovery.
- Add `hifi adapter list` and preview-first `hifi adapter restart`; hide recovery-step output from summary reports.
- Expand the suite to 55 software tests; terminal navigation and layout checked separately. No live radio or adapter restart has been performed in the build environment.

## 0.3.0 — integrated HIFI engine

- Bundle the complete 47-module tagged engine baseline under `hifi.engine`; no separate engine executable is required.
- Use HIFI branding throughout the runtime and expose `hifi engine` plus the existing menu/session workflows.
- Retain all 113 baseline option names and aliases; keep source provenance, original notices and GPL licensing in the distribution.
- Preserve failure exit codes, fix argv handling and pipe draining, and add engine integration coverage.
- Support source, installed-package and zipapp engine launches from any working directory; migrate previous session settings.
- Rename the old capture CLI to `capture-engine`; keep full Exploit and capture-only behavior distinct.

Hardware validation remains pending; inherited incomplete placeholders are documented.

## 0.2.0 — full native Wifite Exploit

- Add Full Wifite Exploit with unfiltered native options, interactive target
  selection and prompts, Ctrl+C forwarding, resize support and terminal restoration.
- Preserve Wifite's installed workflows without injecting WPS, PMKID, cracking
  or deauthentication disable flags; retain separately labeled capture-only modes.
- Add `hifi exploit`, editable native commands, saved arguments and configurable
  Wifite working directory for captures and results; no HIFI native-mode timeout.
- Retain bounded, sanitized terminal output and process status in session history;
  omit native arguments and working paths from summary exports.
- Expand dependency inventory and use Exploit in product labels and branding.
- Add real pseudoterminal integration coverage using a local Wifite fixture.

Radio hardware and real Wifite end-to-end validation remain pending.

## 0.1.0 — first public-source candidate

- Interactive terminal menus and editable reviewed command profiles.
- Adapter diagnostics and explicit local dependency status.
- Scoped passive capture and Wifite passive/active capture integration.
- Metadata, EAPOL and disconnect-frame analysis; offline wordlist Exploit.
- Evidence-based next-step suggestions and optional Ollama explanations.
- Private saved sessions, notes and HTML/JSON exports.
- Synthetic demo mode, software tests and Linux CI configuration.

Physical adapter and real Wifite integration validation remain pending.
