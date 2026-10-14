"""Explicitly synthetic demo output; never touches a radio."""
from .models import Scope, Session, now

HELP = "-i -b -c --wpa --no-wps --no-pmkid --skip-crack --nodeauths --wps --wps-only --pmkid --wep --dict --crack --cracked --check"


def create_demo():
    return Session(demo=True, scope=Scope("wlan0mon", "02:11:22:33:44:55", 6, 30))


def simulate(command):
    outputs = {
        "Wireless interfaces": "phy#0\n\tInterface wlan0mon\n\t\ttype monitor\n\t\tchannel 6 (2437 MHz)\n",
        "Adapter capabilities": "Supported interface modes:\n\t* managed\n\t* monitor\nBand 1: 2.4 GHz (synthetic adapter)\n",
        "Radio blocks": "0: phy0: Wireless LAN\n\tSoft blocked: no\n\tHard blocked: no\n",
        "Interface state": "wlan0mon UP 02:aa:bb:cc:dd:ee\n",
        "USB adapters": "Bus 001 Device 002: Synthetic demo Wi-Fi adapter\n",
        "Selected interface": "Interface wlan0mon\n\ttype monitor\n\tchannel 6 (2437 MHz)\n",
        "Cached Wi-Fi networks": "HIFI-LAB:02\\:11\\:22\\:33\\:44\\:55:6:82:WPA2\n",
        "Full HIFI Exploit": "Native HIFI would open here with its own target selection and prompts.\n"
                               "No options are suppressed. No password or PIN was recovered in this demo.\n",
    }
    record = {"title": command.title, "argv": command.argv, "effect": command.effect,
            "started": now(), "status": "simulated", "returncode": 0, "elapsed": 0,
            "output": "[DEMO: SIMULATED, NO COMMAND EXECUTED]\n" + outputs.get(command.title, "This is a workflow preview. No packets or capture files were produced.\n")}
    if command.interactive:
        record.update(mode="native-engine", cwd=command.cwd)
    return record
