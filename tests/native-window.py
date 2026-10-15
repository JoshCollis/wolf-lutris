#!/usr/bin/env python3
"""Tiny real GTK client to verify focus, resize, maximize and transient dialogs."""
from pathlib import Path
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

window = Gtk.Window(title='Harness Native Window')
window.set_default_size(400, 250)
window.connect('destroy', Gtk.main_quit)
window.add(Gtk.Label(label='Native X11 application under Openbox'))
window.show_all()


def dialog_requested():
    if not Path(sys.argv[1]).exists():
        return True
    dialog = Gtk.MessageDialog(transient_for=window, modal=True,
                               message_type=Gtk.MessageType.INFO,
                               buttons=Gtk.ButtonsType.OK, text='Harness Transient Dialog')
    dialog.set_title('Harness Transient Dialog')
    dialog.connect('response', lambda widget, _: widget.destroy())
    dialog.show_all()
    return False


GLib.timeout_add(100, dialog_requested)
Gtk.main()
