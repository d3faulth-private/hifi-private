"""Reviewed command builders. Edits are parsed as argv, never evaluated by a shell."""
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from .models import Command, Scope
from .backend import engine_argv

TOOLS = {
    "iw": "Wireless interface and capability inspection",
    "ip": "Interface state",
    "rfkill": "Radio block status",
    "lsusb": "USB adapter inventory",
    "nmcli": "NetworkManager's cached Wi-Fi list",
    "dumpcap": "Bounded packet capture",
    "tshark": "Capture analysis",
    "capinfos": "Capture metadata",
    "aircrack-ng": "Offline wordlist Exploit of a selected capture",
    "airmon-ng": "HIFI monitor-interface management",
    "airodump-ng": "HIFI network discovery and handshake capture",
    "aireplay-ng": "HIFI active wireless operations",
    "reaver": "HIFI WPS PIN and Pixie-Dust backend",
    "bully": "Alternative HIFI WPS backend",
    "pixiewps": "Offline WPS Pixie-Dust backend",
    "hcxdumptool": "PMKID capture backend (version-dependent)",
    "hcxpcapngtool": "Capture conversion backend (version-dependent)",
    "hashcat": "HIFI password recovery backend (version-dependent)",
    "john": "Alternative password recovery backend (version-dependent)",
    "cowpatty": "Optional handshake validation backend",
    "packetforge-ng": "WEP packet-forging backend",
    "macchanger": "Optional adapter MAC management",
}


def inventory():
    return [{"name": name, "path": shutil.which(name), "purpose": purpose}
            for name, purpose in TOOLS.items()]


def diagnostics():
    return [
        Command("Wireless interfaces", ["iw", "dev"], "Find wireless interfaces and their current mode."),
        Command("Adapter capabilities", ["iw", "list"], "Inspect monitor mode and supported frequencies."),
        Command("Radio blocks", ["rfkill", "list"], "Check software and physical radio blocks."),
        Command("Interface state", ["ip", "-brief", "link"], "Check whether interfaces are up or down."),
        Command("USB adapters", ["lsusb"], "Check whether a USB adapter is visible to this operating system."),
    ]


def cached_networks():
    return Command("Cached Wi-Fi networks", ["nmcli", "--terse", "--fields",
                   "SSID,BSSID,CHAN,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no"],
                   "Read NetworkManager's existing cache; the list may be stale or empty.")


def interface_info(scope):
    scope.validate()
    if not scope.interface:
        raise ValueError("Set the interface first.")
    return Command("Selected interface", ["iw", "dev", scope.interface, "info"],
                   "Confirm the selected interface's type and channel.")


def capture_path(value):
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Choose an existing regular capture file.")
    return str(path)


def inspect_capture(value, kind="metadata"):
    path = capture_path(value)
    if kind == "metadata":
        return Command("Capture metadata", ["capinfos", path], "Read packet count, link type, duration, and file metadata.", timeout=60)
    filters = {"eapol": "eapol", "management": "wlan.fc.type_subtype == 12 || wlan.fc.type_subtype == 10"}
    if kind not in filters:
        raise ValueError("Unknown capture view.")
    fields = ["frame.number", "frame.time_relative", "wlan.sa", "wlan.da", "_ws.col.Info"]
    argv = ["tshark", "-n", "-r", path, "-Y", filters[kind], "-T", "fields", "-E", "header=y"]
    for field in fields:
        argv.extend(["-e", field])
    return Command("EAPOL frames" if kind == "eapol" else "Disconnect frames", argv,
                   "Inspect observed frames. Their presence alone does not prove a complete handshake or an attack.", timeout=120)


def passive_capture(scope, destination):
    scope.validate(target=True)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Capture output already exists; use a new filename.")
    bpf = f"wlan addr1 {scope.bssid} or wlan addr2 {scope.bssid} or wlan addr3 {scope.bssid}"
    return Command("Passive capture", ["dumpcap", "-i", scope.interface, "-f", bpf,
                   "-a", f"duration:{scope.duration}", "-a", "filesize:51200", "-w", str(destination)],
                   "Listen on an existing monitor interface; filter frames to the selected BSSID. Maximum 50 MB.",
                   "PASSIVE CAPTURE", timeout=scope.duration + 10, root=True)


