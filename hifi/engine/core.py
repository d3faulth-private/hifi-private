# Derived from Wifite2 2.8.2 by derv82, kimocoder and contributors.
# GPL-2.0-only; see LICENSE and CREDITS.md.
# Modified by D3FAULTH on 2026-10-14 for HIFI package integration, branding,
# launcher/cleanup fixes and argument handling; see CREDITS.md for details.
#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from .config import Configuration
except (ValueError, ImportError) as e:
    raise Exception("You may need to run hifi from the root directory (which includes README.md)", e) from e


from .util.color import Color

import os
import subprocess


class HifiEngine(object):

    def __init__(self):
        """
        Initializes HIFI.
        Checks that its running under *nix, with root permissions and ensures dependencies are installed.
        """

        self.print_banner()

        Configuration.initialize(load_interface=False)

        if os.name == 'nt':
            Color.pl('{!} {R}error: {O}hifi{R} must be run under a {O}*NIX{W}{R} like OS')
            raise SystemExit(1)
        if os.getuid() != 0 and not (Configuration.show_cracked or Configuration.show_ignored or Configuration.update_db):
            Color.pl('{!} {R}error: {O}hifi{R} must be run as {O}root{W}')
            Color.pl('{!} {R}re-run with {O}sudo{W}')
            raise SystemExit(1)

        if not (Configuration.show_cracked or Configuration.show_ignored or Configuration.update_db):
            from .tools.dependency import Dependency
            Dependency.run_dependency_check()

    def start(self):
        """
        Starts target-scan + attack loop, or launches utilities depending on user input.
        """
        from .model.result import CrackResult
        from .model.handshake import Handshake
        from .util.crack import CrackHelper

        if Configuration.show_cracked:
            CrackResult.display('cracked')

        elif Configuration.show_ignored:
            CrackResult.display('ignored')

        elif Configuration.check_handshake:
            Handshake.check()

        elif Configuration.crack_handshake:
            CrackHelper.run()

        elif Configuration.update_db:
            from .util.dbupdater import DBUpdater
            DBUpdater.run()

        else:
            Configuration.get_monitor_mode_interface()
            self.scan_and_attack()

    @staticmethod
    def print_banner():
        Color.pl('{G}D3FAULTH  /  H I F I{W}  {D}v%s{W}' % Configuration.version)
        Color.pl('{C}INSPECT. UNDERSTAND. EXPLOIT.{W}')
        Color.pl('{D}GPL-2.0-only · No warranty · License and credits included with source{W}')
        Color.pl('')

    @staticmethod
    def scan_and_attack():
        """
        1) Scans for targets, asks user to select targets
        2) Attacks each target
        """
        from .util.scanner import Scanner
        from .attack.all import AttackAll

        Color.pl('')

        # Scan (no signal handler during scanning to allow proper target selection)
        s = Scanner()
        do_continue = s.find_targets()
        targets = s.select_targets()

        # Attack modules handle KeyboardInterrupt properly, no global handler needed

        if Configuration.infinite_mode:
            while do_continue:
                AttackAll.attack_multiple(targets)
                do_continue = s.update_targets()
                if not do_continue:
                    break
                targets = s.select_targets()
            attacked_targets = s.get_num_attacked()
        else:
            # Attack
            attacked_targets = AttackAll.attack_multiple(targets)

        Color.pl('{+} Finished attacking {C}%d{W} target(s), exiting' % attacked_targets)




def main():
    """Run one engine session, preserving failure and argparse exit statuses."""
    import signal
    import sys
    code = 0
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        engine = HifiEngine()
        engine.start()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except KeyboardInterrupt:
        Color.pl('\n{!} {O}Interrupted, shutting down...{W}')
        code = 130
    except Exception as exc:
        Color.pl('\n{!} {R}HIFI error:{W} %s' % str(exc))
        if Configuration.verbose:
            Color.pexception(exc)
        code = 1
    finally:
        try:
            from .util.process import ProcessManager
            ProcessManager().cleanup_all()
            try:
                Configuration.exit_gracefully()
            except SystemExit:
                pass
        except Exception as exc:
            Color.pl('{!} {O}Cleanup incomplete:{W} %s' % str(exc))
            if code == 0:
                code = 1
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
