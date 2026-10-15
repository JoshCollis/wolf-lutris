"""Pure contracts plus real isolated subprocess/lease lifecycle tests."""
import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'overlay/opt/wolf-lutris'
sys.path.insert(0, str(RUNTIME))


def load(name):
    path = RUNTIME / (name + '.py')
    if not path.exists():
        raise AssertionError('runtime implementation missing: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.s = load('session')

    def test_negotiation_requires_all_values_without_60hz_default(self):
        for env in ({}, {'GAMESCOPE_WIDTH':'1920','GAMESCOPE_HEIGHT':'1080'},
                    {'GAMESCOPE_WIDTH':'1920','GAMESCOPE_HEIGHT':'1080','GAMESCOPE_REFRESH':'60.0'}):
            with self.assertRaises(ValueError): self.s.requested(env)
        self.assertEqual(self.s.requested(dict(GAMESCOPE_WIDTH='2560', GAMESCOPE_HEIGHT='1440', GAMESCOPE_REFRESH='120')), (2560,1440,120))

    def test_mode_mismatch_and_parent_loss_override_clean_app_exit(self):
        mode = [{'width':1920,'height':1080,'refresh_mHz':120000}]
        self.assertEqual(self.s.completed(0,(1920,1080,120),mode),0)
        self.assertEqual(self.s.completed(0,(1920,1080,60),mode),75)
        self.assertEqual(self.s.completed(0,(1920,1080,120),[]),75)
        self.assertEqual(self.s.completed(-15,(1920,1080,120),mode),143)

    def test_lease_excludes_writers_and_rejects_symlink_and_fifo(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            with self.s.lease(home):
                with self.assertRaises(BlockingIOError): self.s.lease(home)
            self.s.lease(home).close()
            lock=home/'.wolf-lutris.lock';lock.unlink();lock.symlink_to(home/'target')
            with self.assertRaises(OSError): self.s.lease(home)
            lock.unlink();os.mkfifo(lock)
            with self.assertRaisesRegex(ValueError,'regular'): self.s.lease(home)

    def test_private_runtime_rejects_wrong_permissions_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.s.validate_runtime(p)
            p.chmod(0o755)
            with self.assertRaises(ValueError):self.s.validate_runtime(p)
            p.chmod(0o700);link=p/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):self.s.validate_runtime(link)

    def test_exact_parent_socket_required(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wayland-9'
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(p))
                self.assertEqual(self.s.parent_socket({'WOLF_LUTRIS_PARENT_WAYLAND':str(p)}),str(p))
                with self.assertRaises(ValueError):self.s.parent_socket({'WAYLAND_DISPLAY':str(p)})

    def test_native_argv_and_private_x11_environment(self):
        self.assertEqual(self.s.client_args([]),['/usr/bin/lutris'])
        self.assertEqual(self.s.client_args(['/bin/true']),['/bin/true'])
        env=self.s.desktop_environment({'WAYLAND_DISPLAY':'old','WAYLAND_SOCKET':'3','DBUS_SESSION_BUS_ADDRESS':'old','PULSE_SERVER':'unix:/audio','HOME':'/home/retro'})
        self.assertNotIn('WAYLAND_DISPLAY',env);self.assertNotIn('WAYLAND_SOCKET',env)
        self.assertNotIn('DBUS_SESSION_BUS_ADDRESS',env)
        self.assertEqual(env['PULSE_SERVER'],'unix:/audio');self.assertEqual(env['GDK_BACKEND'],'x11')

    def test_xwayland_cannot_inherit_wayland_fd_override(self):
        env=self.s.xwayland_environment({'WAYLAND_SOCKET':'9','WAYLAND_DISPLAY':'wrong'},'/exact/socket')
        self.assertNotIn('WAYLAND_SOCKET',env)
        self.assertEqual(env['WAYLAND_DISPLAY'],'/exact/socket')

    def test_xwayland_command_is_authenticated_rootful_not_rootless(self):
        args=self.s.xwayland_args((1920,1080,120),'/private/auth')
        self.assertIn('-fakescreenfps',args);self.assertEqual(args[args.index('-fakescreenfps')+1],'120')
        self.assertIn('-fullscreen',args);self.assertNotIn('-rootless',args)
        self.assertEqual(args[args.index('-auth')+1],'/private/auth')
        self.assertEqual(args[args.index('-nolisten')+1],'tcp')

    def test_shutdown_kills_own_group_even_after_leader_exits(self):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
        self.s.shutdown([child],timeout=.1)
        self.assertIsNotNone(child.poll())
        with self.assertRaises(ProcessLookupError):os.killpg(child.pid,0)

    def test_monitor_prioritizes_parent_failure_over_app_exit(self):
        class Child:
            def __init__(self,code):self.returncode=code
            def poll(self):return self.returncode
        self.assertEqual(self.s.monitor(Child(0),Child(0),(1920,1080,120),lambda:[],lambda:False),75)
        self.assertEqual(self.s.monitor(Child(0),Child(0),(1920,1080,120),lambda:[{'width':1920,'height':1080,'refresh_mHz':120000}],lambda:False),1)
        def lost():raise OSError('gone')
        self.assertEqual(self.s.monitor(Child(None),Child(0),(1920,1080,120),lost,lambda:False),75)

    def test_startup_failure_keeps_home_leased_until_children_stopped(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);sockpath=p/'parent'
            env={'HOME':d,'XDG_RUNTIME_DIR':d,'WOLF_LUTRIS_PARENT_WAYLAND':str(sockpath),
                 'GAMESCOPE_WIDTH':'1920','GAMESCOPE_HEIGHT':'1080','GAMESCOPE_REFRESH':'120'}
            observed=[]
            def cleanup(children, timeout=5):
                if children:
                    try:
                        handle=self.s.lease(p)
                    except BlockingIOError:
                        observed.append('held')
                    else:
                        handle.close();observed.append('released too early')
            class Child:
                returncode=1
                def poll(self):return 1
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(sockpath))
                with patch.dict(os.environ,env,clear=True), patch.object(self.s,'parent_modes',return_value=[{'width':1920,'height':1080,'refresh_mHz':120000}]), patch.object(self.s.subprocess,'run'), patch.object(self.s.subprocess,'Popen',return_value=Child()), patch.object(self.s,'shutdown',side_effect=cleanup):
                    with self.assertRaisesRegex(RuntimeError,'before readiness'):self.s.main([])
            self.assertEqual(observed,['held'])

    def test_parent_loss_during_x_readiness_requires_recreation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);sockpath=p/'parent'
            env={'HOME':d,'XDG_RUNTIME_DIR':d,'WOLF_LUTRIS_PARENT_WAYLAND':str(sockpath),
                 'GAMESCOPE_WIDTH':'1920','GAMESCOPE_HEIGHT':'1080','GAMESCOPE_REFRESH':'120'}
            class Child:
                def poll(self):return None
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(sockpath))
                with patch.dict(os.environ,env,clear=True), patch.object(self.s,'parent_modes',side_effect=[[{'width':1920,'height':1080,'refresh_mHz':120000}],OSError('parent gone')]), patch.object(self.s.subprocess,'run'), patch.object(self.s.subprocess,'Popen',return_value=Child()), patch.object(self.s,'shutdown'):
                    self.assertEqual(self.s.main(['/bin/true']),75)
            self.assertEqual(list(p.glob('wolf-lutris.Xauthority-*')),[])

    def test_initial_parent_failure_returns_recreation_before_spawning(self):
        from unittest.mock import patch
        for failure in (OSError('parent gone'), RuntimeError('malformed output'),
                        [{'width':1920,'height':1080,'refresh_mHz':60000}]):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                p=Path(d); sockpath=p/'parent'
                env={'HOME':d,'XDG_RUNTIME_DIR':d,'WOLF_LUTRIS_PARENT_WAYLAND':str(sockpath),
                     'GAMESCOPE_WIDTH':'1920','GAMESCOPE_HEIGHT':'1080','GAMESCOPE_REFRESH':'120'}
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.bind(str(sockpath))
                    kwargs={'side_effect':failure} if isinstance(failure,Exception) else {'return_value':failure}
                    with patch.dict(os.environ,env,clear=True), patch.object(self.s,'parent_modes',**kwargs), patch.object(self.s.subprocess,'Popen') as spawn:
                        self.assertEqual(self.s.main([]),75)
                        spawn.assert_not_called()

    def test_seed_only_missing_config_preserves_user_files(self):
        with tempfile.TemporaryDirectory() as d:
            env={'HOME':d,'XDG_CONFIG_HOME':d+'/config'}
            self.s.seed_config(env)
            p=Path(d)/'config/lutris/system.yml'
            self.assertIn('/var/lutris/Games',p.read_text())
            p.write_text('existing: untouched\n');self.s.seed_config(env)
            self.assertEqual(p.read_text(),'existing: untouched\n')
            self.assertFalse((Path(d)/'.asoundrc').exists())


if __name__=='__main__':unittest.main()
