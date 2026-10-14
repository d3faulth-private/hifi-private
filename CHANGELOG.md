# Changelog

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
