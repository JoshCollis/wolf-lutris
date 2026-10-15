#!/usr/bin/env python3
"""Optional isolated diagnostic using a user-supplied native BASS library.

Does not download/distribute game libraries or alter game settings. Run as the
session user, with the same PULSE_SERVER/PULSE_SINK and ALSA config as the game.
Successful initialization is not proof of complete gameplay or MIDI support.
"""
import argparse
import ctypes
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library', help='absolute path to a trusted 64-bit libbass.so')
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error('Run as the application user, not root')
    library = os.path.realpath(args.library)
    if not os.path.isabs(args.library) or not os.path.isfile(library):
        parser.error('An existing absolute library path is required')
    bass = ctypes.CDLL(library)
    bass.BASS_Init.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                              ctypes.c_void_p, ctypes.c_void_p]
    bass.BASS_Init.restype = ctypes.c_int
    bass.BASS_ErrorGetCode.restype = ctypes.c_int
    bass.BASS_GetVersion.restype = ctypes.c_uint
    bass.BASS_Free.restype = ctypes.c_int
    ok = bool(bass.BASS_Init(-1, 48000, 0, None, None))
    error = bass.BASS_ErrorGetCode()
    print(json.dumps({'initialized': ok, 'error': error,
                      'BASS_version': hex(bass.BASS_GetVersion()),
                      'scope': 'audio initialization only; not MIDI/gameplay'}))
    if ok:
        bass.BASS_Free()
    return 0 if ok and error == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
