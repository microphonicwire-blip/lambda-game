# entry point for the packaged exe. runs the downloaded current.py if there is one,
# otherwise the copy bundled inside the exe
import os
import runpy
import sys
import traceback

# common stdlib + pygame so updated game code can use them without rebuilding the exe
import base64, collections, colorsys, copy, dataclasses, datetime, enum, functools  # noqa
import hashlib, heapq, itertools, json, math, pathlib, queue, random, re, shutil  # noqa
import socket, ssl, string, struct, subprocess, tempfile, textwrap, threading, time  # noqa
import typing, urllib.parse, urllib.request, zlib  # noqa
import pygame  # noqa
import numpy  # noqa  (gas lab)
import pygame.surfarray  # noqa
try:
    import certifi  # noqa  (https certs for the updater)
except ImportError:
    pass


def data_dir():
    p = os.environ.get('LOGICSIM_SAVE')
    if p:
        return os.path.dirname(p)
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'logicsim')


def run():
    code = os.path.join(data_dir(), 'code')
    ext = os.path.join(code, 'current.py')
    if os.path.exists(ext):
        sys.path.insert(0, code)
        try:
            runpy.run_path(ext, run_name='__main__')
            return
        except Exception:
            # the downloaded version crashed or can't run in this exe: log it, fall back to the bundled one
            try:
                with open(os.path.join(data_dir(), 'crash.log'), 'w') as f:
                    f.write(traceback.format_exc())
                os.replace(ext, ext + '.bad')
                os.remove(os.path.join(data_dir(), 'version.txt'))
            except OSError:
                pass
            sys.path.remove(code)
    import current
    current.main()


if __name__ == '__main__':
    try:
        run()
    except Exception:
        try:
            os.makedirs(data_dir(), exist_ok=True)
            with open(os.path.join(data_dir(), 'crash.log'), 'w') as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        raise
