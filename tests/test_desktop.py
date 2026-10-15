import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
OVERLAY=ROOT/'overlay'
SCRIPT=OVERLAY/'opt/wolf-lutris/desktop.py'


class DesktopTests(unittest.TestCase):
    def test_desktop_exists_and_import_is_safe(self):
        self.assertTrue(SCRIPT.exists(),'private Openbox session implementation missing')
        spec=importlib.util.spec_from_file_location('desktop',SCRIPT)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))

    def run_desktop(self,wm,app):
        self.assertTrue(SCRIPT.exists(),'private Openbox session implementation missing')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);binary=path/'openbox';binary.write_text('#!/bin/sh\n'+wm+'\n');binary.chmod(0o755)
            return subprocess.run([sys.executable,str(SCRIPT),sys.executable,'-c',app],
                                  env=os.environ|{'PATH':str(path)+':'+os.environ['PATH']},timeout=10).returncode

    def test_client_status_is_preserved(self):
        self.assertEqual(self.run_desktop('exec sleep 60','raise SystemExit(23)'),23)

    def test_wm_loss_is_failure_even_when_client_exits_cleanly(self):
        self.assertEqual(self.run_desktop('exit 0','import time; time.sleep(1)'),1)

    def test_term_cleans_up_client(self):
        self.assertTrue(SCRIPT.exists(),'private Openbox session implementation missing')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);wm=p/'openbox';wm.write_text('#!/bin/sh\nexec sleep 60\n');wm.chmod(0o755)
            pidfile=p/'pid'
            app=f'import os,time; open({str(pidfile)!r},"w").write(str(os.getpid())); time.sleep(60)'
            child=subprocess.Popen([sys.executable,str(SCRIPT),sys.executable,'-c',app],env=os.environ|{'PATH':str(p)+':'+os.environ['PATH']},start_new_session=True)
            try:
                deadline=time.monotonic()+3
                while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(pidfile.exists())
                child.send_signal(signal.SIGTERM);self.assertEqual(child.wait(timeout=8),0)
                with self.assertRaises(ProcessLookupError):os.kill(int(pidfile.read_text()),0)
            finally:
                if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait()


class HookContracts(unittest.TestCase):
    def test_startup_unprivileged_tini_and_argv(self):
        p=OVERLAY/'opt/gow/startup.sh';self.assertTrue(p.exists())
        text=p.read_text();self.assertIn('tini -s --',text);self.assertIn('"$@"',text);self.assertIn('id -u',text)

    def test_early_hook_keeps_exact_socket_without_recursive_chown(self):
        p=OVERLAY/'etc/cont-init.d/05-lutris-runtime.sh';self.assertTrue(p.exists())
        text=p.read_text();self.assertIn('WOLF_LUTRIS_PARENT_WAYLAND',text)
        self.assertNotIn('chown -R',text);self.assertIn('/run/user/',text)

    def test_user_hook_never_deletes_existing_account_or_recursive_home_ownership(self):
        p=OVERLAY/'etc/cont-init.d/10-setup_user.sh';self.assertTrue(p.exists())
        text=p.read_text();self.assertNotIn('userdel',text);self.assertNotIn('chown -R',text)
        self.assertNotIn('usermod',text)  # usermod -d/-u can move or recursively chown home
        self.assertIn('/var/lutris',text)

    def test_alsa_uses_pulse_without_user_asoundrc(self):
        p=OVERLAY/'etc/alsa/conf.d/99-wolf-pulse.conf';self.assertTrue(p.exists())
        text=p.read_text();self.assertIn('pcm.!default',text);self.assertIn('ctl.!default',text)
        self.assertEqual(text.count('type pulse'),2);self.assertNotIn('server',text)


if __name__=='__main__':unittest.main()
