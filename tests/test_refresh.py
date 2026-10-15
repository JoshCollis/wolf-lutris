import importlib.util
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest

RUNTIME=Path(__file__).resolve().parents[1]/'overlay/opt/wolf-lutris'
sys.path.insert(0,str(RUNTIME))
import refresh


class RefreshTests(unittest.TestCase):
    def test_refresh_has_no_implicit_60hz(self):
        with self.assertRaises((ValueError,RuntimeError)):refresh.negotiated_refresh({})
        self.assertEqual(refresh.negotiated_refresh({'GAMESCOPE_REFRESH':'240'}),240)

    def test_parent_current_mode_only(self):
        # Real AF_UNIX wire exchange; no renderer/device/display changes.
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'wl')
            server=socket.socket(socket.AF_UNIX);server.bind(path);server.listen(1)
            errors=[]
            def serve():
                try:
                    with server.accept()[0] as peer:
                        peer.settimeout(2)
                        def read(n):
                            data=b''
                            while len(data)<n:
                                chunk=peer.recv(n-len(data))
                                if not chunk:raise RuntimeError('early disconnect')
                                data+=chunk
                            return data
                        def request():
                            obj,word=struct.unpack('II',read(8));return obj,word&65535,read((word>>16)-8)
                        def send(obj,op,payload):peer.sendall(struct.pack('II',obj,((len(payload)+8)<<16)|op)+payload)
                        request();request()
                        name=b'wl_output\0'
                        send(2,0,struct.pack('II',20,len(name))+name+b'\0\0'+struct.pack('I',2))
                        send(3,0,struct.pack('I',0))
                        request();request()
                        send(4,1,struct.pack('Iiii',2,1280,720,60000))
                        send(4,1,struct.pack('Iiii',1,2560,1440,120000))
                        send(5,0,struct.pack('I',0))
                except BaseException as exc:errors.append(exc)
                finally:server.close()
            worker=threading.Thread(target=serve,daemon=True);worker.start()
            self.assertEqual(refresh.parent_modes(path),[{'width':2560,'height':1440,'refresh_mHz':120000}])
            worker.join(timeout=3);self.assertFalse(worker.is_alive());self.assertEqual(errors,[])

    def test_parent_agreement_rejects_ambiguous_output_or_wrong_refresh(self):
        mode={'width':1920,'height':1080,'refresh_mHz':120000}
        refresh.require_parent_mode([mode],1920,1080,120)
        for modes in ([],[mode,mode]):
            with self.assertRaises(RuntimeError):refresh.require_parent_mode(modes,1920,1080,120)
        with self.assertRaises(RuntimeError):refresh.require_parent_mode([mode],1920,1080,60)


if __name__=='__main__':unittest.main()
