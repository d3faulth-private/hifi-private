# Derived from Wifite2 2.8.2 by derv82, kimocoder and contributors.
# GPL-2.0-only; see LICENSE and CREDITS.md.
# Modified by D3FAULTH on 2026-10-14 for HIFI package integration, branding,
# launcher/cleanup fixes and argument handling; see CREDITS.md for details.
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .dependency import Dependency


class Iw(Dependency):
    dependency_required = True
    dependency_name = 'iw'
    dependency_url = 'apt install iw'

    @classmethod
    def mode(cls, iface, mode_name):
        from ..util.process import Process

        if mode_name == "monitor":
            return Process.call(f'iw {iface} set monitor control')
        else:
            return Process.call(f'iw {iface} type {mode_name}')

    @classmethod
    def get_interfaces(cls, mode=None):
        from ..util.process import Process
        import re

        ireg = re.compile(r"\s+Interface\s[a-zA-Z\d]+")
        mreg = re.compile(r"\s+type\s[a-zA-Z]+")

        interfaces = set()
        iface = ''

        (out, err) = Process.call('iw dev')
        if mode is None:
            for line in out.split('\n'):
                if ires := ireg.search(line):
                    interfaces.add(ires.group().split("Interface")[-1])
        else:
            for line in out.split('\n'):
                ires = ireg.search(line)
                if mres := mreg.search(line):
                    if mode == mres.group().split("type")[-1][1:]:
                        interfaces.add(iface)
                if ires:
                    iface = ires.group().split("Interface")[-1][1:]

        return list(interfaces)

    @classmethod
    def is_monitor(cls, iface):
        """Check if the given interface is in monitor mode"""
        monitor_interfaces = cls.get_interfaces(mode='monitor')
        return iface in monitor_interfaces