def engine_help():
    try:
        result = subprocess.run(engine_argv(["-h", "-v"]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=10, text=True, errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise ValueError("HIFI help timed out; inspect the local installation.") from exc
    if result.returncode:
        raise ValueError("HIFI could not show its help. Check the installation and permissions.")
    return result.stdout


def engine_capture(scope, help_text=None, active=False):
    scope.validate(target=True)
    help_text = engine_help() if help_text is None else help_text
    supported = set(re.findall(r"(?<!\w)-{1,2}[a-zA-Z][\w-]*", help_text))
    required = {"-i", "-b", "-c", "--wpa", "--no-wps", "--no-pmkid", "--skip-crack"}
    missing = required - supported
    no_deauth = next((x for x in ["--no-deauths", "--nodeauths"] if x in supported), None)
    if missing or (not active and not no_deauth):
        raise ValueError("Installed HIFI does not advertise the required flags: " +
                         ", ".join(sorted(missing or {"--no-deauths / --nodeauths"})))
    argv = ["hifi", "engine", "-i", scope.interface, "-b", scope.bssid, "-c", str(scope.channel),
            "--wpa", "--no-wps", "--no-pmkid", "--skip-crack"]
    if not active:
        argv.append(no_deauth)
    return Command("HIFI active capture" if active else "HIFI passive capture", argv,
                   "Capture for one selected BSSID. " +
                   ("May disconnect clients to elicit authentication; select an existing monitor interface." if active else
                    "Deauthentication, WPS, PMKID collection and password cracking are disabled; select an existing monitor interface."),
                   "ACTIVE / CLIENT DISRUPTION" if active else "PASSIVE / INTERFACE CHANGES",
                   timeout=scope.duration, root=True)


def offline_audit(scope, capture, wordlist):
    scope.validate()
    if not scope.bssid:
        raise ValueError("Set the capture's BSSID in the session scope first.")
    cap = capture_path(capture)
    words = capture_path(wordlist)
    return Command("Offline wordlist Exploit", ["aircrack-ng", "-b", scope.bssid, "-w", words, cap],
                   "Run a supplied wordlist against the selected WPA/WPA2 capture. No radio transmissions; no guarantee of recovery.",
                   "OFFLINE / SENSITIVE OUTPUT", timeout=scope.duration)


def engine_exploit(arguments=(), workdir=None):
    """Run the bundled engine with native options, without injecting disable flags."""
    if not isinstance(arguments, (list, tuple)) or not all(isinstance(x, str) for x in arguments):
        raise ValueError("HIFI arguments must be a list of strings.")
    if any(any(c in arg for c in "\n\r\x00") for arg in arguments):
        raise ValueError("HIFI arguments cannot contain newlines or NUL bytes.")
    directory = Path(workdir if workdir is not None else Path.cwd()).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError("Choose an existing HIFI working directory.")
    return Command("Full HIFI Exploit", ["hifi", "engine", *arguments],
                   "The bundled HIFI engine handles options and target selection. "
                   "Includes WPS, PMKID, WEP and WPA workflows. "
                   "HIFI's capture scope and time limit do not apply. Ctrl+C reaches HIFI's own menu.",
                   "NATIVE HIFI / MAY DISCONNECT CLIENTS", timeout=None,
                   root=not any(x in {"-h", "--help", "--cracked", "--ignored", "--update-db"} for x in arguments),
                   interactive=True, cwd=str(directory))


def validate_edit(text, original, scope):
    """Keep the executable; bounded profiles enforce scope, native HIFI owns its options."""
    argv = shlex.split(text)
    if not argv or argv[0] != original.argv[0]:
        raise ValueError("Keep this profile's executable. Select another tool from the menu.")
    if any(c in text for c in "\n\r\x00") or any(x in argv for x in [";", "&&", "||", "|", ">", "<", "&"]):
        raise ValueError("Enter one command, without shell operators or redirection.")
    tool = argv[0]
    if tool == "hifi" and argv[:2] != ["hifi", "engine"]:
        raise ValueError("Keep the hifi engine command prefix.")
    if original.interactive:
        if tool != "hifi":
            raise ValueError("Native terminal mode is reserved for HIFI.")
        return engine_exploit(argv[2:], original.cwd)
    if tool == "iw":
        valid = [["iw", "dev"], ["iw", "list"]]
        if scope.interface:
            valid.extend([["iw", "dev", scope.interface] + tail for tail in [["info"], ["link"], ["station", "dump"]]])
        if argv not in valid:
            raise ValueError("Supported iw views: dev, list, or dev <selected interface> info/link/station dump.")
    elif tool == "hifi":
        # Reordering and verbosity are editable; capture target and method stay fixed.
        valued = {"-i", "-b", "-c"}
        flags = {x for x in original.argv if x.startswith("--")} | {"-v", "-vv", "-vvv"}
        settings, switches = {}, []
        i = 2
        while i < len(argv):
            key = argv[i]
            if key in valued and i + 1 < len(argv):
                if key in settings:
                    raise ValueError("Duplicate target options are not supported.")
                settings[key] = argv[i + 1]
                i += 2
            elif key in flags:
                switches.append(key)
                i += 1
            else:
                raise ValueError(f"Unsupported HIFI profile option: {key}")
        expected = {x: original.argv[original.argv.index(x) + 1] for x in valued}
        required = {x for x in original.argv if x.startswith("--")}
        if settings != expected or not required.issubset(switches):
            raise ValueError("Keep this profile's target and method flags; change the session scope or select another profile.")
    elif tool == "aircrack-ng":
        if len(argv) != 6 or argv[1] != "-b" or argv[2] != scope.bssid or argv[3] != "-w":
            raise ValueError("Keep -b <selected BSSID> -w <wordlist> <capture>.")
        argv[4], argv[5] = capture_path(argv[4]), capture_path(argv[5])
    elif tool in {"ip", "rfkill", "lsusb", "nmcli", "dumpcap"}:
        # All operational parameters are editable in Scope or the command builder;
        # radio-profile invariants may not be removed in the raw command editor.
        if argv != original.argv:
            raise ValueError("Edit interface/BSSID/channel/duration or file paths in the builder, then regenerate this command.")
    elif tool == "capinfos":
        if len(argv) != 2:
            raise ValueError("Use capinfos followed by one capture path.")
        argv[1] = capture_path(argv[1])
    elif tool == "tshark":
        allowed = {"-n": 0, "-r": 1, "-Y": 1, "-T": 1, "-e": 1, "-E": 1, "-c": 1}
        seen = {}
        i = 1
        while i < len(argv):
            key = argv[i]
            if key not in allowed:
                raise ValueError(f"Unsupported analysis option: {key}")
            count = allowed[key]
            if i + count >= len(argv):
                raise ValueError(f"Missing value for {key}.")
            seen.setdefault(key, []).append(argv[i + 1] if count else True)
            i += count + 1
        if len(seen.get("-r", [])) != 1 or len(seen.get("-T", [])) != 1 or seen["-T"] != ["fields"]:
            raise ValueError("Keep one -r capture file and -T fields for offline analysis.")
        if any(len(v) != 1 for k, v in seen.items() if k not in {"-e", "-E"}):
            raise ValueError("Duplicate singleton options are not supported.")
        if "-n" not in seen:
            raise ValueError("Keep -n to disable external name resolution.")
        capture_path(seen["-r"][0])
        if "-c" in seen and (not str(seen["-c"][0]).isdigit() or int(seen["-c"][0]) < 1):
            raise ValueError("-c must be a positive packet limit.")
    else:
        raise ValueError("Unknown command profile.")
    return Command(original.title, argv, original.purpose, original.effect, original.timeout, original.root)


def monitor_preflight(scope):
    if not shutil.which("iw"):
        raise ValueError("Install iw to verify monitor mode before capturing.")
    result = subprocess.run(["iw", "dev", scope.interface, "info"], capture_output=True,
                            text=True, timeout=8, errors="replace")
    if result.returncode:
        raise ValueError("Cannot inspect the selected interface: " + result.stderr.strip())
    if not re.search(r"\btype\s+monitor\b", result.stdout):
        raise ValueError("Passive dumpcap capture needs an existing monitor interface. Use your adapter's normal setup procedure, then select it here.")
    channel = re.search(r"\bchannel\s+(\d+)\b", result.stdout)
    if not channel or int(channel.group(1)) != scope.channel:
        raise ValueError("Interface channel does not match the session. Set the adapter channel or edit the scope.")
