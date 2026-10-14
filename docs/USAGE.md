# Hidden-network discovery (0.4.4)

Start HIFI with root access and choose **01 Scan Wi-Fi** (or press Enter).
One connected adapter is selected automatically. With multiple adapters, choose one
when asked; an existing valid selection is retained.
The scan uses that adapter; no BSSID or channel must be entered beforehand.

`[Hidden]` means an access point was observed but its SSID is not yet known.
If ordinary traffic later reveals its name, the same row updates automatically.
The scan does not deauthenticate clients or guess SSIDs. Passive observation
cannot guarantee learning every hidden name.

Use arrows or a row number and Enter to select. HIFI stops the scan, attempts
adapter restoration and saves interface/BSSID/channel into the session scope.
Selection opens **Network Actions**. Choose **01 WPA/WPA2 password Exploit** or
**02 WPS PIN / Pixie-Dust Exploit**; the adapter, BSSID and channel are preserved.
WPA asks for a local wordlist. Review the command and press Enter to start.
Live output stays inside HIFI; Escape stops the attempt and restores the adapter.
**03 Network details** shows security, timestamps, signal and client observations.
**04 Exploit settings** controls the 600-second default overall limit, wordlist
and WPA client disconnects. Results distinguish a recovered password/PIN from
no recovery, timeout, cancellation and process errors.
Press **S** to stop while keeping the table open, **/** to filter, or Escape to
return. **R** retries immediately; **O** opens optional settings, including bands
and scan duration. Both stop and restore an active scan before continuing.
Default: 30 seconds across 2.4 GHz and 5 GHz. **E** shows scanner details.
The saved table is historical evidence; only the live scan refreshes it.

A backend failure displays **SCAN FAILED**. Press **E** to read its exit code and
error; missing dependencies name the Kali installation command. A readable scan
without access points displays **NO NETWORKS RECEIVED**, not a success message.
Empty and failed scans collect adapter state before restoration. These checks
and backend output are saved privately in the session. No networks is an
observation, not proof that no access point exists. Verify USB
passthrough, band support and signal range. Recovery failure is recorded in
history; inspect the adapter and use menu **02** to restore normal Wi-Fi.

Discovery and the selected-network action path manage temporary monitor mode.
The older manual capture-only and advanced Full Exploit paths retain their
existing behavior, described below. The selected-network actions do not inherit
advanced arguments or automatically switch to a different target.

# HIFI usage

## Start

After installation, `hifi` opens the menus. `hifi --demo` explores them without
running radio commands. A demo session stays simulated when reopened.

```bash
hifi
hifi --demo
hifi sessions
hifi --session SESSION_ID
```

Global HIFI options go before the subcommand. `SESSION_ID` is the 12-character
identifier printed by the program. Root and a normal user have separate default
state directories; use the same user context to reopen a radio session.

## Full HIFI Exploit

Open **04 Exploit → Full HIFI Exploit**. Its editable command begins with
`hifi engine`. All baseline engine arguments remain available. Read **HIFI engine
help** for full options. The integrated engine handles scanning, selection,
wireless methods and prompts; no separately installed engine is invoked.

The CLI provides two paths:

```bash
hifi engine --help -v
hifi exploit
hifi exploit --run
hifi exploit --run -- -h -v
```

`engine` is a direct entry point, using the caller's current directory and native
engine behavior. `exploit` previews by default; `--run` executes through the
interactive relay and records the result in HIFI. Put engine flags after `--`.
Live radio operations need suitable privileges; help and saved-result viewing do
not. Full Exploit mode does not use the capture-profile scope or HIFI timeout.

Ctrl+C reaches the engine's current workflow; it can open a continuation menu or
exit. Leaving the workflow returns to HIFI. Escape is only a HIFI menu control,
not a stop shortcut inside the engine.

## Files and saved arguments

A new workbench session uses its private `engine` subdirectory. Reopening a
session reuses the last executed arguments and working directory. Choose
**HIFI working directory** for an existing workspace. Relative engine paths
resolve there; absolute dictionary and capture paths are easiest.

```bash
hifi exploit --workdir /absolute/path/workspace --run -- --cracked
hifi --session SESSION_ID exploit
hifi --session SESSION_ID exploit --fresh
```

New arguments after `--` replace saved arguments. `--fresh` uses an empty argument
list; executing it saves that reset. Previewing does not alter saved arguments.
The menu also has **Reset saved HIFI arguments**. Old saved settings migrate to
the new field names without changing historical evidence.

The engine needs a supplied dictionary or an existing system dictionary for
wordlist recovery. HIFI does not bundle or download a default dictionary. The
system `ieee-data` package supplies vendor mappings; database updates are explicit.

## Capture-only profiles

Configure the intended lab network:

```bash
hifi scope --interface wlan0mon --bssid 02:11:22:33:44:55 --channel 6 --duration 60
```

These values are synthetic examples. The standalone passive profile requires an
already configured monitor interface on that channel and verifies it first:

```bash
hifi --session SESSION_ID capture
```

The engine's separate capture-only profiles are:

```bash
hifi --session SESSION_ID capture-engine
hifi --session SESSION_ID capture-engine --active
```

All three preview by default; add `--run` to execute. Capture-only engine profiles
pin interface, BSSID and channel and disable WPS, PMKID and cracking. The passive
profile disables deauthentication. The active profile can disconnect clients.
The dumpcap profile has time and 50 MB limits. Bounded profiles use closed stdin;
use Full HIFI Exploit when you need the engine's interactive prompts.

## Capture analysis and offline wordlist Exploit

```bash
hifi inspect /absolute/path/capture.pcapng --view all
hifi --session SESSION_ID offline /absolute/path/capture.pcapng --wordlist /absolute/path/words.txt
```

Inspection offers metadata, EAPOL and disconnect-frame views. The separate offline
wordlist command previews unless `--run` is supplied and uses the session BSSID.
The TShark editor allows display filters, fields and packet limits. Packet parsing
is delegated to installed tools; use an unprivileged session for file analysis.
A frame count alone does not prove a usable handshake or recovery result.

## Suggestions and optional local model

```bash
hifi --session SESSION_ID suggest
export HIFI_OLLAMA_MODEL='your-installed-local-model'
hifi --session SESSION_ID ask 'Explain the last result'
```

Suggestions are rules based on evidence. Optional Ollama receives scope and up to
6000 characters from each of the last three outputs via `127.0.0.1:11434`, with
HTTP proxies disabled. Model text is not executed. The request has a 45-second
socket timeout; the UI waits for completion. Configure a local model to avoid a
server that forwards prompts to a cloud provider.

## Reports

```bash
hifi --session SESSION_ID report --output summary.html
hifi --session SESSION_ID report --output private.json --include-sensitive
```

Exports refuse to overwrite files. Summaries omit identifiers, commands, paths,
notes and raw output. Full reports can contain credentials. Process status `ok`
means exit code zero; it is not a recovery verdict. Review evidence before sharing.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `hifi` not found | Open a new terminal after `pipx ensurepath`, or use your virtual environment's launcher |
| Missing Python module | Install the project with pipx or pip in a virtual environment |
| No Wi-Fi interface in VM | USB passthrough, driver support and adapter visibility |
| Missing radio backend | Run `hifi doctor` and install the needed system package |
| Relative file not found | Check the engine workspace or use an absolute path |
| Exploit relay needs a terminal | Open a terminal; use `hifi engine --help` for redirected help output |
| Invalid engine option | Read `hifi engine --help -v`; the included baseline is fixed |
| Capture preflight fails | Verify monitor mode and channel |
| Adapter changed after exit | Inspect `iw dev` and restore its previous state with your normal tools |

## Numbered terminal and adapter recovery (0.4.1)

Type the displayed number, then Enter. Option 02 opens detected-adapter selection,
restart, managed-mode restoration and refresh. The root/user status is shown in
the header. Launch live operations with `sudo "$(command -v hifi)"` after installing
HIFI with pipx. This preserves its Python environment.

`hifi adapter list` reads interface inventory. `hifi adapter restart --interface
wlan0` previews a restart. Append `--run` to execute with root, or
`--restore-managed --run` to return to managed Wi-Fi as well. Only a currently
detected wireless interface can be changed. Recovery does not restart global
network services, delete virtual interfaces, or guarantee reconnection.

The compact home screen has seven sections and **00 Exit**. Submenus use **00 Back**.
Edit scope under **03 Dashboard → Edit session scope**. Manual commands are
editable profiles under **05**; history, notes and exports are grouped under **06**.
Selecting Exit saves session state and returns to the shell with resume instructions.
