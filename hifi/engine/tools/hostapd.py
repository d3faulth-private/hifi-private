# Derived from Wifite2 2.8.2 by derv82, kimocoder and contributors.
# GPL-2.0-only; see LICENSE and CREDITS.md.
# Modified by D3FAULTH on 2026-10-14 for HIFI package integration, branding,
# launcher/cleanup fixes and argument handling; see CREDITS.md for details.
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .dependency import Dependency


class Hostapd(Dependency):
    dependency_required = False
    dependency_name = 'hostapd'
    dependency_url = 'apt install hostapd'
    pid = None

    @classmethod
    def run(cls, iface, target):

        with open('/tmp/hostapd.conf', 'w') as fout:
            fout.write(f'interface={iface}' + '\n')
            fout.write(f'ssid={target.essid}' + '\n')
            fout.write(f'channel={target.channel}' + '\n')
            fout.write('driver=nl80211\n')
        # command = [
        #     'hostapd',
        #     '/tmp/hostapd.conf'
        # ]
        # process = Process(command)

        return None

    @classmethod
    def stop(cls):
        if hasattr(cls, 'pid') and cls.pid and cls.pid.poll() is None:
            cls.pid.interrupt()
        return None
