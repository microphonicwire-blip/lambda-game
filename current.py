#!/usr/bin/env python3
# logic gate sandbox
import colorsys
import hashlib
import io
import random
import re
import heapq
import math
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zlib
from collections import deque
import pygame
try:
    import guard       # signature + credit checks, compiled into the exe
except ImportError:
    guard = None
try:
    import numpy as np          # only the gas lab needs it
    import pygame.surfarray     # noqa
except ImportError:
    np = None

C = 24              # cell size
PAL_W = 144         # palette width (multiple of C so the grid lines up)
HDR = 14            # part header height
GLOW = 0.07         # lamps/displays stay lit this long (s) so fast blinks are visible
MAX_RATE = 4000
SAVE_EVERY = 0.5    # min seconds between autosaves
MAX_LABEL = 20
MAX_DESC = 60
MAX_DEPTH = 5       # chips inside chips, this many levels
MIN_ZOOM, MAX_ZOOM = 0.25, 3.0
CAMX = CAMY = 0.0   # world pixel under the top-left of the work area
ZOOM = 1.0
DPER = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]   # delay / extender lengths
RU = 12             # wire router grid, half a cell
MARGIN = 15         # wires keep this far from parts when they can
PERIODS = [5, 10, 25, 50, 100, 250, 500, 1000]   # clock half-periods in ticks
MONO = 'dejavusansmono,consolas,couriernew,menlo,monospace'
SANS = 'segoeui,helveticaneue,inter,dejavusans,arial'
TOPH = 44           # top bar height (circuit screen)
RPW = 248           # parts panel width, on the right
VX0, VY0 = 0, TOPH  # where the work area starts on screen
FONT = None         # set by App, used to size LABEL parts
ICON_MODE = False   # drawing a tiny part preview: no text


def w2s(x, y):
    # world pixels -> screen pixels
    return VX0 + (x - CAMX) * ZOOM, VY0 + (y - CAMY) * ZOOM


def s2w(x, y):
    return (x - VX0) / ZOOM + CAMX, (y - VY0) / ZOOM + CAMY


def sc(v, lo=1):
    # scale a size with the zoom
    return max(lo, int(v * ZOOM))


def label_w(text):
    # width in cells for a LABEL part
    return max(1, -(-(FONT.size(text)[0] + 8) // C))


# auto update: set this to "owner/repo" to turn it on, e.g. "max/logicsim"
GITHUB_REPO = "microphonicwire-blip/lambda-game"
GITHUB_BRANCH = "main"
# current.py in the repo is the game itself: it replaces whatever file is running
REPO_MAIN = "current.py"
# other repo files that get synced too (text ones are compared ignoring CRLF)
TEXT_EXT = ('.py', '.txt', '.json')
SYNC_EXT = TEXT_EXT + ('.png', '.jpg', '.wav', '.ogg', '.ttf')
SKIP = ('launcher.py', 'guard.py', 'entry.py')     # only used to build the exe
UPDATE_IMG = 'update.png'       # shown on the update notice
CHECK_FILE = 'check.txt'        # signature of current.py
AUTHOR = 'Max, Keaton Technologies'
_CR_A = 'logic sandbox by Max, Keaton Technologies'
_CR_B = 'Max, Keaton Technologies'


def local_path(path):
    if path == REPO_MAIN:
        return MAIN_LOCAL
    return os.path.join(APP_DIR, *path.split('/'))


def save_path():
    p = os.environ.get('LOGICSIM_SAVE')
    if p:
        return p
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'logicsim', 'save.json')


def version_path():
    return os.path.join(os.path.dirname(save_path()), 'version.txt')


FROZEN = getattr(sys, 'frozen', False)      # running as the packaged exe
if FROZEN:
    # the exe can't overwrite itself, so updates live next to the save and the launcher runs them
    APP_DIR = os.path.join(os.path.dirname(save_path()), 'code')
    MAIN_LOCAL = os.path.join(APP_DIR, REPO_MAIN)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    MAIN_LOCAL = os.path.abspath(__file__)


def read_local(path):
    try:
        with open(local_path(path), 'rb') as f:
            return f.read()
    except OSError:
        if FROZEN and path == REPO_MAIN:    # no downloaded copy yet, use the one inside the exe
            try:
                with open(os.path.join(sys._MEIPASS, REPO_MAIN), 'rb') as f:
                    return f.read()
            except OSError:
                pass
        return None


def github_token():
    # only needed for a private repo: env var or a token.txt next to the game
    t = os.environ.get('LOGICSIM_TOKEN')
    if t:
        return t.strip()
    for d in (APP_DIR, os.path.dirname(save_path())):
        try:
            with open(os.path.join(d, 'token.txt')) as f:
                return f.read().strip()
        except OSError:
            pass
    return ''


# ---------------------------------------------------------------- themes
THEMES = {
    'dark': dict(
        BG=(11, 19, 36), GRID=(21, 35, 58), GRID2=(29, 48, 80),
        PANEL=(13, 22, 40), PANEL_LINE=(44, 72, 118),
        PART_BG=(17, 27, 48), PART_LINE=(74, 112, 172),
        TEXT=(214, 228, 248), TEXT_DIM=(104, 130, 170),
        ON=(72, 210, 255), OFF=(62, 156, 100), FLOAT=(150, 170, 205), SHORT=(232, 72, 72),
        SEL=(255, 208, 80), ACTIVE=(22, 64, 96), LAMP_ON=(255, 226, 120),
        SEG_OFF=(27, 40, 68), SEG_DEFAULT=(240, 245, 255), PREVIEW=(150, 190, 235),
        HDR_LOGIC=(92, 70, 160), HDR_INPUT=(176, 112, 38), HDR_OUTPUT=(28, 128, 140),
        HDR_MEM=(160, 58, 120), HDR_CHIP=(50, 112, 190), HDR_TEXT=(255, 255, 255), DIM=(0, 0, 0),
        CARD=(19, 31, 54), CARD_HI=(27, 45, 76)),
    'light': dict(
        BG=(234, 240, 248), GRID=(214, 223, 236), GRID2=(196, 208, 226),
        PANEL=(222, 230, 242), PANEL_LINE=(140, 162, 196),
        PART_BG=(250, 252, 255), PART_LINE=(84, 114, 166),
        TEXT=(20, 32, 54), TEXT_DIM=(112, 126, 152),
        ON=(0, 118, 214), OFF=(34, 140, 80), FLOAT=(96, 110, 142), SHORT=(212, 52, 52),
        SEL=(226, 140, 0), ACTIVE=(206, 230, 250), LAMP_ON=(255, 200, 40),
        SEG_OFF=(214, 222, 236), SEG_DEFAULT=(20, 30, 50), PREVIEW=(70, 110, 170),
        HDR_LOGIC=(132, 112, 206), HDR_INPUT=(222, 150, 60), HDR_OUTPUT=(60, 164, 176),
        HDR_MEM=(200, 100, 166), HDR_CHIP=(70, 130, 210), HDR_TEXT=(255, 255, 255), DIM=(20, 30, 50),
        CARD=(246, 249, 253), CARD_HI=(232, 240, 252)),
}


def set_theme(light):
    globals().update(THEMES['light' if light else 'dark'])


set_theme(False)

# ---------------------------------------------------------------- parts
GATES = {
    'AND':  lambda v: all(v),
    'OR':   lambda v: any(v),
    'NAND': lambda v: not all(v),
    'NOR':  lambda v: not any(v),
    'XOR':  lambda v: sum(v) % 2 == 1,
    'XNOR': lambda v: sum(v) % 2 == 0,
    'NOT':  lambda v: not v[0],
    'BUF':  lambda v: bool(v[0]),
}

TWO_IN = dict(w=4, h=4, pins=[(0, 1, 'in'), (0, 3, 'in'), (4, 2, 'out')])
ONE_IN = dict(w=3, h=2, pins=[(0, 1, 'in'), (3, 1, 'out')])

DEFS = {
    'SOURCE':  dict(w=3, h=2, pins=[(3, 1, 'out')]),    # always on
    'SWITCH':  ONE_IN,                                  # passes signal while on
    'BUTTON':  ONE_IN,                                  # passes signal for 1 tick
    'GATE':    dict(w=3, h=2, pins=[(0, 1, 'in'), (3, 1, 'out'), (1, 0, 'in')]),  # EN on top
    'CLOCK':   dict(w=3, h=2, pins=[(3, 1, 'out')]),    # blinks, click to change speed
    'GAS IN':  dict(w=3, h=2, pins=[(3, 1, 'out')]),    # signal from a gas lab link, click for its id
    'GAS OUT': dict(w=3, h=2, pins=[(0, 1, 'in')]),     # sends its input to the gas lab link with the same id
    'DELAY':   dict(w=3, h=2, pins=[(0, 1, 'in'), (3, 1, 'out')]),    # same signal, N ticks late
    'EXTENDER': dict(w=3, h=2, pins=[(0, 1, 'in'), (3, 1, 'out')]),   # keeps it high N ticks longer
    'LAMP':    dict(w=2, h=2, pins=[(0, 1, 'in')]),
    'LABEL':   dict(w=1, h=1, pins=[]),                 # just text, no ports
    # touch display: a display you can click, pulses OUT when clicked
    'TOUCH':   dict(w=1, h=1, pins=[(0, 0, 'in'), (1, 0, 'in'), (0, 1, 'in'), (1, 1, 'out')]),
    'DISPLAY': dict(w=1, h=1, pins=[(0, 0, 'in'), (1, 0, 'in'), (0, 1, 'in')]),
    # 7 segments on the left, then red green blue along the bottom
    'SCOPE':   dict(w=7, h=4, pins=[(0, 2, 'in')]),     # draws what its input did lately
    '7SEG':    dict(w=5, h=8, pins=[(0, k, 'in') for k in range(1, 8)]
                    + [(1, 8, 'in'), (2, 8, 'in'), (3, 8, 'in')]),
    # PIN = the port of a chip. PIN_O is the same part flipped (chip output)
    'PIN':     dict(w=3, h=2, pins=[(3, 1, 'io')]),
    'PIN_O':   dict(w=3, h=2, pins=[(0, 1, 'io')]),
    'CHIP':    dict(w=4, h=2, pins=[]),         # real size/pins come from its circuit
    'NOT': ONE_IN, 'BUF': ONE_IN,
    'TOGGLE': ONE_IN,                          # flips its output on every rising edge of IN
    'SR LATCH': TWO_IN, 'NV LATCH': TWO_IN,    # NV keeps its state in the save file
    'AND': TWO_IN, 'NAND': TWO_IN, 'OR': TWO_IN,
    'NOR': TWO_IN, 'XOR': TWO_IN, 'XNOR': TWO_IN,
}
NAMES = {'DISPLAY': ['R', 'G', 'B'], 'TOUCH': ['R', 'G', 'B', 'OUT'], 'GATE': ['IN', 'OUT', 'EN'],
         'SR LATCH': ['S', 'R', 'Q'], 'NV LATCH': ['S', 'R', 'Q'],
         '7SEG': ['SEG A', 'SEG B', 'SEG C', 'SEG D', 'SEG E', 'SEG F', 'SEG G',
                  'RED', 'GREEN', 'BLUE']}

PAL_ITEMS = ['SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GATE', 'LAMP', 'DISPLAY', 'TOUCH', '7SEG', 'SCOPE',
             'NOT', 'BUF', 'TOGGLE', 'DELAY', 'EXTENDER', 'AND', 'NAND', 'OR', 'NOR', 'XOR', 'XNOR',
             'SR LATCH', 'NV LATCH', 'GAS IN', 'GAS OUT', 'PIN', 'LABEL']

PAL_CATS = [('INPUT', ['SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GAS IN']),
            ('OUTPUT', ['LAMP', 'DISPLAY', 'TOUCH', '7SEG', 'SCOPE', 'GAS OUT']),
            ('LOGIC', ['GATE', 'NOT', 'BUF', 'AND', 'NAND', 'OR', 'NOR', 'XOR', 'XNOR']),
            ('MEMORY', ['SR LATCH', 'NV LATCH', 'TOGGLE', 'DELAY', 'EXTENDER']),
            ('CHIPS', ['PIN']),
            ('OTHER', ['LABEL'])]
PAL_NICE = {'7SEG': '7-segment', 'GAS IN': 'Gas in', 'GAS OUT': 'Gas out', 'SR LATCH': 'SR latch',
            'NV LATCH': 'NV latch', 'PIN': 'Chip pin', 'GATE': 'Pass gate'}
ICON_TXT = {'SOURCE': 'ON', 'CLOCK': 'CLK', 'GAS IN': 'GAS', 'GAS OUT': 'GAS', 'LAMP': '', 'GATE': 'GATE',
            'SR LATCH': 'SR', 'NV LATCH': 'NV', 'TOGGLE': 'T', 'DELAY': 'DLY', 'EXTENDER': 'EXT',
            'LABEL': 'Aa'}
S_ALIAS = {'BTN': 'BUTTON', 'SW': 'SWITCH', 'LED': 'LAMP', 'SEG': '7SEG', 'CLK': 'CLOCK'}
HELP2 = [('enter', 'compile / build'), ('drag from panel', 'add a part'), ('pin to pin', 'draw a wire'),
         ('drag background', 'box select'), ('ctrl+click', 'add to selection'), ('ctrl+c x v a', 'copy cut paste all'),
         ('del', 'delete'), ('g', 'make a chip'), ('u', 'open a chip'), ('ctrl+s', 'save chip (asks a name)'),
         ('drag chip to panel', 'save it as a chip'),
         ('wheel', 'zoom'), ('rmb drag', 'pan'), ('home', 'reset view'), ('rmb click', 'delete'),
         ('double-click', 'rename'), ('space / n', 'pause / step'), ('up / down', 'speed'),
         ('l', 'light / dark'), ('tab', 'gas lab'), ('` (backtick)', 'script panel'),
         ('ctrl+enter', 'run script'), ('ctrl+f', 'search parts'), ('f5', 'check for update')]
S_HELP = [('on NAME', 'switch on'), ('off NAME', 'switch off'), ('toggle NAME', 'flip a switch'),
          ('press NAME', 'press a button'), ('wait 10', 'ticks (or 0.5s, 200ms)'),
          ('', ''), ('NAME', 'a label you gave a part'), ('', 'or KIND#n, like SWITCH#1'),
          ('# comment', 'NAMES tab lists them all'), ('', ''),
          ('one step per line, top to bottom,', ''), ('a wait pauses the macro.', '')]
RUN_KEYS = {pygame.K_SPACE, pygame.K_UP, pygame.K_DOWN, pygame.K_l, pygame.K_t,
            pygame.K_n, pygame.K_HOME, pygame.K_TAB, pygame.K_RETURN, pygame.K_KP_ENTER}
SEG_NAMES = 'abcdefg'
# kinds with an editable description in the body (double-click the empty space)
DESC_KINDS = set(GATES) | {'SOURCE', 'SWITCH', 'BUTTON', 'GATE', 'LAMP', 'SR LATCH', 'NV LATCH', 'TOGGLE'}
DEFAULT_DESC = {'AND': 'both high', 'OR': 'any high', 'NAND': 'not both', 'NOR': 'none high',
                'XOR': 'odd count', 'XNOR': 'even count', 'NOT': 'inverts', 'BUF': 'copies',
                'SOURCE': 'always on', 'LAMP': 'glows', 'GATE': 'EN opens it',
                'SR LATCH': 'S sets, R resets', 'NV LATCH': 'remembers', 'BUTTON': '1 pulse',
                'TOGGLE': 'flips each pulse'}
IND_KINDS = ('LAMP', 'DISPLAY', 'TOUCH', '7SEG')
SCOPE_LEN = 160
WIDGET_KINDS = ('SWITCH', 'BUTTON')     # these draw a little control in the body


def cat_color(kind):
    if kind in ('SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GAS IN'):
        return HDR_INPUT
    if kind in ('LAMP', 'DISPLAY', 'TOUCH', '7SEG', 'GAS OUT', 'SCOPE'):
        return HDR_OUTPUT
    if kind in ('SR LATCH', 'NV LATCH'):
        return HDR_MEM
    if kind == 'LABEL':
        return TEXT_DIM
    if kind in ('CHIP', 'PIN') or kind.startswith('CHIP:'):
        return HDR_CHIP
    return HDR_LOGIC


def pin_name(p, i):
    kind = p.kind
    if kind == 'CHIP':
        return p.pnames[i]
    if kind == 'PIN':
        return 'PORT'
    if kind in NAMES:
        return NAMES[kind][i]
    pins = DEFS[kind]['pins']
    if pins[i][2] == 'out':
        return 'OUT'
    ins = [j for j, p in enumerate(pins) if p[2] == 'in']
    return 'IN' if len(ins) == 1 else 'AB'[ins.index(i)]


class Part:
    _n = 0

    def __init__(self, kind, gx=0, gy=0):
        Part._n += 1
        self.uid = Part._n
        self.kind = kind
        self.d = DEFS[kind]
        self.gx, self.gy = gx, gy
        self.out = 0            # gate/switch/button output
        self.on = False         # switch state
        self.drive = False      # gate is actually driving its output
        self.pulse = False      # button pressed, passes on next tick
        self.flash = 0.0        # button click visual
        self.glow = 0.0         # lamp/display lit timer
        self.seg_glow = [0.0] * 7   # 7seg lit timers
        self.rgb = None         # display / 7seg color, None = default
        self.label = None       # custom text, None = default
        self.pidx = 0 if kind in ('GAS IN', 'GAS OUT') else 4    # clock speed (index into PERIODS) / link id - 1
        self.counter = 0        # clock ticks since last flip
        self.label_on = None    # switch names, one per state
        self.label_off = None
        self.buf = None         # delay: the signals still on their way
        self.trace = None       # scope: the last few ticks of its input, oldest first
        self.inds = []          # chip: lamps/displays inside that it shows
        self.lw = self.rw = 0   # chip: widest pin names, left and right
        self.desc = None        # body text, None = default
        self.desc_on = None     # switch: one per state
        self.desc_off = None
        self.defn = None        # chip: the saved circuit
        self.inner = None       # chip: this copy's own parts
        self.inner_wires = None
        self.pinmap = None      # chip: the PIN part behind each chip pin
        self.pnames = None

    def rect(self):
        w = self.d['w'] * C
        if self.kind == 'LABEL':
            w = label_w(self.label if self.label is not None else 'LABEL') * C
        x, y = w2s(self.gx * C, self.gy * C)
        return pygame.Rect(round(x), round(y), round(w * ZOOM), round(self.d['h'] * C * ZOOM))

    def pin_world(self, i):
        dx, dy, _ = self.d['pins'][i]
        return ((self.gx + dx) * C, (self.gy + dy) * C)

    def exit_dir(self, i):
        # which way a wire should leave this pin
        dx, dy, _ = self.d['pins'][i]
        if dx == 0:
            return (-1, 0)
        if dx == self.d['w']:
            return (1, 0)
        return (0, -1) if dy == 0 else (0, 1)

    def pin_pos(self, i):
        dx, dy, _ = self.d['pins'][i]
        x, y = w2s((self.gx + dx) * C, (self.gy + dy) * C)
        return (round(x), round(y))


def wire_pts(a, b):
    if a[0] == b[0] or a[1] == b[1]:
        return [a, b]
    wx = s2w((a[0] + b[0]) / 2, 0)[0]
    mx = round(w2s(round(wx / C) * C, 0)[0])
    return [a, (mx, a[1]), (mx, b[1]), b]


def round_pts(pts):
    # orthogonal polyline with its corners rounded off
    if len(pts) < 3:
        return pts
    R = max(3.0, 7 * ZOOM)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        d1, d2 = math.hypot(b[0] - a[0], b[1] - a[1]), math.hypot(c[0] - b[0], c[1] - b[1])
        if d1 == 0 or d2 == 0 or abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-6:
            out.append(b)
            continue
        r = min(R, d1 / 2, d2 / 2)
        p1 = (b[0] + (a[0] - b[0]) * r / d1, b[1] + (a[1] - b[1]) * r / d1)
        p2 = (b[0] + (c[0] - b[0]) * r / d2, b[1] + (c[1] - b[1]) * r / d2)
        for t in (0, 0.25, 0.5, 0.75, 1.0):
            u = 1 - t
            out.append((u * u * p1[0] + 2 * u * t * b[0] + t * t * p2[0],
                        u * u * p1[1] + 2 * u * t * b[1] + t * t * p2[1]))
    out.append(pts[-1])
    return out


def draw_wire(surf, pts, color, w):
    pts = round_pts(pts)
    if len(pts) < 2:
        return
    pygame.draw.lines(surf, color, False, pts, w)
    if w > 2:
        r = w // 2
        for q in pts[1:-1]:
            pygame.draw.circle(surf, color, (int(q[0]), int(q[1])), r)


def poly_len(pts):
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def point_at(pts, d):
    # point d pixels along an orthogonal polyline
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = abs(b[0] - a[0]) + abs(b[1] - a[1])
        if d <= seg or i == len(pts) - 2:
            t = 0 if seg == 0 else min(1.0, d / seg)
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        d -= seg
    return pts[-1]


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    cx, cy = ax + t * dx, ay + t * dy
    return ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5


# ---------------------------------------------------------------- updater
def git_blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def safe_repo_path(path):
    parts = path.split('/')
    return all(p and p not in ('.', '..') and not p.startswith('.') for p in parts)


def ssl_context():
    # packaged builds can't always find the system certs: certifi first (bundled in the exe), then the usual spots
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for f in ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt',
              '/etc/ssl/cert.pem', '/etc/ca-certificates/extracted/tls-ca-bundle.pem'):
        if os.path.exists(f):
            try:
                return ssl.create_default_context(cafile=f)
            except (ssl.SSLError, OSError):
                pass
    return ssl.create_default_context()


def log_update(msg):
    try:
        os.makedirs(os.path.dirname(save_path()), exist_ok=True)
        with open(os.path.join(os.path.dirname(save_path()), 'update.log'), 'a') as f:
            f.write(time.strftime('%H:%M:%S ') + msg + '\n')
    except OSError:
        pass


def credits_ok():
    # the credit lives in a few places, and the compiled guard knows what it should say
    if guard is None:
        return True
    try:
        return guard.seal('a', AUTHOR) and guard.seal('b', _CR_B) and _CR_A.endswith(AUTHOR)
    except Exception:
        return False


def locked_screen(surf):
    surf.fill((12, 12, 18))
    f = pygame.font.SysFont('consolas,dejavusansmono,monospace', 22)
    for i, t in enumerate(['this copy has been changed', 'it is not an official logic sandbox build',
                           'get the real one from Max, Keaton Technologies']):
        r = f.render(t, True, (230, 90, 90) if i == 0 else (200, 205, 220))
        surf.blit(r, r.get_rect(center=(surf.get_width() // 2, surf.get_height() // 2 - 30 + i * 34)))
    pygame.display.flip()


def news_path(ext):
    return os.path.join(os.path.dirname(save_path()), 'whatsnew.' + ext)


class Updater:
    # checks github on boot (and on F5) and installs whatever changed right away, then the next start says what was new
    def __init__(self, start=True, manual=False):
        self.state = 'off'      # off idle checking installing failed restart
        self.message = ''
        self.body = ''          # rest of the commit message
        self.image = None       # update.png bytes
        self.surf = None
        self.scaled = None
        self.sha = ''
        self.todo = []
        self.raw = {}           # files already downloaded by the fallback check
        self.note = ''          # one-line status for the toast
        self.manual = manual
        self.news = False       # show "what was updated" after a restart
        if os.path.exists(news_path('json')):
            try:
                with open(news_path('json'), encoding='utf-8') as f:
                    d = json.load(f)
                self.message, self.body = d.get('message', ''), d.get('body', '')
                try:
                    with open(news_path('png'), 'rb') as f:
                        self.image = f.read()
                except OSError:
                    pass
                self.news = True
            except Exception:
                self.close_news()
        if GITHUB_REPO:
            self.state = 'checking'
            if start:
                threading.Thread(target=self._check, daemon=True).start()

    def modal(self):
        return self.news or self.state in ('installing', 'failed')

    def close_news(self):
        self.news = False
        self.surf = self.scaled = self.image = None
        for e in ('json', 'png'):
            try:
                os.remove(news_path(e))
            except OSError:
                pass

    def picture(self):
        # update.png as a surface (made on the main thread)
        if self.surf is None and self.image:
            try:
                self.surf = pygame.image.load(io.BytesIO(self.image)).convert_alpha()
            except Exception:
                self.image = None
        return self.surf

    def _get(self, url, raw=False, tries=2):
        err = None
        for _ in range(tries):
            req = urllib.request.Request(url, headers={
                'User-Agent': 'logicsim', 'Cache-Control': 'no-cache',
                'Accept': 'application/vnd.github.raw' if raw else 'application/vnd.github+json'})
            tok = github_token()
            if tok and ('api.github.com' in url or 'raw.githubusercontent.com' in url):
                req.add_header('Authorization', 'Bearer ' + tok)
            try:
                with urllib.request.urlopen(req, timeout=10, context=ssl_context()) as r:
                    return r.read()
            except Exception as e:
                err = e
                time.sleep(0.5)
        raise err

    def _write_version(self, sha):
        try:
            os.makedirs(os.path.dirname(version_path()), exist_ok=True)
            with open(version_path(), 'w') as f:
                f.write(sha)
        except OSError:
            pass

    def _check(self):
        try:
            self._check_api()
        except Exception as err:
            log_update(f'api check failed: {err!r}, trying raw file')
            try:
                self._check_raw()
            except Exception as err2:
                log_update(f'raw check failed: {err2!r}')
                self.note = f'update check failed ({type(err2).__name__}), f5 to retry'
                self.state = 'idle'
                return
        if self.manual and self.state == 'idle' and not self.note:
            self.note = 'up to date'

    def _check_api(self):
        api = f'https://api.github.com/repos/{GITHUB_REPO}'
        head = json.loads(self._get(f'{api}/commits/{GITHUB_BRANCH}'))
        sha = head['sha']
        try:
            with open(version_path()) as f:
                cur = f.read().strip()
        except OSError:
            cur = ''
        if cur == sha and read_local(REPO_MAIN) is not None:
            self.state = 'idle'
            return
        tree = json.loads(self._get(f"{api}/git/trees/{head['commit']['tree']['sha']}?recursive=1"))
        todo = []
        has_main = any(t['path'] == REPO_MAIN for t in tree['tree'])
        paths = {t['path'] for t in tree['tree']}
        for t in tree['tree']:
            path = t['path']
            ext = os.path.splitext(path)[1].lower()
            if t['type'] != 'blob' or ext not in SYNC_EXT or not safe_repo_path(path) \
                    or os.path.basename(path) in SKIP or path.startswith('tools/'):
                continue
            if has_main and path != REPO_MAIN and local_path(path) == MAIN_LOCAL:
                continue        # same file as current.py, current.py wins
            local = read_local(path)
            if local is not None and ext in TEXT_EXT:
                local = local.replace(b'\r\n', b'\n')
            if local is None or git_blob_sha(local) != t['sha']:
                todo.append(path)
        if not todo:
            self._write_version(sha)     # already matches, nothing to say
            self.state = 'idle'
            return
        # the commit message that goes with the game file (not the bot commit that signs it)
        full = head['commit']['message']
        try:
            last = json.loads(self._get(f'{api}/commits?path={REPO_MAIN}&sha={GITHUB_BRANCH}&per_page=1'))
            full = last[0]['commit']['message']
        except Exception:
            pass
        full = full.strip().replace('\r\n', '\n')
        msg, _, body = full.partition('\n')
        self.sha, self.message, self.body, self.todo = sha, msg.strip(), body.strip(), todo
        if CHECK_FILE in paths and CHECK_FILE not in todo:
            self.todo.append(CHECK_FILE)
        self._fetch_image(UPDATE_IMG in paths)
        self._install()

    def _check_raw(self):
        # api down or rate limited (60 checks an hour): just compare the main file straight from github
        base = f'https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/'
        data = self._get(base + f'{REPO_MAIN}?t={int(time.time())}', raw=True)
        local = read_local(REPO_MAIN)
        if local is not None and local.replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n'):
            self.state = 'idle'
            return
        self.sha, self.message, self.body, self.todo = '', 'new version of the game', '', [REPO_MAIN, CHECK_FILE]
        self.raw = {REPO_MAIN: data}
        self._fetch_image(True)
        self._install()

    def _fetch_image(self, exists):
        if not exists:
            return
        try:
            self.image = self._fetch(UPDATE_IMG)
        except Exception as err:
            log_update(f'no update image: {err!r}')
            self.image = None

    def _fetch(self, path):
        if path in self.raw:
            return self.raw[path]
        q = urllib.parse.quote(path)
        try:
            if not self.sha:
                raise OSError('no commit yet')
            return self._get(f'https://api.github.com/repos/{GITHUB_REPO}/contents/{q}?ref={self.sha}', raw=True)
        except Exception as err:
            log_update(f'api download of {path} failed: {err!r}, trying raw')
            return self._get(f'https://raw.githubusercontent.com/{GITHUB_REPO}/{self.sha or GITHUB_BRANCH}/{q}', raw=True)

    def _install(self):
        self.state = 'installing'
        try:
            files = []
            for path in self.todo:
                try:
                    data = self._fetch(path)
                except Exception:
                    if path == CHECK_FILE:
                        continue        # no signature in the repo yet, handled below
                    raise
                if path.endswith('.py'):
                    compile(data, path, 'exec')      # don't install something that can't even parse
                files.append((path, data))
            main = dict(files).get(REPO_MAIN)
            if guard is not None and main is not None:
                # only games signed with the owner's key are installed
                chk = dict(files).get(CHECK_FILE)
                if chk is None:
                    try:
                        chk = self._fetch(CHECK_FILE)
                        files.append((CHECK_FILE, chk))
                    except Exception:
                        chk = None
                if chk is None or not guard.check_ok(main, chk.decode('utf-8', 'replace')):
                    log_update('update not signed (yet), skipped')
                    self.note = 'update is not signed yet, will try again next launch'
                    self.state = 'idle'
                    return
            for path, data in files:
                dst = local_path(path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst + '.new', 'wb') as f:
                    f.write(data)
                os.replace(dst + '.new', dst)
                log_update(f'installed {path} -> {dst}')
            if self.sha:
                self._write_version(self.sha)
            else:
                try:
                    os.remove(version_path())   # unknown commit, let the next api check sort it out
                except OSError:
                    pass
            if main is not None:
                try:
                    os.makedirs(os.path.dirname(news_path('json')), exist_ok=True)
                    with open(news_path('json'), 'w', encoding='utf-8') as f:
                        json.dump(dict(message=self.message, body=self.body), f)
                    if self.image:
                        with open(news_path('png'), 'wb') as f:
                            f.write(self.image)
                    elif os.path.exists(news_path('png')):
                        os.remove(news_path('png'))
                except OSError:
                    pass
            self.state = 'restart'
        except Exception as err:
            log_update(f'install failed: {err!r}')
            self.message = f'{type(err).__name__}: {err}'[:80]
            self.state = 'failed'

    def dismiss(self):
        self.state = 'idle'


def wrap(font, text, width):
    lines, cur = [], ''
    for word in text.split():
        t = (cur + ' ' + word).strip()
        if font.size(t)[0] <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- script (macro) panel
S_CMDS = ('on', 'off', 'toggle', 'press', 'click', 'wait')
S_TOK = re.compile(r'(#.*|//.*)|("[^"]*")|(\b\d+(?:\.\d+)?(?:ms|s)?\b)|(\S+)|(\s+)')
S_EXAMPLES = [
    ('load', '# flip a switch, press a few buttons, one after another\non SWITCH#1\nwait 10\npress BUTTON#1\nwait 5\npress BUTTON#2\nwait 5\noff SWITCH#1\n'),
    ('blink', '# flip the first switch on and off\non SWITCH#1\nwait 20\noff SWITCH#1\nwait 20\non SWITCH#1\nwait 20\noff SWITCH#1\n'),
    ('seconds', '# waits can be in seconds too\ntoggle SWITCH#1\nwait 0.5s\ntoggle SWITCH#1\nwait 200ms\npress BUTTON#1\n'),
]


def s_tokens(s):
    # split a script line into words, "quoted names" stay in one piece
    out = []
    for m in re.finditer(r'"([^"]*)"|(\S+)', s):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    return out


def s_strip(raw):
    # drop # and // comments (only where a word starts, so SWITCH#1 survives)
    q = False
    for i, ch in enumerate(raw):
        if ch == '"':
            q = not q
        elif not q and (ch == '#' or raw[i:i + 2] == '//') and (i == 0 or raw[i - 1] in ' \t'):
            return raw[:i]
    return raw


def s_dur(tok):
    # '10' ticks, '0.5s' seconds, '200ms' -> (number, unit)
    m = re.fullmatch(r'(\d+(?:\.\d+)?)(ms|s)?', tok.lower())
    if not m:
        raise ValueError(f'"{tok}" is not a time (try 10, 0.5s or 200ms)')
    return float(m.group(1)), (m.group(2) or 't')


def s_parse(text):
    # -> (program, {row: error}); a program is a list of on / off / toggle / press / wait steps
    prog, errs = [], {}
    for ln, raw in enumerate(text.split('\n')):
        s = s_strip(raw).strip()
        toks = s_tokens(s) if s else []
        if not toks:
            continue
        cmd, args = toks[0].lower(), toks[1:]
        if cmd not in S_CMDS:
            errs[ln] = f'unknown command "{toks[0]}" (on off toggle press wait)'
        elif cmd == 'wait':
            if len(args) != 1:
                errs[ln] = 'usage: wait 10   (ticks, or 0.5s, 200ms)'
                continue
            try:
                prog.append(dict(op='wait', dur=s_dur(args[0]), ln=ln))
            except ValueError as ex:
                errs[ln] = str(ex)
        elif not args:
            errs[ln] = f'usage: {cmd} NAME'
        else:
            prog.append(dict(op=cmd, names=args, ln=ln))
    return prog, errs


class Runner:
    # runs a script one sim tick at a time, so "wait 10" means ten ticks of the circuit
    def __init__(self, app):
        self.app = app
        self.active = False
        self.prog = []
        self.pc = 0
        self.wait = 0
        self.ticks = 0

    def log(self, text, kind='info'):
        self.app.log_add(f't{self.ticks} · {text}', kind)

    def start(self, text):
        app = self.app
        prog, errs = s_parse(text)
        ed = app.ed
        ed.err = dict(errs)
        for ins in prog:
            for nm in ins.get('names', ()):
                ps = app.find_parts(nm)
                if not ps:
                    ed.err[ins['ln']] = f'no part named "{nm}"'
                elif ins['op'] in ('on', 'off', 'toggle') and any(p.kind != 'SWITCH' for p in ps):
                    ed.err[ins['ln']] = f'"{nm}" is not a switch'
                elif ins['op'] in ('press', 'click') and any(p.kind not in ('BUTTON', 'TOUCH', 'SWITCH') for p in ps):
                    ed.err[ins['ln']] = f'"{nm}" is not a button'
        if ed.err:
            for ln in sorted(ed.err):
                app.log_add(f'line {ln + 1}: {ed.err[ln]}', 'err')
            app.say('fix the script first (see the log)')
            return False
        if not prog:
            app.log_add('nothing to run', 'err')
            return False
        self.prog, self.pc, self.wait, self.ticks = prog, 0, 0, 0
        self.active = True
        app.log_add('script started', 'info')
        return True

    def stop(self, why='stopped', kind='info'):
        if self.active:
            self.app.log_add(f't{self.ticks} · {why}', kind)
        self.active = False
        self.app.ed.run_row = -1

    def ticks_of(self, dur):
        v, u = dur
        if u == 's':
            v *= self.app.rate
        elif u == 'ms':
            v *= self.app.rate / 1000.0
        return max(1, int(round(v)))

    def before_tick(self):
        if not self.active:
            return
        app = self.app
        self.ticks += 1
        if self.wait > 0:
            self.wait -= 1
            if self.wait > 0:
                return
        while self.pc < len(self.prog):
            ins = self.prog[self.pc]
            self.pc += 1
            app.ed.run_row = ins['ln']
            op = ins['op']
            if op == 'wait':
                self.wait = self.ticks_of(ins['dur'])
                return
            for nm in ins['names']:
                for p in app.find_parts(nm):
                    if op == 'on':
                        p.on = True
                    elif op == 'off':
                        p.on = False
                    elif op == 'toggle' and p.kind == 'SWITCH':
                        p.on = not p.on
                    else:
                        app.run_click(p)
            self.log(f'{op} {" ".join(ins["names"])}', 'ok')
        self.stop('done', 'ok')


class Editor:
    # small multi-line text box for the script panel
    LH = 18

    def __init__(self):
        self.lines = ['']
        self.cx = self.cy = 0
        self.anchor = None
        self.scroll = 0
        self.focus = False
        self.undo, self.redo = [], []
        self.last_edit = 0
        self.last_kind = ''
        self.err = {}
        self.run_row = -1
        self.clip = ''
        self.font = None
        self.gutter = 40

    def text(self):
        return '\n'.join(self.lines)

    def set_text(self, t):
        self.lines = str(t).replace('\r', '').split('\n') or ['']
        self.cx = self.cy = 0
        self.anchor = None
        self.scroll = 0
        self.undo, self.redo = [], []
        self.err = {}

    # -- selection / editing helpers
    def sel_range(self):
        if self.anchor is None or self.anchor == (self.cx, self.cy):
            return None
        a, b = self.anchor, (self.cx, self.cy)
        if (a[1], a[0]) > (b[1], b[0]):
            a, b = b, a
        return a, b

    def selected(self):
        r = self.sel_range()
        if not r:
            return ''
        (x0, y0), (x1, y1) = r
        if y0 == y1:
            return self.lines[y0][x0:x1]
        return '\n'.join([self.lines[y0][x0:]] + self.lines[y0 + 1:y1] + [self.lines[y1][:x1]])

    def snap(self, kind):
        now = pygame.time.get_ticks()
        if kind != self.last_kind or now - self.last_edit > 700:
            self.undo.append((list(self.lines), self.cx, self.cy))
            del self.undo[:-200]
        self.redo.clear()
        self.last_kind, self.last_edit = kind, now

    def del_sel(self):
        r = self.sel_range()
        if not r:
            return False
        (x0, y0), (x1, y1) = r
        self.lines[y0:y1 + 1] = [self.lines[y0][:x0] + self.lines[y1][x1:]]
        self.cx, self.cy = x0, y0
        self.anchor = None
        return True

    def insert(self, s):
        self.del_sel()
        parts = s.replace('\r', '').split('\n')
        line = self.lines[self.cy]
        head, tail = line[:self.cx], line[self.cx:]
        if len(parts) == 1:
            self.lines[self.cy] = head + parts[0] + tail
            self.cx += len(parts[0])
        else:
            self.lines[self.cy:self.cy + 1] = [head + parts[0]] + parts[1:-1] + [parts[-1] + tail]
            self.cy += len(parts) - 1
            self.cx = len(parts[-1])
        self.anchor = None

    def move(self, dx, dy, shift):
        if shift and self.anchor is None:
            self.anchor = (self.cx, self.cy)
        elif not shift:
            self.anchor = None
        self.cy = max(0, min(len(self.lines) - 1, self.cy + dy))
        self.cx = max(0, min(len(self.lines[self.cy]), self.cx))
        if dx:
            self.cx += dx
            if self.cx < 0:
                if self.cy > 0:
                    self.cy -= 1
                    self.cx = len(self.lines[self.cy])
                else:
                    self.cx = 0
            elif self.cx > len(self.lines[self.cy]):
                if self.cy < len(self.lines) - 1:
                    self.cy += 1
                    self.cx = 0
                else:
                    self.cx = len(self.lines[self.cy])

    def get_clip(self):
        try:
            if pygame.scrap.get_init():
                t = pygame.scrap.get_text()
                if t:
                    return t
        except Exception:
            pass
        return self.clip

    def put_clip(self, t):
        self.clip = t
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put_text(t)
        except Exception:
            pass

    def key(self, e):
        k, mod = e.key, e.mod
        ctrl, shift = bool(mod & pygame.KMOD_CTRL), bool(mod & pygame.KMOD_SHIFT)
        if ctrl:
            if k == pygame.K_a:
                self.anchor = (0, 0)
                self.cy = len(self.lines) - 1
                self.cx = len(self.lines[self.cy])
            elif k == pygame.K_c:
                if self.selected():
                    self.put_clip(self.selected())
            elif k == pygame.K_x:
                if self.selected():
                    self.put_clip(self.selected())
                    self.snap('cut')
                    self.del_sel()
            elif k == pygame.K_v:
                t = self.get_clip()
                if t:
                    self.snap('paste')
                    self.insert(t)
            elif k == pygame.K_z:
                if self.undo:
                    self.redo.append((list(self.lines), self.cx, self.cy))
                    self.lines, self.cx, self.cy = self.undo.pop()
                    self.anchor = None
            elif k == pygame.K_y:
                if self.redo:
                    self.undo.append((list(self.lines), self.cx, self.cy))
                    self.lines, self.cx, self.cy = self.redo.pop()
                    self.anchor = None
            elif k in (pygame.K_LEFT, pygame.K_RIGHT):
                if shift and self.anchor is None:
                    self.anchor = (self.cx, self.cy)
                elif not shift:
                    self.anchor = None
                line = self.lines[self.cy]
                if k == pygame.K_LEFT:
                    i = self.cx
                    while i > 0 and line[i - 1] == ' ':
                        i -= 1
                    while i > 0 and line[i - 1] != ' ':
                        i -= 1
                    self.cx = i
                else:
                    i = self.cx
                    while i < len(line) and line[i] == ' ':
                        i += 1
                    while i < len(line) and line[i] != ' ':
                        i += 1
                    self.cx = i
            return
        if k == pygame.K_LEFT:
            if self.sel_range() and not shift:
                a, b = self.sel_range()
                self.cx, self.cy = a
                self.anchor = None
            else:
                self.move(-1, 0, shift)
        elif k == pygame.K_RIGHT:
            if self.sel_range() and not shift:
                a, b = self.sel_range()
                self.cx, self.cy = b
                self.anchor = None
            else:
                self.move(1, 0, shift)
        elif k == pygame.K_UP:
            self.move(0, -1, shift)
        elif k == pygame.K_DOWN:
            self.move(0, 1, shift)
        elif k == pygame.K_HOME:
            self.move(-len(self.lines[self.cy]), 0, shift)
        elif k == pygame.K_END:
            self.move(len(self.lines[self.cy]), 0, shift)
        elif k == pygame.K_PAGEUP:
            self.move(0, -10, shift)
        elif k == pygame.K_PAGEDOWN:
            self.move(0, 10, shift)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.snap('enter')
            self.del_sel()
            line = self.lines[self.cy]
            ind = len(line) - len(line.lstrip(' '))
            word = line.strip().split(' ')[0].lower() if line.strip() else ''
            if word in ('repeat', 'forever', 'if', 'else'):
                ind += 2
            self.insert('\n' + ' ' * ind)
        elif k == pygame.K_BACKSPACE:
            self.snap('del')
            if not self.del_sel():
                if self.cx > 0:
                    line = self.lines[self.cy]
                    n = 1
                    if line[:self.cx].strip() == '' and self.cx >= 2:
                        n = 2 if self.cx % 2 == 0 else 1
                    self.lines[self.cy] = line[:self.cx - n] + line[self.cx:]
                    self.cx -= n
                elif self.cy > 0:
                    prev = self.lines[self.cy - 1]
                    self.lines[self.cy - 1] = prev + self.lines[self.cy]
                    del self.lines[self.cy]
                    self.cy -= 1
                    self.cx = len(prev)
        elif k == pygame.K_DELETE:
            self.snap('del')
            if not self.del_sel():
                line = self.lines[self.cy]
                if self.cx < len(line):
                    self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
                elif self.cy < len(self.lines) - 1:
                    self.lines[self.cy] = line + self.lines[self.cy + 1]
                    del self.lines[self.cy + 1]
        elif k == pygame.K_TAB:
            self.snap('tab')
            self.insert('  ')
        elif e.unicode and e.unicode.isprintable():
            self.snap('type')
            self.insert(e.unicode)

    # -- mouse
    def pos_at(self, pos, rect):
        row = max(0, min(len(self.lines) - 1, self.scroll + (pos[1] - rect.y - 4) // self.LH))
        x = pos[0] - rect.x - self.gutter - 6
        line = self.lines[row]
        col = 0
        for i in range(len(line) + 1):
            if self.font.size(line[:i])[0] > x + 3:
                break
            col = i
        return col, row

    def click(self, pos, rect, shift=False):
        self.focus = True
        col, row = self.pos_at(pos, rect)
        if shift and self.anchor is None:
            self.anchor = (self.cx, self.cy)
        elif not shift:
            self.anchor = (col, row)
        self.cx, self.cy = col, row

    def drag(self, pos, rect):
        self.cx, self.cy = self.pos_at(pos, rect)

    def wheel(self, dy, rect):
        vis = max(1, (rect.h - 8) // self.LH)
        self.scroll = max(0, min(max(0, len(self.lines) - vis), self.scroll - dy * 3))

    def draw(self, surf, rect, col):
        # col: dict of colors
        f = self.font
        vis = max(1, (rect.h - 8) // self.LH)
        if self.cy < self.scroll:
            self.scroll = self.cy
        elif self.cy >= self.scroll + vis:
            self.scroll = self.cy - vis + 1
        self.scroll = max(0, min(max(0, len(self.lines) - vis), self.scroll))
        pygame.draw.rect(surf, col['bg'], rect, border_radius=8)
        old = surf.get_clip()
        surf.set_clip(rect.inflate(-2, -2).clip(old))
        gx = rect.x + self.gutter
        pygame.draw.rect(surf, col['gut'], (rect.x, rect.y, self.gutter, rect.h), border_top_left_radius=8, border_bottom_left_radius=8)
        sel = self.sel_range()
        for r in range(self.scroll, min(len(self.lines), self.scroll + vis + 1)):
            y = rect.y + 4 + (r - self.scroll) * self.LH
            line = self.lines[r]
            if r == self.run_row:
                pygame.draw.rect(surf, col['run'], (rect.x + 2, y - 1, rect.w - 4, self.LH), border_radius=4)
            elif r in self.err:
                pygame.draw.rect(surf, col['errbg'], (rect.x + 2, y - 1, rect.w - 4, self.LH), border_radius=4)
            elif r == self.cy and self.focus and not sel:
                pygame.draw.rect(surf, col['cur'], (gx, y - 1, rect.w - self.gutter - 2, self.LH), border_radius=4)
            if sel:
                (x0, y0), (x1, y1) = sel
                if y0 <= r <= y1:
                    a = x0 if r == y0 else 0
                    b = x1 if r == y1 else len(line) + 1
                    xa = gx + 6 + f.size(line[:a])[0]
                    xb = gx + 6 + f.size(line[:b])[0] + (4 if b > len(line) else 0)
                    pygame.draw.rect(surf, col['sel'], (xa, y - 1, max(3, xb - xa), self.LH))
            num = f.render(str(r + 1), True, col['err'] if r in self.err else col['dim'])
            surf.blit(num, (rect.x + self.gutter - 8 - num.get_width(), y + (self.LH - num.get_height()) // 2 - 1))
            first = True
            for m in S_TOK.finditer(line):
                t = m.group(0)
                if m.group(5):
                    continue
                if m.group(1):
                    c = col['cmt']
                elif first:
                    c = col['cmd'] if t.lower() in S_CMDS else col['err']
                    first = False
                elif m.group(2):
                    c = col['str']
                elif m.group(3):
                    c = col['num']
                elif t.lower() in ('on', 'off'):
                    c = col['kw']
                else:
                    c = col['name']
                img = f.render(t, True, c)
                surf.blit(img, (gx + 6 + f.size(line[:m.start()])[0], y + (self.LH - img.get_height()) // 2 - 1))
            if r in self.err:
                pygame.draw.circle(surf, col['err'], (rect.x + 7, y + self.LH // 2 - 1), 3)
        if self.focus and (pygame.time.get_ticks() // 500) % 2 == 0:
            y = rect.y + 4 + (self.cy - self.scroll) * self.LH
            x = gx + 6 + f.size(self.lines[self.cy][:self.cx])[0]
            pygame.draw.line(surf, col['caret'], (x, y), (x, y + self.LH - 3), 2)
        surf.set_clip(old)
        if len(self.lines) > vis:
            th = max(18, int(rect.h * vis / len(self.lines)))
            ty = rect.y + int((rect.h - th) * self.scroll / max(1, len(self.lines) - vis))
            pygame.draw.rect(surf, col['dim'], (rect.right - 5, ty, 3, th), border_radius=2)


# ---------------------------------------------------------------- compiled circuit
_TBL = None


def _gate_table():
    # rows: AND OR NAND NOR XOR XNOR NOT BUF, columns: a*2+b
    return np.array([[0, 0, 0, 1], [0, 1, 1, 1], [1, 1, 1, 0], [1, 0, 0, 0],
                     [0, 1, 1, 0], [1, 0, 0, 1], [1, 1, 0, 0], [0, 0, 1, 1]], np.int8)


GATE_CODE = {'AND': 0, 'OR': 1, 'NAND': 2, 'NOR': 3, 'XOR': 4, 'XNOR': 5, 'NOT': 6, 'BUF': 7}


class Compiled:
    # the whole circuit as flat numpy arrays, one vectorised pass per tick
    def __init__(self, app):
        global _TBL
        if _TBL is None:
            _TBL = _gate_table()
        if app.topo_key != app.topo_sig():
            app.build_topo()
        self.app = app
        parts = self.parts = list(app.sim_parts)
        P = len(parts)
        gid = app.gid

        def nid(p, i):
            return gid[(p.uid, i)]

        kinds = [p.kind for p in parts]

        def of(*ks):
            return [i for i, k in enumerate(kinds) if k in ks]

        def arr(x, dt=np.int64):
            return np.array(x, dt)

        self.out = np.zeros(P, np.int8)
        self.drive = np.ones(P, bool)
        self.cnt = np.zeros(P, np.int32)
        for i, p in enumerate(parts):
            self.out[i] = 1 if p.kind == 'SOURCE' else int(p.out)
            self.cnt[i] = p.counter
            if p.kind == 'GATE':
                self.drive[i] = p.drive
        dp, dn = [], []
        for i, p in enumerate(parts):
            for j, (_, _, role) in enumerate(p.d['pins']):
                if role == 'out':
                    dp.append(i)
                    dn.append(nid(p, j))
        self.dp, self.dn = arr(dp), arr(dn)
        self.N = max(1, app.ngroups)
        ein = app.edges_in
        es = [s_ for d_, ss in ein.items() for s_ in ss]
        ed = [d_ for d_, ss in ein.items() for _ in ss]
        self.es, self.ed = arr(es), arr(ed)
        self.rt = arr([t for t, _ in app.relays])
        self.rs = arr([r for _, r in app.relays])
        self.rdepth = app.relay_depth
        # gates
        self.ci = arr(of(*GATES))
        self.ctype = arr([GATE_CODE[kinds[i]] for i in self.ci])
        self.ca = arr([nid(parts[i], 0) for i in self.ci])
        self.cb = arr([nid(parts[i], 1) if len(parts[i].d['pins']) > 2 else nid(parts[i], 0) for i in self.ci])
        self.gi = arr(of('GATE'))
        self.gst = arr([nid(parts[i], 0) for i in self.gi])
        self.gen = arr([nid(parts[i], 2) for i in self.gi])
        # inputs
        self.si = arr(of('SWITCH'))
        self.s_net = arr([nid(parts[i], 0) for i in self.si])
        self.bi = arr(of('BUTTON'))
        self.b_net = arr([nid(parts[i], 0) for i in self.bi])
        self.ti = arr(of('TOUCH'))
        self.ki = arr(of('CLOCK'))
        self.kper = arr([PERIODS[parts[i].pidx] for i in self.ki])
        # delay as a ring buffer
        self.di = arr(of('DELAY'))
        self.d_net = arr([nid(parts[i], 0) for i in self.di])
        self.d_n = arr([DPER[parts[i].pidx] - 1 for i in self.di])
        self.d_rows = np.flatnonzero(self.d_n > 0)
        mx = int(self.d_n.max()) if self.di.size and self.d_n.max() > 0 else 1
        self.d_buf = np.zeros((len(self.di), mx), np.int8)
        self.d_ptr = np.zeros(len(self.di), np.int64)
        for r, i in enumerate(self.di):
            p = parts[i]
            n = int(self.d_n[r])
            if n > 0 and p.buf is not None and len(p.buf) == n:
                self.d_buf[r, :n] = list(p.buf)
        self.ei = arr(of('EXTENDER'))
        self.e_net = arr([nid(parts[i], 0) for i in self.ei])
        self.e_len = arr([DPER[parts[i].pidx] - 1 for i in self.ei], np.int32)
        self.tgi = arr(of('TOGGLE'))
        self.tg_net = arr([nid(parts[i], 0) for i in self.tgi])
        self.li = arr(of('SR LATCH', 'NV LATCH'))
        self.l_s = arr([nid(parts[i], 0) for i in self.li])
        self.l_r = arr([nid(parts[i], 1) for i in self.li])
        self.xi = arr(of('GAS IN'))
        self.x_id = arr([parts[i].pidx + 1 for i in self.xi])
        self.oi = arr(of('GAS OUT'))
        self.o_net = arr([nid(parts[i], 0) for i in self.oi])
        self.o_id = arr([parts[i].pidx + 1 for i in self.oi])
        self.go_last = np.zeros(len(self.oi), bool)
        # things that light up
        self.sci = arr(of('SCOPE'))
        self.sc_net = arr([nid(parts[i], 0) for i in self.sci])
        self.sc_hist = np.zeros((len(self.sci), SCOPE_LEN), np.int8)
        for r, i in enumerate(self.sci):
            if parts[i].trace is not None:
                t_ = np.asarray(parts[i].trace, np.int8)[-SCOPE_LEN:]
                self.sc_hist[r, SCOPE_LEN - len(t_):] = t_
        self.sc_ptr = 0
        self.mi = arr(of('LAMP'))
        self.m_net = arr([nid(parts[i], 0) for i in self.mi])
        self.m_lit = np.zeros(len(self.mi), bool)
        self.pi = arr(of('DISPLAY', 'TOUCH'))
        self.p_nets = arr([[nid(parts[i], j) for j in range(3)] for i in self.pi]).reshape(-1, 3)
        self.p_lit = np.zeros((len(self.pi), 3), bool)
        self.zi = arr(of('7SEG'))
        self.z_seg = arr([[nid(parts[i], j) for j in range(7)] for i in self.zi]).reshape(-1, 7)
        self.z_col = arr([[nid(parts[i], j) for j in (7, 8, 9)] for i in self.zi]).reshape(-1, 3)
        self.z_slit = np.zeros((len(self.zi), 7), bool)
        self.z_clit = np.zeros((len(self.zi), 3), bool)
        self.sw_on = np.zeros(len(self.si), bool)
        self.b_pulse = np.zeros(len(self.bi), bool)
        self.t_pulse = np.zeros(len(self.ti), bool)
        self.tx = np.zeros(17, np.int8)
        self.last_out = self.out.copy()
        self.last_drive = self.drive.copy()
        self.nparts = P

    def nets(self):
        val = self.out[self.dp]
        act = self.drive[self.dp]
        N = self.N
        bh = np.bincount(self.dn[act & (val == 1)], minlength=N) > 0
        bl = np.bincount(self.dn[act & (val == 0)], minlength=N) > 0
        hi, lo = bh, bl & ~bh
        es, ed = self.es, self.ed

        def pull(hi, lo):
            ih = np.bincount(ed[hi[es]], minlength=N) > 0
            il = np.bincount(ed[lo[es]], minlength=N) > 0
            return hi | ih, lo | (il & ~ih)

        for _ in range(self.rdepth):
            hi, lo = pull(hi, lo)
            rh = np.bincount(self.rt[hi[self.rs]], minlength=N) > 0
            rl = np.bincount(self.rt[lo[self.rs]], minlength=N) > 0
            hi = bh | rh
            lo = (bl | rl) & ~hi
        return pull(hi, lo) if es.size else (hi, lo)

    def settle(self):
        # instant logic: gates resolve completely inside the tick
        out, drive = self.out, self.drive
        for _ in range(64):
            hi, lo = self.nets()
            h8 = hi.view(np.int8)
            ch = False
            if self.ci.size:
                new = _TBL[self.ctype, h8[self.ca] * 2 + h8[self.cb]]
                if (new != out[self.ci]).any():
                    out[self.ci] = new
                    ch = True
            if self.gi.size:
                st1 = hi[self.gst]
                dr = hi[self.gen] & (st1 | lo[self.gst])
                v = st1.astype(np.int8)
                if (dr != drive[self.gi]).any() or (v != out[self.gi]).any():
                    drive[self.gi] = dr
                    out[self.gi] = v
                    ch = True
            if not ch:
                return hi, lo
        return self.nets()

    def tick(self):
        app = self.app
        hi, lo = self.settle() if app.instant else self.nets()
        out, cnt, drive = self.out, self.cnt, self.drive
        h8 = hi.view(np.int8)
        if self.ci.size:
            out[self.ci] = _TBL[self.ctype, h8[self.ca] * 2 + h8[self.cb]]
        if self.gi.size:
            st1 = hi[self.gst]
            drive[self.gi] = hi[self.gen] & (st1 | lo[self.gst])
            out[self.gi] = st1
        if self.si.size:
            out[self.si] = hi[self.s_net] & self.sw_on
        if self.bi.size:
            out[self.bi] = hi[self.b_net] & self.b_pulse
        if self.ti.size:
            out[self.ti] = self.t_pulse
        if self.ki.size:
            cnt[self.ki] += 1
            m = self.ki[cnt[self.ki] >= self.kper]
            cnt[m] = 0
            out[m] = 1 - out[m]
        if self.di.size:
            v = hi[self.d_net].astype(np.int8)
            res = v.copy()
            r = self.d_rows
            if r.size:
                pt = self.d_ptr[r]
                res[r] = self.d_buf[r, pt]
                self.d_buf[r, pt] = v[r]
                self.d_ptr[r] = (pt + 1) % self.d_n[r]
            out[self.di] = res
        if self.ei.size:
            h = hi[self.e_net]
            c = cnt[self.ei]
            out[self.ei] = h | (c > 0)
            cnt[self.ei] = np.where(h, self.e_len, np.maximum(c - 1, 0))
        if self.tgi.size:
            v = hi[self.tg_net].astype(np.int8)
            c, o = cnt[self.tgi], out[self.tgi]
            out[self.tgi] = np.where((v == 1) & (c == 0), 1 - o, o)
            cnt[self.tgi] = v
        if self.li.size:
            out[self.li] = np.where(hi[self.l_r], 0, np.where(hi[self.l_s], 1, out[self.li]))
        if self.xi.size:
            out[self.xi] = self.tx[self.x_id]
        if self.oi.size:
            self.go_last = hi[self.o_net]
        if self.sci.size:
            self.sc_hist[:, self.sc_ptr] = hi[self.sc_net]
            self.sc_ptr = (self.sc_ptr + 1) % SCOPE_LEN
        if self.mi.size:
            self.m_lit |= hi[self.m_net]
        if self.pi.size:
            self.p_lit |= hi[self.p_nets]
        if self.zi.size:
            self.z_slit |= hi[self.z_seg]
            self.z_clit |= hi[self.z_col]
        self.b_pulse[:] = False
        self.t_pulse[:] = False

    def run(self, n):
        if n <= 0:
            return
        parts = self.parts
        for r, i in enumerate(self.si):
            self.sw_on[r] = parts[i].on
        for r, i in enumerate(self.bi):
            self.b_pulse[r] = parts[i].pulse
        for r, i in enumerate(self.ti):
            self.t_pulse[r] = parts[i].pulse
        if self.xi.size:
            self.tx[:] = [GAS_TX.get(i, 0) for i in range(17)]
        for _ in range(n):
            self.tick()
        self.sync()

    def sync(self):
        app, parts, out, drive = self.app, self.parts, self.out, self.drive
        for i in np.flatnonzero((out != self.last_out) | (drive != self.last_drive)):
            p = parts[i]
            if p.kind == 'SOURCE':
                continue
            p.out = int(out[i])
            if p.kind == 'GATE':
                p.drive = bool(drive[i])
            elif p.kind == 'NV LATCH':
                app.dirty = True
        self.last_out[:] = out
        self.last_drive[:] = drive
        for i in self.bi:
            parts[i].pulse = False
        for i in self.ti:
            parts[i].pulse = False
        for r, i in enumerate(self.sci):
            parts[i].trace = np.roll(self.sc_hist[r], -self.sc_ptr)
        for r in np.flatnonzero(self.m_lit):
            parts[self.mi[r]].glow = GLOW
        self.m_lit[:] = False
        for r in np.flatnonzero(self.p_lit.any(axis=1)):
            p = parts[self.pi[r]]
            p.rgb = tuple(255 if x else 0 for x in self.p_lit[r])
            p.glow = GLOW
        self.p_lit[:] = False
        for r in range(len(self.zi)):
            p = parts[self.zi[r]]
            col = tuple(255 if x else 0 for x in self.z_clit[r])
            p.rgb = col if any(col) else None
            for j in np.flatnonzero(self.z_slit[r]):
                p.seg_glow[j] = GLOW
        self.z_slit[:] = False
        self.z_clit[:] = False
        if self.oi.size or GAS_RX:
            GAS_RX.clear()
            GAS_RX.update({int(i): 1 for i in self.o_id[self.go_last]})

    def stop(self):
        # hand the state back to the parts (so build mode and saves see it)
        parts = self.parts
        for i, p in enumerate(parts):
            if p.kind != 'SOURCE':
                p.out = int(self.out[i])
            if p.kind == 'GATE':
                p.drive = bool(self.drive[i])
            if p.kind in ('CLOCK', 'EXTENDER', 'TOGGLE'):
                p.counter = int(self.cnt[i])
            if p.kind in ('BUTTON', 'TOUCH'):
                p.pulse = False
        for r, i in enumerate(self.sci):
            parts[i].trace = np.roll(self.sc_hist[r], -self.sc_ptr)
        for r, i in enumerate(self.di):
            n = int(self.d_n[r])
            if n > 0:
                pt = int(self.d_ptr[r])
                parts[i].buf = deque(int(self.d_buf[r, (pt + k) % n]) for k in range(n))


# ---------------------------------------------------------------- app
class App:
    def __init__(self):
        self.parts = []
        self.wires = []     # (partA, pinA, partB, pinB)
        self.drag = None
        self.paused = False
        self.rate = 500     # ticks per second
        self.acc = 0.0
        self.anim = 0.0
        self.dirty = False
        self.last_save = 0.0
        self.path = save_path()
        self.font = pygame.font.SysFont(MONO, 16, bold=True)
        self.small = pygame.font.SysFont(MONO, 13)
        self.tiny = pygame.font.SysFont(MONO, 11, bold=True)
        self.descf = pygame.font.SysFont(MONO, 11)
        self.ui = pygame.font.SysFont(SANS, 14)
        self.ui_b = pygame.font.SysFont(SANS, 14, bold=True)
        self.ui_s = pygame.font.SysFont(SANS, 12)
        self.ui_h = pygame.font.SysFont(SANS, 17, bold=True)
        self.edf = pygame.font.SysFont(MONO, 13)
        self.edit_field = 'title'
        global FONT
        FONT = self.font
        self.light = False
        self.instant = True     # gates always settle inside one tick (no race glitches)
        self.running = False    # False = build mode (frozen, editable), True = compiled and running
        self.cmp = None
        self.updater = None
        self.modal_img = None
        self.editing = None     # part being renamed
        self.namebox = None     # chip name prompt: dict(part, text, fresh)
        self.edit_on = False
        self.edit_text = ''
        self.edit_fresh = False
        self.last_click = (None, 0)
        self.sel = set()        # selected parts
        self.clip = None        # copied parts + the wires between them
        self.pal_scroll = 0
        self.search, self.search_focus, self.cat_open, self.icons = '', False, {}, {}
        self.dock_open, self.dock_h, self.dock_tab, self.dock_drag = False, 260, 'SCRIPT', None
        self.ed = Editor()
        self.ed.font = self.edf
        self.ed.set_text('# macro: on / off / toggle / press / wait\n# example:  on SWITCH#1   then   wait 10   then   press BUTTON#1\n# ctrl+enter runs it, the ? button lists the commands\n')
        self.runner = Runner(self)
        self.script_log, self.log_scroll, self.names_scroll, self.ex_i = [], 0, 0, 0
        self.help_open = False
        self.topo_key = None    # cached net layout, rebuilt when parts/wires change
        self.root = {}
        self.out_pins = []
        self.grid_cache = None
        self.gid = {}
        self.wsrc = []
        self.obs_ver = None     # wire routes are redone when parts move
        self.blocked = None
        self.routes = {}
        self.occ = None         # cells used by routed wires, so new wires lay next to them
        self.occ_key = None
        self.occ_ver = 0
        self.route_budget = 12
        self.tint_cache = {}
        self.sim_parts = []     # every real part, chip insides included
        self.chip_defs = {}     # chips saved as files, name -> circuit
        self.toast = ('', 0.0)
        self.mode = 'circuit'   # or 'gas'
        self.view_moved = False

    # ------------------------------------------------------------ sim
    def topo_sig(self):
        return (id(self.parts), len(self.parts), id(self.wires), len(self.wires))

    @staticmethod
    def k(p, i):
        # net key of a pin; a chip's pin is really the PIN part inside it
        if p.kind == 'CHIP':
            return (p.pinmap[i].uid, 0)
        return (p.uid, i)

    @staticmethod
    def flatten(p, parts, wires):
        if p.kind == 'CHIP':
            for q in p.inner:
                App.flatten(q, parts, wires)
            wires.extend(p.inner_wires)
        else:
            parts.append(p)

    def end_info(self, p, i):
        # (key, role) of a wire end. A chip pin seen from outside, or the PIN part seen from
        # inside, are the two faces of the same relay.
        if p.kind == 'CHIP':
            q = p.pinmap[i]
            return (q.uid, 'o'), ('out' if q.on else 'in')
        if p.kind == 'PIN':
            return (p.uid, 'i'), ('in' if p.on else 'out')
        return (p.uid, i), p.d['pins'][i][2]

    def build_topo(self):
        parent = {}
        sim, all_wires = [], list(self.wires)
        for p in self.parts:
            self.flatten(p, sim, all_wires)
        self.sim_parts = sim
        for p in sim:
            for i in range(len(p.d['pins'])):
                k = (p.uid, i)
                parent[k] = k

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for pa, ia, pb, ib in all_wires:
            ra, rb = find(self.k(pa, ia)), find(self.k(pb, ib))
            if ra != rb:
                parent[ra] = rb
        self.root = {k: find(k) for k in list(parent)}       # plain connectivity, for routing

        # directed model: outputs only ever push into inputs
        par, role = {}, {}

        def f2(a):
            par.setdefault(a, a)
            while par[a] != a:
                par[a] = par[par[a]]
                a = par[a]
            return a

        def reg(key, r):
            role[key] = r
            f2(key)

        for p in sim:
            if p.kind == 'PIN':
                reg((p.uid, 'i'), 'in' if p.on else 'out')
                reg((p.uid, 'o'), 'out' if p.on else 'in')
            else:
                for i, (_, _, r) in enumerate(p.d['pins']):
                    reg((p.uid, i), r)
        edges = []
        for pa, ia, pb, ib in all_wires:
            (ka, ra), (kb, rb) = self.end_info(pa, ia), self.end_info(pb, ib)
            reg(ka, ra)
            reg(kb, rb)
            if ra == rb:
                x, y = f2(ka), f2(kb)
                if x != y:
                    par[x] = y
            elif ra == 'out':
                edges.append((ka, kb))
            else:
                edges.append((kb, ka))
        ids = {}

        def gid(key):
            r = f2(key)
            g = ids.get(r)
            if g is None:
                g = ids[r] = len(ids)
            return g

        for key in list(role):
            gid(key)
        self.ngroups = len(ids)
        self.gid = {}
        for p in sim:
            if p.kind == 'PIN':
                self.gid[(p.uid, 0)] = gid((p.uid, 'o'))
            else:
                for i in range(len(p.d['pins'])):
                    self.gid[(p.uid, i)] = gid((p.uid, i))
        self.out_pins = []
        for p in sim:
            if p.kind != 'PIN':
                for i, (_, _, r) in enumerate(p.d['pins']):
                    if r == 'out':
                        self.out_pins.append((p, i, gid((p.uid, i))))
        ein = {}
        for ko, ki in set((gid(a), gid(b)) for a, b in edges):
            ein.setdefault(ki, []).append(ko)
        self.edges_in = {k: tuple(v) for k, v in ein.items()}
        self.relays = []
        for p in sim:
            if p.kind == 'PIN':
                if p.on:
                    self.relays.append((gid((p.uid, 'o')), gid((p.uid, 'i'))))
                else:
                    self.relays.append((gid((p.uid, 'i')), gid((p.uid, 'o'))))
        # how many relay hops deep the longest chain goes
        by_tg = {}
        for tg, src in self.relays:
            by_tg.setdefault(tg, []).append(src)
        memo, busy = {}, set()

        def depth(src):
            if src in memo:
                return memo[src]
            if src in busy:
                return 0
            busy.add(src)
            d = 0
            for og in self.edges_in.get(src, ()):
                for s2 in by_tg.get(og, ()):
                    d = max(d, 1 + depth(s2))
            busy.discard(src)
            memo[src] = d
            return d

        self.relay_depth = max([1 + depth(src) for _, src in self.relays] or [0])
        # wires show the value of the end that drives them
        self.wsrc = []
        for pa, ia, pb, ib in self.wires:
            (ka, ra), (kb, rb) = self.end_info(pa, ia), self.end_info(pb, ib)
            self.wsrc.append(gid(kb if (ra == 'in' and rb == 'out') else ka))
        self.topo_key = self.topo_sig()

    def netstate(self):
        if self.topo_key != self.topo_sig():
            self.build_topo()
        drv = {}
        for p, i, og in self.out_pins:
            k = p.kind
            if k == 'GATE' and not p.drive:
                continue        # open gate puts nothing on the wire
            v = 1 if k == 'SOURCE' else p.out
            if v:
                drv[og] = {1}           # outputs sharing a wire act like an OR
            elif og not in drv:
                drv[og] = {0}
        ein = self.edges_in

        def pull():
            for ig, srcs in ein.items():
                lo = False
                for sg in srcs:
                    d = drv.get(sg)
                    if d is None:
                        continue
                    if 1 in d:
                        drv[ig] = {1}
                        break
                    lo = True
                else:
                    if lo:
                        drv[ig] = {0}

        if self.relay_depth:
            base = dict(drv)
            for _ in range(self.relay_depth):
                pull()
                cur = dict(base)
                for tg, src in self.relays:
                    d = drv.get(src)
                    if d is None:
                        continue
                    if 1 in d:
                        cur[tg] = {1}
                    elif tg not in cur:
                        cur[tg] = {0}
                drv.clear()
                drv.update(cur)
        pull()
        return self.gid.get, drv

    def settle(self):
        # instant logic: gates (and the send gate) resolve fully inside the tick, only
        # delays, latches, clocks etc. still cost a tick. Capped so loops can't hang.
        comb = [p for p in self.sim_parts if p.kind in GATES or p.kind == 'GATE']
        find, drv = self.netstate()
        for _ in range(64):
            ch = []
            for p in comb:
                if p.kind == 'GATE':
                    st = drv.get(find((p.uid, 0)))
                    en = drv.get(find((p.uid, 2))) == {1}
                    dr, v = en and st in ({0}, {1}), 1 if st == {1} else 0
                    if dr != p.drive or v != p.out:
                        ch.append((p, dr, v))
                else:
                    ins = [drv.get(find((p.uid, i))) == {1}
                           for i, (_, _, r) in enumerate(p.d['pins']) if r == 'in']
                    v = int(GATES[p.kind](ins))
                    if v != p.out:
                        ch.append((p, p.drive, v))
            if not ch:
                break
            for p, dr, v in ch:
                p.drive, p.out = dr, v
            find, drv = self.netstate()
        return find, drv

    def step(self):
        find, drv = self.settle() if self.instant else self.netstate()

        def hi(p, i):
            return drv.get(find((p.uid, i))) == {1}

        new = []
        passes = []
        gas_rx = set()
        for p in self.sim_parts:
            k = p.kind
            if k == 'GATE':
                st = drv.get(find((p.uid, 0)))
                passes.append((p, hi(p, 2) and st in ({0}, {1}), 1 if st == {1} else 0))
            elif k in GATES or k in ('SWITCH', 'BUTTON'):
                ins = [hi(p, i) for i, (_, _, r) in enumerate(p.d['pins']) if r == 'in']
                if k in GATES:
                    v = int(GATES[k](ins))
                elif k == 'SWITCH':
                    v = int(ins[0] and p.on)
                else:
                    v = int(ins[0] and p.pulse)
                new.append((p, v))
            elif k == 'CLOCK':
                p.counter += 1
                if p.counter >= PERIODS[p.pidx]:
                    p.counter = 0
                    new.append((p, 1 - p.out))
            elif k == 'DELAY':
                n = DPER[p.pidx] - 1
                v = int(hi(p, 0))
                if n <= 0:
                    new.append((p, v))
                else:
                    if p.buf is None or len(p.buf) != n:
                        p.buf = deque([0] * n)
                    p.buf.append(v)
                    new.append((p, p.buf.popleft()))
            elif k == 'EXTENDER':
                if hi(p, 0):
                    p.counter = DPER[p.pidx] - 1
                    new.append((p, 1))
                elif p.counter > 0:
                    p.counter -= 1
                    new.append((p, 1))
                else:
                    new.append((p, 0))
            elif k == 'TOGGLE':
                v = int(hi(p, 0))
                new.append((p, 1 - p.out if v and not p.counter else p.out))
                p.counter = v       # last input, to catch the rising edge
            elif k in ('SR LATCH', 'NV LATCH'):
                # reset wins if both are high
                new.append((p, 0 if hi(p, 1) else (1 if hi(p, 0) else p.out)))
            elif k == 'GAS IN':
                new.append((p, int(GAS_TX.get(p.pidx + 1, 0))))
            elif k == 'GAS OUT':
                if hi(p, 0):
                    gas_rx.add(p.pidx + 1)
            elif k == 'LAMP':
                if hi(p, 0):
                    p.glow = GLOW
            elif k in ('DISPLAY', 'TOUCH'):
                rgb = tuple(255 if hi(p, i) else 0 for i in range(3))
                if any(rgb):
                    p.rgb = rgb
                    p.glow = GLOW
                if k == 'TOUCH':
                    new.append((p, int(p.pulse)))
            elif k == 'SCOPE':
                p.trace = ((list(p.trace) if p.trace is not None else [])[-(SCOPE_LEN - 1):]) + [int(hi(p, 0))]
            elif k == '7SEG':
                col = tuple(255 if hi(p, i) else 0 for i in (7, 8, 9))
                p.rgb = col if any(col) else None
                for i in range(7):
                    if hi(p, i):
                        p.seg_glow[i] = GLOW
        if any(p.kind == 'GAS OUT' for p in self.sim_parts) or GAS_RX:
            GAS_RX.clear()
            GAS_RX.update({i: 1 for i in gas_rx})
        for p, drive, v in passes:
            p.drive, p.out = drive, v
        for p, v in new:
            if p.kind == 'NV LATCH' and p.out != v:
                self.dirty = True
            p.out = v
            if p.kind in ('BUTTON', 'TOUCH'):
                p.pulse = False

    def update(self, dt):
        self.route_budget = 12
        self.update_obstacles()
        if len(self.routes) > 2 * len(self.wires) + 50:
            self.routes.clear()
        for p in self.parts:
            p.flash = max(0.0, p.flash - dt)
        if self.paused or not self.running:
            return
        self.anim += dt
        for p in self.sim_parts:
            if p.glow > 0:
                p.glow = max(0.0, p.glow - dt)
            if p.kind == '7SEG':
                p.seg_glow = [max(0.0, g - dt) for g in p.seg_glow]
        self.acc += dt
        tick = 1.0 / self.rate
        n = 0
        while self.acc >= tick and n < 400:
            self.acc -= tick
            n += 1
        if n == 400:
            self.acc = 0.0
        self.advance(n)

    def advance(self, n):
        r = self.runner
        i = 0
        while i < n:
            if r.active:
                r.before_tick()     # the script gets a go before every tick
                k = 1
            else:
                k = n - i
            if self.cmp:
                self.cmp.run(k)
            else:
                for _ in range(k):
                    self.step()
            i += k

    def toggle_run(self):
        if self.running:
            if self.runner.active:
                self.runner.stop('stopped (build mode)')
            if self.cmp:
                self.cmp.stop()
                self.cmp = None
            self.running = False
            self.drag = None
            self.say('build mode, enter to compile and run')
            return
        self.drag = None
        self.sel.clear()
        self.build_topo()
        if np is not None:
            try:
                self.cmp = Compiled(self)
                self.say(f'compiled: {self.cmp.nparts} parts, {self.cmp.N} nets')
            except Exception as ex:
                self.cmp = None
                self.say(f'compile failed ({type(ex).__name__}), running slow engine')
        else:
            self.say('running (no numpy, slow engine)')
        self.running = True
        self.acc = 0.0

    def run_click(self, p):
        if p.kind == 'SWITCH':
            p.on = not p.on
        elif p.kind in ('BUTTON', 'TOUCH'):
            p.pulse = True
            p.flash = 0.15

    # ------------------------------------------------------------ wire routing
    def update_obstacles(self):
        ver = hash(tuple((p.uid, p.gx, p.gy) for p in self.parts if p.kind != 'LABEL'))
        if ver != self.obs_ver:
            self.obs_ver = ver
            self.blocked = None

    def blocked_set(self):
        # hard = inside a part (never routed through), soft = its 15px margin (costs extra)
        if self.blocked is None:
            hard, soft = set(), set()
            for p in self.parts:
                if p.kind == 'LABEL':
                    continue
                x0, y0 = p.gx * C, p.gy * C
                x1, y1 = (p.gx + p.d['w']) * C, (p.gy + p.d['h']) * C
                for ix in range(math.floor((x0 - MARGIN) / RU) + 1, math.ceil((x1 + MARGIN) / RU)):
                    for iy in range(math.floor((y0 - MARGIN) / RU) + 1, math.ceil((y1 + MARGIN) / RU)):
                        if x0 <= ix * RU <= x1 and y0 <= iy * RU <= y1:
                            hard.add((ix, iy))
                        else:
                            soft.add((ix, iy))
            self.blocked = (hard, soft - hard)
        return self.blocked

    def occupancy(self):
        key = (self.occ_ver, len(self.wires), self.obs_ver)
        if self.occ is not None and self.occ_key == key:
            return self.occ
        occ = {}
        for w in self.wires:
            ent = self.routes.get(w)
            if not ent or not ent[2] or ent[0] != self.obs_ver:
                continue
            net = self.root.get(self.k(w[0], w[1]))
            pts = ent[2]
            for p, q in zip(pts, pts[1:]):
                if p[1] == q[1]:
                    cy = round(p[1] / RU)
                    for cx in range(round(min(p[0], q[0]) / RU), round(max(p[0], q[0]) / RU) + 1):
                        occ.setdefault((cx, cy, 0), set()).add((net, w))
                elif p[0] == q[0]:
                    cx = round(p[0] / RU)
                    for cy in range(round(min(p[1], q[1]) / RU), round(max(p[1], q[1]) / RU) + 1):
                        occ.setdefault((cx, cy, 1), set()).add((net, w))
        self.occ, self.occ_key = occ, key
        return occ

    def route_world(self, w):
        # orthogonal path around parts (world px), or None if there's no room
        pa, ia, pb, ib = w
        a, b = pa.pin_world(ia), pb.pin_world(ib)
        da, db = pa.exit_dir(ia), pb.exit_dir(ib)
        sa = ((a[0] + da[0] * C) // RU, (a[1] + da[1] * C) // RU)
        sb = ((b[0] + db[0] * C) // RU, (b[1] + db[1] * C) // RU)
        blocked, soft = self.blocked_set()
        if sa in blocked or sb in blocked:
            return None
        lo = (min(sa[0], sb[0]) - 14, min(sa[1], sb[1]) - 14)
        hi = (max(sa[0], sb[0]) + 14, max(sa[1], sb[1]) + 14)
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        occ = self.occupancy()
        mynet = self.root.get(self.k(pa, ia))

        def others(key):
            # nets other than mine that sit on this cell and axis
            v = occ.get(key)
            return bool(v) and any(n != mynet for n, _ in v)

        start = (sa[0], sa[1], dirs.index(da))
        heap = [(abs(sa[0] - sb[0]) + abs(sa[1] - sb[1]), 0, start)]
        best, parent, n, end = {start: 0}, {}, 0, None
        while heap:
            f, g, st = heapq.heappop(heap)
            if g > best.get(st, 1e9):
                continue
            x, y, d = st
            if (x, y) == sb:
                end = st
                break
            n += 1
            if n > 5000:
                return None
            for nd, (dx, dy) in enumerate(dirs):
                if nd == d ^ 1:
                    continue
                nx, ny = x + dx, y + dy
                if nx < lo[0] or nx > hi[0] or ny < lo[1] or ny > hi[1] or (nx, ny) in blocked:
                    continue
                ax = nd >> 1
                step = 1.0
                if others((nx, ny, ax)):
                    step += 5.0                 # never ride on top of another net's wire
                elif ax == 0 and (others((nx, ny - 1, 0)) or others((nx, ny + 1, 0))) \
                        or ax == 1 and (others((nx - 1, ny, 1)) or others((nx + 1, ny, 1))):
                    step = 0.4                  # next to a wire going the same way: lay alongside it
                elif others((nx, ny, 1 - ax)):
                    step += 1.0                 # crossing
                ng = g + step + (0 if nd == d else 2) + (4 if (nx, ny) in soft else 0)
                ns = (nx, ny, nd)
                if ng < best.get(ns, 1e9):
                    best[ns] = ng
                    parent[ns] = st
                    heapq.heappush(heap, (ng + abs(nx - sb[0]) + abs(ny - sb[1]), ng, ns))
        if end is None:
            return None
        cells = []
        st = end
        while st is not None:
            cells.append((st[0] * RU, st[1] * RU))
            st = parent.get(st)
        cells.reverse()
        pts = [a] + cells + [b]
        out = [pts[0]]
        for q in pts[1:]:       # drop points in the middle of straight runs
            while len(out) >= 2 and ((out[-2][0] == out[-1][0] == q[0]) or (out[-2][1] == out[-1][1] == q[1])):
                out.pop()
            if q != out[-1]:
                out.append(q)
        return out

    def wire_screen(self, w):
        pa, ia, pb, ib = w
        pins = (pa.pin_world(ia), pb.pin_world(ib))
        ent = self.routes.get(w)
        fresh = ent is not None and ent[0] == self.obs_ver and ent[1] == pins
        if not fresh:
            dragging = self.drag is not None and self.drag['kind'] == 'part' and self.drag['moved']
            same_pins = ent is not None and ent[1] == pins
            if dragging and same_pins:
                pass            # wires nobody is touching keep their path while you drag
            elif self.route_budget > 0:
                self.route_budget -= 1
                ent = (self.obs_ver, pins, self.route_world(w))
                self.routes[w] = ent
                self.occ_ver += 1
            elif not same_pins:
                ent = None      # no time left this frame, plain route for now
        pts = ent[2] if ent else None
        if pts:
            return [(round(x), round(y)) for x, y in (w2s(*q) for q in pts)]
        return wire_pts(pa.pin_pos(ia), pb.pin_pos(ib))

    def tint(self, w, state):
        # every wire gets its own hue, brightness still says on / off / floating
        pa, ia, pb, ib = w
        key = (pa.gx, pa.gy, ia, pb.gx, pb.gy, ib)
        ck = (key, state, self.light)
        c = self.tint_cache.get(ck)
        if c is None:
            hue = (zlib.crc32(repr(key).encode()) % 997) / 997
            if self.light:
                l, sat = {'on': (0.38, 1.0), 'off': (0.66, 0.55), 'float': (0.45, 0.25)}[state]
            else:
                l, sat = {'on': (0.62, 1.0), 'off': (0.38, 0.65), 'float': (0.64, 0.28)}[state]
            c = tuple(int(v * 255) for v in colorsys.hls_to_rgb(hue, l, sat))
            if len(self.tint_cache) > 20000:
                self.tint_cache.clear()
            self.tint_cache[ck] = c
        return c

    # ------------------------------------------------------------ saving
    @staticmethod
    def prims(p):
        out = []
        App.flatten(p, out, [])
        return out

    def part_to_dict(self, p, dx=0, dy=0):
        d = dict(kind=p.kind, gx=p.gx - dx, gy=p.gy - dy, on=p.on, label=p.label, pidx=p.pidx,
                 label_on=p.label_on, label_off=p.label_off,
                 desc=p.desc, desc_on=p.desc_on, desc_off=p.desc_off,
                 q=p.out if p.kind == 'NV LATCH' else 0)
        if p.kind == 'CHIP':
            d['defn'] = p.defn
            d['st'] = [[int(q.on), q.out] for q in self.prims(p)]
        return d

    def part_from_dict(self, d, level=0):
        if d['kind'] not in DEFS:
            return None
        if d['kind'] == 'CHIP':
            p = self.build_chip(d['defn'], int(d['gx']), int(d['gy']), level)
            st = d.get('st')
            prims = self.prims(p)
            if isinstance(st, list) and len(st) == len(prims):
                for q, (on, out) in zip(prims, st):
                    if q.kind == 'SWITCH':
                        q.on = bool(on)
                    elif q.kind == 'NV LATCH':
                        q.out = int(bool(out))
        else:
            p = Part(d['kind'], int(d['gx']), int(d['gy']))
        p.on = bool(d.get('on'))
        p.pidx = max(0, min((16 if p.kind in ('GAS IN', 'GAS OUT') else len(DPER) if p.kind in ('DELAY', 'EXTENDER') else len(PERIODS)) - 1, int(d.get('pidx', 3 if p.kind in ('DELAY', 'EXTENDER') else 4))))
        if p.kind == 'PIN':
            self.set_pin_dir(p, p.on)
            if d.get('label') in ('IN', 'OUT'):     # old saves pinned the default name
                d = dict(d, label=None)
        if isinstance(d.get('label'), str):
            p.label = d['label'][:MAX_LABEL]
            if p.kind == 'SWITCH':      # old saves: one name for both states
                p.label_on = p.label_off = p.label
                p.label = None
        if isinstance(d.get('label_on'), str):
            p.label_on = d['label_on'][:MAX_LABEL]
        if isinstance(d.get('label_off'), str):
            p.label_off = d['label_off'][:MAX_LABEL]
        for f in ('desc', 'desc_on', 'desc_off'):
            if isinstance(d.get(f), str):
                setattr(p, f, d[f][:MAX_DESC])
        if p.kind == 'NV LATCH':
            p.out = int(bool(d.get('q')))
        return p

    def set_pin_dir(self, p, out):
        p.on = bool(out)
        p.d = DEFS['PIN_O' if out else 'PIN']

    def build_chip(self, defn, gx, gy, level=0):
        if level > MAX_DEPTH:
            raise ValueError('chips nested too deep')
        clones = [self.part_from_dict(d, level + 1) for d in defn['parts']]
        if None in clones:
            raise ValueError('bad chip')
        p = Part('CHIP', gx, gy)
        p.defn = defn
        p.inner = clones
        p.inner_wires = [(clones[a], ia, clones[b], ib) for a, ia, b, ib in defn['wires']]
        pins = sorted((c for c in clones if c.kind == 'PIN'), key=lambda c: (c.gy, c.gx))
        ins = [c for c in pins if not c.on]
        outs = [c for c in pins if c.on]
        p.pinmap = ins + outs
        p.pnames = [self.base_label(c) for c in p.pinmap]
        nl = len(ins)
        lw = max([len(n) for n in p.pnames[:nl]] or [0])
        rw = max([len(n) for n in p.pnames[nl:]] or [0])
        # lamps, displays and 7seg digits inside show up in the chip body
        inds = []
        for q in sorted(clones, key=lambda c: (c.gy, c.gx)):
            if q.kind in IND_KINDS:
                inds.append(q)
            elif q.kind == 'CHIP':
                inds.extend(q.inds)
        p.inds, p.lw, p.rw = inds, lw, rw
        w = max(4, -(-((lw + rw) * 7 + 24) // C))
        h = max(len(ins), len(outs), 1) + 1
        if inds:
            cols = min(len(inds), 5)
            w = max(4, -(-((lw + rw) * 7 + 24) // C) + cols * 2)
            h = max(h, -(-len(inds) // cols) * 3 + 1)
        p.d = dict(w=w, h=h, pins=[(0, i + 1, 'in') for i in range(len(ins))]
                   + [(w, j + 1, 'out') for j in range(len(outs))])
        p.label = defn.get('name', 'CHIP')
        return p

    def save(self):
        idx = {p.uid: i for i, p in enumerate(self.parts)}
        data = dict(
            version=2, made_by=AUTHOR, rate=self.rate, light=self.light,
            view=[CAMX, CAMY, ZOOM], script=self.ed.text(), dock=self.dock_open, dock_h=self.dock_h,
            parts=[self.part_to_dict(p) for p in self.parts],
            wires=[[idx[a.uid], ia, idx[b.uid], ib] for a, ia, b, ib in self.wires])
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
        except OSError as err:
            print('save failed:', err)
        self.dirty = False
        self.last_save = time.time()

    def autosave(self):
        if self.dirty and time.time() - self.last_save >= SAVE_EVERY:
            self.save()

    def load(self):
        global CAMX, CAMY, ZOOM
        try:
            with open(self.path) as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (ValueError, OSError):
            data = None
        try:
            if data is None:
                raise ValueError
            parts = [self.part_from_dict(d) for d in data['parts']]
            wires = []
            for a, ia, b, ib in data['wires']:
                pa, pb = parts[a], parts[b]
                if pa and pb and 0 <= ia < len(pa.d['pins']) and 0 <= ib < len(pb.d['pins']):
                    wires.append((pa, ia, pb, ib))
            self.parts = [p for p in parts if p]
            self.wires = wires
            self.topo_key = None
            self.rate = max(1, min(MAX_RATE, int(data.get('rate', self.rate))))
            self.light = bool(data.get('light'))
            v = data.get('view')
            if isinstance(v, list) and len(v) == 3:
                CAMX, CAMY = float(v[0]), float(v[1])
                ZOOM = max(MIN_ZOOM, min(MAX_ZOOM, float(v[2])))
            if isinstance(data.get('script'), str):
                self.ed.set_text(data['script'][:20000])
            self.dock_open = bool(data.get('dock'))
            self.dock_h = max(130, min(600, int(data.get('dock_h', 260))))
            set_theme(self.light)
            self.reset_caches()
        except (KeyError, TypeError, ValueError, IndexError):
            try:
                os.replace(self.path, self.path + '.bad')   # keep the broken file
            except OSError:
                pass

    def reset_caches(self):
        self.grid_cache = None
        self.icons = {}

    # ------------------------------------------------------------ helpers
    def pal_items(self):
        return PAL_ITEMS + ['CHIP: ' + n for n in self.chip_defs]

    def chips_dir(self):
        return os.path.join(os.path.dirname(self.path), 'chips')

    def scan_chips(self):
        self.chip_defs = {}
        try:
            names = sorted(os.listdir(self.chips_dir()))
        except OSError:
            return
        for fn in names:
            if not fn.endswith('.chip.json'):
                continue
            try:
                with open(os.path.join(self.chips_dir(), fn)) as f:
                    d = json.load(f)
                if isinstance(d, dict) and 'parts' in d and 'wires' in d:
                    self.chip_defs[str(d.get('name') or fn[:-10])[:MAX_LABEL]] = d
            except (OSError, ValueError):
                pass

    def save_chip(self):
        # ctrl+s / button: ask for a name for the selected chip
        chips = [p for p in self.parts if p in self.sel and p.kind == 'CHIP']
        if len(chips) != 1:
            self.say('select a chip (or drag one onto the CHIPS panel)')
            return
        self.ask_chip_name(chips[0])

    def ask_chip_name(self, p):
        self.finish_edit(False) if self.editing else None
        self.namebox = dict(part=p, text=(p.label or 'CHIP')[:MAX_LABEL], fresh=True)
        pygame.key.set_repeat(400, 35)

    def namebox_key(self, e):
        nb = self.namebox
        k = e.key
        if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            name = nb['text'].strip()
            if not name:
                self.say('give it a name first')
                return
            self.namebox = None
            pygame.key.set_repeat()
            self.write_chip(nb['part'], name[:MAX_LABEL])
        elif k == pygame.K_ESCAPE:
            self.namebox = None
            pygame.key.set_repeat()
        elif k == pygame.K_BACKSPACE:
            nb['text'] = '' if nb['fresh'] else nb['text'][:-1]
            nb['fresh'] = False
        elif e.unicode and e.unicode.isprintable():
            if nb['fresh']:
                nb['text'], nb['fresh'] = '', False
            if len(nb['text']) < MAX_LABEL:
                nb['text'] += e.unicode

    def namebox_rects(self, W, H):
        box = pygame.Rect(0, 0, 380, 150)
        box.center = (W // 2, H // 2)
        field = pygame.Rect(box.x + 24, box.y + 54, box.w - 48, 36)
        ok = pygame.Rect(0, 0, 90, 30)
        ok.bottomright = (box.right - 24, box.bottom - 16)
        cancel = pygame.Rect(0, 0, 90, 30)
        cancel.bottomright = (ok.x - 10, box.bottom - 16)
        return box, field, ok, cancel

    def namebox_mouse(self, e):
        if e.type != pygame.MOUSEBUTTONDOWN or e.button != 1:
            return
        _, _, ok, cancel = self.namebox_rects(*pygame.display.get_surface().get_size())
        if ok.collidepoint(e.pos):
            self.namebox_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode=''))
        elif cancel.collidepoint(e.pos):
            self.namebox_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=''))

    def draw_namebox(self, surf):
        W, H = surf.get_size()
        nb = self.namebox
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((*DIM, 150))
        surf.blit(dim, (0, 0))
        box, field, ok, cancel = self.namebox_rects(W, H)
        pygame.draw.rect(surf, PANEL, box, border_radius=12)
        pygame.draw.rect(surf, PART_LINE, box, 1, border_radius=12)
        self.label(surf, 'name your chip', TEXT, (box.centerx, box.y + 26))
        pygame.draw.rect(surf, BG, field, border_radius=8)
        pygame.draw.rect(surf, SEL, field, 1, border_radius=8)
        caret = '_' if (pygame.time.get_ticks() // 400) % 2 == 0 else ' '
        t = self.font.render(nb['text'] + caret, True, SEL if nb['fresh'] else TEXT)
        surf.blit(t, (field.x + 10, field.centery - t.get_height() // 2))
        mp = pygame.mouse.get_pos()
        for r, lab, hot in ((cancel, 'cancel', False), (ok, 'save', True)):
            pygame.draw.rect(surf, SEL if hot else CARD_HI if r.collidepoint(mp) else CARD, r, border_radius=8)
            self.label(surf, lab, BG if hot else TEXT, r.center)

    def write_chip(self, p, name):
        safe = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name).strip('_') or 'chip'
        d = json.loads(json.dumps(p.defn))
        d['name'] = name
        p.label = name
        self.dirty = True
        d['made_by'] = AUTHOR
        try:
            os.makedirs(self.chips_dir(), exist_ok=True)
            tmp = os.path.join(self.chips_dir(), safe + '.tmp')
            with open(tmp, 'w') as f:
                json.dump(d, f)
            os.replace(tmp, os.path.join(self.chips_dir(), safe + '.chip.json'))
        except OSError as err:
            self.say(f'could not save chip ({err.__class__.__name__})')
            return
        self.scan_chips()
        self.say(f'saved "{name}", it is in the CHIPS list now')

    def new_part(self, k):
        if k.startswith('CHIP: '):
            d = self.chip_defs.get(k[6:])
            if d is None:
                return None
            try:
                return self.build_chip(json.loads(json.dumps(d)), 0, 0)
            except (ValueError, KeyError, TypeError):
                self.say("that chip file is broken")
                return None
        return Part(k)

    def pin_at(self, pos, r=6):
        best, bd = None, r + 1
        for p in reversed(self.parts):
            for i in range(len(p.d['pins'])):
                q = p.pin_pos(i)
                d = max(abs(q[0] - pos[0]), abs(q[1] - pos[1]))
                if d <= r and d < bd:
                    best, bd = (p, i), d
        return best

    def part_at(self, pos):
        for p in reversed(self.parts):
            if p.rect().collidepoint(pos):
                return p
        return None

    def wire_at(self, pos):
        for w in reversed(self.wires):
            pts = self.wire_screen(w)
            if any(seg_dist(pos, a, b) <= 6 for a, b in zip(pts, pts[1:])):
                return w
        return None

    def remove_part(self, p):
        if p is self.editing:
            self.finish_edit(False)
        self.parts.remove(p)
        self.sel.discard(p)
        self.wires = [w for w in self.wires if w[0] is not p and w[2] is not p]
        self.topo_key = None

    def add_wire(self, pa, ia, pb, ib):
        for w in self.wires:
            if (w[0] is pa and w[1] == ia and w[2] is pb and w[3] == ib) or \
                    (w[0] is pb and w[1] == ib and w[2] is pa and w[3] == ia):
                return False
        self.wires.append((pa, ia, pb, ib))
        self.topo_key = None
        return True

    def clear_all(self):
        self.parts.clear()
        self.wires.clear()
        self.sel.clear()
        self.topo_key = None
        self.dirty = True

    # overlap
    def group_collides(self, group):
        gs = set(group)
        orects = [q.rect() for q in self.parts if q not in gs]
        return any(p.rect().collidelist(orects) != -1 for p in group)

    def label_fits(self, p, text):
        r0 = p.rect()
        r = pygame.Rect(r0.x, r0.y, round(label_w(text + '_') * C * ZOOM), r0.h)
        return not any(q is not p and r.colliderect(q.rect()) for q in self.parts)

    # ------------------------------------------------------------ selection and clipboard
    def delete_sel(self):
        for p in [q for q in self.parts if q in self.sel]:
            self.remove_part(p)
        self.sel.clear()
        self.dirty = True

    def copy_sel(self):
        group = [p for p in self.parts if p in self.sel]
        if not group:
            return
        minx, miny = min(p.gx for p in group), min(p.gy for p in group)
        idx = {p.uid: i for i, p in enumerate(group)}
        self.clip = dict(
            parts=[self.part_to_dict(p, minx, miny) for p in group],
            wires=[[idx[a.uid], ia, idx[b.uid], ib] for a, ia, b, ib in self.wires
                   if a.uid in idx and b.uid in idx])

    def paste(self):
        if not self.clip:
            return
        if self.drag and self.drag.get('carry'):
            self.cancel_carry()
        try:
            clones = [self.part_from_dict(d) for d in self.clip['parts']]
        except (ValueError, KeyError):
            return
        self.parts.extend(clones)
        for a, ia, b, ib in self.clip['wires']:
            self.wires.append((clones[a], ia, clones[b], ib))
        self.topo_key = None
        self.sel = set(clones)
        bw = max(p.gx + p.d['w'] for p in clones) * C * ZOOM
        bh = max(p.gy + p.d['h'] for p in clones) * C * ZOOM
        d = dict(kind='part', parts=clones, rel=[(p.gx, p.gy) for p in clones],
                 ox=bw // 2, oy=bh // 2, start=pygame.mouse.get_pos(), moved=True,
                 new=True, carry=True, hit=None, orig=None)
        self.place_group(d, *pygame.mouse.get_pos())
        self.drag = d       # follows the mouse until you click to drop it

    # chips
    def say(self, text):
        self.toast = (text, time.time() + 2.8)

    def find_free(self, group):
        # nudge a group to the nearest spot where it doesn't overlap anything
        base = [(p.gx, p.gy) for p in group]
        for r in range(0, 80):
            for dx in range(-r, r + 1):
                rest = r - abs(dx)
                for dy in ({rest, -rest}):
                    for p, (gx, gy) in zip(group, base):
                        p.gx, p.gy = gx + dx, gy + dy
                    if not self.group_collides(group):
                        return
        for p, (gx, gy) in zip(group, base):
            p.gx, p.gy = gx, gy

    def chipify(self):
        group = [p for p in self.parts if p in self.sel and p.kind != 'LABEL']
        if not group:
            self.say('select some parts first')
            return
        depth = 1 + max([p.defn.get('depth', 1) for p in group if p.kind == 'CHIP'] or [0])
        if depth > MAX_DEPTH:
            self.say(f'chips can only nest {MAX_DEPTH} deep')
            return
        minx, miny = min(p.gx for p in group), min(p.gy for p in group)
        idx = {p.uid: i for i, p in enumerate(group)}
        defn = dict(name='CHIP', depth=depth,
                    parts=[self.part_to_dict(p, minx, miny) for p in group],
                    wires=[[idx[a.uid], ia, idx[b.uid], ib] for a, ia, b, ib in self.wires
                           if a.uid in idx and b.uid in idx])
        try:
            chip = self.build_chip(defn, minx, miny)
        except (ValueError, KeyError):
            self.say("couldn't make that chip")
            return
        for p in group:
            self.remove_part(p)
        self.parts.append(chip)
        self.find_free([chip])
        self.topo_key = None
        self.sel = {chip}
        self.dirty = True
        self.say('chip made, drag it onto the parts panel to name + save it')

    def unpack(self):
        chips = [p for p in self.parts if p in self.sel and p.kind == 'CHIP']
        if not chips:
            self.say('select a chip first')
            return
        chip = chips[0]
        self.parts.remove(chip)
        self.wires = [w for w in self.wires if w[0] is not chip and w[2] is not chip]
        for q in chip.inner:
            q.gx += chip.gx
            q.gy += chip.gy
        self.parts.extend(chip.inner)
        self.wires.extend(chip.inner_wires)
        self.find_free(chip.inner)
        self.sel = set(chip.inner)
        self.topo_key = None
        self.dirty = True

    def cancel_carry(self):
        d, self.drag = self.drag, None
        for p in d['parts']:
            if p in self.parts:
                self.remove_part(p)

    def on_escape(self):
        # True if esc did something (so the game doesn't quit)
        if self.namebox:
            self.namebox = None
            pygame.key.set_repeat()
            return True
        if self.help_open:
            self.help_open = False
            return True
        if self.ed.focus or self.search_focus:
            self.set_focus(None)
            return True
        if self.drag and self.drag.get('carry'):
            self.cancel_carry()
            return True
        if self.sel:
            self.sel.clear()
            return True
        return False

    def place_group(self, d, mx, my):
        wx, wy = s2w(mx - d['ox'], my - d['oy'])
        gx0, gy0 = round(wx / C), round(wy / C)
        for p, (rx, ry) in zip(d['parts'], d['rel']):
            p.gx, p.gy = gx0 + rx, gy0 + ry

    def begin_part_drag(self, group, pos, hit):
        minx, miny = min(p.gx for p in group), min(p.gy for p in group)
        sx, sy = w2s(minx * C, miny * C)
        self.drag = dict(kind='part', parts=group,
                         rel=[(p.gx - minx, p.gy - miny) for p in group],
                         ox=pos[0] - sx, oy=pos[1] - sy,
                         start=pos, moved=False, new=False, carry=False, hit=hit,
                         orig=[(p.gx, p.gy) for p in group])

    def finish_part_drag(self, d, pos):
        group = d['parts']
        self.dirty = True
        if d['moved']:
            self.last_click = (None, 0)     # a drag isn't half a double-click
        lay_ = self.layout()
        if (d['moved'] and not d['new'] and len(group) == 1 and group[0].kind == 'CHIP'
                and lay_['right'].collidepoint(pos)):
            for p, (gx, gy) in zip(group, d['orig']):
                p.gx, p.gy = gx, gy
            self.sel = {group[0]}
            self.ask_chip_name(group[0])
            return
        if self.group_collides(group):
            if d['new']:
                for p in group:
                    if p in self.parts:
                        self.remove_part(p)
            else:
                for p, (gx, gy) in zip(group, d['orig']):
                    p.gx, p.gy = gx, gy
        elif not self.in_work(pos) and d['moved']:
            for p in group:             # dropped back on the panel
                if p in self.parts:
                    self.remove_part(p)
        elif not d['moved'] and d['hit'] is not None:
            h = d['hit']
            if h.kind == 'SWITCH':
                h.on = not h.on
            elif h.kind in ('BUTTON', 'TOUCH'):
                h.pulse = True
                h.flash = 0.15
            elif h.kind == 'CLOCK':
                h.pidx = (h.pidx + 1) % len(PERIODS)
                h.counter = 0
            elif h.kind in ('DELAY', 'EXTENDER'):
                h.pidx = (h.pidx + 1) % len(DPER)
                h.counter, h.buf = 0, None
            elif h.kind in ('GAS IN', 'GAS OUT'):
                h.pidx = (h.pidx + 1) % 16
                self.dirty = True
            elif h.kind == 'PIN':
                self.set_pin_dir(h, not h.on)

    # ------------------------------------------------------------ renaming
    def base_label(self, p):
        if p.kind == 'SWITCH':
            t = p.label_on if p.on else p.label_off
            return t if t is not None else ('ON' if p.on else 'OFF')
        if p.label is not None:
            return p.label
        k = p.kind
        if k == 'SOURCE':
            return 'ON'
        if k == 'BUTTON':
            return 'BTN'
        if k == 'CLOCK':
            return f'CLK {PERIODS[p.pidx]}'
        if k in ('DISPLAY', 'TOUCH'):
            return ''
        if k == 'PIN':
            return 'OUT' if p.on else 'IN'
        if k == 'CHIP':
            return 'CHIP'
        return k

    def base_desc(self, p):
        if p.kind == 'SWITCH':
            t = p.desc_on if p.on else p.desc_off
            return t if t is not None else ('passes' if p.on else 'blocks')
        if p.desc is not None:
            return p.desc
        return DEFAULT_DESC.get(p.kind, '')

    def desc_text(self, p):
        if p is self.editing and self.edit_field == 'desc':
            return self.edit_text + ('_' if (pygame.time.get_ticks() // 400) % 2 == 0 else ' ')
        return self.base_desc(p)

    def label_text(self, p):
        if p is self.editing and self.edit_field == 'title':
            return self.edit_text + ('_' if (pygame.time.get_ticks() // 400) % 2 == 0 else ' ')
        return self.base_label(p)

    def start_edit(self, p, field='title'):
        self.editing = p
        self.edit_field = field
        self.edit_text = self.base_desc(p) if field == 'desc' else self.base_label(p)
        self.edit_on = p.on
        self.edit_fresh = True      # first key replaces everything
        pygame.key.set_repeat(400, 35)

    def finish_edit(self, commit):
        p = self.editing
        self.editing = None
        pygame.key.set_repeat()
        if p and commit and p in self.parts and self.edit_field == 'desc':
            if p.kind == 'SWITCH':
                if self.edit_on:
                    p.desc_on = self.edit_text
                else:
                    p.desc_off = self.edit_text
            else:
                p.desc = self.edit_text
            self.dirty = True
        elif p and commit and p in self.parts:
            if p.kind == 'SWITCH':
                if self.edit_on:
                    p.label_on = self.edit_text
                else:
                    p.label_off = self.edit_text
            else:
                p.label = None
                if self.edit_text != self.base_label(p):    # untouched text stays default
                    p.label = self.edit_text
            self.dirty = True

    def edit_key(self, e):
        k = e.key
        if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.finish_edit(True)
        elif k == pygame.K_ESCAPE:
            self.finish_edit(False)
        elif k == pygame.K_BACKSPACE:
            self.edit_text = '' if self.edit_fresh else self.edit_text[:-1]
            self.edit_fresh = False
        elif e.unicode and e.unicode.isprintable():
            if self.edit_fresh:
                self.edit_text = ''
                self.edit_fresh = False
            if self.edit_field == 'desc':
                if len(self.edit_text) < MAX_DESC:
                    self.edit_text += e.unicode
            elif len(self.edit_text) < MAX_LABEL:
                cand = self.edit_text + e.unicode
                if self.editing.kind != 'LABEL' or self.label_fits(self.editing, cand):
                    self.edit_text = cand

    # ------------------------------------------------------------ input
    def update_text(self, width):
        # (text, is_title) lines of the update notice: commit title then the description under it
        u = self.updater
        out = [(l, True) for l in wrap(self.font, u.message or 'new version of the game', width)[:3]]
        for para in (u.body or '').split('\n'):
            para = para.strip()
            if para:
                out += [(l, False) for l in wrap(self.font, para, width)]
        return out[:10]

    def modal_rects(self, W, H):
        u = self.updater
        w, h, img = 560, 190, None
        if u and u.news and u.state != 'installing':
            lines = self.update_text(w - 40)
            pic = u.picture()
            ih = 0
            if pic:
                k = min((w - 40) / pic.get_width(), 230 / pic.get_height())
                ih = max(1, int(pic.get_height() * k))
                img = pygame.Rect(0, 0, max(1, int(pic.get_width() * k)), ih)
            h = min(100 + len(lines) * 20 + (ih + 14 if ih else 0) + 40, H - 20)
        box = pygame.Rect(0, 0, w, h)
        box.center = (W // 2, H // 2)
        btn = pygame.Rect(0, 0, 90, 32)
        btn.midbottom = (box.centerx, box.bottom - 16)
        if img:
            img.midtop = (box.centerx, box.y + 52)
        self.modal_img = img
        return box, btn

    def handle(self, e):
        u = self.updater
        if u and u.modal():
            if u.state != 'installing':
                _, btn = self.modal_rects(*pygame.display.get_surface().get_size())
                ok = (e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)) \
                    or (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and btn.collidepoint(e.pos))
                if ok:
                    u.close_news() if u.state != 'failed' else u.dismiss()
            return
        if self.namebox:
            if e.type == pygame.KEYDOWN:
                self.namebox_key(e)
            else:
                self.namebox_mouse(e)
            return
        if self.ui_event(e):
            return
        if self.running:
            # run mode: nothing can be edited, only clicked
            if e.type == pygame.KEYDOWN:
                if e.key in RUN_KEYS and not (e.mod & pygame.KMOD_CTRL):
                    self.on_key(e)
                return
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if self.in_work(e.pos):
                    p = self.part_at(e.pos)
                    if p:
                        self.run_click(p)
                return
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                return
        if e.type == pygame.KEYDOWN and self.editing:
            self.edit_key(e)
            return
        if e.type == pygame.MOUSEBUTTONDOWN and self.editing:
            self.finish_edit(True)
        if e.type == pygame.KEYDOWN:
            self.on_key(e)
        elif e.type == pygame.MOUSEWHEEL:
            mp = pygame.mouse.get_pos()
            if self.in_work(mp):
                self.zoom_at(mp, 1.12 ** e.y)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.on_down(e)
        elif e.type == pygame.MOUSEMOTION:
            self.on_motion(e)
        elif e.type == pygame.MOUSEBUTTONUP:
            if e.button == 1:
                self.on_up(e)
            elif e.button in (2, 3):
                self.end_pan(e)

    def zoom_at(self, mp, f):
        # zoom toward whatever the mouse is pointing at
        global CAMX, CAMY, ZOOM
        wx, wy = s2w(*mp)
        ZOOM = max(MIN_ZOOM, min(MAX_ZOOM, ZOOM * f))
        CAMX = wx - (mp[0] - VX0) / ZOOM
        CAMY = wy - (mp[1] - VY0) / ZOOM
        self.dirty = True
        d = self.drag
        if d and d['kind'] == 'part' and d.get('carry'):
            self.place_group(d, *mp)

    def end_pan(self, e):
        d = self.drag
        if not d or d['kind'] != 'pan':
            return
        self.drag = None
        if d['moved'] or d['button'] != 3 or self.running:
            return
        p = self.part_at(d['start'])        # rmb click without moving = delete
        if p:
            self.remove_part(p)
            self.dirty = True
        else:
            w = self.wire_at(d['start'])
            if w:
                self.wires.remove(w)
                self.topo_key = None
                self.dirty = True

    def on_key(self, e):
        k = e.key
        ctrl = bool(e.mod & pygame.KMOD_CTRL)
        shift = bool(e.mod & pygame.KMOD_SHIFT)
        if ctrl and k == pygame.K_c:
            self.copy_sel()
        elif ctrl and k == pygame.K_x:
            self.copy_sel()
            self.delete_sel()
        elif ctrl and k == pygame.K_v:
            self.paste()
        elif ctrl and k == pygame.K_s:
            self.save_chip()
        elif ctrl and k == pygame.K_a:
            self.sel = set(self.parts)
        elif ctrl and shift and k == pygame.K_DELETE:
            self.clear_all()
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self.delete_sel()
        elif k == pygame.K_TAB:
            if np is None:
                self.say('gas lab needs numpy (pip install numpy)')
            else:
                self.mode = 'gas'
        elif k == pygame.K_g and not ctrl:
            self.chipify()
        elif k == pygame.K_u and not ctrl:
            self.unpack()
        elif k == pygame.K_HOME:
            global CAMX, CAMY, ZOOM
            CAMX = CAMY = 0.0
            ZOOM = 1.0
            self.dirty = True
        elif k == pygame.K_SPACE:
            self.paused = not self.paused
        elif k == pygame.K_l:
            self.light = not self.light
            set_theme(self.light)
            self.reset_caches()
            self.dirty = True
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and not ctrl:
            self.toggle_run()
        elif k == pygame.K_UP:
            self.rate = min(MAX_RATE, self.rate * 2)
            self.dirty = True
        elif k == pygame.K_DOWN:
            self.rate = max(1, self.rate // 2)
            self.dirty = True
        elif k == pygame.K_n and self.paused and self.running:
            for p in self.sim_parts:
                p.glow = 0.0
                p.seg_glow = [0.0] * 7
            self.advance(1)

    def on_down(self, e):
        mx, my = e.pos
        if e.button in (2, 3):
            if self.drag and self.drag.get('carry'):
                if e.button == 3:
                    self.cancel_carry()
                return
            if self.drag is None and self.in_work(e.pos):
                self.drag = dict(kind='pan', start=e.pos, cam=(CAMX, CAMY), moved=False,
                                 button=e.button)
            return
        if e.button != 1:
            return
        if self.drag and self.drag.get('carry'):
            d, self.drag = self.drag, None
            self.finish_part_drag(d, e.pos)
            return
        if not self.in_work(e.pos):
            return
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)
        hit = self.pin_at(e.pos)
        if hit:
            self.drag = dict(kind='wire', a=hit)
            return
        p = self.part_at(e.pos)
        if p:
            if ctrl:                    # ctrl+click adds/removes from the selection
                if p in self.sel:
                    self.sel.discard(p)
                else:
                    self.sel.add(p)
                return
            now = pygame.time.get_ticks()
            if p is self.last_click[0] and now - self.last_click[1] < 400 \
                    and p.kind not in ('DISPLAY', 'TOUCH'):
                self.last_click = (None, 0)
                if p.kind == 'SWITCH':
                    p.on = not p.on     # undo the first click's toggle
                elif p.kind == 'CLOCK':
                    p.pidx = (p.pidx - 1) % len(PERIODS)
                elif p.kind in ('DELAY', 'EXTENDER'):
                    p.pidx = (p.pidx - 1) % len(DPER)
                    p.counter, p.buf = 0, None
                elif p.kind in ('GAS IN', 'GAS OUT'):
                    p.pidx = (p.pidx - 1) % 16
                elif p.kind == 'PIN':
                    self.set_pin_dir(p, not p.on)
                body = p.kind in DESC_KINDS and e.pos[1] >= p.rect().y + sc(HDR)
                self.start_edit(p, 'desc' if body else 'title')
                return
            self.last_click = (p, now)
            if p in self.sel and len(self.sel) > 1:
                group = [q for q in self.parts if q in self.sel]
            else:
                if p not in self.sel:
                    self.sel.clear()
                group = [p]
            self.begin_part_drag(group, e.pos, p)
        else:
            self.drag = dict(kind='box', start=e.pos, cur=e.pos, moved=False,
                             add=bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_SHIFT)))

    def on_motion(self, e):
        d = self.drag
        if not d:
            return
        if d['kind'] == 'pan':
            global CAMX, CAMY
            dx, dy = e.pos[0] - d['start'][0], e.pos[1] - d['start'][1]
            if abs(dx) + abs(dy) > 4:
                d['moved'] = True
            if d['moved']:
                CAMX = d['cam'][0] - dx / ZOOM
                CAMY = d['cam'][1] - dy / ZOOM
                self.dirty = True
            return
        if d['kind'] == 'part':
            if abs(e.pos[0] - d['start'][0]) + abs(e.pos[1] - d['start'][1]) > 4:
                d['moved'] = True
            if d['moved']:
                self.place_group(d, e.pos[0], e.pos[1])
        elif d['kind'] == 'box':
            d['cur'] = e.pos
            if abs(e.pos[0] - d['start'][0]) + abs(e.pos[1] - d['start'][1]) > 4:
                d['moved'] = True

    def on_up(self, e):
        d = self.drag
        if not d or d.get('carry') or d['kind'] == 'pan':
            return
        self.drag = None
        if d['kind'] == 'wire':
            hit = self.pin_at(e.pos)
            if hit and hit != d['a']:
                (pa, ia), (pb, ib) = d['a'], hit
                if self.add_wire(pa, ia, pb, ib):
                    self.dirty = True
        elif d['kind'] == 'box':
            if d['moved']:
                r = self.box_rect(d)
                hits = {p for p in self.parts if p.rect().colliderect(r)}
                self.sel = (self.sel | hits) if d['add'] else hits
            elif not d['add']:
                self.sel.clear()
        else:
            self.finish_part_drag(d, e.pos)

    def box_rect(self, d):
        (x0, y0), (x1, y1) = d['start'], d['cur']
        w = self.layout()['work']
        x0, x1 = max(w.x, min(x0, x1)), min(w.right, max(x0, x1))
        y0, y1 = max(w.y, min(y0, y1)), min(w.bottom, max(y0, y1))
        return pygame.Rect(x0, y0, max(0, x1 - x0), max(0, y1 - y0))

    # ------------------------------------------------------------ draw
    def label(self, surf, text, color, center):
        t = self.font.render(text, True, color)
        surf.blit(t, t.get_rect(center=center))

    def draw_grid(self, surf, lay):
        work = lay['work']
        surf.fill(PANEL)
        pygame.draw.rect(surf, BG, work)
        old = surf.get_clip()
        surf.set_clip(work)
        step = C * ZOOM
        i0 = int(CAMX // C)
        i1 = int((CAMX + work.w / ZOOM) // C) + 1
        for i in range(i0, i1 + 1):
            major = i % 4 == 0
            if step < 9 and not major:
                continue
            x = round(VX0 + (i * C - CAMX) * ZOOM)
            pygame.draw.line(surf, GRID2 if major else GRID, (x, work.y), (x, work.bottom))
        j0 = int(CAMY // C)
        j1 = int((CAMY + work.h / ZOOM) // C) + 1
        for j in range(j0, j1 + 1):
            major = j % 4 == 0
            if step < 9 and not major:
                continue
            y = round(VY0 + (j * C - CAMY) * ZOOM)
            pygame.draw.line(surf, GRID2 if major else GRID, (work.x, y), (work.right, y))
        surf.set_clip(old)

    def net_color(self, s):
        if not s:
            return FLOAT
        if len(s) == 2:
            return SHORT
        return ON if 1 in s else OFF

    @staticmethod
    def seg_rects(x0, y0, dw, dh, t):
        vl = (dh - 3 * t) // 2
        return [(x0 + t, y0, dw - 2 * t, t),                     # a
                (x0 + dw - t, y0 + t, t, vl),                    # b
                (x0 + dw - t, y0 + 2 * t + vl, t, vl),           # c
                (x0 + t, y0 + dh - t, dw - 2 * t, t),            # d
                (x0, y0 + 2 * t + vl, t, vl),                    # e
                (x0, y0 + t, t, vl),                             # f
                (x0 + t, y0 + t + vl, dw - 2 * t, t)]            # g

    def draw_7seg(self, surf, p, r):
        hdr = sc(HDR)
        x0, y0 = r.x + sc(34), r.y + hdr + sc(10)
        segs = self.seg_rects(x0, y0, sc(68), r.h - hdr - sc(10) - sc(28), sc(9))
        color = p.rgb or SEG_DEFAULT
        for i, rect in enumerate(segs):
            pygame.draw.rect(surf, color if p.seg_glow[i] > 0 else SEG_OFF, rect)

    def draw_ind(self, surf, q, cell):
        # one lamp / display / digit shown inside a chip
        k = q.kind
        if k == '7SEG':
            w = int(min(cell.w - 4, (cell.h - 4) / 1.7))
            if w < 6:
                return
            h = int(w * 1.7)
            t = max(2, w // 5)
            segs = self.seg_rects(cell.centerx - w // 2, cell.centery - h // 2, w, h, t)
            color = q.rgb or SEG_DEFAULT
            for i, rect in enumerate(segs):
                pygame.draw.rect(surf, color if q.seg_glow[i] > 0 else SEG_OFF, rect)
            return
        side = min(cell.w, cell.h) - 4
        if side < 4:
            return
        box = pygame.Rect(0, 0, side, side)
        box.center = cell.center
        if k == 'LAMP':
            lit = q.glow > 0
            pygame.draw.rect(surf, LAMP_ON if lit else SEG_OFF, box)
        else:
            lit = q.glow > 0 and q.rgb
            pygame.draw.rect(surf, q.rgb if lit else SEG_OFF, box)
        pygame.draw.rect(surf, PART_LINE, box, 1)

    def draw_chip_body(self, surf, p, r, hdrh):
        n = len(p.inds)
        lp, rp = sc(p.lw * 7 + 10, 4), sc(p.rw * 7 + 10, 4)
        area = pygame.Rect(r.x + lp, r.y + hdrh + 3, r.w - lp - rp, r.h - hdrh - 6)
        if n == 0 or area.w < 8 or area.h < 8:
            return
        best, bc = -1, 1
        for cols in range(1, n + 1):
            rows = -(-n // cols)
            score = min(area.w / cols, area.h / rows / 1.7)
            if score > best:
                best, bc = score, cols
        cols, rows = bc, -(-n // bc)
        cw, ch = area.w / cols, area.h / rows
        for i, q in enumerate(p.inds):
            cx, cy = i % cols, i // cols
            self.draw_ind(surf, q, pygame.Rect(int(area.x + cx * cw), int(area.y + cy * ch),
                                               int(cw), int(ch)))

    def draw_part(self, surf, p, pcol):
        r = p.rect()
        k = p.kind
        editing = p is self.editing
        txt = ZOOM >= 0.55 and not ICON_MODE          # skip text when zoomed way out
        if k == 'LABEL':
            text = self.label_text(p)
            r = pygame.Rect(r.x, r.y, round(label_w(text) * C * ZOOM), r.h)
            if editing or not text.strip():
                pygame.draw.rect(surf, SEL if editing else FLOAT, r, 1)
            if txt:
                self.label(surf, text, SEL if editing and self.edit_fresh else TEXT, r.center)
            return
        hdrh = sc(HDR)
        rad = max(2, sc(5))
        if k in ('DISPLAY', 'TOUCH'):
            pygame.draw.rect(surf, p.rgb if p.glow > 0 and p.rgb else PART_BG, r, border_radius=rad)
            pygame.draw.rect(surf, SEL if editing else (ON if p.flash > 0 else PART_LINE), r, 1, border_radius=rad)
        else:
            body = PART_BG
            if k == 'LAMP' and p.glow > 0:
                body = LAMP_ON
            elif k == 'SOURCE' or (k == 'SWITCH' and p.on) or (k == 'BUTTON' and p.flash > 0) \
                    or (k in ('CLOCK', 'SR LATCH', 'NV LATCH', 'GATE') and (p.out and (k != 'GATE' or p.drive))):
                body = ACTIVE
            pygame.draw.rect(surf, body, r, border_radius=rad)
            hdr = pygame.Rect(r.x, r.y, r.w, hdrh)
            pygame.draw.rect(surf, cat_color(k), hdr, border_top_left_radius=rad, border_top_right_radius=rad)
            if txt:
                text = self.label_text(p)
                if text.strip():
                    t = self.tiny.render(text, True, SEL if editing and self.edit_fresh else HDR_TEXT)
                    surf.set_clip(hdr.inflate(-4, 0))
                    surf.blit(t, t.get_rect(center=hdr.center))
                    surf.set_clip(None)
            pygame.draw.rect(surf, SEL if editing else PART_LINE, r, 1, border_radius=rad)
            cx, cy = r.centerx, r.y + hdrh + (r.h - hdrh) // 2
            if k in DESC_KINDS and txt:
                text = self.desc_text(p)
                widget = k in WIDGET_KINDS
                if text.strip():
                    if widget:
                        cy = r.bottom - sc(10)
                    room = r.bottom - (sc(18) if widget else sc(4)) - (r.y + hdrh + 3)
                    lines = wrap(self.descf, text, r.w - 8)[:max(0, room // 12)]
                    col = SEL if p is self.editing and self.edit_fresh else TEXT_DIM
                    surf.set_clip(pygame.Rect(r.x + 2, r.y + hdrh, r.w - 4, r.h - hdrh - 1))
                    for li, line in enumerate(lines):
                        t = self.descf.render(line, True, col)
                        surf.blit(t, t.get_rect(midtop=(r.centerx, r.y + hdrh + 3 + li * 12)))
                    surf.set_clip(None)
            if k == 'SWITCH':
                track = pygame.Rect(cx - sc(12), cy - sc(5), sc(24), sc(10))
                pygame.draw.rect(surf, TEXT_DIM, track, 1, border_radius=sc(5))
                kx = track.right - sc(10) if p.on else track.x + sc(2)
                pygame.draw.rect(surf, ON if p.on else TEXT_DIM, (kx, track.y + sc(2), sc(8), sc(6)), border_radius=sc(3))
            elif k == 'BUTTON':
                b = pygame.Rect(cx - sc(10), cy - sc(5), sc(20), sc(10))
                pygame.draw.rect(surf, ON if p.flash > 0 else PART_BG, b, border_radius=sc(4))
                pygame.draw.rect(surf, TEXT_DIM, b, 1, border_radius=sc(4))
            elif k in ('GAS IN', 'GAS OUT') and txt:
                t = self.tiny.render(f'link {p.pidx + 1}', True, TEXT_DIM)
                surf.blit(t, t.get_rect(center=(cx, cy)))
            elif k in ('CLOCK', 'DELAY', 'EXTENDER') and txt:
                n = (PERIODS if k == 'CLOCK' else DPER)[p.pidx]
                t = self.tiny.render(f'{n} ticks', True, TEXT_DIM)
                surf.blit(t, t.get_rect(center=(cx, cy)))
            elif k == 'PIN':
                a = sc(7)       # little arrow, signals always go left to right through a pin
                pygame.draw.polygon(surf, ON if p.on else TEXT_DIM,
                                    [(cx - a, cy - a), (cx + a, cy), (cx - a, cy + a)])
            elif k == '7SEG':
                self.draw_7seg(surf, p, r)
            elif k == 'SCOPE':
                scr = pygame.Rect(r.x + 4, r.y + hdrh + 3, r.w - 8, r.h - hdrh - 7)
                pygame.draw.rect(surf, BG, scr)
                tr = p.trace
                if tr is not None and len(tr) > 1 and scr.h > 6:
                    n_ = len(tr)
                    hi_y, lo_y = scr.y + 3, scr.bottom - 4
                    pts, last = [], None
                    for j in range(n_):
                        x_ = scr.x + 1 + j * (scr.w - 2) / (n_ - 1)
                        y_ = hi_y if tr[j] else lo_y
                        if last is not None and y_ != last:
                            pts.append((x_, last))
                        pts.append((x_, y_))
                        last = y_
                    pygame.draw.lines(surf, ON if tr[-1] else TEXT_DIM, False, pts, 1)
                pygame.draw.rect(surf, PANEL_LINE, scr, 1)
            elif k == 'CHIP' and p.inds:
                self.draw_chip_body(surf, p, r, hdrh)
        # pins
        small = k in ('DISPLAY', 'TOUCH')
        o, i_ = (sc(7, 3), sc(3, 2)) if small else (sc(9, 4), sc(5, 2))
        for i in range(len(p.d['pins'])):
            q = p.pin_pos(i)
            pygame.draw.circle(surf, BG, q, o // 2 + 1)
            pygame.draw.circle(surf, pcol(p, i), q, max(2, i_ // 2 + 1))
            if not txt:
                continue
            if k == '7SEG':
                if i < 7:
                    t = self.tiny.render(SEG_NAMES[i], True, TEXT_DIM)
                    surf.blit(t, t.get_rect(center=(q[0] + sc(11), q[1])))
                else:
                    t = self.tiny.render('RGB'[i - 7], True, TEXT_DIM)
                    surf.blit(t, t.get_rect(center=(q[0], q[1] - sc(10))))
            elif k == 'CHIP':
                t = self.tiny.render(p.pnames[i], True, TEXT_DIM)
                if p.d['pins'][i][2] == 'in':
                    surf.blit(t, t.get_rect(midleft=(q[0] + sc(7), q[1])))
                else:
                    surf.blit(t, t.get_rect(midright=(q[0] - sc(7), q[1])))

    # ------------------------------------------------------------ chrome: top bar, parts panel, script dock
    def layout(self):
        W, H = pygame.display.get_surface().get_size()
        rp = min(RPW, max(170, W // 3))
        dh = 0
        if self.dock_open:
            dh = max(130, min(self.dock_h, H - TOPH - 150))
        return dict(W=W, H=H, rp=rp, top=pygame.Rect(0, 0, W, TOPH),
                    right=pygame.Rect(W - rp, TOPH, rp, H - TOPH),
                    work=pygame.Rect(0, TOPH, W - rp, H - TOPH - dh),
                    dock=pygame.Rect(0, H - dh, W - rp, dh) if dh else None)

    def in_work(self, pos):
        return self.layout()['work'].collidepoint(pos)

    @staticmethod
    def nice(k):
        if k.startswith('CHIP: '):
            return k[6:]
        return PAL_NICE.get(k) or (k if k in GATES else k.capitalize())

    def pal_cats(self):
        out = []
        for name, kinds in PAL_CATS:
            ks = list(kinds)
            if name == 'CHIPS':
                ks += ['CHIP: ' + n for n in self.chip_defs]
            out.append((name, ks))
        return out

    def pal_layout(self, rp):
        q = self.search.strip().lower()
        pad, gap = 10, 8
        tw = (rp.w - 2 * pad - gap) // 2
        th = 86
        rows, y = [], 0
        for name, ks in self.pal_cats():
            if q:
                ks = [k for k in ks if q in self.nice(k).lower() or q in k.lower()]
                if not ks:
                    continue
            op = True if q else self.cat_open.get(name, True)
            rows.append(dict(t='hdr', cat=name, n=len(ks), open=op, rect=pygame.Rect(pad, y, rp.w - 2 * pad, 28)))
            y += 30
            if op:
                for i, k in enumerate(ks):
                    rows.append(dict(t='tile', kind=k, rect=pygame.Rect(pad + (i % 2) * (tw + gap), y + (i // 2) * (th + gap), tw, th)))
                y += -(-len(ks) // 2) * (th + gap)
            y += 4
        return rows, y

    def pal_geom(self, lay):
        rp = lay['right']
        search = pygame.Rect(rp.x + 10, rp.y + 38, rp.w - 20, 28)
        area = pygame.Rect(rp.x, rp.y + 74, rp.w, rp.h - 74 - 24)
        return search, area

    def pal_clamp(self, lay):
        rows, total = self.pal_layout(lay['right'])
        _, area = self.pal_geom(lay)
        self.pal_scroll = max(0, min(max(0, total - area.h), self.pal_scroll))
        return rows, total

    def part_icon(self, k, w, h):
        cd = self.chip_defs.get(k[6:]) if k.startswith('CHIP: ') else None
        key = (k, w, h, self.light, id(cd))
        s = self.icons.get(key)
        if s is not None:
            return s
        global CAMX, CAMY, ZOOM, VX0, VY0, ICON_MODE
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        p = self.new_part(k)
        if p is not None:
            pw = (label_w(p.label or 'LABEL') if p.kind == 'LABEL' else p.d['w']) * C
            ph = p.d['h'] * C
            z = min((w - 12) / pw, (h - 10) / ph, 0.9)
            keep = (CAMX, CAMY, ZOOM, VX0, VY0)
            ZOOM, CAMX, CAMY = z, 0.0, 0.0
            VX0, VY0 = (w - pw * z) / 2, (h - ph * z) / 2
            ICON_MODE = True
            try:
                self.draw_part(s, p, lambda a, b: FLOAT)
            finally:
                ICON_MODE = False
                CAMX, CAMY, ZOOM, VX0, VY0 = keep
            tx = ICON_TXT.get(k, k if k in GATES else '')
            if k.startswith('CHIP: '):
                tx = ''
            if tx:
                t = self.tiny.render(tx, True, TEXT_DIM)
                s.blit(t, t.get_rect(center=(w // 2, h // 2 + 5)))
        self.icons[key] = s
        return s

    # -- naming parts for the script
    def part_names(self):
        counts, out = {}, []
        for p in sorted(self.parts, key=lambda q: (q.gy, q.gx)):
            if p.kind == 'LABEL':
                continue
            counts[p.kind] = counts.get(p.kind, 0) + 1
            out.append((f'{p.kind}#{counts[p.kind]}', p))
        return out

    def find_parts(self, name):
        nm = name.strip().lower()
        m = re.fullmatch(r'(.+?)#(\d+)', nm)
        if m:
            kind = S_ALIAS.get(m.group(1).upper(), m.group(1).upper())
            want = f'{kind}#{int(m.group(2))}'.lower()
            return [p for d, p in self.part_names() if d.lower() == want]
        return [p for p in self.parts
                if nm in {x.lower() for x in (p.label, p.label_on, p.label_off) if x}]

    def part_value(self, p):
        find, drv = self.netstate()
        if p.kind == 'SOURCE':
            return True
        pins = p.d['pins']
        outs = [i for i, q in enumerate(pins) if q[2] == 'out']
        ins = [i for i, q in enumerate(pins) if q[2] == 'in']
        i = outs[0] if outs else (ins[0] if ins else None)
        if i is None:
            return False
        return drv.get(find(self.k(p, i))) == {1}

    def log_add(self, text, kind='info'):
        self.script_log.append((text, kind))
        del self.script_log[:-400]
        self.log_scroll = 0

    def script_run(self):
        if self.runner.active:
            self.runner.stop('restarted')
        self.ed.err = {}
        if not self.running:
            self.toggle_run()
        self.paused = False
        self.runner.start(self.ed.text())

    def script_stop(self):
        if self.runner.active:
            self.runner.stop('stopped')
        else:
            self.say('no script is running')

    def set_focus(self, what):
        # what: 'ed', 'search' or None
        self.ed.focus = what == 'ed'
        self.search_focus = what == 'search'
        if what:
            pygame.key.set_repeat(400, 35)
        elif not self.editing:
            pygame.key.set_repeat()

    # -- top bar
    def top_buttons(self, lay):
        W = lay['W']
        y, h = 7, 30
        compact = W < 940
        x0 = 10 if compact else 176
        b = [(pygame.Rect(x0, y, 84, h), 'noop', 'Circuits', 'seg_on'),
             (pygame.Rect(x0 + 84, y, 84, h), 'gas', 'Gas lab', 'seg')]
        cw = lay['work'].w
        x = x0 + 190 if compact else max(368, (cw - 330) // 2 + 100)
        b.append((pygame.Rect(x, y, 92, h), 'run', 'Stop' if self.running else 'Run', 'primary'))
        x += 98
        b.append((pygame.Rect(x, y, 34, h), 'pause', '', 'pause'))
        x += 40
        b.append((pygame.Rect(x, y, 34, h), 'step', '', 'step'))
        x += 50
        b.append((pygame.Rect(x, y, 28, h), 'rate-', '', 'minus'))
        b.append((pygame.Rect(x + 28, y, 82, h), 'noop', f'{self.rate} Hz', 'label'))
        b.append((pygame.Rect(x + 110, y, 28, h), 'rate+', '', 'plus'))
        rx = W - 14
        for act, lab, kind, w in (('help', '', 'help', 34), ('theme', '', 'theme', 34), ('script', '' if compact else 'Script', 'toggle', 34 if compact else 88)):
            rx -= w
            b.append((pygame.Rect(rx, y, w, h), act, lab, kind))
            rx -= 6
        return b

    def do_action(self, act):
        global CAMX, CAMY, ZOOM
        if act == 'run':
            self.toggle_run()
        elif act == 'pause':
            self.paused = not self.paused
        elif act == 'step':
            if not self.running:
                self.say('press Run first')
            else:
                self.paused = True
                for p in self.sim_parts:
                    p.glow = 0.0
                    p.seg_glow = [0.0] * 7
                if self.runner.active:
                    self.runner.before_tick()
                self.advance(1)
        elif act == 'rate-':
            self.rate = max(1, self.rate // 2)
            self.dirty = True
        elif act == 'rate+':
            self.rate = min(MAX_RATE, self.rate * 2)
            self.dirty = True
        elif act == 'script':
            self.dock_open = not self.dock_open
            if not self.dock_open:
                self.set_focus(None)
            self.dirty = True
        elif act == 'theme':
            self.light = not self.light
            set_theme(self.light)
            self.reset_caches()
            self.dirty = True
        elif act == 'help':
            self.help_open = not self.help_open
        elif act == 'gas':
            if np is None:
                self.say('gas lab needs numpy (pip install numpy)')
            else:
                self.mode = 'gas'
        elif act == 'chipsave':
            self.save_chip()
        elif act == 'script_run':
            self.script_run()
        elif act == 'script_stop':
            self.script_stop()
        elif act == 'script_example':
            name, text = S_EXAMPLES[self.ex_i % len(S_EXAMPLES)]
            self.ex_i += 1
            self.ed.snap('example')
            self.ed.set_text(text)
            self.ed.undo = []
            self.say(f'example: {name}')
            self.dirty = True
        elif act == 'log_clear':
            self.script_log = []

    # -- dock
    def dock_geom(self, dock):
        head = pygame.Rect(dock.x, dock.y, dock.w, 38)
        body = pygame.Rect(dock.x + 10, dock.y + 44, dock.w - 20, dock.h - 52)
        tabs = [(pygame.Rect(dock.x + 12 + i * 92, dock.y + 6, 86, 28), t) for i, t in enumerate(('SCRIPT', 'NAMES'))]
        btns, rx = [], dock.right - 12
        for act, lab, w in (('log_clear', 'Clear log', 84), ('script_example', 'Example', 80), ('script_stop', 'Stop', 64), ('script_run', 'Run script', 104)):
            if dock.w < 620 and act in ('log_clear', 'script_example'):
                continue
            rx -= w
            btns.append((pygame.Rect(rx, dock.y + 6, w, 28), act, lab))
            rx -= 6
        lw = max(180, int(body.w * 0.36))
        ed = pygame.Rect(body.x, body.y, body.w - lw - 10, body.h)
        lg = pygame.Rect(ed.right + 10, body.y, lw, body.h)
        return head, body, tabs, btns, ed, lg

    def names_layout(self, body):
        rows, x, y, rh = [], 0, 0, 28
        for d, p in self.part_names():
            shown = p.label or p.label_on or p.label_off or d
            tag = d if shown != d else ''
            t = (shown + ('   ' + tag if tag else ''))
            w = self.ui_s.size(t)[0] + 22
            if x + w > body.w and x:
                x, y = 0, y + rh + 6
            rows.append((pygame.Rect(body.x + x, body.y + y, w, rh), d, p, t))
            x += w + 6
        return rows, y + rh

    def log_lines(self, w):
        out = []
        for text, kind in self.script_log:
            for i, ln in enumerate(wrap(self.ui_s, text, w - 16) or ['']):
                out.append((('   ' if i else '') + ln, kind))
        return out

    def ed_colors(self):
        if self.light:
            return dict(bg=(251, 253, 255), gut=(236, 241, 249), run=(196, 224, 246), errbg=(250, 214, 214),
                        cur=(240, 245, 252), sel=(176, 206, 240), dim=(140, 152, 176), err=(205, 50, 50),
                        cmt=(130, 144, 168), cmd=(0, 100, 190), str=(170, 110, 0), num=(200, 100, 20),
                        kw=(20, 140, 80), name=(30, 42, 66), caret=(20, 30, 50))
        return dict(bg=(9, 15, 28), gut=(13, 22, 40), run=(26, 66, 98), errbg=(70, 28, 36),
                    cur=(15, 26, 46), sel=(38, 82, 136), dim=(86, 108, 146), err=(240, 100, 100),
                    cmt=(92, 116, 150), cmd=(100, 200, 255), str=(240, 200, 110), num=(255, 170, 90),
                    kw=(120, 225, 160), name=(214, 228, 248), caret=(214, 228, 248))

    # -- events for all the chrome. True = used up
    def ui_event(self, e):
        lay = self.layout()
        ed = self.ed
        if self.help_open:
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.help_open = False
            return e.type != pygame.MOUSEMOTION
        if e.type == pygame.KEYDOWN:
            if self.editing:
                return False
            ctrl = bool(e.mod & pygame.KMOD_CTRL)
            if ed.focus:
                if ctrl and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.script_run()
                else:
                    ed.key(e)
                    self.dirty = True
                return True
            if self.search_focus:
                if e.key == pygame.K_BACKSPACE:
                    self.search = self.search[:-1]
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.set_focus(None)
                elif e.unicode and e.unicode.isprintable():
                    self.search = (self.search + e.unicode)[:24]
                self.pal_scroll = 0
                return True
            if ctrl and e.key == pygame.K_f:
                self.set_focus('search')
                return True
            if e.key == pygame.K_F1:
                self.help_open = True
                return True
            if e.key == pygame.K_BACKQUOTE:
                self.do_action('script')
                return True
            if ctrl and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.dock_open = True
                self.script_run()
                return True
            return False
        pos = getattr(e, 'pos', None)
        if e.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            if lay['right'].collidepoint(pos):
                rows, total = self.pal_layout(lay['right'])
                _, area = self.pal_geom(lay)
                self.pal_scroll = max(0, min(max(0, total - area.h), self.pal_scroll - e.y * 40))
                return True
            if lay['dock'] and lay['dock'].collidepoint(pos):
                head, body, tabs, btns, edr, lg = self.dock_geom(lay['dock'])
                if self.dock_tab == 'SCRIPT' and edr.collidepoint(pos):
                    ed.wheel(e.y, edr)
                elif self.dock_tab == 'SCRIPT' and lg.collidepoint(pos):
                    self.log_scroll = max(0, self.log_scroll + e.y * 2)
                elif self.dock_tab == 'NAMES':
                    self.names_scroll = max(0, self.names_scroll - e.y * 30)
                return True
            return lay['top'].collidepoint(pos)
        if e.type == pygame.MOUSEMOTION:
            if self.dock_drag == 'resize':
                self.dock_h = lay['H'] - e.pos[1]
                return True
            if self.dock_drag == 'ed' and lay['dock']:
                ed.drag(e.pos, self.dock_geom(lay['dock'])[4])
                return True
            return False
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.dock_drag:
                self.dock_drag = None
                return True
            return False
        if e.type != pygame.MOUSEBUTTONDOWN or e.button != 1:
            if e.type == pygame.MOUSEBUTTONDOWN and (lay['right'].collidepoint(pos) or lay['top'].collidepoint(pos)
                                                    or (lay['dock'] and lay['dock'].collidepoint(pos))):
                return True
            return False
        if self.drag and self.drag.get('carry'):
            return False
        pos = e.pos
        if lay['top'].collidepoint(pos):
            self.set_focus(None)
            for r, act, _, _ in self.top_buttons(lay):
                if r.collidepoint(pos):
                    self.do_action(act)
                    break
            return True
        dock = lay['dock']
        if dock and (dock.collidepoint(pos) or abs(pos[1] - dock.y) <= 3 and pos[0] < dock.right):
            if abs(pos[1] - dock.y) <= 3:
                self.dock_drag = 'resize'
                return True
            head, body, tabs, btns, edr, lg = self.dock_geom(dock)
            for r, t in tabs:
                if r.collidepoint(pos):
                    self.dock_tab = t
                    self.set_focus(None)
                    return True
            for r, act, _ in btns:
                if r.collidepoint(pos) and (act != 'log_clear' or self.dock_tab == 'SCRIPT'):
                    self.do_action(act)
                    return True
            if self.dock_tab == 'SCRIPT':
                if edr.collidepoint(pos):
                    self.set_focus('ed')
                    ed.click(pos, edr, bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
                    self.dock_drag = 'ed'
                else:
                    self.set_focus(None)
            else:
                self.set_focus(None)
                rows, total = self.names_layout(body)
                for r, d, p, t in rows:
                    if r.move(0, -self.names_scroll).collidepoint(pos):
                        name = p.label or p.label_on or p.label_off or d
                        ins = f'"{name}"' if ' ' in name else name
                        self.dock_tab = 'SCRIPT'
                        self.set_focus('ed')
                        ed.snap('name')
                        ed.insert(ins)
                        self.dirty = True
                        break
            return True
        rp = lay['right']
        if rp.collidepoint(pos):
            search, area = self.pal_geom(lay)
            if search.collidepoint(pos):
                self.set_focus('search')
                return True
            self.set_focus(None)
            if area.collidepoint(pos):
                rows, total = self.pal_clamp(lay)
                for row in rows:
                    r = row['rect'].move(area.x, area.y - self.pal_scroll)
                    if not r.collidepoint(pos):
                        continue
                    if row['t'] == 'hdr':
                        if row['cat'] == 'CHIPS' and pos[0] > r.right - 78:
                            self.save_chip()
                        else:
                            self.cat_open[row['cat']] = not row['open']
                        return True
                    if self.running:
                        self.say('stop the run to add parts')
                        return True
                    p = self.new_part(row['kind'])
                    if p is None:
                        return True
                    d = dict(kind='part', parts=[p], rel=[(0, 0)],
                             ox=p.d['w'] * C * ZOOM // 2, oy=p.d['h'] * C * ZOOM // 2, start=pos,
                             moved=True, new=True, carry=False, hit=None, orig=None)
                    self.place_group(d, *pos)
                    self.parts.append(p)
                    self.topo_key = None
                    self.sel.clear()
                    self.drag = d
                    return True
            return True
        if lay['work'].collidepoint(pos):
            self.set_focus(None)
        return False

    # -- drawing
    def draw_icon(self, surf, name, r, color):
        cx, cy = r.center
        if name == 'play':
            pygame.draw.polygon(surf, color, [(cx - 5, cy - 7), (cx + 7, cy), (cx - 5, cy + 7)])
        elif name == 'stop':
            pygame.draw.rect(surf, color, (cx - 6, cy - 6, 12, 12), border_radius=2)
        elif name == 'pause':
            pygame.draw.rect(surf, color, (cx - 6, cy - 6, 4, 12), border_radius=1)
            pygame.draw.rect(surf, color, (cx + 2, cy - 6, 4, 12), border_radius=1)
        elif name == 'step':
            pygame.draw.polygon(surf, color, [(cx - 6, cy - 6), (cx + 3, cy), (cx - 6, cy + 6)])
            pygame.draw.rect(surf, color, (cx + 4, cy - 6, 3, 12), border_radius=1)
        elif name == 'minus':
            pygame.draw.rect(surf, color, (cx - 5, cy - 1, 10, 2), border_radius=1)
        elif name == 'plus':
            pygame.draw.rect(surf, color, (cx - 5, cy - 1, 10, 2), border_radius=1)
            pygame.draw.rect(surf, color, (cx - 1, cy - 5, 2, 10), border_radius=1)
        elif name == 'help':
            t = self.ui_b.render('?', True, color)
            surf.blit(t, t.get_rect(center=r.center))
        elif name == 'theme':
            pygame.draw.circle(surf, color, (cx, cy), 7, 2)
            pygame.draw.rect(surf, color, (cx, cy - 7, 8, 14))
            pygame.draw.circle(surf, color, (cx, cy), 7, 2)
        elif name == 'script':
            pygame.draw.lines(surf, color, False, [(cx - 5, cy - 5), (cx - 10, cy), (cx - 5, cy + 5)], 2)
            pygame.draw.lines(surf, color, False, [(cx + 5, cy - 5), (cx + 10, cy), (cx + 5, cy + 5)], 2)

    def draw_btn(self, surf, r, label, kind, mp, active=False, icon=None):
        hov = r.collidepoint(mp)
        if kind == 'primary':
            fill, line, txt = (OFF if self.running else ON), (OFF if self.running else ON), (8, 16, 30)
            if hov:
                fill = tuple(min(255, c + 24) for c in fill)
            pygame.draw.rect(surf, fill, r, border_radius=8)
            self.draw_icon(surf, 'stop' if self.running else 'play', pygame.Rect(r.x + 8, r.y, 22, r.h), txt)
            t = self.ui_b.render(label, True, txt)
            surf.blit(t, t.get_rect(midleft=(r.x + 34, r.centery)))
            return
        if kind == 'label':
            t = self.ui.render(label, True, TEXT)
            surf.blit(t, t.get_rect(center=r.center))
            return
        on = active or kind == 'seg_on'
        pygame.draw.rect(surf, ACTIVE if on else (CARD_HI if hov else CARD), r, border_radius=8)
        pygame.draw.rect(surf, ON if on else (PART_LINE if hov else PANEL_LINE), r, 1, border_radius=8)
        col = ON if on else TEXT
        if icon:
            self.draw_icon(surf, icon, pygame.Rect(r.x, r.y, 26 if label else r.w, r.h), col)
        if label:
            t = self.ui.render(label, True, col)
            surf.blit(t, t.get_rect(center=(r.centerx + (10 if icon else 0), r.centery)))

    def draw_top(self, surf, lay, mp):
        top = lay['top']
        pygame.draw.rect(surf, PANEL, top)
        pygame.draw.line(surf, PANEL_LINE, (0, top.bottom - 1), (top.right, top.bottom - 1))
        if lay['W'] >= 940:
            t = self.ui_h.render('logic sandbox', True, TEXT)
            surf.blit(t, (16, top.centery - t.get_height() // 2))
        for r, act, label, kind in self.top_buttons(lay):
            icon = {'pause': 'pause', 'step': 'step', 'minus': 'minus', 'plus': 'plus', 'help': 'help',
                    'theme': 'theme', 'toggle': 'script'}.get(kind)
            active = (kind == 'pause' and self.paused) or (kind == 'toggle' and self.dock_open) \
                or (kind == 'help' and self.help_open)
            self.draw_btn(surf, r, label, kind, mp, active, icon)
        if self.runner.active:
            st, col = 'script running', SEL
        elif self.running:
            st, col = ('compiled' if self.cmp else 'running'), ON
        else:
            st, col = 'build mode', TEXT_DIM
        if self.paused and self.running:
            st, col = st + ' · paused', SEL
        for r, act, label, kind in self.top_buttons(lay):
            if act == 'rate+' and lay['W'] >= 1100:
                s = self.ui_s.render(st, True, col)
                surf.blit(s, (r.right + 14, top.centery - s.get_height() // 2))
                break

    def draw_right(self, surf, lay, mp):
        rp = lay['right']
        pygame.draw.rect(surf, PANEL, rp)
        pygame.draw.line(surf, PANEL_LINE, (rp.x, rp.y), (rp.x, rp.bottom))
        t = self.ui_h.render('Parts', True, TEXT)
        surf.blit(t, (rp.x + 14, rp.y + 8))
        search, area = self.pal_geom(lay)
        pygame.draw.rect(surf, BG, search, border_radius=8)
        pygame.draw.rect(surf, ON if self.search_focus else PANEL_LINE, search, 1, border_radius=8)
        if self.search or self.search_focus:
            s = self.ui.render(self.search + ('|' if self.search_focus and (pygame.time.get_ticks() // 450) % 2 == 0 else ''), True, TEXT)
        else:
            s = self.ui.render('search · Ctrl+F', True, TEXT_DIM)
        surf.blit(s, (search.x + 10, search.centery - s.get_height() // 2))
        rows, total = self.pal_clamp(lay)
        old = surf.get_clip()
        surf.set_clip(area.clip(old))
        for row in rows:
            r = row['rect'].move(area.x, area.y - self.pal_scroll)
            if r.bottom < area.y or r.top > area.bottom:
                continue
            if row['t'] == 'hdr':
                col = TEXT_DIM
                arrow = [(r.x + 6, r.centery - 3), (r.x + 14, r.centery - 3), (r.x + 10, r.centery + 3)] if row['open'] \
                    else [(r.x + 7, r.centery - 5), (r.x + 7, r.centery + 5), (r.x + 13, r.centery)]
                pygame.draw.polygon(surf, col, arrow)
                s = self.ui_s.render(row['cat'], True, col)
                surf.blit(s, (r.x + 22, r.centery - s.get_height() // 2))
                n = self.ui_s.render(str(row['n']), True, col)
                if row['cat'] == 'CHIPS':
                    b = pygame.Rect(r.right - 74, r.y + 2, 74, r.h - 4)
                    pygame.draw.rect(surf, CARD_HI if b.collidepoint(mp) else CARD, b, border_radius=6)
                    pygame.draw.rect(surf, PANEL_LINE, b, 1, border_radius=6)
                    s2 = self.ui_s.render('save chip', True, TEXT)
                    surf.blit(s2, s2.get_rect(center=b.center))
                    surf.blit(n, (b.x - n.get_width() - 8, r.centery - n.get_height() // 2))
                else:
                    surf.blit(n, (r.right - n.get_width() - 4, r.centery - n.get_height() // 2))
                continue
            hov = r.collidepoint(mp) and area.collidepoint(mp)
            pygame.draw.rect(surf, CARD_HI if hov else CARD, r, border_radius=10)
            pygame.draw.rect(surf, cat_color(row['kind']) if hov else PANEL_LINE, r, 1, border_radius=10)
            ic = self.part_icon(row['kind'], r.w - 8, 54)
            surf.blit(ic, (r.x + 4, r.y + 4))
            nm = self.nice(row['kind'])
            while len(nm) > 3 and self.ui_s.size(nm)[0] > r.w - 10:
                nm = nm[:-2] + '…'
            s = self.ui_s.render(nm, True, TEXT)
            surf.blit(s, s.get_rect(midtop=(r.centerx, r.y + 62)))
        surf.set_clip(old)
        if total > area.h:
            th = max(24, int(area.h * area.h / total))
            ty = area.y + int((area.h - th) * self.pal_scroll / max(1, total - area.h))
            pygame.draw.rect(surf, PANEL_LINE, (rp.right - 5, ty, 3, th), border_radius=2)
        ct = self.ui_s.render(_CR_A, True, TEXT_DIM)
        while ct.get_width() > rp.w - 16 and len(_CR_A) > 4:
            ct = pygame.transform.smoothscale(ct, (rp.w - 16, ct.get_height()))
        surf.blit(ct, (rp.x + 8, rp.bottom - 20))

    def draw_dock(self, surf, lay, mp):
        dock = lay['dock']
        if not dock:
            return
        pygame.draw.rect(surf, PANEL, dock)
        pygame.draw.line(surf, PANEL_LINE, (dock.x, dock.y), (dock.right, dock.y))
        pygame.draw.line(surf, ON if self.dock_drag == 'resize' else PANEL_LINE, (dock.centerx - 18, dock.y + 1), (dock.centerx + 18, dock.y + 1), 3)
        head, body, tabs, btns, edr, lg = self.dock_geom(dock)
        for r, t in tabs:
            on = t == self.dock_tab
            if on:
                pygame.draw.rect(surf, CARD, r, border_radius=8)
            s = self.ui_b.render(t, True, ON if on else TEXT_DIM)
            surf.blit(s, s.get_rect(center=r.center))
            if on:
                pygame.draw.line(surf, ON, (r.x + 10, r.bottom + 2), (r.right - 10, r.bottom + 2), 2)
        for r, act, lab in btns:
            if act == 'log_clear' and self.dock_tab != 'SCRIPT':
                continue
            if act == 'script_run':
                fill = ON if not self.runner.active else SEL
                if r.collidepoint(mp):
                    fill = tuple(min(255, c + 24) for c in fill)
                pygame.draw.rect(surf, fill, r, border_radius=8)
                self.draw_icon(surf, 'play', pygame.Rect(r.x + 4, r.y, 24, r.h), (8, 16, 30))
                s = self.ui_b.render('Restart' if self.runner.active else lab, True, (8, 16, 30))
                surf.blit(s, s.get_rect(midleft=(r.x + 30, r.centery)))
            else:
                pygame.draw.rect(surf, CARD_HI if r.collidepoint(mp) else CARD, r, border_radius=8)
                pygame.draw.rect(surf, PANEL_LINE, r, 1, border_radius=8)
                s = self.ui.render(lab, True, TEXT)
                surf.blit(s, s.get_rect(center=r.center))
        if self.dock_tab == 'SCRIPT':
            self.ed.font = self.edf
            self.ed.draw(surf, edr, self.ed_colors())
            pygame.draw.rect(surf, PANEL_LINE, edr, 1, border_radius=8)
            pygame.draw.rect(surf, BG, lg, border_radius=8)
            pygame.draw.rect(surf, PANEL_LINE, lg, 1, border_radius=8)
            old = surf.get_clip()
            surf.set_clip(lg.inflate(-2, -2).clip(old))
            lines = self.log_lines(lg.w)
            lh = 16
            vis = max(1, (lg.h - 12) // lh)
            self.log_scroll = max(0, min(max(0, len(lines) - vis), self.log_scroll))
            end = len(lines) - self.log_scroll
            show = lines[max(0, end - vis):end]
            cols = {'info': TEXT_DIM, 'ok': OFF, 'fail': SHORT, 'err': SHORT, 'print': TEXT}
            if not lines:
                s = self.ui_s.render('output shows up here', True, TEXT_DIM)
                surf.blit(s, (lg.x + 10, lg.y + 8))
            for i, (txt, kind) in enumerate(show):
                s = self.ui_s.render(txt, True, cols.get(kind, TEXT))
                surf.blit(s, (lg.x + 8, lg.y + 6 + i * lh))
            surf.set_clip(old)
        else:
            rows, total = self.names_layout(body)
            self.names_scroll = max(0, min(max(0, total - body.h), self.names_scroll))
            old = surf.get_clip()
            surf.set_clip(body.clip(old))
            if not rows:
                s = self.ui.render('no parts yet, add some and their names show up here', True, TEXT_DIM)
                surf.blit(s, (body.x + 4, body.y + 6))
            for r, d, p, t in rows:
                r = r.move(0, -self.names_scroll)
                if r.bottom < body.y or r.y > body.bottom:
                    continue
                hov = r.collidepoint(mp)
                pygame.draw.rect(surf, CARD_HI if hov else CARD, r, border_radius=8)
                pygame.draw.rect(surf, cat_color(p.kind) if hov else PANEL_LINE, r, 1, border_radius=8)
                s = self.ui_s.render(t, True, TEXT)
                surf.blit(s, s.get_rect(center=r.center))
            surf.set_clip(old)

    def draw_help(self, surf, lay):
        W, H = lay['W'], lay['H']
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((*DIM, 150))
        surf.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, min(W - 40, 860), min(H - 40, 560))
        box.center = (W // 2, H // 2)
        pygame.draw.rect(surf, PANEL, box, border_radius=14)
        pygame.draw.rect(surf, PART_LINE, box, 1, border_radius=14)
        half = box.w // 2
        s = self.ui_h.render('Controls', True, TEXT)
        surf.blit(s, (box.x + 24, box.y + 18))
        s = self.ui_h.render('Script commands', True, TEXT)
        surf.blit(s, (box.x + half + 10, box.y + 18))
        for i, (a, b) in enumerate(HELP2):
            y = box.y + 54 + i * 20
            surf.blit(self.ui_s.render(a, True, ON), (box.x + 24, y))
            surf.blit(self.ui_s.render(b, True, TEXT_DIM), (box.x + 24 + 128, y))
        y = box.y + 54
        for i, (a, b) in enumerate(S_HELP):
            surf.blit(self.edf.render(a, True, ON), (box.x + half + 10, y + i * 20))
            surf.blit(self.ui_s.render(b, True, TEXT_DIM), (box.x + half + 10 + 190, y + i * 20))
        s = self.ui_s.render('click anywhere to close', True, TEXT_DIM)
        surf.blit(s, s.get_rect(midbottom=(box.centerx, box.bottom - 12)))

    def draw(self, surf):
        W, H = surf.get_size()
        lay = self.layout()
        work = lay['work']
        self.draw_grid(surf, lay)
        surf.set_clip(work)
        find, drv = self.netstate()
        mp = pygame.mouse.get_pos()

        k_ = self.k

        def pcol(p, i):
            return self.net_color(drv.get(find(k_(p, i))))

        # wires
        for wi, (pa, ia, pb, ib) in enumerate(self.wires):
            pts = self.wire_screen(self.wires[wi])
            s = drv.get(self.wsrc[wi]) if wi < len(self.wsrc) else None
            color = self.net_color(s)
            if len(s or ()) < 2:
                color = self.tint(self.wires[wi], 'float' if not s else ('on' if 1 in s else 'off'))
            w = 1 if not s else (2 if s == {0} else 3)
            draw_wire(surf, pts, color, w)

        if self.drag and self.drag['kind'] == 'wire':
            pa, ia = self.drag['a']
            draw_wire(surf, wire_pts(pa.pin_pos(ia), mp), PREVIEW, 2)

        view = work
        for p in self.parts:
            if p.rect().colliderect(view):
                self.draw_part(surf, p, pcol)

        for p in self.sel:
            pygame.draw.rect(surf, SEL, p.rect().inflate(6, 6), 2, border_radius=9)

        # red tint on dragged parts that are over something (can't be placed there)
        d = self.drag
        if d and d['kind'] == 'part':
            gs = set(d['parts'])
            orects = [q.rect() for q in self.parts if q not in gs]
            for p in d['parts']:
                r = p.rect()
                if r.collidelist(orects) != -1:
                    tint = pygame.Surface(r.size, pygame.SRCALPHA)
                    tint.fill((220, 40, 40, 120))
                    surf.blit(tint, r.topleft)
        elif d and d['kind'] == 'box' and d['moved']:
            r = self.box_rect(d)
            tint = pygame.Surface(r.size, pygame.SRCALPHA)
            tint.fill((*SEL, 36))
            surf.blit(tint, r.topleft)
            pygame.draw.rect(surf, SEL, r, 1)

        surf.set_clip(None)
        self.draw_right(surf, lay, mp)
        self.draw_dock(surf, lay, mp)
        self.draw_top(surf, lay, mp)

        # pin label on hover
        if work.collidepoint(mp) and not (d and d['kind'] in ('part', 'box')) and not self.help_open:
            hit = self.pin_at(mp)
            if hit:
                p, i = hit
                t = self.small.render(f"{p.label if p.kind == 'CHIP' else p.kind} {pin_name(p, i)}", True, TEXT)
                w, h = t.get_width() + 10, t.get_height() + 6
                x, y = mp[0] + 14, mp[1] + 14
                if x + w > W:
                    x = mp[0] - w - 6
                if y + h > H:
                    y = mp[1] - h - 6
                pygame.draw.rect(surf, PANEL, (x, y, w, h), border_radius=6)
                pygame.draw.rect(surf, PART_LINE, (x, y, w, h), 1, border_radius=6)
                surf.blit(t, (x + 5, y + 3))

        if self.toast[0] and time.time() < self.toast[1]:
            t = self.font.render(self.toast[0], True, TEXT)
            tr = pygame.Rect(0, 0, t.get_width() + 24, t.get_height() + 14)
            tr.midtop = (work.centerx, work.y + 12)
            pygame.draw.rect(surf, PANEL, tr, border_radius=10)
            pygame.draw.rect(surf, SEL, tr, 1, border_radius=10)
            surf.blit(t, t.get_rect(center=tr.center))

        if self.help_open:
            self.draw_help(surf, lay)
        if self.namebox:
            self.draw_namebox(surf)

        u = self.updater
        if u and u.modal():
            dim = pygame.Surface((W, H), pygame.SRCALPHA)
            dim.fill((*DIM, 170))
            surf.blit(dim, (0, 0))
            box, btn = self.modal_rects(W, H)
            pygame.draw.rect(surf, PANEL, box)
            pygame.draw.rect(surf, PART_LINE, box, 2)
            self.label(surf, 'UPDATING' if u.state == 'installing' else 'UPDATED' if u.news else 'UPDATE', TEXT, (box.centerx, box.y + 26))
            if u.state == 'installing':
                self.label(surf, 'getting the new version...', TEXT, (box.centerx, box.centery))
            elif u.news:
                y = box.y + 56
                if self.modal_img:
                    if u.scaled is None or u.scaled.get_size() != self.modal_img.size:
                        u.scaled = pygame.transform.smoothscale(u.picture(), self.modal_img.size)
                    surf.blit(u.scaled, self.modal_img)
                    pygame.draw.rect(surf, PART_LINE, self.modal_img.inflate(2, 2), 1)
                    y = self.modal_img.bottom + 22
                else:
                    self.label(surf, 'what changed:', TEXT_DIM, (box.centerx, y + 6))
                    y += 32
                for i, (line, title) in enumerate(self.update_text(box.w - 40)):
                    self.label(surf, line, ON if title else TEXT_DIM, (box.centerx, y + i * 20))
            else:
                self.label(surf, 'update failed, keeping this version', TEXT, (box.centerx, box.y + 70))
                for i, line in enumerate(wrap(self.font, u.message, box.w - 40)[:2]):
                    self.label(surf, line, TEXT_DIM, (box.centerx, box.y + 96 + i * 20))
            if u.state != 'installing':
                pygame.draw.rect(surf, PART_BG, btn)
                pygame.draw.rect(surf, PART_LINE, btn, 2)
                self.label(surf, 'OK', TEXT, btn.center)


# ---------------------------------------------------------------- gas lab
GW, GH = 224, 152           # gas grid size in cells
G_SPECIES = ['N2', 'O2', 'H2', 'C3H8', 'CH4', 'CO2', 'H2O', 'He',
             'Ar', 'Ne', 'NH3', 'CO', 'C4H10', 'C2H2', 'C2H5OH', 'Cl2', 'SF6', 'C12H26']
G_IDX = {s: i for i, s in enumerate(G_SPECIES)}
G_MASS = [28, 32, 2, 44, 16, 44, 18, 4, 40, 20, 17, 28, 58, 26, 46, 71, 146, 170]                 # g/mol
G_CV = [2.5, 2.5, 2.5, 8.0, 3.3, 3.5, 3.0, 1.5, 1.5, 1.5, 3.4, 2.5, 10.5, 4.0, 8.0, 3.1, 10.0, 14.0]         # heat capacity, in units of R
G_COLOR = [(46, 66, 108), (60, 100, 160), (130, 70, 190), (170, 145, 40), (60, 140, 85),
           (110, 110, 110), (90, 150, 180), (180, 100, 150),
           (120, 90, 200), (230, 90, 110), (200, 215, 110), (150, 120, 90), (205, 130, 60),
           (240, 190, 90), (190, 120, 170), (150, 200, 60), (90, 205, 190), (200, 150, 40)]
G_NICE = {'N2': 'N2', 'O2': 'O2', 'H2': 'H2', 'C3H8': 'propane', 'CH4': 'methane',
          'CO2': 'CO2', 'H2O': 'steam', 'He': 'He', 'Ar': 'argon', 'Ne': 'neon', 'NH3': 'ammonia',
          'CO': 'CO', 'C4H10': 'butane', 'C2H2': 'acetylene', 'C2H5OH': 'ethanol', 'Cl2': 'chlorine',
          'SF6': 'SF6', 'C12H26': 'diesel'}
# fuel: (O2 needed per fuel, products, heat released / R per mol, activation temp K)
G_FUELS = {'H2': (0.5, {'H2O': 1}, 29100, 7000),
           'C3H8': (5, {'CO2': 3, 'H2O': 4}, 245800, 8500),
           'CH4': (2, {'CO2': 1, 'H2O': 2}, 96460, 9500),
           'CO': (0.5, {'CO2': 1}, 34000, 8500),
           'C4H10': (6.5, {'CO2': 4, 'H2O': 5}, 346000, 8500),
           'C2H2': (2.5, {'CO2': 2, 'H2O': 1}, 156000, 7000),
           'C2H5OH': (3, {'CO2': 2, 'H2O': 3}, 153600, 9000),
           'NH3': (0.75, {'N2': 0.5, 'H2O': 1.5}, 38000, 11000),
           'C12H26': (18.5, {'CO2': 12, 'H2O': 13}, 854000, 4500)}      # diesel: low activation, lights from compression heat alone
G_AIR = {'N2': 0.79, 'O2': 0.21}
# solid kinds: (name, strength in atm per cell of thickness (0 = never breaks), color)
G_SOLIDS = [None, ('WALL', 60, (150, 160, 178)), ('STEEL', 0, (100, 108, 122)),
            ('GLASS', 4, (150, 210, 225)), ('IGNITER', 60, (235, 125, 30)),
            ('VALVE', 0, (200, 60, 60)), ('SENSOR', 60, (150, 90, 200)),
            ('FILTER', 0, (120, 200, 190)), ('CHECK VALVE', 0, (205, 175, 60)),
            ('HEATER', 60, (240, 90, 40)), ('COOLER', 60, (80, 170, 240)),
            ('PUMP', 0, (90, 200, 90)), ('SOURCE', 60, (230, 230, 110)),
            ('VENT', 60, (70, 70, 80)), ('LINK', 60, (235, 235, 245)),
            ('RELIEF VALVE', 0, (215, 110, 170)), ('EXCHANGER', 60, (150, 152, 168)),
            ('TURBINE', 60, (215, 205, 90)), ('URANIUM', 60, (110, 190, 70)),
            ('CONTROL ROD', 60, (70, 72, 92))]
G_WALL, G_STEEL, G_GLASS, G_IGNITER, G_VALVE, G_SENSOR = 1, 2, 3, 4, 5, 6
G_FILTER, G_CHECK, G_HEATER, G_COOLER, G_PUMP, G_SOURCE, G_VENT, G_LINK = 7, 8, 9, 10, 11, 12, 13, 14
G_RELIEF, G_EXCH, G_TURB = 15, 16, 17
G_TOUGH = (G_VALVE, G_FILTER, G_CHECK, G_PUMP, G_RELIEF)      # these never break
G_URAN, G_CTRL = 18, 19
G_THERM = (G_EXCH, G_URAN, G_CTRL)      # solid parts that keep their own temperature and trade heat with the gas
G_THERM_C = np.zeros(256, np.float32)
G_THERM_C[G_EXCH], G_THERM_C[G_URAN], G_THERM_C[G_CTRL] = 3.0, 6.0, 3.0
G_LIQ_C = 9.0           # heat capacity of liquid water per unit
G_REACT = dict(D=0.22, LOSS=0.012, ABS_W=0.01, ROD=0.9, K=3.4, GAIN=0.3, F0=0.38, DOPP=5000.0, PHI_MAX=12.0,
               SRC=0.003, POWER=6.0, DECAY_K=0.9, DECAY_T=0.0007, MELT=1300.0)
G_PASS = (G_FILTER, G_CHECK, G_PUMP, G_TURB)    # gas flows through these cells
G_LAT = 4896.0          # latent heat of water / R, in K (boils at 373K at 1 atm)
G_LIQ_CAP = 4.0         # liquid water a cell can hold
G_LIQ_ITERS = 5       # quick water moves per sim step
G_PHASE = 0.3           # how fast steam condenses / water evaporates toward equilibrium
G_EXCH_C = 3.0          # heat capacity of an exchanger wall cell
G_EXCH_K = 0.2          # how well exchanger walls conduct heat
G_TURB_P = 0.4          # pressure across the blades turns the rotor
G_TURB_D = 0.1          # gas drag on the blades (what limits the spin)
G_TURB_COUPLE = 0.3     # how hard the rotor drags the gas along (and the gas drags it)
G_HEAT_LEVELS = [400, 600, 900, 1400, 2200]     # K
G_COOL_LEVELS = [270, 230, 180, 120, 77]        # K
G_RATE = 0.12       # source emit rate per step
G_PUMP_V = 0.45     # pump face speed
# signals shared with the circuit side (GAS IN / GAS OUT parts): link id -> 0/1
GAS_TX = {}         # gas lab -> circuits
GAS_RX = {}         # circuits -> gas lab
# sensors: palette name -> type. block sensors look 5 cells ahead, temp/pressure check the cells touching them
G_SENSOR_TYPES = {'BLK SENSOR': 'block', 'TEMP SENSOR': 'temp', 'PRES SENSOR': 'press', 'HINGE SENSOR': 'hinge', 'TIMER': 'timer'}
G_SENSOR_KINDS = ['block', 'temp', 'press', 'hinge', 'timer']
G_SENSOR_COLOR = {'block': (160, 95, 220), 'temp': (225, 85, 55), 'press': (70, 140, 235), 'hinge': (230, 200, 70), 'timer': (110, 210, 120)}
G_TIMER_PERIODS = [20, 40, 80, 160, 320]      # sim steps
G_TIMER_DUTY = [0.1, 0.25, 0.5, 0.75]
G_STARTER_T = 3.0       # starter motor torque
G_STARTER_MAX = 0.04    # ...stops pushing above this spin (rad / step)
G_SHAFT_DENS = 0.25     # shaft mass per cell of area (inertia = half m r^2)
G_SHAFT_DAMP = 0.9995   # bearing friction
G_MECH = ('SHAFT', 'COG', 'HINGE', 'ROD', 'CHAIN', 'WHEEL')
G_SLAB = 32             # the world scrolls in slabs this wide (the sim window is 7 slabs)
G_WHEEL_T = 1.5         # tire thickness on top of the shaft radius
G_RB_KINDS = (1, 2, 3)  # wall, steel, glass: plain solids that can spin freely
G_RB_E = 0.12           # bounce of spinning bodies
G_RB_MU = 0.6           # friction of spinning bodies
G_GRIP = 1.6            # tire grip, friction limit = grip x weight
G_SHAFT_MASS = 0.1      # shaft weight per cell of area when it rides on a physics object
G_FRAME_DAMP = 0.999
G_COG_DENS = 0.05       # cogs weigh much less than shafts, so gas can actually turn them
G_COG_FRICTION = 0.995  # extra bearing friction on cogs
G_COG_PUSH = 1.0        # pressure on the teeth
G_COG_DAMP = 0.005       # gas drag on spinning cogs (keeps them from spinning themselves up)
G_COG_FLOW = 0.05       # how hard moving gas turns cogs (and how hard they feel it back)
G_TEMP_LEVELS = [100, 200, 400, 700, 1000]        # C
G_PRES_LEVELS = [1.5, 2, 3, 5, 10]                # atm
G_DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]
G_DIR_NAMES = ['right', 'down', 'left', 'up']
G_SENSE_RANGE = 5
G_VALVE_OPEN = (70, 200, 100)
G_BLOCK_COLOR, G_BLOCK_EDGE = (178, 130, 86), (120, 84, 52)
G_MATS = [('WALL', None), ('STEEL', None), ('GLASS', None), ('BLOCK', None), ('IGNITER', None),
          ('VALVE', None), ('FILTER', None), ('CHECK VALVE', None), ('HEATER', None),
          ('COOLER', None), ('PUMP', None), ('SOURCE', None), ('VENT', None), ('LINK', None),
          ('RELIEF VALVE', None), ('EXCHANGER', None), ('TURBINE', None), ('URANIUM', None), ('CONTROL ROD', None),
          ('SHAFT', None), ('COG', None), ('HINGE', None), ('ROD', None), ('CHAIN', None), ('WHEEL', None),
          ('BLK SENSOR', None), ('TEMP SENSOR', None), ('PRES SENSOR', None), ('HINGE SENSOR', None), ('TIMER', None), ('THRUST PROBE', None),
          ('AIR', G_AIR), ('HYDROGEN', {'H2': 1}),
          ('PROPANE', {'C3H8': 1}), ('METHANE', {'CH4': 1}), ('OXYGEN', {'O2': 1}),
          ('HELIUM', {'He': 1}), ('CO2', {'CO2': 1}),
          ('NITROGEN', {'N2': 1}), ('STEAM', {'H2O': 1}), ('ARGON', {'Ar': 1}), ('NEON', {'Ne': 1}),
          ('AMMONIA', {'NH3': 1}), ('CO', {'CO': 1}), ('BUTANE', {'C4H10': 1}),
          ('ACETYLENE', {'C2H2': 1}), ('ETHANOL', {'C2H5OH': 1}), ('CHLORINE', {'Cl2': 1}),
          ('SF6', {'SF6': 1}), ('DIESEL', {'C12H26': 1}), ('WATER', None),
          ('H2+O2 2:1', {'H2': 2 / 3, 'O2': 1 / 3}), ('CH4+O2 1:2', {'CH4': 1 / 3, 'O2': 2 / 3}),
          ('C3H8+O2 1:5', {'C3H8': 1 / 6, 'O2': 5 / 6}), ('CO+O2 2:1', {'CO': 2 / 3, 'O2': 1 / 3}), ('DIESEL+AIR', {'C12H26': 0.011, 'N2': 0.78, 'O2': 0.209}),
          ('VACUUM', None)]
G_SOLID_MATS = {'WALL': G_WALL, 'STEEL': G_STEEL, 'GLASS': G_GLASS, 'IGNITER': G_IGNITER,
                'VALVE': G_VALVE, 'FILTER': G_FILTER, 'CHECK VALVE': G_CHECK, 'HEATER': G_HEATER,
                'COOLER': G_COOLER, 'PUMP': G_PUMP, 'SOURCE': G_SOURCE, 'VENT': G_VENT,
                'RELIEF VALVE': G_RELIEF, 'EXCHANGER': G_EXCH, 'TURBINE': G_TURB,
                'URANIUM': G_URAN, 'CONTROL ROD': G_CTRL}
G_DEFAULT_AUX = {G_FILTER: G_IDX['H2'], G_CHECK: 0, G_HEATER: 2, G_COOLER: 2, G_PUMP: 0, G_SOURCE: G_IDX['H2'],
                 G_RELIEF: 2, G_TURB: 0, G_CTRL: 4}
G_TOOLS = ['BRUSH', 'LINE', 'RECT', 'FILL', 'ERASE', 'SELECT']
G_K = 0.24          # how hard pressure pushes
G_DAMP = 0.998      # flow friction
G_DIFF = 0.02       # gases mixing
G_HEAT = 0.05       # heat conduction
G_BURN = 0.35       # burn speed once lit
G_EFF = 0.6         # share of the reaction heat that stays (real flames lose some)
G_COMP = {'C12H26': 0.3}       # diesel lights from compression: squeezed gas counts as hotter, T * density^0.3
G_BURN_A = {f: 0.25 / math.exp(-v[3] / 1500) for f, v in G_FUELS.items()}   # 0.25/step at 1500K
G_BUOY = 4e-4       # how fast light / hot gas rises and heavy gas sinks
G_PDV = 0.35         # compression heating / expansion cooling
G_PUSH = 0.01       # how hard pressure shoves blocks
G_BODY_DENSITY = 1.0
G_BODY_G = 0.0015   # block gravity
G_COOL = 0.0004     # hot gas slowly radiating heat away
G_WALLCOOL = 0.01   # walls soak up heat from gas touching them
G_VISC = 0.02
G_SUB = 1           # flow sub-steps per step: gas moves, jets and shocks run this much faster
G_UMAX = 0.95        # fastest flow on a cell face (cells / step)
G_COLL = 5.0         # how much fast flow ignores sideways pressure (keeps jets narrow), 0 = off
G_ADV = 0.8         # flow carries its own momentum: speeds up in narrow pipes, pressure drops there (bernoulli)
G_CATS = [('WALLS', ['WALL', 'STEEL', 'GLASS', 'BLOCK']),
          ('FLOW', ['VALVE', 'FILTER', 'CHECK VALVE', 'PUMP', 'VENT', 'RELIEF VALVE', 'TURBINE']),
          ('HEAT & POWER', ['IGNITER', 'HEATER', 'COOLER', 'EXCHANGER', 'SOURCE', 'URANIUM', 'CONTROL ROD']),
          ('MECHANICS', ['SHAFT', 'COG', 'HINGE', 'ROD', 'CHAIN', 'WHEEL']),
          ('SENSORS', ['BLK SENSOR', 'TEMP SENSOR', 'PRES SENSOR', 'HINGE SENSOR', 'TIMER', 'LINK', 'THRUST PROBE']),
          ('GASES', ['AIR', 'HYDROGEN', 'PROPANE', 'METHANE', 'OXYGEN', 'HELIUM', 'CO2', 'NITROGEN', 'STEAM', 'ARGON', 'NEON',
                     'AMMONIA', 'CO', 'BUTANE', 'ACETYLENE', 'ETHANOL', 'CHLORINE', 'SF6', 'DIESEL', 'WATER']),
          ('MIXES', ['H2+O2 2:1', 'CH4+O2 1:2', 'C3H8+O2 1:5', 'CO+O2 2:1', 'DIESEL+AIR', 'VACUUM'])]
G_HELP = ['tab = circuits', 'lmb = tool, rmb = erase', 'wheel = size / scroll', 'e = ignite',
          'space = pause, . = step', 'up/dn = speed', 'o = air / closed / void', 'g = gravity',
          'hold p = valves', 'hold k = starter', 'i = pin readout', 'select + ctrl+c/v',
          'm = symmetry, rmb = erase with tool', 'ctrl+wheel = zoom, mmb = pan', 'v = smooth gas', 't = overlay views',
          'click block = cycle it', 'a = reset air', 'clr: ctrl+sh+del',
          'select + r = physics (moves, spins)', 'shift+r = no spin, box only', 'del = delete selection', 'ctrl+f = search parts',
          'left/right = scroll the world', 'wheel tool on a shaft, chain tool joins two']


def ramp(v, stops):
    # v in 0..1 -> colors, stops = [(pos, (r, g, b)), ...]
    xs = [a for a, _ in stops]
    out = np.empty(v.shape + (3,), np.float32)
    for ch in range(3):
        out[..., ch] = np.interp(v, xs, [c[ch] for _, c in stops])
    return out


G_RAMP_P = [(0, (20, 30, 110)), (0.2, (40, 110, 220)), (0.33, (200, 230, 245)), (0.5, (250, 220, 90)),
            (0.7, (240, 110, 40)), (0.88, (210, 30, 60)), (1, (255, 120, 255))]
G_RAMP_T = [(0, (10, 10, 40)), (0.2, (60, 20, 120)), (0.45, (200, 40, 50)), (0.7, (255, 150, 30)),
            (0.9, (255, 235, 130)), (1, (255, 255, 255))]
G_RAMP_S = [(0, (8, 10, 30)), (0.3, (30, 70, 200)), (0.6, (40, 200, 230)), (0.85, (230, 250, 120)), (1, (255, 255, 255))]
G_VIEWS = ['normal', 'pressure', 'temperature', 'speed']


class GasSim:
    # 2d gas grid: each cell has amounts of each gas, a temperature, and flow on its faces.
    # walls are static cells, BLOCKs are rigid boxes that get shoved around by the gas
    def __init__(self):
        S = len(G_SPECIES)
        self.W2, self.H2 = GW + 2, GH + 2       # one ghost cell around the edge
        shape = (self.W2, self.H2)
        self.n = np.zeros((S,) + shape, np.float32)     # 1.0 = 1 atm worth at 20C
        self.T = np.full(shape, 293.0, np.float32)
        self.kind = np.zeros(shape, np.uint8)           # 0 gas, else index into G_SOLIDS
        self.strength = np.zeros(shape, np.float32)     # atm per cell of thickness, 0 = never breaks
        self.solid = np.zeros(shape, bool)              # walls + blocks, what the gas sees
        self.u = np.zeros((self.W2 - 1, self.H2), np.float32)
        self.v = np.zeros((self.W2, self.H2 - 1), np.float32)
        self.ring = np.ones(shape, bool)
        self.ring[1:-1, 1:-1] = False
        self.open = True                        # edges open to the outside
        self.void = False                       # ...and the outside is empty space (gas that gets out is gone)
        self.probes = {}                        # (x, y) -> thrust probe on a wall cell
        self.gravity = True
        self.starter = False                    # hold k: motor spins the shafts up
        self.manual_valves = False              # P held: opens valves that aren't linked to a sensor
        self.valve_open = np.zeros(shape, bool)
        self.relief_open = np.zeros(shape, bool)    # relief valves that popped open
        self.liq = np.zeros(shape, np.float32)      # liquid water in each cell
        self.phi = np.zeros(shape, np.float32)      # neutron flux
        self.decay = np.zeros(shape, np.float32)    # decay heat stored in fuel
        self.scram = np.zeros(shape, bool)          # control rods slammed in by a sensor / circuit
        self.news = []                              # messages for the ui (meltdowns)
        self.link = np.full(shape, -1, np.int32)    # valve/igniter -> sensor key (x * H2 + y), -1 = manual
        self.sensors = {}                       # (x, y) -> dict(type, dir, level, on)
        self.spark_t = np.zeros(shape, np.int16)
        self.aux = np.zeros(shape, np.int8)        # filter gas / direction / level / source gas
        self.glinks = {}                        # (x, y) -> dict(id, tgt, role, on) circuit links
        self.shafts = []                        # dict(x, y, R, th, om)
        self.hinges = []                        # dict(kind, ref, ox, oy, cx, cy)
        self.rods = []                          # dict(a, b, L) between two hinges
        self.meshes = []                        # dict(a, b, k): two cogs whose teeth touch turn together
        self.chains = []                        # dict(a, b, k): two shafts joined by a chain (same direction, radius = ratio)
        self.wx = 0                             # world column of the left edge of the window (the world scrolls past it)
        self.slabs = {}                         # world slab index -> what was built there while it is out of the window
        self.rbs = []                           # free spinning bodies (plain solids), see make_rbody
        self.frames = []                        # physics objects: dict(x0, y0, w, h, fx, fy, vx, vy), a box of the world that moves as one
        self.cogmask = np.zeros(shape, bool)    # cells covered by cog bases and teeth right now
        self.comp_cache = {}
        self.has = set()
        self.passable = np.zeros(256, bool)
        self.passable[list(G_PASS)] = True
        self.near_wall = None
        self.active = {0, 1}                    # which gases exist (index into G_SPECIES)
        self.age = 0
        self.bodies = []                        # moving blocks
        self.debris = []                        # [x, y, vx, vy, life, color] bits of broken walls
        self.cvv = np.array(G_CV, np.float32)
        self.Mv = np.array(G_MASS, np.float32)
        self.amb = self.mix(G_AIR)
        X, Y = np.meshgrid(np.arange(self.W2), np.arange(self.H2), indexing='ij')
        self.X, self.Y = X.astype(np.float32), Y.astype(np.float32)
        self.update_ambient()
        self.reset_air()

    def mix(self, comp):
        v = np.zeros(len(G_SPECIES), np.float32)
        for k, f in comp.items():
            v[G_IDX[k]] = f
        return v

    def update_ambient(self):
        # outside air is a bit denser at the bottom when gravity is on
        self.amb_field = self.amb[:, None, None] * np.ones((1, 1, self.H2), np.float32)
        self.amb_ring = np.broadcast_to(self.amb_field, self.n.shape)[:, self.ring].copy()

    def reset_air(self):
        self.n[:] = 0 if self.void else self.amb_field
        self.T[:] = 293
        self.liq[:] = 0
        self.phi[:] = 0
        self.decay[:] = 0
        self.n[:, self.solid] = 0
        self.u[:] = 0
        self.v[:] = 0
        self.active = {0, 1}

    def clear(self):
        self.probes = {}
        self.shafts, self.hinges, self.rods, self.meshes = [], [], [], []
        self.chains, self.frames, self.rbs = [], [], []
        self.slabs = {}
        self.cogmask[:] = False
        self.sensors = {}
        self.glinks = {}
        self.aux[:] = 0
        self.comp_cache = {}
        self.link[:] = -1
        self.valve_open[:] = False
        self.relief_open[:] = False
        self.spark_t[:] = 0
        self.kind[:] = 0
        self.strength[:] = 0
        self.bodies = []
        self.debris = []
        self.rebuild()
        self.reset_air()

    def rebuild(self):
        sol = (self.kind > 0) & ~self.valve_open & ~self.relief_open & ~self.passable[self.kind]
        self.has = set(np.unique(self.kind).tolist())
        for b in self.bodies:
            sol[b['x']:b['x'] + b['w'], b['y']:b['y'] + b['h']] = True
        sol |= self.cogmask
        self.solid = sol
        self.near_wall = None

    def body_mask(self, skip=None):
        m = np.zeros(self.solid.shape, bool)
        for b in self.bodies:
            if b is not skip:
                m[b['x']:b['x'] + b['w'], b['y']:b['y'] + b['h']] = True
        return m

    # editing
    def add_gas(self, mask, comp, amount):
        mask = mask & ~self.solid
        if not mask.any():
            return
        vec = self.mix(comp) * amount
        self.active |= set(np.nonzero(vec)[0].tolist())
        c_old = (self.n[:, mask] * self.cvv[:, None]).sum(0)
        add_c = float((vec * self.cvv).sum())
        e = c_old * self.T[mask] + add_c * 293
        self.n[:, mask] += vec[:, None]
        self.T[mask] = e / np.maximum(c_old + add_c, 1e-6)

    def drain(self, mask, keep):
        mask = mask & ~self.solid
        self.n[:, mask] *= keep
        self.liq[mask] *= keep

    def component(self, x, y):
        # all cells touching (x, y) with the same kind (so one click changes a whole filter / pump)
        k = self.kind[x, y]
        m = np.zeros(self.kind.shape, bool)
        if k == 0:
            return m
        todo = [(x, y)]
        m[x, y] = True
        while todo and m.sum() < 4000:
            cx, cy = todo.pop()
            for dx, dy in G_DIRS:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.W2 and 0 <= ny < self.H2 and not m[nx, ny] and self.kind[nx, ny] == k:
                    m[nx, ny] = True
                    todo.append((nx, ny))
        return m

    def comp_mask(self, key):
        m = self.comp_cache.get(key)
        if m is None:
            m = self.component(*key)
            self.comp_cache[key] = m
        return m

    def cycle(self, x, y):
        # click a placed filter / pump / heater ... to change its setting
        k = int(self.kind[x, y])
        m = self.component(x, y)
        a = int(self.aux[x, y])
        if k in (G_FILTER, G_SOURCE):
            a = (a + 1) % len(G_SPECIES)
        elif k in (G_CHECK, G_PUMP):
            a = (a + 1) % 4
        elif k in (G_HEATER, G_COOLER, G_RELIEF):
            a = (a + 1) % 5
        elif k == G_CTRL:
            a = (a + 1) % 5
        self.aux[m] = a
        return self.describe(x, y)

    def describe(self, x, y):
        k = int(self.kind[x, y])
        a = int(self.aux[x, y])
        if k == G_FILTER:
            return f'filter, only lets {G_NICE[G_SPECIES[a]]} through (click to change)'
        if k == G_SOURCE:
            return f'source of {G_NICE[G_SPECIES[a]]} (click to change)'
        if k == G_CHECK:
            return f'one-way valve, flows {G_DIR_NAMES[a]}'
        if k == G_PUMP:
            return f'pump, pushes {G_DIR_NAMES[a]}'
        if k == G_HEATER:
            return f'heater, {G_HEAT_LEVELS[a] - 273}C'
        if k == G_COOLER:
            return f'cooler, {G_COOL_LEVELS[a] - 273}C'
        if k == G_VENT:
            return 'vent, eats gas next to it'
        if k == G_RELIEF:
            return f'relief valve, pops open above {G_PRES_LEVELS[a]} atm, shuts again below 90% (click to change)'
        if k == G_EXCH:
            return f'heat exchanger wall, {float(self.T[x, y]) - 273:.0f}C, passes heat but no gas'
        if k == G_TURB:
            return f'turbine, flow {G_DIR_NAMES[a]} (click to turn), touch a shaft to drive it, or spin the shaft to push gas'
        if k == G_URAN:
            return (f'uranium fuel, {float(self.T[x, y]) - 273:.0f}C, flux {float(self.phi[x, y]):.1f}, '
                    f'decay heat {float(self.decay[x, y]):.2f}. needs water around it to go critical')
        if k == G_CTRL:
            sc = ', SCRAMMED' if self.scram[x, y] else ''
            return f'control rod, {a * 25}% in{sc} (click to change, link a sensor to scram it)'
        if k == G_LINK:
            lk = self.glinks.get((x, y))
            if lk:
                what = 'sensor reading' if lk['role'] == 'tx' else 'valve / igniter'
                return f"link {lk['id']} ({what}), {'ON' if lk.get('on') else 'off'}"
            return 'link'
        return ''

    def add_link(self, x, y, lid, tgt):
        if self.kind[x, y] or self.solid[x, y] or self.ring[x, y]:
            return False
        role = 'tx' if tgt in self.sensors else 'rx'
        self.kind[x, y] = G_LINK
        self.strength[x, y] = G_SOLIDS[G_LINK][1]
        self.n[:, x, y] = 0
        self.glinks[(x, y)] = dict(id=lid, tgt=tgt, role=role, on=False)
        self.rebuild()
        return True

    def links_tick(self):
        tx = {}
        changed = False
        for key, lk in self.glinks.items():
            tgt = lk['tgt']
            if lk['role'] == 'tx':
                sn = self.sensors.get(tgt)
                tx[lk['id']] = tx.get(lk['id'], 0) | int(bool(sn and sn['on']))
            else:
                st = bool(GAS_RX.get(lk['id'], 0))
                if st != lk['on']:
                    lk['on'] = st
                    changed = True
                    if st and self.kind[tgt] == G_IGNITER:
                        self.ignite(self.comp_mask(tgt))
        GAS_TX.clear()
        GAS_TX.update(tx)
        if changed:
            self.update_valves()

    def set_solid(self, mask, kind, link=-1):
        mask = mask & ~self.ring & ~self.body_mask() & (self.kind != G_SENSOR) & (self.kind != G_LINK)
        self.comp_cache = {}
        self.kind[mask] = kind
        self.aux[mask] = G_DEFAULT_AUX.get(kind, 0)
        self.strength[mask] = G_SOLIDS[kind][1]
        self.link[mask] = link if kind in (G_VALVE, G_IGNITER, G_CTRL) else -1
        self.valve_open[mask] = False
        self.relief_open[mask] = False
        self.liq[mask] = 0
        self.phi[mask] = 0
        self.decay[mask] = 0
        self.n[:, mask] = 0
        self.T[mask] = 293
        self.rebuild()
        self.update_valves()

    def add_sensor(self, x, y, typ):
        if self.solid[x, y] or self.ring[x, y] or self.kind[x, y]:
            return False
        self.kind[x, y] = G_SENSOR
        self.strength[x, y] = G_SOLIDS[G_SENSOR][1]
        self.n[:, x, y] = 0
        self.sensors[(x, y)] = dict(type=typ, dir=0, level=2, on=False)
        self.rebuild()
        return True

    def remove_sensors(self, mask):
        for key in [k for k in self.glinks if mask[k]]:
            del self.glinks[key]
        for key in [k for k in self.sensors if mask[k]]:
            del self.sensors[key]
            self.link[self.link == key[0] * self.H2 + key[1]] = -1

    def sense(self, p):
        # check every sensor; linked igniters fire when it turns on, linked valves follow it
        bm = self.body_mask() if any(v['type'] == 'block' for v in self.sensors.values()) else None
        changed = False
        for (x, y), sn in self.sensors.items():
            t = sn['type']
            if t == 'block':
                dx, dy = G_DIRS[sn['dir']]
                on = False
                for k in range(1, G_SENSE_RANGE + 1):
                    cx, cy = x + dx * k, y + dy * k
                    if not (0 <= cx < self.W2 and 0 <= cy < self.H2):
                        break
                    if bm[cx, cy]:
                        on = True
                        break
                    if self.kind[cx, cy] and not self.valve_open[cx, cy]:
                        break       # can't see through walls
            elif t == 'timer':
                per = G_TIMER_PERIODS[sn['level']]
                on = (self.age % per) < max(1, int(per * G_TIMER_DUTY[sn['dir'] % 4]))
            elif t == 'hinge':
                dx, dy = G_DIRS[sn['dir']]
                on = False
                for h in self.hinges:
                    hx, hy = self.hinge_pos(h)[:2]
                    tt = (hx - x - 0.5) * dx + (hy - y - 0.5) * dy
                    pp = abs((hx - x - 0.5) * dy - (hy - y - 0.5) * dx)
                    if 0.4 <= tt <= G_SENSE_RANGE + 0.6 and pp <= 0.8:
                        on = True
                        break
            else:
                vals = []
                for dx, dy in G_DIRS:
                    cx, cy = x + dx, y + dy
                    if not self.solid[cx, cy]:
                        vals.append(float(self.T[cx, cy]) - 273 if t == 'temp' else float(p[cx, cy]))
                lim = G_TEMP_LEVELS[sn['level']] if t == 'temp' else G_PRES_LEVELS[sn['level']]
                on = bool(vals) and max(vals) > lim
            if on != sn['on']:
                sn['on'] = on
                changed = True
                if on:
                    self.ignite(self.link == x * self.H2 + y)
        if changed:
            self.update_valves()

    def update_valves(self):
        valve = self.kind == G_VALVE
        on_keys = [x * self.H2 + y for (x, y), sn in self.sensors.items() if sn['on']]
        if G_CTRL in self.has:
            sc = (self.kind == G_CTRL) & np.isin(self.link, on_keys)
            for lk in self.glinks.values():
                if lk['role'] == 'rx' and lk['on'] and lk['tgt'] and self.kind[lk['tgt']] == G_CTRL:
                    sc |= self.comp_mask(lk['tgt'])
            self.scram = sc
        want = valve & (((self.link < 0) & self.manual_valves) | np.isin(self.link, on_keys))
        for lk in self.glinks.values():
            if lk['role'] == 'rx' and lk['on'] and self.kind[lk['tgt']] == G_VALVE:
                want |= self.comp_mask(lk['tgt'])
        if (want == self.valve_open).all():
            return
        closing = self.valve_open & ~want
        self.valve_open = want
        self.rebuild()
        if closing.any():
            # closing squeezes whatever gas was in the valve into the open cells next to it
            xs, ys = np.nonzero(closing)
            for dx, dy in G_DIRS:
                nx, ny = xs + dx, ys + dy
                ok = ~self.solid[nx, ny]
                if ok.any():
                    self.merge_gas(xs[ok], ys[ok], nx[ok], ny[ok])
            self.n[:, closing] = 0
            self.T[closing] = 293

    def new_probe(self):
        return dict(hist=deque(maxlen=240), imp=[0.0, 0.0], peak=0.0, f=(0.0, 0.0))

    def add_probe(self, x, y):
        if not (self.kind[x, y] and self.solid[x, y]) or self.kind[x, y] in (G_SENSOR, G_LINK):
            return 'put the thrust probe on a wall of the engine'
        if (x, y) in self.probes:
            self.probes[(x, y)] = self.new_probe()
            return 'probe reset'
        if len(self.probes) >= 4:
            return 'up to 4 probes'
        self.probes[(x, y)] = self.new_probe()
        return 'thrust probe placed, it adds up the gas pressure on everything this wall is attached to'

    def probe_mask(self, x, y):
        key = ('thrust', x, y, int(self.solid.sum()))
        m = self.comp_cache.get(key)
        if m is None:
            m = np.zeros(self.kind.shape, bool)
            if self.solid[x, y]:
                m[x, y] = True
                todo = [(x, y)]
                while todo and m.sum() < 6000:
                    cx, cy = todo.pop()
                    for dx, dy in G_DIRS:
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < self.W2 and 0 <= ny < self.H2 and not m[nx, ny] and self.solid[nx, ny] \
                                and self.kind[nx, ny] and not self.ring[nx, ny]:
                            m[nx, ny] = True
                            todo.append((nx, ny))
            self.comp_cache[key] = m
        return m

    def probe_tick(self):
        # net force of the gas pressure on the whole piece of structure the probe sits on (= thrust of an engine)
        p = self.n.sum(0) * self.T / 293
        gas = ~self.solid
        for (x, y), pr in self.probes.items():
            M = self.probe_mask(x, y)
            fx = float(p[:-1][M[1:] & gas[:-1]].sum()) - float(p[1:][M[:-1] & gas[1:]].sum())
            fy = float(p[:, :-1][M[:, 1:] & gas[:, :-1]].sum()) - float(p[:, 1:][M[:, :-1] & gas[:, 1:]].sum())
            pr['f'] = (fx, fy)
            pr['imp'][0] += fx
            pr['imp'][1] += fy
            mag = math.hypot(fx, fy)
            pr['peak'] = max(pr['peak'], mag)
            if self.age % 2 == 0:
                pr['hist'].append((fx, fy))

    def erase(self, mask):
        mask = mask & ~self.ring
        for key in [k for k in self.probes if mask[k]]:
            del self.probes[key]
        hit = mask & (self.kind > 0)
        self.comp_cache = {}
        self.remove_sensors(hit)
        self.aux[hit] = 0
        self.kind[hit] = 0
        self.strength[hit] = 0
        self.link[hit] = -1
        self.valve_open[hit] = False
        self.relief_open[hit] = False
        self.liq[mask] = 0
        self.T[hit] = 293      # the hole starts empty and gas rushes in
        self.bodies = [b for b in self.bodies
                       if not mask[b['x']:b['x'] + b['w'], b['y']:b['y'] + b['h']].any()]
        if self.rbs:
            self.rbs = [rb for rb in self.rbs if not mask[rb['cx'], rb['cy']].any()]
        if self.shafts or self.hinges:
            self.erase_mech(mask & ~self.ring)
        self.rebuild()

    def add_body(self, x0, y0, x1, y1):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if self.solid[x0:x1 + 1, y0:y1 + 1].any() or w * h < 1:
            return False
        self.n[:, x0:x1 + 1, y0:y1 + 1] = 0
        self.bodies.append(dict(x=x0, y=y0, w=w, h=h, vx=0.0, vy=0.0, fx=0.0, fy=0.0))
        self.rebuild()
        return True

    def set_valves(self, on):
        self.manual_valves = on
        self.update_valves()

    def ignite(self, which=None):
        # which = mask of igniters to fire; default = every igniter not linked to a sensor
        ign = (self.kind == G_IGNITER) & ((self.link < 0) if which is None else which)
        if not ign.any():
            return
        m = ign.copy()
        for _ in range(2):
            g = m.copy()
            g[1:] |= m[:-1]
            g[:-1] |= m[1:]
            g[:, 1:] |= m[:, :-1]
            g[:, :-1] |= m[:, 1:]
            m = g
        self.spark_t[m & ~self.solid] = 8

    # moving blocks
    def merge_gas(self, sx, sy, dx, dy):
        # pour the gas of cells (sx, sy) into cells (dx, dy), keeping the heat right
        if len(sx) == 0:
            return
        cs = self.cvv @ self.n[:, sx, sy]
        cd = self.cvv @ self.n[:, dx, dy]
        e = cs * self.T[sx, sy] + cd * self.T[dx, dy]
        self.n[:, dx, dy] += self.n[:, sx, sy]
        self.n[:, sx, sy] = 0
        self.T[dx, dy] = np.where(cs + cd > 1e-6, e / np.maximum(cs + cd, 1e-6), 293)

    def try_move(self, b, dx, dy):
        x, y, w, h = b['x'], b['y'], b['w'], b['h']
        if dx:
            lead = x + w if dx > 0 else x - 1
            trail = x if dx > 0 else x + w - 1
            rows = np.arange(y, y + h)
            lx, ly = np.full(h, lead), rows
            tx, ty = np.full(h, trail), rows
            bx, by = np.full(h, lead + dx), rows
        else:
            lead = y + h if dy > 0 else y - 1
            trail = y if dy > 0 else y + h - 1
            cols = np.arange(x, x + w)
            lx, ly = cols, np.full(w, lead)
            tx, ty = cols, np.full(w, trail)
            bx, by = cols, np.full(w, lead + dy)
        if (self.solid[lx, ly] | self.ring[lx, ly] | (self.kind[lx, ly] > 0)).any():
            return False
        # free the trailing edge, push the gas in front ahead (or behind if it's boxed in)
        self.solid[tx, ty] = False
        ok = ~(self.solid[bx, by] | self.ring[bx, by])
        self.merge_gas(lx[ok], ly[ok], bx[ok], by[ok])
        self.merge_gas(lx[~ok], ly[~ok], tx[~ok], ty[~ok])
        self.solid[lx, ly] = True
        self.T[lx, ly] = 293
        b['x'] += dx
        b['y'] += dy
        self.near_wall = None
        return True

    # ---- copy / paste of a region (cells, gas, blocks, sensors, links, shafts, hinges, rods)
    def copy_region(self, x0, y0, x1, y1, gas=True):
        x0, x1 = sorted((max(1, x0), min(self.W2 - 2, x1)))
        y0, y1 = sorted((max(1, y0), min(self.H2 - 2, y1)))
        sl = (slice(x0, x1 + 1), slice(y0, y1 + 1))
        inside = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
        clip = dict(w=x1 - x0 + 1, h=y1 - y0 + 1, x0=x0, y0=y0,
                    n=self.n[(slice(None),) + sl].copy() if gas else None, T=self.T[sl].copy() if gas else None, kind=self.kind[sl].copy(),
                    strength=self.strength[sl].copy(), aux=self.aux[sl].copy(), link=self.link[sl].copy())
        clip['sensors'] = {k: dict(v) for k, v in self.sensors.items() if inside(*k)}
        clip['glinks'] = {k: dict(v) for k, v in self.glinks.items() if inside(*k)}
        bodies = [b for b in self.bodies if inside(b['x'], b['y']) and inside(b['x'] + b['w'] - 1, b['y'] + b['h'] - 1)]
        shafts = [q for q in self.shafts if inside(q['x'] - q['R'] - q.get('tl', 0), q['y'] - q['R'] - q.get('tl', 0))
                  and inside(q['x'] + q['R'] + q.get('tl', 0), q['y'] + q['R'] + q.get('tl', 0))]
        clip['bodies'], clip['shafts'] = bodies, shafts
        hs = [h for h in self.hinges if any(h['ref'] is o for o in (bodies if h['kind'] == 'body' else shafts))]
        clip['hinges'] = hs
        clip['rods'] = [r for r in self.rods if any(r['a'] is h for h in hs) and any(r['b'] is h for h in hs)]
        clip['meshes'] = [m for m in self.meshes if any(m['a'] is q for q in shafts) and any(m['b'] is q for q in shafts)]
        clip['chains'] = [m for m in self.chains if any(m['a'] is q for q in shafts) and any(m['b'] is q for q in shafts)]
        return clip

    def paste(self, clip, ox, oy):
        # ox, oy = where the top-left corner of the copy lands
        dx, dy = ox - clip['x0'], oy - clip['y0']
        w, h = clip['w'], clip['h']
        if ox < 1 or oy < 1 or ox + w > self.W2 - 1 or oy + h > self.H2 - 1:
            return False
        sl = (slice(ox, ox + w), slice(oy, oy + h))
        mask = np.zeros(self.kind.shape, bool)
        mask[sl] = True
        self.erase(mask)
        for b in [b for b in self.bodies if mask[b['x']:b['x'] + b['w'], b['y']:b['y'] + b['h']].any()]:
            self.bodies.remove(b)
        if clip['n'] is not None:
            self.n[(slice(None),) + sl] = clip['n']
            self.T[sl] = clip['T']
        self.kind[sl] = clip['kind']
        self.strength[sl] = clip['strength']
        self.aux[sl] = clip['aux']
        old_h2 = self.H2
        lk = clip['link'].copy()
        # valve / igniter -> sensor links point at cells, so shift them with the copy
        for ix in range(w):
            for iy in range(h):
                v = lk[ix, iy]
                if v >= 0:
                    sx, sy = divmod(int(v), self.H2)
                    lk[ix, iy] = (sx + dx) * self.H2 + (sy + dy) if (sx, sy) in clip['sensors'] else -1
        self.link[sl] = lk
        self.valve_open[sl] = False
        for (x, y), v in clip['sensors'].items():
            v = dict(v)
            v['on'] = False
            self.sensors[(x + dx, y + dy)] = v
        for (x, y), v in clip['glinks'].items():
            v = dict(v)
            v['on'] = False
            t = v['tgt']
            v['tgt'] = (t[0] + dx, t[1] + dy) if t and clip['x0'] <= t[0] < clip['x0'] + w and clip['y0'] <= t[1] < clip['y0'] + h else None
            if v['tgt']:
                self.glinks[(x + dx, y + dy)] = v
            else:
                self.kind[x + dx, y + dy] = 0
        newb, news = {}, {}
        for b in clip['bodies']:
            nb = dict(b)
            nb['x'] += dx
            nb['y'] += dy
            nb['vx'] = nb['vy'] = 0.0
            nb['fx'] = nb['fy'] = 0.0
            self.bodies.append(nb)
            newb[id(b)] = nb
        for q in clip['shafts']:
            nq = dict(q)
            nq['x'] += dx
            nq['y'] += dy
            nq['om'] = 0.0
            nq['grace'] = 200
            self.shafts.append(nq)
            news[id(q)] = nq
        newh = {}
        for h_ in clip['hinges']:
            nh = dict(h_)
            nh['ref'] = (newb if h_['kind'] == 'body' else news)[id(h_['ref'])]
            self.hinges.append(nh)
            newh[id(h_)] = nh
        for r in clip['rods']:
            self.rods.append(dict(a=newh[id(r['a'])], b=newh[id(r['b'])], L=r['L']))
        for m in clip['meshes']:
            self.meshes.append(dict(a=news[id(m['a'])], b=news[id(m['b'])], k=m['k']))
        for m in clip.get('chains', []):
            self.chains.append(dict(a=news[id(m['a'])], b=news[id(m['b'])], k=m['k']))
        self.comp_cache = {}
        self.rebuild()
        self.update_valves()
        if clip['n'] is not None:
            self.active |= set(np.nonzero(clip['n'].reshape(clip['n'].shape[0], -1).max(1) > 1e-7)[0].tolist())
        return True

    # ---- crankshafts: shafts spin, hinges sit on blocks / shafts, rods hold two hinges a fixed distance apart
    def shaft_inertia(self, sh):
        R = sh['R']
        n = sh.get('teeth', 0)
        dens = G_COG_DENS if n else G_SHAFT_DENS      # cogs are light, shafts are the flywheels
        I = 0.5 * dens * math.pi * R ** 4
        if n:
            tl = sh['tl']
            I += dens * n * tl * (math.pi * R / n) * (R + tl / 2) ** 2     # the teeth
        return I

    def cog_cells(self, sh):
        # (x0, y0, mask) of the cells a cog covers: base disk plus teeth (half of each tooth period)
        R, tl, n = sh['R'], sh['tl'], sh['teeth']
        Ro = R + tl
        x0, x1 = max(1, int(sh['x'] - Ro) - 1), min(self.W2 - 2, int(sh['x'] + Ro) + 2)
        y0, y1 = max(1, int(sh['y'] - Ro) - 1), min(self.H2 - 2, int(sh['y'] + Ro) + 2)
        if x1 < x0 or y1 < y0:
            return x0, y0, np.zeros((0, 0), bool)
        rx = np.arange(x0, x1 + 1)[:, None] + 0.5 - sh['x']
        ry = np.arange(y0, y1 + 1)[None, :] + 0.5 - sh['y']
        r = np.hypot(rx, ry)
        P = 2 * math.pi / n
        ph = np.mod(np.arctan2(ry, rx) - sh['th'], P)
        return x0, y0, (r <= R) | ((r <= Ro) & (ph < P / 2))

    def update_cogs(self):
        # rotating cogs are solid: cells they sweep over push their gas out of the way, cells they leave are empty
        cogs = [sh for sh in self.shafts if sh.get('teeth')]
        cm = np.zeros(self.kind.shape, bool)
        for sh in cogs:
            x0, y0, m = self.cog_cells(sh)
            cm[x0:x0 + m.shape[0], y0:y0 + m.shape[1]] |= m
        for rb in self.rbs:
            cm[rb['cx'], rb['cy']] = True
        if (cm == self.cogmask).all():
            return
        new = cm & ~self.cogmask & ~self.solid
        self.cogmask = cm
        self.rebuild()
        if new.any():
            # squeeze the gas of newly covered cells evenly into the open cells around them (energy kept)
            xs, ys = np.nonzero(new)
            S = self.n.shape[0]
            amt = self.n[:, xs, ys].copy()
            es = (self.cvv @ amt) * self.T[xs, ys]
            oks = [~self.solid[xs + dx, ys + dy] for dx, dy in G_DIRS]
            cnt = np.maximum(sum(o.astype(np.int32) for o in oks), 1)
            e_before = (self.cvv @ self.n.reshape(S, -1)).reshape(self.T.shape) * self.T
            e_add = np.zeros(self.T.shape, np.float32)
            touched = np.zeros(self.T.shape, bool)
            for (dx, dy), ok in zip(G_DIRS, oks):
                if not ok.any():
                    continue
                tx, ty = xs[ok] + dx, ys[ok] + dy
                for sp in range(S):
                    if amt[sp, ok].any():
                        np.add.at(self.n[sp], (tx, ty), amt[sp, ok] / cnt[ok])
                np.add.at(e_add, (tx, ty), es[ok] / cnt[ok])
                touched[tx, ty] = True
            self.n[:, new] = 0
            c_new = (self.cvv @ self.n.reshape(S, -1)).reshape(self.T.shape)
            m = touched & ~self.solid & (c_new > 1e-6)
            self.T[m] = (e_before[m] + e_add[m]) / c_new[m]
        self.T[self.solid] = 293

    def cog_torque(self, p):
        # gas pushes on the teeth with its flow: force ~ density x (gas speed - surface speed) on every exposed face.
        # the surface speed part is solved implicitly, so it can only ever slow a cog down toward the gas speed
        ucell = np.zeros(self.kind.shape, np.float32)
        vcell = np.zeros(self.kind.shape, np.float32)
        ucell[1:-1, :] = 0.5 * (self.u[:-1] + self.u[1:])
        vcell[:, 1:-1] = 0.5 * (self.v[:, :-1] + self.v[:, 1:])
        rho = self.n.sum(0)
        for sh in self.shafts:
            if not sh.get('teeth'):
                continue
            x0, y0, m = self.cog_cells(sh)
            if not m.any():
                continue
            xs, ys = np.nonzero(m)
            gx, gy = xs + x0, ys + y0
            rx, ry = gx + 0.5 - sh['x'], gy + 0.5 - sh['y']
            tau = D = 0.0
            om = sh['om']
            for dx, dy in G_DIRS:
                nx, ny = gx + dx, gy + dy
                o = ~self.solid[nx, ny]
                if not o.any():
                    continue
                rfx, rfy = rx[o] + 0.5 * dx, ry[o] + 0.5 * dy
                q = rfx * dy - rfy * dx
                kr = G_COG_FLOW * np.minimum(rho[nx[o], ny[o]], 8.0)
                c_in = -(ucell[nx[o], ny[o]] * dx + vcell[nx[o], ny[o]] * dy) + om * q    # how fast the gas hits the face
                tau += float((-kr * c_in * np.abs(c_in) * q).sum())
                D += float((2 * kr * np.abs(c_in) * q * q).sum())
                # plain pressure on the face pushes it inwards, damped below so the wake can't spin it up by itself
                rf = np.minimum(rho[nx[o], ny[o]], 8.0)
                tau += float((-p[nx[o], ny[o]] * q).sum()) * G_PUSH * G_COG_PUSH
                D += float((G_COG_DAMP * rf * q * q).sum())
            I = self.shaft_inertia(sh)
            if sh.get('grace', 0) > 0:
                sh['grace'] -= 1
                tau = 0.0
            sh['om'] = (om + tau / (I + D)) * G_COG_FRICTION

    def mesh_phase(self, a, b):
        # turn b so its teeth fall into the gaps of a, along the line between them, then lock the pair
        phi = math.atan2(b['y'] - a['y'], b['x'] - a['x'])
        PA, PB = 2 * math.pi / a['teeth'], 2 * math.pi / b['teeth']
        fa = math.fmod(phi - a['th'], PA) / PA % 1.0
        fb = (fa + 0.5) % 1.0
        b['th'] = (phi + math.pi - fb * PB) % (2 * math.pi)

    def pitch(self, sh):
        return sh['R'] + sh['tl'] / 2

    def cpitch(self, sh):
        return sh['R'] + sh.get('tl', 0) / 2

    def add_chain(self, a, b):
        if a is b:
            return 'pick two different shafts'
        for m in self.chains:
            if (m['a'] is a and m['b'] is b) or (m['a'] is b and m['b'] is a):
                self.chains.remove(m)
                return 'chain removed'
        self.chains.append(dict(a=a, b=b, k=a['th'] * self.cpitch(a) - b['th'] * self.cpitch(b)))
        ra, rb = self.cpitch(a), self.cpitch(b)
        return f'chain on, ratio {ra / rb:.2f} : 1'

    def near_shaft(self, fx, fy):
        best, bd = None, 1e9
        for sh in self.shafts:
            d = math.hypot(sh['x'] - fx, sh['y'] - fy)
            if d <= sh['R'] + sh.get('tl', 0) and d < bd:
                best, bd = sh, d
        return best

    def toggle_wheel(self, fx, fy):
        sh = self.near_shaft(fx, fy)
        if sh is None:
            return 'wheels only go on shafts'
        if sh.get('teeth'):
            return 'cogs cannot be wheels, use a plain shaft'
        sh['wheel'] = not sh.get('wheel')
        return 'wheel on' if sh['wheel'] else 'wheel off'

    # ---- the world is wider than the window: it scrolls past in slabs, and what was built is kept in storage
    def pack_slab(self, lo, hi):
        k = (self.wx + lo - 1) // G_SLAB
        import copy
        clip = copy.deepcopy(self.copy_region(lo, 1, hi, self.H2 - 2, gas=False))      # a snapshot, not the live parts
        if (clip['kind'] > 0).any() or clip['bodies'] or clip['shafts'] or clip['sensors']:
            self.slabs[k] = clip
        else:
            self.slabs.pop(k, None)

    def scroll_world(self, d):
        # d = +1: the window moves right along the world, -1: left. returns an error text or None
        amt = G_SLAB * d
        W2, H2 = self.W2, self.H2
        gw = W2 - 2
        lo = 1 if d > 0 else gw - G_SLAB + 1
        hi = lo + G_SLAB - 1
        for f in self.frames:
            if not (f['x0'] + f['w'] - 1 < lo or f['x0'] > hi):
                return 'a physics object is in the way, move it first'
        for rb in self.rbs:
            if ((rb['cx'] >= lo) & (rb['cx'] <= hi)).any():
                return 'a spinning body is in the way, move it first'
        self.pack_slab(lo, hi)
        for arr in (self.T, self.kind, self.strength, self.valve_open, self.relief_open, self.liq, self.phi,
                    self.decay, self.scram, self.aux, self.link, self.spark_t, self.cogmask, self.u, self.v):
            arr[:] = np.roll(arr, -amt, axis=0)
        self.n[:] = np.roll(self.n, -amt, axis=1)
        e0 = gw - G_SLAB + 1 if d > 0 else 1         # the slab that comes in
        cols = slice(e0, e0 + G_SLAB)
        for c_ in (slice(0, 1), slice(W2 - 1, W2), cols):
            self.kind[c_] = 0
            self.strength[c_] = 0
            self.aux[c_] = 0
            self.link[c_] = -1
            self.valve_open[c_] = False
            self.relief_open[c_] = False
            self.scram[c_] = False
            self.cogmask[c_] = False
            for arr in (self.liq, self.phi, self.decay, self.spark_t, self.u, self.v):
                arr[c_] = 0
            self.T[c_] = 293
            self.n[:, c_] = 0 if self.void else self.amb_field
        self.wx += amt
        # everything that lives in the window moves with it
        for b in self.bodies:
            b['x'] -= amt
        for q in self.shafts:
            q['x'] -= amt
        for f in self.frames:
            f['x0'] -= amt
        for rb in self.rbs:
            rb['x'] -= amt
            rb['cx'] = rb['cx'] - amt
        for dbr in self.debris:
            dbr[0] -= amt
        self.sensors = {(k[0] - amt, k[1]): v for k, v in self.sensors.items()}
        self.probes = {(k[0] - amt, k[1]): v for k, v in self.probes.items()}
        gl = {}
        for k, v in self.glinks.items():
            t = v['tgt']
            if t:
                v['tgt'] = (t[0] - amt, t[1])
            gl[(k[0] - amt, k[1])] = v
        self.glinks = gl
        self.link[self.link >= 0] -= amt * H2
        gone = len([b for b in self.bodies if b['x'] < 1 or b['x'] + b['w'] > W2 - 1]) \
            + len([q for q in self.shafts if not (1 <= q['x'] < W2 - 1)])
        self.bodies = [b for b in self.bodies if not (b['x'] < 1 or b['x'] + b['w'] > W2 - 1)]
        self.shafts = [q for q in self.shafts if 1 <= q['x'] < W2 - 1]
        self.sensors = {k: v for k, v in self.sensors.items() if 1 <= k[0] < W2 - 1}
        self.probes = {k: v for k, v in self.probes.items() if 1 <= k[0] < W2 - 1}
        self.glinks = {k: v for k, v in self.glinks.items() if 1 <= k[0] < W2 - 1 and (v['tgt'] is None or 1 <= v['tgt'][0] < W2 - 1)}
        valid = [x * H2 + y for (x, y) in self.sensors]
        self.link[(self.link >= 0) & ~np.isin(self.link, valid)] = -1
        self.prune_mech()
        k = (self.wx + e0 - 1) // G_SLAB
        clip = self.slabs.get(k)
        self.comp_cache = {}
        self.cogmask[:] = False
        self.rebuild()
        if clip is not None:
            self.paste(clip, e0, 1)
        self.update_cogs()
        self.rebuild()
        self.u[:] = np.clip(self.u, -G_UMAX, G_UMAX)
        return None

    def follow_frame(self):
        # a driving physics object pulls the window along with it
        for f in self.frames:
            if not any(q.get('wheel') for q in self.frame_shafts(f)):
                continue
            cx = f['x0'] + f['w'] / 2.0
            if cx > self.W2 - 44:
                return 1 if self.scroll_world(1) is None else 0
            if cx < 44:
                return -1 if self.scroll_world(-1) is None else 0
        return 0

    def save_world(self, path):
        import pickle
        try:
            if self.slabs:
                tmp = path + '.tmp'
                with open(tmp, 'wb') as f_:
                    pickle.dump(self.slabs, f_, protocol=4)
                os.replace(tmp, path)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def load_world(self, path):
        import pickle
        self.slabs = {}
        try:
            if os.path.exists(path):
                with open(path, 'rb') as f_:
                    d_ = pickle.load(f_)
                if isinstance(d_, dict):
                    self.slabs = d_
        except Exception:
            self.slabs = {}

    # ---- spinning bodies: a pile of plain solid cells that turns into a free rigid body (it can rotate)
    def make_rbody(self, x0, y0, x1, y1):
        # None = this selection can't be a free body (it has parts / mechanisms in it)
        x0, x1 = sorted((max(1, x0), min(self.W2 - 2, x1)))
        y0, y1 = sorted((max(1, y0), min(self.H2 - 2, y1)))
        sl = (slice(x0, x1 + 1), slice(y0, y1 + 1))
        ins = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
        if any(x0 <= q['x'] <= x1 + 1 and y0 <= q['y'] <= y1 + 1 for q in self.shafts):
            return None
        if any(ins(*k) for k in list(self.sensors) + list(self.glinks) + list(self.probes)):
            return None
        kinds = self.kind[sl]
        if ((kinds > 0) & ~np.isin(kinds, G_RB_KINDS)).any():
            return None
        bods = []
        for b in self.bodies:
            inx = not (b['x'] + b['w'] - 1 < x0 or b['x'] > x1 or b['y'] + b['h'] - 1 < y0 or b['y'] > y1)
            if inx:
                if not (ins(b['x'], b['y']) and ins(b['x'] + b['w'] - 1, b['y'] + b['h'] - 1)):
                    return None
                bods.append(b)
        cells = []                      # (x, y, kind, strength)
        xs, ys = np.nonzero(kinds > 0)
        for a_, b_ in zip(xs.tolist(), ys.tolist()):
            cells.append((x0 + a_, y0 + b_, int(kinds[a_, b_]), float(self.strength[x0 + a_, y0 + b_])))
        for b in bods:
            for cx in range(b['x'], b['x'] + b['w']):
                for cy in range(b['y'], b['y'] + b['h']):
                    cells.append((cx, cy, 255, 0.0))
        if not cells:
            return None
        for x_, y_, k_, st_ in cells:
            if k_ != 255:
                self.kind[x_, y_] = 0
                self.strength[x_, y_] = 0
        for b in bods:
            self.bodies.remove(b)
        self.prune_mech()
        gx0 = min(c[0] for c in cells)
        gy0 = min(c[1] for c in cells)
        gw = max(c[0] for c in cells) - gx0 + 1
        gh = max(c[1] for c in cells) - gy0 + 1
        grid = np.full((gw, gh), -1, np.int32)
        for i, c in enumerate(cells):
            grid[c[0] - gx0, c[1] - gy0] = i
        N = len(cells)
        gi = np.array([c[0] - gx0 for c in cells], np.float64) + 0.5
        gj = np.array([c[1] - gy0 for c in cells], np.float64) + 0.5
        cmx, cmy = float(gi.mean()), float(gj.mean())
        rr = (gi - cmx) ** 2 + (gj - cmy) ** 2
        rb = dict(gw=gw, gh=gh, grid=grid, kind=np.array([c[2] for c in cells], np.uint8),
                  strength=np.array([c[3] for c in cells], np.float32),
                  cmx=cmx, cmy=cmy, x=gx0 + cmx, y=gy0 + cmy, th=0.0, vx=0.0, vy=0.0, om=0.0,
                  m=float(N), I=float(rr.sum() + N / 6.0), r=float(math.sqrt(rr.max()) + 1.0))
        rb['col'] = np.array([G_BLOCK_COLOR if c[2] == 255 else G_SOLIDS[c[2]][2] for c in cells], np.uint8)
        self.rb_pose(rb)
        self.rbs.append(rb)
        self.rebuild()
        return rb

    def rb_raster(self, rb, x, y, th):
        r = rb['r'] + 1.5
        ix0, ix1 = max(0, int(math.floor(x - r))), min(self.W2 - 1, int(math.ceil(x + r)))
        iy0, iy1 = max(0, int(math.floor(y - r))), min(self.H2 - 1, int(math.ceil(y + r)))
        if ix1 < ix0 or iy1 < iy0:
            e = np.zeros(0, np.int64)
            return e, e, e
        X = (np.arange(ix0, ix1 + 1)[:, None] + 0.5 - x)
        Y = (np.arange(iy0, iy1 + 1)[None, :] + 0.5 - y)
        c, s_ = math.cos(th), math.sin(th)
        gi = np.floor(c * X + s_ * Y + rb['cmx']).astype(np.int64)
        gj = np.floor(-s_ * X + c * Y + rb['cmy']).astype(np.int64)
        ok = (gi >= 0) & (gi < rb['gw']) & (gj >= 0) & (gj < rb['gh'])
        idx = np.full(gi.shape, -1, np.int64)
        idx[ok] = rb['grid'][gi[ok], gj[ok]]
        m = idx >= 0
        xs, ys = np.nonzero(m)
        return xs + ix0, ys + iy0, idx[m]

    def rb_pose(self, rb):
        rb['cx'], rb['cy'], rb['ci'] = self.rb_raster(rb, rb['x'], rb['y'], rb['th'])

    def rb_foreign(self, rb):
        fm = self.solid | self.ring
        fm[rb['cx'], rb['cy']] = False
        for f in self.frames:
            fm[f['x0']:f['x0'] + f['w'], f['y0']:f['y0'] + f['h']] = True
        return fm

    def move_rbodies(self, p):
        for rb in list(self.rbs):
            cx, cy = rb['cx'], rb['cy']
            if len(cx) == 0:
                self.rbs.remove(rb)
                continue
            Fx = Fy = tau = 0.0
            for dx, dy in G_DIRS:
                nx, ny = cx + dx, cy + dy
                g = ~self.solid[nx, ny]
                pp = p[nx, ny] * g
                fx_, fy_ = -dx * pp, -dy * pp
                Fx += float(fx_.sum())
                Fy += float(fy_.sum())
                rx = cx + 0.5 + 0.5 * dx - rb['x']
                ry = cy + 0.5 + 0.5 * dy - rb['y']
                tau += float((rx * fy_ - ry * fx_).sum())
            m, I = rb['m'], rb['I']
            rb['vx'] = (rb['vx'] + Fx * G_PUSH / m) * 0.999
            rb['vy'] = (rb['vy'] + Fy * G_PUSH / m + (G_BODY_G if self.gravity else 0)) * 0.999
            rb['om'] = (rb['om'] + tau * G_PUSH / I) * 0.998
            vmax = 0.45
            rb['vx'] = max(-vmax, min(vmax, rb['vx']))
            rb['vy'] = max(-vmax, min(vmax, rb['vy']))
            wmax = vmax / rb['r']
            rb['om'] = max(-wmax, min(wmax, rb['om']))
            self.rb_move(rb)
        self.update_cogs()

    def rb_move(self, rb):
        fm = self.rb_foreign(rb)
        x, y, th = rb['x'] + rb['vx'], rb['y'] + rb['vy'], rb['th'] + rb['om']
        old = (rb['x'], rb['y'], rb['th'])
        m, I = rb['m'], rb['I']
        ok = False
        for _ in range(4):
            wx, wy, _i = self.rb_raster(rb, x, y, th)
            hit = fm[wx, wy]
            if not hit.any():
                ok = True
                break
            hx, hy = wx[hit], wy[hit]
            Nx = Ny = 0.0
            for ddx in range(-2, 3):
                for ddy in range(-2, 3):
                    if ddx or ddy:
                        v = fm[np.clip(hx + ddx, 0, self.W2 - 1), np.clip(hy + ddy, 0, self.H2 - 1)]
                        Nx -= ddx * float(v.sum())
                        Ny -= ddy * float(v.sum())
            L = math.hypot(Nx, Ny)
            if L < 1e-6:
                Nx, Ny = x - float(hx.mean()) - 0.5, y - float(hy.mean()) - 0.5
                L = math.hypot(Nx, Ny) or 1.0
            Nx, Ny = Nx / L, Ny / L
            for _k in range(10):
                x += Nx * 0.2
                y += Ny * 0.2
                wx, wy, _i = self.rb_raster(rb, x, y, th)
                if not fm[wx, wy].any():
                    break
            rx, ry = float(hx.mean()) + 0.5 - x, float(hy.mean()) + 0.5 - y
            vcx, vcy = rb['vx'] - rb['om'] * ry, rb['vy'] + rb['om'] * rx
            vn = vcx * Nx + vcy * Ny
            if vn < 0:
                rn = rx * Ny - ry * Nx
                e = 0.0 if -vn < 0.03 else G_RB_E
                j = -(1 + e) * vn / (1.0 / m + rn * rn / I)
                rb['vx'] += j * Nx / m
                rb['vy'] += j * Ny / m
                rb['om'] += rn * j / I
                tx, ty = -Ny, Nx
                vt = vcx * tx + vcy * ty
                rt = rx * ty - ry * tx
                jt = -vt / (1.0 / m + rt * rt / I)
                jt = max(-G_RB_MU * j, min(G_RB_MU * j, jt))
                rb['vx'] += jt * tx / m
                rb['vy'] += jt * ty / m
                rb['om'] += rt * jt / I
        if not ok:
            x, y, th = old
            rb['vx'] *= 0.5
            rb['vy'] *= 0.5
            rb['om'] *= 0.5
        rb['x'], rb['y'], rb['th'] = x, y, th
        self.rb_pose(rb)

    def rb_rows(self, k, rb):
        ii, jj = np.nonzero(rb['grid'] >= 0)
        idx = rb['grid'][ii, jj]
        return [[k, int(a), int(b), int(rb['kind'][i]), int(rb['strength'][i])] for a, b, i in zip(ii.tolist(), jj.tolist(), idx.tolist())]

    def load_rbs(self, meta, cells):
        for k, row in enumerate(meta.tolist()):
            x, y, th, vx, vy, om, cmx, cmy, gw, gh = row
            gw, gh = int(gw), int(gh)
            mine = cells[cells[:, 0] == k]
            grid = np.full((gw, gh), -1, np.int32)
            kinds, stre, cols = [], [], []
            for i, (_k, gi, gj, kd, st) in enumerate(mine.tolist()):
                grid[gi, gj] = i
                kinds.append(kd)
                stre.append(st)
                cols.append(G_BLOCK_COLOR if kd == 255 else G_SOLIDS[kd][2])
            N = max(1, len(kinds))
            ii, jj = np.nonzero(grid >= 0)
            rr = (ii + 0.5 - cmx) ** 2 + (jj + 0.5 - cmy) ** 2
            rb = dict(gw=gw, gh=gh, grid=grid, kind=np.array(kinds, np.uint8), strength=np.array(stre, np.float32),
                      col=np.array(cols, np.uint8), cmx=cmx, cmy=cmy, x=x, y=y, th=th, vx=vx, vy=vy, om=om,
                      m=float(N), I=float(rr.sum() + N / 6.0), r=float(math.sqrt(rr.max() if len(rr) else 1.0) + 1.0))
            self.rb_pose(rb)
            self.rbs.append(rb)

    def freeze_rbody(self, rb):
        # turn it back into ordinary static cells where it is now
        for x, y, i in zip(rb['cx'].tolist(), rb['cy'].tolist(), rb['ci'].tolist()):
            k = int(rb['kind'][i])
            self.kind[x, y] = G_WALL if k == 255 else k
            self.strength[x, y] = rb['strength'][i]
        self.rbs.remove(rb)
        self.cogmask[:] = False
        self.update_cogs()
        self.rebuild()

    def release_rbodies(self, x0, y0, x1, y1):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        gone = [rb for rb in self.rbs
                if ((rb['cx'] >= x0) & (rb['cx'] <= x1) & (rb['cy'] >= y0) & (rb['cy'] <= y1)).any()]
        for rb in gone:
            self.freeze_rbody(rb)
        return len(gone)

    # ---- physics objects: a box of the world (walls, gas inside, blocks, shafts, rods) that moves as one piece
    def frame_at(self, x, y, pad=0.01):
        for f in self.frames:
            if f['x0'] - pad <= x <= f['x0'] + f['w'] + pad and f['y0'] - pad <= y <= f['y0'] + f['h'] + pad:
                return f
        return None

    def foff(self, x, y):
        # how far (in cells) the physics object at this spot is shifted from its whole-cell position
        f = self.frame_at(x, y)
        return (f['fx'], f['fy']) if f else (0.0, 0.0)

    def hoff(self, h):
        r = h['ref']
        if h['kind'] == 'body':
            return self.foff(r['x'] + r['w'] / 2.0, r['y'] + r['h'] / 2.0)
        return self.foff(r['x'], r['y'])

    def make_frame(self, x0, y0, x1, y1):
        x0, x1 = sorted((max(1, x0), min(self.W2 - 2, x1)))
        y0, y1 = sorted((max(1, y0), min(self.H2 - 2, y1)))
        w, h = x1 - x0 + 1, y1 - y0 + 1
        for f in self.frames:
            if not (x1 < f['x0'] or x0 >= f['x0'] + f['w'] or y1 < f['y0'] or y0 >= f['y0'] + f['h']):
                return 'that overlaps another physics object'
        if any(((rb['cx'] >= x0) & (rb['cx'] <= x1) & (rb['cy'] >= y0) & (rb['cy'] <= y1)).any() for rb in self.rbs):
            return 'that overlaps a spinning body'
        sl = (slice(x0, x1 + 1), slice(y0, y1 + 1))
        has_sh = any(x0 <= q['x'] <= x1 + 1 and y0 <= q['y'] <= y1 + 1 for q in self.shafts)
        if not (self.solid[sl].any() or has_sh):
            return 'nothing solid in the selection'
        for b in self.bodies:
            inx = not (b['x'] + b['w'] - 1 < x0 or b['x'] > x1 or b['y'] + b['h'] - 1 < y0 or b['y'] > y1)
            full = x0 <= b['x'] and b['x'] + b['w'] - 1 <= x1 and y0 <= b['y'] and b['y'] + b['h'] - 1 <= y1
            if inx and not full:
                return 'the selection cuts a block in half'
        # shrink the box to what is actually in it, so empty air below the wheels doesn't hold the car off the ground
        occ = self.solid[sl] | (self.kind[sl] > 0)
        xs, ys = np.nonzero(occ)
        lo_x, hi_x, lo_y, hi_y = (xs.min(), xs.max(), ys.min(), ys.max()) if len(xs) else (w, -1, h, -1)
        for q in self.shafts:
            if x0 <= q['x'] <= x1 + 1 and y0 <= q['y'] <= y1 + 1:
                lo_x, hi_x = min(lo_x, int(q['x']) - x0), max(hi_x, int(q['x']) - x0)
                lo_y, hi_y = min(lo_y, int(q['y']) - y0), max(hi_y, int(q['y']) - y0)
        x0, x1, y0, y1 = x0 + lo_x, x0 + hi_x, y0 + lo_y, y0 + hi_y
        w, h = x1 - x0 + 1, y1 - y0 + 1
        self.frames.append(dict(x0=int(x0), y0=int(y0), w=int(w), h=int(h), fx=0.0, fy=0.0, vx=0.0, vy=0.0))
        return None

    def release_frames(self, x0, y0, x1, y1):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        gone = [f for f in self.frames
                if not (x1 < f['x0'] or x0 >= f['x0'] + f['w'] or y1 < f['y0'] or y0 >= f['y0'] + f['h'])]
        for f in gone:
            self.frames.remove(f)
        return len(gone)

    def in_frame(self, f, x, y):
        return f['x0'] <= x < f['x0'] + f['w'] and f['y0'] <= y < f['y0'] + f['h']

    def frame_shafts(self, f):
        return [sh for sh in self.shafts if self.in_frame(f, sh['x'], sh['y'])]

    def frame_mass(self, f):
        sl = (slice(f['x0'], f['x0'] + f['w']), slice(f['y0'], f['y0'] + f['h']))
        m = float(np.count_nonzero(self.solid[sl])) * G_BODY_DENSITY
        for sh in self.frame_shafts(f):
            m += G_SHAFT_MASS * math.pi * sh['R'] ** 2
        return max(m, 4.0)

    def frame_cogs(self, f):
        cm = np.zeros(self.kind.shape, bool)
        for sh in self.frame_shafts(f):
            if sh.get('teeth'):
                x0, y0, m = self.cog_cells(sh)
                cm[x0:x0 + m.shape[0], y0:y0 + m.shape[1]] |= m
        return cm

    def rim_points(self, sh, n=16, lower=False):
        Rw = sh['R'] + G_WHEEL_T
        out = []
        for k in range(n):
            a = 2 * math.pi * k / n
            if lower and math.sin(a) < 0.3:
                continue
            out.append((sh['x'] + Rw * math.cos(a), sh['y'] + Rw * math.sin(a)))
        return out

    def foreign_cell(self, f, cx, cy, own):
        # is this cell something the physics object can't pass through?
        if not (0 <= cx < self.W2 and 0 <= cy < self.H2):
            return True
        if self.in_frame(f, cx, cy):
            return False
        if self.ring[cx, cy] or self.kind[cx, cy] > 0:
            return True
        if (self.solid[cx, cy] or self.cogmask[cx, cy]) and not own[cx, cy]:
            return True
        return any(o is not f and self.in_frame(o, cx, cy) for o in self.frames)

    def frame_blocked(self, f, dx, dy, own=None):
        x0, y0, w, h = f['x0'], f['y0'], f['w'], f['h']
        for o in self.frames:
            if o is not f and not (x0 + dx + w <= o['x0'] or x0 + dx >= o['x0'] + o['w']
                                   or y0 + dy + h <= o['y0'] or y0 + dy >= o['y0'] + o['h']):
                return True
        if dx:
            sx = x0 + w if dx > 0 else x0 - 1
            sl = (slice(sx, sx + 1), slice(y0, y0 + h))
        else:
            sy = y0 + h if dy > 0 else y0 - 1
            sl = (slice(x0, x0 + w), slice(sy, sy + 1))
        if own is None:
            own = self.frame_cogs(f)
        edge = self.solid[sl] | (self.kind[sl] > 0) | self.ring[sl]
        if edge.any() and (edge & ~own[sl]).any():
            return True
        for sh in self.frame_shafts(f):
            if sh.get('wheel'):
                for px, py in self.rim_points(sh):
                    if self.foreign_cell(f, int(math.floor(px)) + dx, int(math.floor(py)) + dy, own):
                        return True
        return False

    def wheel_grounded(self, f, sh, own):
        for px, py in self.rim_points(sh, 16, True):
            if self.foreign_cell(f, int(math.floor(px)), int(math.floor(py)) + 1, own):
                return True
        return False

    def roll_region(self, f, dx, dy):
        # shift the whole box one cell: everything in it moves, the air in the way flows round to the other side
        x0, y0, w, h = f['x0'], f['y0'], f['w'], f['h']
        x1, y1 = x0 + w - 1, y0 + h - 1
        if dx:
            ex0, ex1, ey0, ey1 = (x0, x1 + 1, y0, y1) if dx > 0 else (x0 - 1, x1, y0, y1)
            ax, sh_ = 0, dx
        else:
            ex0, ex1, ey0, ey1 = (x0, x1, y0, y1 + 1) if dy > 0 else (x0, x1, y0 - 1, y1)
            ax, sh_ = 1, dy
        sl = (slice(ex0, ex1 + 1), slice(ey0, ey1 + 1))
        for arr in (self.T, self.kind, self.strength, self.valve_open, self.relief_open, self.liq, self.phi,
                    self.decay, self.scram, self.aux, self.link, self.spark_t, self.cogmask):
            arr[sl] = np.roll(arr[sl], sh_, axis=ax)
        ns = (slice(None),) + sl
        self.n[ns] = np.roll(self.n[ns], sh_, axis=ax + 1)
        su = (slice(ex0, ex1), slice(ey0, ey1 + 1))
        sv = (slice(ex0, ex1 + 1), slice(ey0, ey1))
        self.u[su] = np.roll(self.u[su], sh_, axis=ax)
        self.v[sv] = np.roll(self.v[sv], sh_, axis=ax)
        # everything that lives in the box follows it
        for b in self.bodies:
            if self.in_frame(f, b['x'], b['y']) and self.in_frame(f, b['x'] + b['w'] - 1, b['y'] + b['h'] - 1):
                b['x'] += dx
                b['y'] += dy
        for q in self.shafts:
            if self.in_frame(f, q['x'], q['y']):
                q['x'] += dx
                q['y'] += dy
        moved = {}
        for key in [k for k in self.sensors if self.in_frame(f, *k)]:
            moved[key] = (key[0] + dx, key[1] + dy)
        if moved:
            old = dict(self.sensors)
            for k in moved:
                del self.sensors[k]
            for k, nk in moved.items():
                self.sensors[nk] = old[k]
            src = self.link.copy()
            for k, nk in moved.items():
                self.link[src == k[0] * self.H2 + k[1]] = nk[0] * self.H2 + nk[1]
        if self.glinks:
            gl = {}
            for k, v in self.glinks.items():
                nk = (k[0] + dx, k[1] + dy) if self.in_frame(f, *k) else k
                t = v['tgt']
                if t and self.in_frame(f, *t):
                    v['tgt'] = (t[0] + dx, t[1] + dy)
                gl[nk] = v
            self.glinks = gl
        if self.probes:
            self.probes = {((k[0] + dx, k[1] + dy) if self.in_frame(f, *k) else k): v for k, v in self.probes.items()}
        f['x0'] += dx
        f['y0'] += dy
        self.near_wall = None
        self.comp_cache = {}
        self.rebuild()

    def move_frames(self, p):
        for f in self.frames:
            x0, y0, w, h = f['x0'], f['y0'], f['w'], f['h']
            sl = (slice(x0 - 1, x0 + w + 1), slice(y0 - 1, y0 + h + 1))
            sol = self.solid[sl]
            pe = p[sl]
            gas = ~sol
            inner = sol[1:-1, 1:-1]
            fxp = float((inner * (pe[:-2, 1:-1] * gas[:-2, 1:-1] - pe[2:, 1:-1] * gas[2:, 1:-1])).sum())
            fyp = float((inner * (pe[1:-1, :-2] * gas[1:-1, :-2] - pe[1:-1, 2:] * gas[1:-1, 2:])).sum())
            m = self.frame_mass(f)
            vx_old = f['vx']
            f['vx'] = (f['vx'] + fxp * G_PUSH / m) * G_FRAME_DAMP
            f['vy'] = (f['vy'] + fyp * G_PUSH / m + (G_BODY_G if self.gravity else 0)) * G_FRAME_DAMP
            own = self.frame_cogs(f)
            wheels = [sh for sh in self.frame_shafts(f) if sh.get('wheel')]
            grounded = False
            if wheels:
                gr = [sh for sh in wheels if self.wheel_grounded(f, sh, own)]
                grounded = bool(gr)
                for sh in gr:
                    Rw = sh['R'] + G_WHEEL_T
                    I = self.shaft_inertia(sh)
                    slip = f['vx'] - sh['om'] * Rw
                    j = -slip / (1.0 / m + Rw * Rw / I)
                    jm = G_GRIP * m * G_BODY_G / len(gr)
                    j = max(-jm, min(jm, j))
                    f['vx'] += j / m
                    sh['om'] -= Rw * j / I
            f['vx'] = max(-0.9, min(0.9, f['vx']))
            f['vy'] = max(-0.9, min(0.9, f['vy']))
            self.slosh(f, f['vx'] - vx_old)
            for axis in (0, 1):
                vk, fk = ('vx', 'fx') if axis == 0 else ('vy', 'fy')
                v = f[vk]
                if v == 0:
                    continue
                d = 1 if v > 0 else -1
                ddx, ddy = (d, 0) if axis == 0 else (0, d)

                def bonk():
                    f[vk] = 0.0 if abs(f[vk]) < 0.02 else f[vk] * -0.2
                    if f[fk] * d > 0:
                        f[fk] = 0.0
                    if axis == 1 and d > 0 and not grounded:
                        f['vx'] *= 0.92         # sliding on the floor
                if self.frame_blocked(f, ddx, ddy, own):
                    bonk()
                    continue
                f[fk] += v
                while abs(f[fk]) >= 1:
                    if self.frame_blocked(f, ddx, ddy, own):
                        bonk()
                        break
                    self.roll_region(f, ddx, ddy)
                    f[fk] -= d
                    own = self.frame_cogs(f)

    def slosh(self, f, dv):
        # speeding up makes the water lag behind: push it toward the back wall
        if not self.gravity or abs(dv) < 0.002:
            return
        x0, y0, w, h = f['x0'], f['y0'], f['w'], f['h']
        sl = (slice(x0, x0 + w), slice(y0, y0 + h))
        L = self.liq[sl]
        if not L.any():
            return
        F = ~self.solid[sl]
        q = min(0.45, abs(dv) * 30)
        if dv > 0:      # accelerating right, water slides left
            amt = np.minimum(L[1:] * q, np.maximum(G_LIQ_CAP - L[:-1], 0)) * (F[1:] & F[:-1])
            L[1:] -= amt
            L[:-1] += amt
        else:
            amt = np.minimum(L[:-1] * q, np.maximum(G_LIQ_CAP - L[1:], 0)) * (F[1:] & F[:-1])
            L[:-1] -= amt
            L[1:] += amt

    def add_cog(self, x, y, R, tl, n):
        for sh in self.shafts:
            if math.hypot(sh['x'] - x, sh['y'] - y) < 1:
                return False
        cog = dict(x=x, y=y, R=max(3.0, R), th=0.0, om=0.0, teeth=max(4, int(n)), tl=max(1.0, tl), grace=200)
        phased = False
        for o in self.shafts:
            if o.get('teeth'):
                d = math.hypot(o['x'] - x, o['y'] - y)
                if o['R'] + cog['R'] - 0.5 < d < o['R'] + o['tl'] + cog['R'] + cog['tl'] - 0.2:
                    if not phased:
                        self.mesh_phase(o, cog)
                        phased = True
                    self.meshes.append(dict(a=o, b=cog, k=0.0))
        self.shafts.append(cog)
        for m in self.meshes:
            if m['b'] is cog or m['a'] is cog:
                m['k'] = m['a']['th'] * self.pitch(m['a']) + m['b']['th'] * self.pitch(m['b'])
        return True

    def hinge_pos(self, h):
        # (x, y, vx, vy, rx, ry), r = lever arm from the shaft centre (None on blocks)
        r = h['ref']
        if h['kind'] == 'body':
            return (r['x'] + r['fx'] + h['cx'] * r['w'], r['y'] + r['fy'] + h['cy'] * r['h'],
                    r['vx'], r['vy'], None, None)
        c, sn = math.cos(r['th']), math.sin(r['th'])
        rx = h['ox'] * c - h['oy'] * sn
        ry = h['ox'] * sn + h['oy'] * c
        return (r['x'] + rx, r['y'] + ry, -r['om'] * ry, r['om'] * rx, rx, ry)

    def add_shaft(self, x, y, R):
        for sh in self.shafts:
            if math.hypot(sh['x'] - x, sh['y'] - y) < 1:
                return False
        self.shafts.append(dict(x=x, y=y, R=max(3.0, R), th=0.0, om=0.0))
        return True

    def mirror_pts(self, x, y, sym):
        W2, H2 = self.W2, self.H2
        out = [(x, y)]
        if sym in (1, 3): out.append((W2 - x, y))
        if sym in (2, 3): out.append((x, H2 - y))
        if sym == 3: out.append((W2 - x, H2 - y))
        return out

    def add_hinge(self, fx, fy):
        # on a block: snaps to the middle of the closest side. on a shaft: 4 spots on the rim and 4 halfway in
        for b in self.bodies:
            if b['x'] <= fx < b['x'] + b['w'] and b['y'] <= fy < b['y'] + b['h']:
                d = {'l': fx - b['x'], 'r': b['x'] + b['w'] - fx, 't': fy - b['y'], 'b': b['y'] + b['h'] - fy}
                side = min(d, key=d.get)
                cx, cy = {'l': (0, 0.5), 'r': (1, 0.5), 't': (0.5, 0), 'b': (0.5, 1)}[side]
                for h in self.hinges:
                    if h['kind'] == 'body' and h['ref'] is b and h['cx'] == cx and h['cy'] == cy:
                        return 'that side already has a hinge'
                self.hinges.append(dict(kind='body', ref=b, ox=0.0, oy=0.0, cx=cx, cy=cy))
                return 'hinge on block'
        for sh in self.shafts:
            dx, dy = fx - sh['x'], fy - sh['y']
            dist = math.hypot(dx, dy)
            if dist <= sh['R']:
                # direction in the shaft's own frame, snapped to the nearest of 4
                ang = math.atan2(dy, dx) - sh['th']
                ang = round(ang / (math.pi / 2)) * (math.pi / 2)
                rad = sh['R'] if dist > sh['R'] * 0.75 else sh['R'] * 0.5
                ox, oy = rad * math.cos(ang), rad * math.sin(ang)
                for h in self.hinges:
                    if h['kind'] == 'shaft' and h['ref'] is sh and abs(h['ox'] - ox) < 1e-6 and abs(h['oy'] - oy) < 1e-6:
                        return 'that spot already has a hinge'
                self.hinges.append(dict(kind='shaft', ref=sh, ox=ox, oy=oy, cx=0, cy=0))
                return 'hinge on shaft rim' if rad == sh['R'] else 'hinge on shaft, halfway in'
        return 'put hinges on a block or inside a shaft'

    def near_hinge(self, fx, fy, reach=3.0):
        best, bd = None, reach
        for h in self.hinges:
            hx, hy = self.hinge_pos(h)[:2]
            d = math.hypot(hx - fx, hy - fy)
            if d < bd:
                best, bd = h, d
        return best

    def add_rod(self, ha, hb):
        if ha is hb:
            return False
        for r in self.rods:
            if (r['a'] is ha and r['b'] is hb) or (r['a'] is hb and r['b'] is ha):
                return False
        pa, pb = self.hinge_pos(ha), self.hinge_pos(hb)
        self.rods.append(dict(a=ha, b=hb, L=max(1.0, math.hypot(pa[0] - pb[0], pa[1] - pb[1]))))
        return True

    def prune_mech(self):
        live_b = {id(b) for b in self.bodies}
        live_s = {id(sh) for sh in self.shafts}
        self.hinges = [h for h in self.hinges
                       if id(h['ref']) in (live_b if h['kind'] == 'body' else live_s)]
        ids = {id(h) for h in self.hinges}
        self.rods = [r for r in self.rods if id(r['a']) in ids and id(r['b']) in ids]
        self.meshes = [m for m in self.meshes if id(m['a']) in live_s and id(m['b']) in live_s]
        self.chains = [m for m in self.chains if id(m['a']) in live_s and id(m['b']) in live_s]

    def erase_mech(self, mask):
        keep = []
        for sh in self.shafts:
            Ro = sh['R'] + sh.get('tl', 0)
            x0, x1 = int(sh['x'] - Ro) - 1, int(sh['x'] + Ro) + 2
            y0, y1 = int(sh['y'] - Ro) - 1, int(sh['y'] + Ro) + 2
            sub = mask[max(0, x0):max(0, x1), max(0, y0):max(0, y1)]
            hit = False
            if sub.any():
                xs, ys = np.nonzero(sub)
                hit = bool((((xs + max(0, x0) + 0.5 - sh['x']) ** 2 + (ys + max(0, y0) + 0.5 - sh['y']) ** 2) <= Ro ** 2).any())
            if not hit:
                keep.append(sh)
        self.shafts = keep
        self.hinges = [h for h in self.hinges
                       if not mask[min(self.W2 - 1, max(0, int(self.hinge_pos(h)[0]))),
                                   min(self.H2 - 1, max(0, int(self.hinge_pos(h)[1])))]
                       or (h['kind'] == 'shaft' and h['ref'] in keep and False)]
        self.prune_mech()
        self.update_cogs()      # a deleted cog stops being a solid shape

    def solve_rods(self):
        # velocity-level distance constraints (impulses), with a little push-back so errors don't pile up
        for _ in range(6):
            for m in self.chains:
                a, b = m['a'], m['b']
                ra, rb = self.cpitch(a), self.cpitch(b)
                Ia, Ib = self.shaft_inertia(a), self.shaft_inertia(b)
                err = a['th'] * ra - b['th'] * rb - m['k']
                lam = -(ra * a['om'] - rb * b['om'] + 0.1 * err) / (ra * ra / Ia + rb * rb / Ib)
                a['om'] += lam * ra / Ia
                b['om'] -= lam * rb / Ib
            for m in self.meshes:
                a, b = m['a'], m['b']
                ra, rb = self.pitch(a), self.pitch(b)
                Ia, Ib = self.shaft_inertia(a), self.shaft_inertia(b)
                err = a['th'] * ra + b['th'] * rb - m['k']
                lam = -(ra * a['om'] + rb * b['om'] + 0.1 * err) / (ra * ra / Ia + rb * rb / Ib)
                a['om'] += lam * ra / Ia
                b['om'] += lam * rb / Ib
            for r in self.rods:
                A, B = self.hinge_pos(r['a']), self.hinge_pos(r['b'])
                dx, dy = A[0] - B[0], A[1] - B[1]
                dist = math.hypot(dx, dy)
                if dist < 1e-6:
                    continue
                dx, dy = dx / dist, dy / dist
                vrel = (A[2] - B[2]) * dx + (A[3] - B[3]) * dy
                inv = []
                for h, P in ((r['a'], A), (r['b'], B)):
                    if h['kind'] == 'body':
                        b = h['ref']
                        m = b['w'] * b['h'] * G_BODY_DENSITY
                        ix = 0.0 if b.get('lx', 0) > 0 else 1.0 / m
                        iy = 0.0 if b.get('ly', 0) > 0 else 1.0 / m
                        inv.append(dx * dx * ix + dy * dy * iy)
                    else:
                        cr = P[4] * dy - P[5] * dx
                        inv.append(cr * cr / self.shaft_inertia(h['ref']))
                tot = inv[0] + inv[1]
                if tot < 1e-9:
                    continue
                lam = -(vrel + 0.25 * (dist - r['L'])) / tot
                for h, P, sgn in ((r['a'], A, 1), (r['b'], B, -1)):
                    if h['kind'] == 'body':
                        b = h['ref']
                        m = b['w'] * b['h'] * G_BODY_DENSITY
                        if b.get('lx', 0) <= 0:
                            b['vx'] += sgn * lam * dx / m
                        if b.get('ly', 0) <= 0:
                            b['vy'] += sgn * lam * dy / m
                    else:
                        cr = P[4] * dy - P[5] * dx
                        h['ref']['om'] += sgn * lam * cr / self.shaft_inertia(h['ref'])

    def move_bodies(self, p):
        for b in self.bodies:
            x, y, w, h = b['x'], b['y'], b['w'], b['h']
            mass = w * h * G_BODY_DENSITY
            # pressure on each side (gas cells only)
            def side(xs, ys):
                return float((p[xs, ys] * ~self.solid[xs, ys]).sum())
            fx = side(x - 1, slice(y, y + h)) - side(x + w, slice(y, y + h))
            fy = side(slice(x, x + w), y - 1) - side(slice(x, x + w), y + h)
            b['vx'] = (b['vx'] + fx * G_PUSH / mass) * 0.998
            b['vy'] = (b['vy'] + fy * G_PUSH / mass + (G_BODY_G if self.gravity else 0)) * 0.998
            b['vx'] = max(-0.9, min(0.9, b['vx']))
            b['vy'] = max(-0.9, min(0.9, b['vy']))
        if any(sh.get('teeth') for sh in self.shafts):
            self.cog_torque(p)
        if self.rods or self.meshes or self.chains:
            self.solve_rods()
            for b in self.bodies:
                b['vx'] = max(-0.9, min(0.9, b['vx']))
                b['vy'] = max(-0.9, min(0.9, b['vy']))
        for b in self.bodies:
            b['lx'] = max(0, b.get('lx', 0) - 1)
            b['ly'] = max(0, b.get('ly', 0) - 1)
            for axis in ('x', 'y'):
                vk, fk = 'v' + axis, 'f' + axis
                b[fk] += b[vk]
                while abs(b[fk]) >= 1:
                    d = 1 if b[fk] > 0 else -1
                    moved = self.try_move(b, d, 0) if axis == 'x' else self.try_move(b, 0, d)
                    if not moved:
                        b[vk] *= -0.25          # bonk
                        b[fk] = 0.0
                        b['l' + axis] = 3       # rods can't push a block into a wall
                        if axis == 'y':
                            b['vx'] *= 0.9      # friction on the floor
                        break
                    b[fk] -= d
        for sh in self.shafts:
            if self.starter and not sh.get('teeth') and sh['om'] < G_STARTER_MAX:
                sh['om'] = min(G_STARTER_MAX, sh['om'] + G_STARTER_T / self.shaft_inertia(sh))
            sh['th'] += sh['om']        # not wrapped, meshing cogs compare total turns
            sh['om'] *= G_SHAFT_DAMP
        if any(sh.get('teeth') for sh in self.shafts) or self.cogmask.any():
            self.update_cogs()

    # walls cracking
    def check_breaks(self, p):
        brk_full = (self.strength > 0) & self.solid
        if not brk_full.any():
            return
        # only look at the area around breakable walls
        xs, ys = np.nonzero(brk_full)
        x0, x1 = max(0, xs.min() - 8), min(self.W2, xs.max() + 9)
        y0, y1 = max(0, ys.min() - 8), min(self.H2, ys.max() + 9)
        box = (slice(x0, x1), slice(y0, y1))
        p = p[box]
        brk = brk_full[box]
        gas = ~self.solid[box]
        wall = (self.kind[box] > 0) & self.solid[box]
        load = np.zeros_like(p)
        for d, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
            pg = np.roll(p, d, axis)            # pressure on the near side
            g_ok = np.roll(gas, d, axis)
            # how thick the wall is going away from that gas (up to 6)
            t = np.ones_like(p)
            cont = wall.copy()
            pb = np.ones_like(p)
            found = np.zeros(p.shape, bool)
            for k in range(1, 7):
                nxt_wall = np.roll(wall, -k * d, axis)
                nxt_gas = np.roll(gas, -k * d, axis)
                hit = cont & ~nxt_wall & ~found
                pb = np.where(hit & nxt_gas, np.roll(p, -k * d, axis), pb)
                found |= hit
                cont = cont & nxt_wall
                t += cont
            l = np.where(g_ok & wall, (pg - pb) / t, 0)
            np.maximum(load, l, out=load)
        broken = np.zeros_like(brk_full)
        broken[box] = brk & (load > self.strength[box])
        broken &= ~self.ring
        if broken.any():
            xs, ys = np.nonzero(broken)
            for x, y in zip(xs.tolist(), ys.tolist()):
                if len(self.debris) < 600:
                    col = G_SOLIDS[int(self.kind[x, y])][2]
                    uu = float(self.u[min(x, self.W2 - 2), y] if x < self.W2 - 1 else 0)
                    vv = float(self.v[x, min(y, self.H2 - 2)])
                    self.debris.append([x + 0.5, y + 0.5, uu * 2 + random.uniform(-0.3, 0.3),
                                        vv * 2 + random.uniform(-0.3, 0.3), 2.0, col])
            self.kind[broken] = 0
            self.strength[broken] = 0
            self.rebuild()

    def move_debris(self, steps, dt):
        alive = []
        for d in self.debris:
            d[0] += d[2] * steps
            d[1] += d[3] * steps
            d[3] += 0.002 * steps if self.gravity else 0
            d[2] *= 0.995 ** steps
            d[4] -= dt
            if d[4] > 0 and 0 <= d[0] < self.W2 and 0 <= d[1] < self.H2:
                alive.append(d)
        self.debris = alive

    # physics
    def shift(self, m, dx, dy):
        # m moved so that out[x, y] = m[x + dx, y + dy] (False off the edge)
        o = np.zeros_like(m)
        xs = slice(max(0, -dx), m.shape[0] - max(0, dx))
        xd = slice(max(0, dx), m.shape[0] - max(0, -dx))
        ys = slice(max(0, -dy), m.shape[1] - max(0, dy))
        yd = slice(max(0, dy), m.shape[1] - max(0, -dy))
        o[xs, ys] = m[xd, yd]
        return o

    def update_relief(self, p0):
        r = self.kind == G_RELIEF
        thr = np.array(G_PRES_LEVELS, np.float32)[np.clip(self.aux, 0, 4)]
        mx = np.zeros_like(p0)
        for dx, dy in G_DIRS:
            mx = np.maximum(mx, self.shift(p0, dx, dy))
        new = r & ((mx > thr) | (self.relief_open & (mx > 0.9 * thr)))
        if (new == self.relief_open).all():
            return
        closing = self.relief_open & ~new
        self.relief_open = new
        self.rebuild()
        if closing.any():
            xs, ys = np.nonzero(closing)
            for dx, dy in G_DIRS:
                nx, ny = xs + dx, ys + dy
                ok = ~self.solid[nx, ny]
                if ok.any():
                    self.merge_gas(xs[ok], ys[ok], nx[ok], ny[ok])
            self.n[:, closing] = 0
            self.T[closing] = 293

    def thermal(self):
        return G_THERM_C[self.kind] > 0

    def exchange(self, n, T):
        # exchanger walls / fuel / rods pass heat between whatever touches them, but no gas
        S = n.shape[0]
        ex = self.thermal()
        Cg = (self.cvv @ n.reshape(S, -1)).reshape(T.shape) + G_LIQ_C * self.liq
        Cc = np.where(ex, G_THERM_C[self.kind], Cg)
        part = ~self.solid | ex
        E = Cc * T
        fu = self.kind == G_URAN
        Kc = np.where(fu, 0.004, G_EXCH_K)       # bare fuel sheds heat into gas badly, but wet fuel (boiling contact) well
        wet = np.clip(self.liq, 0, 1)
        Kx = np.minimum(Kc[:-1], Kc[1:]) + 0.3 * np.maximum(wet[:-1], wet[1:]) * (fu[:-1] | fu[1:])
        Ky = np.minimum(Kc[:, :-1], Kc[:, 1:]) + 0.3 * np.maximum(wet[:, :-1], wet[:, 1:]) * (fu[:, :-1] | fu[:, 1:])
        dx_ = Kx * np.minimum(Cc[:-1], Cc[1:]) * (T[:-1] - T[1:]) * (part[:-1] & part[1:] & (ex[:-1] | ex[1:]))
        E[:-1] -= dx_
        E[1:] += dx_
        dy_ = Ky * np.minimum(Cc[:, :-1], Cc[:, 1:]) * (T[:, :-1] - T[:, 1:]) * (part[:, :-1] & part[:, 1:] & (ex[:, :-1] | ex[:, 1:]))
        E[:, :-1] -= dy_
        E[:, 1:] += dy_
        m = part & (Cc > 1e-5)
        T[m] = E[m] / Cc[m]

    def reactor(self, n, T):
        # neutron flux diffuses through everything, water slows neutrons so fuel can catch them, control rods soak them up.
        # hot fuel catches fewer (doppler), fuel makes heat and keeps making some after shutdown (decay heat)
        R = G_REACT
        kind = self.kind
        fuel = kind == G_URAN
        rod = kind == G_CTRL
        phi = self.phi
        h = G_IDX['H2O']
        md = np.clip(self.liq, 0, 2) * 0.5 + np.clip(n[h], 0, 3) * 0.05
        md[self.solid] = 0
        mb = md.copy()
        mb[1:-1, 1:-1] = (md[1:-1, 1:-1] * 2 + md[:-2, 1:-1] + md[2:, 1:-1] + md[1:-1, :-2] + md[1:-1, 2:]) / 6
        mb = np.clip(mb, 0, 1)
        ins = np.where(self.scram, 1.0, self.aux * 0.25).astype(np.float32) * rod
        ab = R['LOSS'] + R['ABS_W'] * mb + R['ROD'] * ins
        ab = np.minimum(ab, 0.9)
        keff = R['K'] * (R['F0'] + (1 - R['F0']) * mb) / (1 + np.maximum(T - 293, 0) / R['DOPP'])
        gain = np.where(fuel, R['GAIN'] * (keff - 1), 0)
        src = np.where(fuel, R['SRC'], 0)
        for _ in range(2):
            lap = np.zeros_like(phi)
            lap[1:-1, 1:-1] = phi[:-2, 1:-1] + phi[2:, 1:-1] + phi[1:-1, :-2] + phi[1:-1, 2:] - 4 * phi[1:-1, 1:-1]
            phi += R['D'] * lap
            phi *= (1 - ab * 0.5)
            phi *= (1 + gain * 0.5)
            phi += src * 0.5
        phi[self.ring] = 0
        np.clip(phi, 0, R['PHI_MAX'], out=phi)
        if fuel.any():
            pw = np.where(fuel, R['POWER'] * phi, 0)
            self.decay += np.where(fuel, (R['DECAY_K'] * pw - self.decay) * R['DECAY_T'], 0)
            T += (pw + self.decay) / G_THERM_C[kind].clip(1)  * fuel
            melt = fuel & (T > R['MELT'])
            if melt.any():
                kind[melt] = 0
                self.strength[melt] = 0
                self.aux[melt] = 0
                self.comp_cache = {}
                self.decay[melt] = 0
                self.rebuild()
                self.melted = getattr(self, 'melted', 0) + int(melt.sum())
                if self.age - getattr(self, 'melt_t', -999) > 40:
                    self.news.append('MELTDOWN, the fuel is melting!')
                self.melt_t = self.age

    def turbines(self, u, v, p):
        # blades turn a shaft they touch from the pressure across them, and a spinning shaft drags the gas along
        if not self.shafts:
            return
        kx, ky = np.nonzero(self.kind == G_TURB)
        if not len(kx):
            return
        rho = self.n.sum(0)
        dirs = self.aux[kx, ky].astype(int) & 3
        dxs = np.array([g[0] for g in G_DIRS])[dirs]
        dys = np.array([g[1] for g in G_DIRS])[dirs]
        pg = p[kx - dxs, ky - dys] - p[kx + dxs, ky + dys]          # upstream minus downstream
        taken = np.zeros(len(kx), bool)
        for sh in self.shafts:
            if sh.get('teeth'):
                continue
            R = sh['R']
            m = (np.hypot(kx + 0.5 - sh['x'], ky + 0.5 - sh['y']) <= R + 1.5) & ~taken
            if not m.any():
                continue
            taken |= m
            Reff = 0.7 * R
            I = self.shaft_inertia(sh)
            rr = np.minimum(rho[kx[m], ky[m]], 8.0)
            A = G_TURB_P * R * float(pg[m].sum())
            B = G_TURB_D * R * Reff * float(rr.sum())
            om2 = (sh['om'] + A / I) / (1 + B / I)
            sh['om'] = om2
            vt = om2 * Reff
            for d, (dx, dy) in enumerate(G_DIRS):
                mm = m & (dirs == d)
                if not mm.any():
                    continue
                x, y = kx[mm], ky[mm]
                if dx:
                    for fx in (x - 1, x):
                        u[fx, y] += G_TURB_COUPLE * (dx * vt - u[fx, y])
                else:
                    for fy in (y - 1, y):
                        v[x, fy] += G_TURB_COUPLE * (dy * vt - v[x, fy])

    def mist(self, up, un, vp, vn, s):
        # thin liquid (spray, fog) rides along with the gas, thick pools stay put
        liq = self.liq
        m = liq * np.clip(1 - liq / 1.5, 0, 1)
        fx = m[:-1] * up * s[:-1] + m[1:] * un * s[1:]
        fy = m[:, :-1] * vp * s[:, :-1] + m[:, 1:] * vn * s[:, 1:]
        liq[:-1] -= fx
        liq[1:] += fx
        liq[:, :-1] -= fy
        liq[:, 1:] += fy
        np.clip(liq, 0, G_LIQ_CAP, out=liq)

    def liquid_step(self, n, T):
        liq = self.liq
        h = G_IDX['H2O']
        free = ~self.solid
        liq[~free] = 0
        liq[self.ring] = 0
        if not liq.any() and n[h].max() < 1e-4:
            return
        S = n.shape[0]
        Tc = np.maximum(T, 1.0)
        nsat = np.exp(G_LAT * (1 / 373.0 - 1 / Tc)) * 293 / Tc          # steam the cell can hold at this temperature
        nh = n[h]
        C = (self.cvv @ n.reshape(S, -1)).reshape(T.shape) + G_LIQ_C * liq
        E = C * T
        cond = np.where(free, np.maximum(nh - nsat, 0) * G_PHASE, 0)
        cond = np.minimum(cond, G_LIQ_CAP - liq).clip(0)
        evap = np.where(free & (liq > 0), np.minimum(liq, np.maximum(nsat - nh, 0) * G_PHASE), 0)
        evap = np.minimum(evap, 0.5 * E / G_LAT)          # boiling can't cool the gas below half its heat
        d = cond - evap
        if d.any():
            n[h] -= d
            liq += d
            E += d * G_LAT
            C2 = (self.cvv @ n.reshape(S, -1)).reshape(T.shape) + G_LIQ_C * liq
            m = (d != 0) & (C2 > 1e-5)
            T[m] = E[m] / C2[m]
            self.active.add(h)
        np.maximum(n[h], 0, out=n[h])
        if self.gravity and liq.any():
            # water gets several quick moves per sim step: fall, slide down diagonals, then level out sideways.
            # only the part of the grid that has water in it is touched
            xs = np.flatnonzero(liq.any(1))
            ys = np.flatnonzero(liq.any(0))
            x0, x1 = max(0, xs[0] - 2), min(liq.shape[0], xs[-1] + 3)
            y0, y1 = max(0, ys[0] - 2), min(liq.shape[1], ys[-1] + 3)
            L = liq[x0:x1, y0:y1]
            F = free[x0:x1, y0:y1]
            ff = F[:, :-1] & F[:, 1:]
            fx = F[:-1] & F[1:]
            fd1 = F[:-1, :-1] & F[1:, 1:]       # down-right
            fd2 = F[1:, :-1] & F[:-1, 1:]       # down-left
            for it in range(G_LIQ_ITERS):
                amt = np.minimum(L[:, :-1], np.maximum(G_LIQ_CAP - L[:, 1:], 0)) * ff
                L[:, :-1] -= amt
                L[:, 1:] += amt
                stuck = ~F[:, 1:] | (L[:, 1:] >= G_LIQ_CAP - 0.05)
                for sx in ((1, -1) if it % 2 == 0 else (-1, 1)):
                    if sx == 1:
                        src, dst, ok = L[:-1, :-1], L[1:, 1:], fd1 & stuck[:-1]
                    else:
                        src, dst, ok = L[1:, :-1], L[:-1, 1:], fd2 & stuck[1:]
                    a2 = np.minimum(src, np.maximum(G_LIQ_CAP - dst, 0)) * 0.5 * ok
                    src -= a2
                    dst += a2
                sup = np.ones(L.shape, bool)
                sup[:, :-1] = ~F[:, 1:] | (L[:, 1:] >= G_LIQ_CAP - 0.05)
                diff = L[:-1] - L[1:]
                ok = fx & (((diff > 0) & sup[:-1]) | ((diff < 0) & sup[1:]))
                fl = 0.5 * diff * ok
                L[:-1] -= fl
                L[1:] += fl
        np.clip(liq, 0, G_LIQ_CAP, out=liq)
        liq[liq < 1e-4] = 0

    def flow_devices(self, u, v):
        # one-way valves only let flow go their way, pumps push it
        for kd, push in ((G_CHECK, False), (G_PUMP, True)):
            if kd not in self.has:
                continue
            for d, (dx, dy) in enumerate(G_DIRS):
                m = (self.kind == kd) & (self.aux == d)
                if not m.any():
                    continue
                xs, ys = np.nonzero(m)
                if dx:
                    for fx in (xs - 1, xs):
                        ok = (fx >= 0) & (fx < u.shape[0])
                        a, b = fx[ok], ys[ok]
                        u[a, b] = np.maximum(u[a, b], G_PUMP_V if push else 0) if dx > 0 \
                            else np.minimum(u[a, b], -G_PUMP_V if push else 0)
                    ok = (ys >= 0) & (ys < v.shape[1])
                    v[xs[ok], ys[ok]] = 0
                    ok = ys >= 1
                    v[xs[ok], ys[ok] - 1] = 0
                else:
                    for fy in (ys - 1, ys):
                        ok = (fy >= 0) & (fy < v.shape[1])
                        a, b = xs[ok], fy[ok]
                        v[a, b] = np.maximum(v[a, b], G_PUMP_V if push else 0) if dy > 0 \
                            else np.minimum(v[a, b], -G_PUMP_V if push else 0)
                    ok = (xs >= 0) & (xs < u.shape[0])
                    u[xs[ok], ys[ok]] = 0
                    ok = xs >= 1
                    u[xs[ok] - 1, ys[ok]] = 0

    def devices(self, n, T, sol):
        S = n.shape[0]
        ntot = n.sum(0)
        p = ntot * T / 293
        if G_FILTER in self.has:
            f = self.kind == G_FILTER
            # whatever isn't the allowed gas is pushed back out to the neighbour with the highest pressure
            best = np.full(T.shape, -1.0, np.float32)
            pick = np.full(T.shape, -1, np.int8)
            for d, (dx, dy) in enumerate(G_DIRS):
                pk = np.where(self.shift(~sol & ~f, dx, dy), self.shift(p, dx, dy), -1.0)
                better = pk > best
                best = np.where(better, pk, best)
                pick = np.where(better, d, pick).astype(np.int8)
            for d, (dx, dy) in enumerate(G_DIRS):
                m = f & (pick == d)
                if not m.any():
                    continue
                xs, ys = np.nonzero(m)
                blocked = n[:, xs, ys].copy()
                blocked[self.aux[xs, ys].astype(int), np.arange(len(xs))] = 0
                n[:, xs, ys] -= blocked
                n[:, xs + dx, ys + dy] += blocked
        if G_HEATER in self.has or G_COOLER in self.has:
            src = (self.kind == G_HEATER) | (self.kind == G_COOLER)
            tv = np.where(self.kind == G_HEATER, np.array(G_HEAT_LEVELS, np.float32)[np.clip(self.aux, 0, 4)],
                          np.array(G_COOL_LEVELS, np.float32)[np.clip(self.aux, 0, 4)])
            acc = np.zeros(T.shape, np.float32)
            cnt = np.zeros(T.shape, np.float32)
            for dx, dy in G_DIRS:
                sm = self.shift(src, dx, dy)
                acc += np.where(sm, self.shift(tv, dx, dy), 0)
                cnt += sm
            m = (cnt > 0) & ~sol & (ntot > 1e-3)
            T[m] += 0.25 * (acc[m] / cnt[m] - T[m])
        if G_SOURCE in self.has:
            for sp in np.unique(self.aux[self.kind == G_SOURCE]).tolist():
                src = (self.kind == G_SOURCE) & (self.aux == sp)
                adj = np.zeros(T.shape, bool)
                for dx, dy in G_DIRS:
                    adj |= self.shift(src, dx, dy)
                adj &= ~sol
                add = adj & (p < 4)
                n[sp][add] += G_RATE
                self.active.add(sp)
        if G_VENT in self.has:
            src = self.kind == G_VENT
            adj = np.zeros(T.shape, bool)
            for dx, dy in G_DIRS:
                adj |= self.shift(src, dx, dy)
            adj &= ~sol
            n[:, adj] *= 0.85

    def step(self):
        n, T, sol = self.n, self.T, self.solid
        ring = self.ring
        if self.open:
            sol[ring] = False
            if self.void:
                n[:, ring] = 0
            else:
                n[:, ring] = self.amb_ring
            T[ring] = 293
        else:
            sol[ring] = True
            n[:, ring] = 0
        self.age += 1
        # blocks and cracking walls work on the whole grid before the gas moves
        if self.bodies or self.shafts or self.frames or self.rbs or self.cogmask.any() or self.sensors or G_RELIEF in self.has \
                or (self.age % 4 == 0 and self.strength.any()):
            p0 = n.sum(0) * T / 293
            if self.bodies or self.shafts:
                self.move_bodies(p0)
            if self.frames:
                self.move_frames(p0)
            if self.rbs or self.cogmask.any():
                self.move_rbodies(p0)
            if self.sensors:
                self.sense(p0)
            if self.age % 4 == 0:
                self.check_breaks(p0)    # walls crack when the pressure across them is too much
            if G_RELIEF in self.has:
                self.update_relief(p0)
            sol = self.solid
            n[:, sol] = 0
        if self.glinks:
            self.links_tick()
        # only push around the gases that actually exist right now (much faster)
        if self.age % 120 == 0:
            live = n.reshape(n.shape[0], -1).max(1) > 1e-7
            self.active = set(np.nonzero(live)[0].tolist()) | ({0, 1} if self.open else set())
        idx = np.array(sorted(self.active) or [0])
        full = n
        for _sub in range(G_SUB):
            n = full[idx]
            cvv, Mv = self.cvv[idx], self.Mv[idx]
            S = n.shape[0]
            flat = n.reshape(S, -1)
            C = (cvv @ flat).reshape(T.shape)
            p = flat.sum(0).reshape(T.shape) * T / 293
            rho = (Mv @ flat).reshape(T.shape) / 29 + 0.02
            ox = ~sol[:-1] & ~sol[1:]
            oy = ~sol[:, :-1] & ~sol[:, 1:]
            u, v = self.u, self.v
            # pressure pushes the flow (capped so it can't overshoot into a checkerboard)
            ku = np.minimum(G_K / (0.5 * (rho[:-1] + rho[1:])), 0.25 / (np.maximum(p[:-1], p[1:]) + 1e-3))
            kv = np.minimum(G_K / (0.5 * (rho[:, :-1] + rho[:, 1:])), 0.25 / (np.maximum(p[:, :-1], p[:, 1:]) + 1e-3))
            if G_COLL:
                # fast flow barely feels pressure sideways, so jets keep their shape instead of ballooning at the exit
                ub = np.zeros_like(v)
                ub[1:-1] = 0.25 * (u[:-1, :-1] + u[1:, :-1] + u[:-1, 1:] + u[1:, 1:])
                vb = np.zeros_like(u)
                vb[:, 1:-1] = 0.25 * (v[:-1, :-1] + v[:-1, 1:] + v[1:, :-1] + v[1:, 1:])
                ku = ku / (1 + G_COLL * vb * vb / 0.08)
                kv = kv / (1 + G_COLL * ub * ub / 0.08)
            u += ku * (p[:-1] - p[1:])
            v += kv * (p[:, :-1] - p[:, 1:])
            if self.gravity:
                # buoyancy: gas lighter than air would be at that pressure floats, heavier sinks
                rf = 0.5 * (rho[:, :-1] + rho[:, 1:])
                pf = 0.5 * (p[:, :-1] + p[:, 1:])
                v += G_BUOY * np.clip((rf - 0.02 - pf) / rf, -3, 3) * (pf > 0.05)
            # viscosity keeps jets smooth
            uu, vv = u.copy(), v.copy()
            u[1:-1] += G_VISC * (uu[:-2] + uu[2:] - 2 * uu[1:-1])
            u[:, 1:-1] += G_VISC * (uu[:, :-2] + uu[:, 2:] - 2 * uu[:, 1:-1])
            v[1:-1] += G_VISC * (vv[:-2] + vv[2:] - 2 * vv[1:-1])
            v[:, 1:-1] += G_VISC * (vv[:, :-2] + vv[:, 2:] - 2 * vv[:, 1:-1])
            if G_ADV:
                uu, vv = u.copy(), v.copy()
                du = np.where(uu[1:-1] > 0, uu[1:-1] - uu[:-2], uu[2:] - uu[1:-1])
                u[1:-1] -= G_ADV * uu[1:-1] * du
                dv = np.where(vv[:, 1:-1] > 0, vv[:, 1:-1] - vv[:, :-2], vv[:, 2:] - vv[:, 1:-1])
                v[:, 1:-1] -= G_ADV * vv[:, 1:-1] * dv
                vbar = 0.25 * (vv[:-1, :-1] + vv[:-1, 1:] + vv[1:, :-1] + vv[1:, 1:])      # (W2-1, H2-2), v seen from the u faces
                duy = np.where(vbar > 0, uu[:, 1:-1] - uu[:, :-2], uu[:, 2:] - uu[:, 1:-1])
                u[:, 1:-1] -= G_ADV * vbar * duy
                ubar = 0.25 * (uu[:-1, :-1] + uu[1:, :-1] + uu[:-1, 1:] + uu[1:, 1:])      # (W2-2, H2-1)
                dvx = np.where(ubar > 0, vv[1:-1] - vv[:-2], vv[2:] - vv[1:-1])
                v[1:-1] -= G_ADV * ubar * dvx
            u *= G_DAMP * ox
            v *= G_DAMP * oy
            chk = (self.kind == G_CHECK) if G_CHECK in self.has else None
            if G_PUMP in self.has or chk is not None:
                self.flow_devices(u, v)
            if G_TURB in self.has and _sub == 0:
                self.turbines(u, v, p)
            np.clip(u, -G_UMAX, G_UMAX, out=u)
            np.clip(v, -G_UMAX, G_UMAX, out=v)
            # never move more than 70% of a cell out in one step
            up, un = np.maximum(u, 0), np.minimum(u, 0)
            vp, vn = np.maximum(v, 0), np.minimum(v, 0)
            out = np.zeros_like(T)
            out[:-1] += up
            out[1:] -= un
            out[:, :-1] += vp
            out[:, 1:] -= vn
            s = np.minimum(1.0, 0.95 / (out + 1e-9))
            # flux = (what leaves the left cell) - (what leaves the right cell), upwind + mixing
            if chk is not None:
                dx = G_DIFF * (ox & ~(chk[:-1] | chk[1:]))      # no backwards leaking through one-way valves
                dy = G_DIFF * (oy & ~(chk[:, :-1] | chk[:, 1:]))
            else:
                dx = G_DIFF * ox
                dy = G_DIFF * oy
            al = up * s[:-1] + dx
            ar = un * s[1:] - dx
            bl = vp * s[:, :-1] + dy
            br = vn * s[:, 1:] - dy
            exm = self.thermal() if self.has & set(G_THERM) else None
            exT = T[exm].copy() if exm is not None else None
            E = C * T
            # squeezing gas heats it, letting it expand cools it (p dV work)
            ue = up * s[:-1] + un * s[1:]
            ve = vp * s[:, :-1] + vn * s[:, 1:]
            div = np.zeros_like(T)
            div[:-1] += ue
            div[1:] -= ue
            div[:, :-1] += ve
            div[:, 1:] -= ve
            E -= G_PDV * flat.sum(0).reshape(T.shape) * T * div
            np.maximum(E, 0, out=E)
            fx = n[:, :-1] * al + n[:, 1:] * ar
            fy = n[:, :, :-1] * bl + n[:, :, 1:] * br
            hx = G_HEAT * np.minimum(C[:-1], C[1:]) * ox
            hy = G_HEAT * np.minimum(C[:, :-1], C[:, 1:]) * oy
            ex = E[:-1] * al + E[1:] * ar + hx * (T[:-1] - T[1:])
            ey = E[:, :-1] * bl + E[:, 1:] * br + hy * (T[:, :-1] - T[:, 1:])
            n[:, :-1] -= fx
            n[:, 1:] += fx
            n[:, :, :-1] -= fy
            n[:, :, 1:] += fy
            if self.liq.any():
                self.mist(up, un, vp, vn, s)
            E[:-1] -= ex
            E[1:] += ex
            E[:, :-1] -= ey
            E[:, 1:] += ey
            np.maximum(n, 0, out=n)
            C = (cvv @ n.reshape(S, -1)).reshape(T.shape)
            T[:] = np.where(C > 1e-5, E / np.maximum(C, 1e-5), 293)
            if exm is not None:
                T[exm] = exT
            full[idx] = n
        n = full
        S = n.shape[0]
        if self.has & {G_FILTER, G_HEATER, G_COOLER, G_SOURCE, G_VENT}:
            self.devices(n, T, sol)
        if G_URAN in self.has:
            self.reactor(n, T)
        if self.has & set(G_THERM):
            self.exchange(n, T)
        if self.probes:
            self.probe_tick()
        # sparks from igniters
        if self.spark_t.any():
            sm = (self.spark_t > 0) & ~sol
            T[sm] = np.maximum(T[sm], 1900)
            self.spark_t[self.spark_t > 0] -= 1
        # burning: reaction speed climbs steeply with temperature (arrhenius)
        if (T > 650).any() or n[G_IDX['C12H26']].max() > 1e-5:
            o2 = G_IDX['O2']
            for f, (nu, prods, dh, ta) in G_FUELS.items():
                fi = G_IDX[f]
                Te = T
                if f in G_COMP:
                    Te = T * np.clip(n.sum(0), 1, 60) ** G_COMP[f]
                m = (Te > 650) & (n[fi] > 1e-5) & (n[o2] > 1e-5)
                if not m.any():
                    continue
                k = np.minimum(G_BURN, G_BURN_A[f] * np.exp(-ta / np.maximum(Te, 1)))
                b = np.where(m, k * np.minimum(n[fi], n[o2] / nu), 0)
                e = (self.cvv @ n.reshape(S, -1)).reshape(T.shape) * T + b * dh * G_EFF
                n[fi] -= b
                n[o2] -= nu * b
                for pr, kk in prods.items():
                    n[G_IDX[pr]] += kk * b
                    self.active.add(G_IDX[pr])
                C = (self.cvv @ n.reshape(S, -1)).reshape(T.shape)
                T[:] = np.where(C > 1e-5, e / np.maximum(C, 1e-5), 293)
        self.liquid_step(n, T)
        T += (293 - T) * G_COOL
        if self.near_wall is None:
            w = np.zeros_like(sol)
            w[1:] |= sol[:-1]
            w[:-1] |= sol[1:]
            w[:, 1:] |= sol[:, :-1]
            w[:, :-1] |= sol[:, 1:]
            self.near_wall = w & ~sol
        T[self.near_wall] += (293 - T[self.near_wall]) * G_WALLCOOL
        np.clip(T, 20, 5000, out=T)
        n[:, sol] = 0
        if self.has & set(G_THERM):
            keep = sol & self.thermal()
            exT2 = T[keep].copy()
            T[sol] = 293
            T[keep] = exT2
        else:
            T[sol] = 293

    def render(self, view=0):
        # pressure: dark = thin, normal = gas color, high = red. hot = flame glow
        n = self.n[:, 1:-1, 1:-1]
        T = self.T[1:-1, 1:-1]
        ntot = n.sum(0)
        p = ntot * T / 293
        frac = n / np.maximum(ntot, 1e-6)
        col = np.tensordot(frac, np.array(G_COLOR, np.float32), axes=(0, 0))
        col *= (0.2 + 0.8 * np.clip(p, 0, 1) ** 0.6)[..., None]
        red = np.clip((p - 1.15) / 5, 0, 1)[..., None]
        col = col * (1 - red) + np.array([235, 40, 30], np.float32) * red
        heat = np.clip((T - 500) / 1500, 0, 1)[..., None]
        hot = np.clip((T - 1500) / 1500, 0, 1)[..., None]
        flame = np.array([255, 120, 20], np.float32) * (1 - hot) + np.array([255, 235, 170], np.float32) * hot
        col = col * (1 - heat) + flame * heat
        col[ntot < 1e-3] = (6, 8, 16)
        wl = np.clip(self.liq[1:-1, 1:-1] / 1.5, 0, 0.9)[..., None]
        col = col * (1 - wl) + np.array([45, 115, 225], np.float32) * wl
        kind = self.kind[1:-1, 1:-1]
        for i in range(1, len(G_SOLIDS)):
            col[kind == i] = G_SOLIDS[i][2]
        aux = self.aux[1:-1, 1:-1]
        gx = np.arange(kind.shape[0])[:, None]
        gy = np.arange(kind.shape[1])[None, :]
        for kd in (G_CHECK, G_PUMP, G_TURB):
            if kd in self.has:
                for d, (dx, dy) in enumerate(G_DIRS):
                    m = (kind == kd) & (aux == d) & (((gx * dx + gy * dy) % 3) == 0)
                    col[m] = np.minimum(255, col[m] * 1.5 + 30)
        if G_FILTER in self.has or G_SOURCE in self.has:
            gc = np.array(G_COLOR, np.float32)
            for kd in (G_FILTER, G_SOURCE):
                m = kind == kd
                if m.any():
                    col[m] = np.minimum(255, gc[aux[m].astype(int)] * 1.6 + 40)
        if G_HEATER in self.has or G_COOLER in self.has:
            for kd, base in ((G_HEATER, (255, 70, 20)), (G_COOLER, (30, 140, 255))):
                m = kind == kd
                if m.any():
                    col[m] = np.array(base, np.float32) * (0.45 + 0.14 * np.clip(aux[m], 0, 4))[:, None]
        col[self.valve_open[1:-1, 1:-1]] = G_VALVE_OPEN
        col[self.relief_open[1:-1, 1:-1]] = (240, 170, 210)
        if self.has & set(G_THERM):
            m = kind == G_EXCH
            tt = np.clip((self.T[1:-1, 1:-1][m] - 293) / 600, -1, 1)[:, None]
            base = np.array(G_SOLIDS[G_EXCH][2], np.float32)
            col[m] = np.where(tt > 0, base * (1 - tt) + np.array([255, 90, 40], np.float32) * tt,
                              base * (1 + tt) + np.array([40, 120, 255], np.float32) * -tt)
        if G_URAN in self.has:
            ph = np.clip(self.phi[1:-1, 1:-1] * 0.35, 0, 1)
            Ti = self.T[1:-1, 1:-1]
            lw = np.clip(self.liq[1:-1, 1:-1] / 1.0, 0, 1)
            col += np.array([20, 70, 255], np.float32) * (ph * lw * 0.9)[..., None]       # cherenkov glow in water
            m = kind == G_URAN
            if m.any():
                base = np.array(G_SOLIDS[G_URAN][2], np.float32)
                g = np.clip((Ti[m] - 600) / 1800, 0, 1)[:, None]
                glow = np.array([255, 150, 40], np.float32) * (1 - g) + np.array([255, 245, 200], np.float32) * g
                k = np.clip(ph[m] * 0.6 + g[:, 0], 0, 1)[:, None]
                col[m] = base * (1 - k) + glow * k + 25
        if G_CTRL in self.has:
            m = kind == G_CTRL
            if m.any():
                lv = np.where(self.scram[1:-1, 1:-1], 4, aux).astype(np.float32)[m]
                col[m] = np.array([200, 200, 90], np.float32) * (0.2 + 0.18 * lv)[:, None] * 0.6 + np.array([40, 42, 55], np.float32)
                hot = np.clip((self.T[1:-1, 1:-1][m] - 600) / 1500, 0, 1)[:, None]
                col[m] = col[m] * (1 - hot) + np.array([255, 120, 40], np.float32) * hot
        col[self.cogmask[1:-1, 1:-1]] = (70, 78, 100)      # cog body, the drawn outline goes on top
        for rb in self.rbs:
            col[rb['cx'] - 1, rb['cy'] - 1] = rb['col'][rb['ci']]
        for (x, y), sn in self.sensors.items():
            c = G_SENSOR_COLOR[sn['type']]
            col[x - 1, y - 1] = tuple(min(255, v + 90) for v in c) if sn['on'] else c
        for b in self.bodies:
            x, y, w, h = b['x'] - 1, b['y'] - 1, b['w'], b['h']
            col[x:x + w, y:y + h] = G_BLOCK_EDGE
            if w > 2 and h > 2:
                col[x + 1:x + w - 1, y + 1:y + h - 1] = G_BLOCK_COLOR
        if view:
            gm = ~self.solid[1:-1, 1:-1] & (kind == 0) & ~self.cogmask[1:-1, 1:-1]
            if view == 1:
                v = np.clip((np.log2(np.maximum(p, 1e-3)) + 3) / 9, 0, 1)         # 0.125 atm .. 64 atm
                col = np.where(gm[..., None], ramp(v, G_RAMP_P), col)
            elif view == 2:
                v = np.clip((T - 200) / 4800, 0, 1) ** 0.7
                col = np.where(gm[..., None], ramp(v, G_RAMP_T), col)
            else:
                uu, vv = self.u, self.v
                uc = 0.5 * (uu[:-1] + uu[1:])[:, 1:-1]
                vc = 0.5 * (vv[:, :-1] + vv[:, 1:])[1:-1]
                v = np.clip(np.hypot(uc, vc) / G_UMAX, 0, 1) ** 0.6
                col = np.where(gm[..., None], ramp(v, G_RAMP_S), col)
            col[gm & (ntot < 1e-3)] = (6, 8, 16)
        return np.clip(col, 0, 255).astype(np.uint8)

    def info(self, cx, cy):
        x, y = cx + 1, cy + 1
        if self.kind[x, y]:
            name, st, _ = G_SOLIDS[int(self.kind[x, y])]
            if self.kind[x, y] == G_SENSOR:
                sn = self.sensors.get((x, y))
                if sn:
                    st_ = 'ON' if sn['on'] else 'off'
                    if sn['type'] == 'timer':
                        per = G_TIMER_PERIODS[sn['level']]
                        return f"timer, on {int(per * G_TIMER_DUTY[sn['dir'] % 4])} of every {per} steps, {st_} (click = period, ctrl+click = on time)"
                    if sn['type'] == 'hinge':
                        return f"hinge sensor, looks {G_DIR_NAMES[sn['dir']]} {G_SENSE_RANGE} cells, {st_}"
                    if sn['type'] == 'block':
                        return f"block sensor, looks {G_DIR_NAMES[sn['dir']]} {G_SENSE_RANGE} cells, {st_}"
                    if sn['type'] == 'temp':
                        return f"temp sensor, on above {G_TEMP_LEVELS[sn['level']]}C, {st_}"
                    return f"pressure sensor, on above {G_PRES_LEVELS[sn['level']]} atm, {st_}"
            if self.kind[x, y] >= G_FILTER:
                return self.describe(x, y)
            linked = '  (linked to a sensor)' if self.link[x, y] >= 0 else ''
            if self.kind[x, y] == G_VALVE:
                return 'valve ' + ('open' if self.valve_open[x, y] else
                                   'closed' + (linked or ', hold p to open'))
            if self.kind[x, y] == G_IGNITER:
                return 'igniter' + (linked.strip() and ' ' + linked.strip() or ', e to spark')
            return name.lower() + (f'  holds {st:.0f} atm/cell' if st else '  unbreakable')
        if self.cogmask[x, y]:
            return 'cog'
        if self.solid[x, y]:
            return 'block'
        n = self.n[:, x, y]
        tot = float(n.sum())
        wtxt = f'water {float(self.liq[x, y]):.1f}  ' if self.liq[x, y] > 0.05 else ''
        if tot < 1e-3:
            return wtxt + 'vacuum'
        p = tot * float(self.T[x, y]) / 293
        parts = sorted(((float(a) / tot, G_NICE[s]) for s, a in zip(G_SPECIES, n)), reverse=True)
        mix = ' '.join(f'{name} {f * 100:.0f}%' for f, name in parts[:3] if f > 0.03)
        return wtxt + f'{p:.2f} atm  {float(self.T[x, y]) - 273:.0f}C  {mix}'

    def save(self, path):
        tmp = path + '.tmp'
        bodies = np.array([[b['x'], b['y'], b['w'], b['h'], b['vx'], b['vy']] for b in self.bodies],
                          np.float32).reshape(-1, 6)
        with open(tmp, 'wb') as f:
            sens = np.array([[x, y, G_SENSOR_KINDS.index(v['type']), v['dir'], v['level']]
                             for (x, y), v in self.sensors.items()], np.int32).reshape(-1, 5)
            np.savez_compressed(f, n=self.n, T=self.T, kind=self.kind, strength=self.strength,
                                made_by=np.array(AUTHOR), bodies=bodies, open=np.array(self.open), void=np.array(self.void),
                                probes=np.array(list(self.probes), np.int32).reshape(-1, 2), gravity=np.array(self.gravity),
                                sensors=sens, link=self.link, aux=self.aux, liq=self.liq, phi=self.phi, decay=self.decay,
                                shafts=np.array([[q['x'], q['y'], q['R'], q['th'], q['om'], q.get('teeth', 0), q.get('tl', 0),
                                                  int(bool(q.get('wheel')))]
                                                 for q in self.shafts], np.float64).reshape(-1, 8),
                                chains=np.array([[self.shafts.index(m['a']), self.shafts.index(m['b']), m['k']]
                                                 for m in self.chains if m['a'] in self.shafts and m['b'] in self.shafts],
                                                np.float64).reshape(-1, 3),
                                wx=np.array(self.wx),
                                frames=np.array([[f['x0'], f['y0'], f['w'], f['h'], f['fx'], f['fy'], f['vx'], f['vy']]
                                                 for f in self.frames], np.float64).reshape(-1, 8),
                                rb_meta=np.array([[rb['x'], rb['y'], rb['th'], rb['vx'], rb['vy'], rb['om'], rb['cmx'], rb['cmy'], rb['gw'], rb['gh']]
                                                  for rb in self.rbs], np.float64).reshape(-1, 10),
                                rb_cells=np.array([row for k, rb in enumerate(self.rbs) for row in self.rb_rows(k, rb)],
                                                  np.int32).reshape(-1, 5),
                                meshes=np.array([[self.shafts.index(m['a']), self.shafts.index(m['b']), m['k']]
                                                 for m in self.meshes], np.float64).reshape(-1, 3),
                                hinges=np.array([[int(h['kind'] == 'shaft'),
                                                  (self.shafts if h['kind'] == 'shaft' else self.bodies).index(h['ref']),
                                                  h['ox'], h['oy'], h['cx'], h['cy']] for h in self.hinges],
                                                np.float64).reshape(-1, 6),
                                rods=np.array([[self.hinges.index(r['a']), self.hinges.index(r['b']), r['L']]
                                               for r in self.rods], np.float64).reshape(-1, 3),
                                glinks=np.array([[x, y, v['id'], v['tgt'][0] if v['tgt'] else -1,
                                                  v['tgt'][1] if v['tgt'] else -1, int(v['role'] == 'rx')]
                                                 for (x, y), v in self.glinks.items()], np.int32).reshape(-1, 6))
        os.replace(tmp, path)

    def load(self, path):
        with np.load(path) as d:
            if d['n'].shape[1:] != self.n.shape[1:]:
                return
            self.n[:] = 0
            self.n[:d['n'].shape[0]] = d['n'][:self.n.shape[0]]      # older saves have fewer gases
            self.T[:] = d['T']
            if 'kind' in d:
                self.kind[:] = d['kind']
                self.strength[:] = d['strength']
                self.strength[np.isin(self.kind, G_TOUGH)] = 0
            else:       # first gas lab version: plain walls + igniters
                self.kind[:] = np.where(d['solid'], G_WALL, 0)
                self.kind[d['ign']] = G_IGNITER
                self.strength[:] = np.array([0] + [s[1] for s in G_SOLIDS[1:]], np.float32)[self.kind]
            self.bodies = []
            if 'bodies' in d:
                for x, y, w, h, vx, vy in d['bodies'].tolist():
                    self.bodies.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), vx=vx, vy=vy,
                                            fx=0.0, fy=0.0))
            self.sensors = {}
            if 'sensors' in d:
                for x, y, t, dr, lv in d['sensors'].tolist():
                    self.sensors[(x, y)] = dict(type=G_SENSOR_KINDS[t], dir=dr, level=lv, on=False)
                self.link[:] = d['link']
            self.shafts, self.hinges, self.rods, self.meshes = [], [], [], []
            self.chains, self.frames, self.rbs = [], [], []
            self.wx = int(d['wx']) if 'wx' in d else 0
            self.cogmask[:] = False
            if 'rb_meta' in d:
                self.load_rbs(d['rb_meta'], d['rb_cells'])
            if 'shafts' in d:
                for row in d['shafts'].tolist():
                    x, y, R, th, om = row[:5]
                    q = dict(x=x, y=y, R=R, th=th, om=om)
                    if len(row) > 5 and row[5]:
                        q['teeth'], q['tl'] = int(row[5]), row[6]
                    if len(row) > 7 and row[7]:
                        q['wheel'] = True
                    self.shafts.append(q)
                if 'chains' in d:
                    for ia, ib, k in d['chains'].tolist():
                        if int(ia) < len(self.shafts) and int(ib) < len(self.shafts):
                            self.chains.append(dict(a=self.shafts[int(ia)], b=self.shafts[int(ib)], k=k))
                if 'frames' in d:
                    for x0_, y0_, w_, h_, fx_, fy_, vx_, vy_ in d['frames'].tolist():
                        self.frames.append(dict(x0=int(x0_), y0=int(y0_), w=int(w_), h=int(h_), fx=fx_, fy=fy_, vx=vx_, vy=vy_))
                if 'meshes' in d:
                    for ia, ib, k in d['meshes'].tolist():
                        if int(ia) < len(self.shafts) and int(ib) < len(self.shafts):
                            self.meshes.append(dict(a=self.shafts[int(ia)], b=self.shafts[int(ib)], k=k))
                for kd, ri, ox, oy, cx, cy in d['hinges'].tolist():
                    lst = self.shafts if kd else self.bodies
                    if int(ri) < len(lst):
                        self.hinges.append(dict(kind='shaft' if kd else 'body', ref=lst[int(ri)],
                                                ox=ox, oy=oy, cx=float(cx), cy=float(cy)))
                    else:
                        self.hinges.append(None)
                for a_, b_, L in d['rods'].tolist():
                    ha, hb = self.hinges[int(a_)], self.hinges[int(b_)]
                    if ha and hb:
                        self.rods.append(dict(a=ha, b=hb, L=L))
                self.hinges = [h for h in self.hinges if h]
            self.aux[:] = d['aux'] if 'aux' in d else 0
            self.liq[:] = d['liq'] if 'liq' in d else 0
            self.phi[:] = d['phi'] if 'phi' in d else 0
            self.decay[:] = d['decay'] if 'decay' in d else 0
            self.scram[:] = False
            self.relief_open[:] = False
            self.glinks = {}
            if 'glinks' in d:
                for x, y, lid, tx_, ty_, rx_ in d['glinks'].tolist():
                    self.glinks[(x, y)] = dict(id=lid, tgt=(tx_, ty_) if tx_ >= 0 else None,
                                               role='rx' if rx_ else 'tx', on=False)
            self.comp_cache = {}
            self.open = bool(d['open'])
            self.void = bool(d['void']) if 'void' in d else False
            self.probes = {}
            if 'probes' in d:
                for px_, py_ in d['probes'].tolist():
                    self.probes[(px_, py_)] = self.new_probe()
            if 'gravity' in d:
                self.gravity = bool(d['gravity'])
            self.update_ambient()
            self.rebuild()
            live = self.n.reshape(self.n.shape[0], -1).max(1) > 1e-7
            self.active = set(np.nonzero(live)[0].tolist()) | {0, 1}


class GasMode:
    # the gas lab screen: same window, tab flips between this and the circuits
    def __init__(self, app):
        if not credits_ok():
            raise SystemExit
        self.app = app
        self.view = 0               # 0 normal, 1 pressure, 2 temperature, 3 speed
        self.smooth = True          # blend the gas colors between cells (looks finer, walls stay sharp)
        self.zcs = None             # zoomed cell size in pixels, None = fit the window
        self.panx = self.pany = None
        self.pan_from = None
        self.fit = 1
        self.sim = GasSim()
        self.tool = 'BRUSH'
        self.mat = 'WALL'
        self.size = 2
        self.speed = 8          # sim steps per frame
        self.paused = False
        self.drag = None
        self.dirty = False
        self.last_save = time.time()
        self.path = os.path.join(os.path.dirname(save_path()), 'gas.npz')
        self.world_path = os.path.join(os.path.dirname(save_path()), 'gas_world.bin')
        self.cs, self.x0, self.y0 = 5, 0, TOPH
        self.view_rect = pygame.Rect(0, TOPH, 800, 600)
        self.right_rect = pygame.Rect(800, TOPH, RPW, 600)
        self.search, self.search_focus, self.pal_scroll, self.help_open = '', False, 0, False
        self.cat_open = {}
        self.icons = {}
        self.link_sensor = None     # sensor that new valves / igniters get hooked to
        self.link_target = None     # sensor / valve / igniter that the next LINK cell connects to
        self.link_id = 1
        self.rod_first = None       # first hinge of a rod being placed
        self.chain_first = None     # first shaft of a chain being placed
        self.rb_spr = {}            # pictures of spinning bodies
        self.slide, self.slide_dir, self.slide_img = 0.0, 0, None      # camera glide after the world scrolls
        self.sym = 0                # mirror drawing: 0 off, 1 left/right, 2 up/down, 3 both
        self.cog_prev = None        # cog being sized: base chosen, now picking tooth length
        self.sel = None             # SELECT tool rectangle (cell corners)
        self.clip = None
        self.pasting = False
        self.pins = []              # cells with a live readout
        self.hist = {}              # pinned cell -> recent (pressure, temp) for the graphs
        self.hist_n = 0
        self.sps, self._steps, self._t0 = 240.0, 0, time.time()
        self.mat_scroll = 0
        self.list_bottom = 560
        try:
            if os.path.exists(self.path):
                self.sim.load(self.path)
                self.sim.load_world(self.world_path)
        except Exception:
            try:
                os.replace(self.path, self.path + '.bad')
            except OSError:
                pass

    # layout
    def layout(self, W, H):
        rp = min(RPW, max(170, W // 3))
        self.view_rect = vr = pygame.Rect(0, TOPH, W - rp, H - TOPH)
        self.right_rect = pygame.Rect(W - rp, TOPH, rp, H - TOPH)
        fit = max(1, min(vr.w // GW, vr.h // GH))
        self.fit = fit
        if self.zcs is not None and self.zcs <= fit:
            self.zcs = None
        if self.zcs is None:
            self.cs = fit
            self.panx = self.pany = None
        else:
            self.cs = self.zcs
        gw, gh = GW * self.cs, GH * self.cs
        if self.panx is None:
            self.panx = vr.x + (vr.w - gw) // 2
            self.pany = vr.y + (vr.h - gh) // 2
        # the grid can't be dragged away from the view
        self.panx = max(vr.right - gw, min(vr.x, self.panx)) if gw > vr.w else vr.x + (vr.w - gw) // 2
        self.pany = max(vr.bottom - gh, min(vr.y, self.pany)) if gh > vr.h else vr.y + (vr.h - gh) // 2
        self.x0, self.y0 = self.panx, self.pany

    def zoom_at(self, pos, steps):
        # ctrl + wheel: zoom in on the cell under the mouse
        old = self.cs
        new = max(self.fit, min(40, old + steps * max(1, old // 5)))
        if new == old:
            return
        fx, fy = (pos[0] - self.x0) / old, (pos[1] - self.y0) / old
        self.zcs = None if new <= self.fit else new
        self.cs = new
        self.panx = int(pos[0] - fx * new)
        self.pany = int(pos[1] - fy * new)

    def cell(self, pos, clamp=True):
        cx = (pos[0] - self.x0) // self.cs
        cy = (pos[1] - self.y0) // self.cs
        if clamp:
            return (max(0, min(GW - 1, cx)), max(0, min(GH - 1, cy)))
        return (cx, cy) if 0 <= cx < GW and 0 <= cy < GH else None

    # ------------------------------------------------------------ chrome: top bar, tools + materials panel, selection bar
    def in_view(self, pos):
        return self.view_rect.collidepoint(pos) and not self.right_rect.collidepoint(pos)

    def mat_nice(self, m):
        if any(ch.isdigit() for ch in m) or m in ('CO', 'CO2', 'SF6', 'LINK'):
            return m
        return m.title()

    def mat_cats(self):
        q = self.search.strip().lower()
        out = []
        for name, ms in G_CATS:
            if q:
                ms = [m for m in ms if q in m.lower() or q in self.mat_nice(m).lower()]
                if not ms:
                    continue
            out.append((name, ms))
        return out

    def pal_rows(self, rp):
        q = self.search.strip()
        pad, gap = 10, 8
        tw = (rp.w - 2 * pad - gap) // 2
        th = 62
        rows, y = [], 0
        for name, ms in self.mat_cats():
            op = True if q else self.cat_open.get(name, True)
            rows.append(dict(t='hdr', cat=name, n=len(ms), open=op, rect=pygame.Rect(pad, y, rp.w - 2 * pad, 28)))
            y += 30
            if op:
                for i, m in enumerate(ms):
                    rows.append(dict(t='tile', mat=m, rect=pygame.Rect(pad + (i % 2) * (tw + gap), y + (i // 2) * (th + gap), tw, th)))
                y += -(-len(ms) // 2) * (th + gap)
            y += 4
        return rows, y

    def g_geom(self):
        rp = self.right_rect
        pad = 10
        tw = (rp.w - 2 * pad - 12) // 3
        tools = [(pygame.Rect(rp.x + pad + (i % 3) * (tw + 6), rp.y + 40 + (i // 3) * 36, tw, 30), t) for i, t in enumerate(G_TOOLS)]
        sy = rp.y + 40 + 2 * 36 + 4
        size = (pygame.Rect(rp.right - pad - 28 * 2 - 40, sy, 28, 26), pygame.Rect(rp.right - pad - 28 - 40, sy, 40, 26),
                pygame.Rect(rp.right - pad - 28, sy, 28, 26))
        search = pygame.Rect(rp.x + pad, sy + 34, rp.w - 2 * pad, 28)
        area = pygame.Rect(rp.x, search.bottom + 8, rp.w, rp.bottom - search.bottom - 8 - 24)
        return tools, size, search, area

    def pal_clamp(self):
        rows, total = self.pal_rows(self.right_rect)
        _, _, _, area = self.g_geom()
        self.pal_scroll = max(0, min(max(0, total - area.h), self.pal_scroll))
        return rows, total

    def g_top(self, W):
        y, h = 7, 30
        compact = W < 1180
        x0 = 10 if W < 940 else 176
        b = [(pygame.Rect(x0, y, 84, h), 'tab_circuit', 'Circuits', 'seg'),
             (pygame.Rect(x0 + 84, y, 84, h), 'noop', 'Gas lab', 'seg_on')]
        x = x0 + 190
        b.append((pygame.Rect(x, y, 34, h), 'pause', '', 'pause'))
        x += 40
        b.append((pygame.Rect(x, y, 34, h), 'step', '', 'step'))
        x += 46
        b.append((pygame.Rect(x, y, 28, h), 'speed-', '', 'minus'))
        b.append((pygame.Rect(x + 28, y, 50, h), 'noop', f'x{self.speed}', 'label'))
        b.append((pygame.Rect(x + 78, y, 28, h), 'speed+', '', 'plus'))
        x += 118
        sim = self.sim
        edge = 'void' if sim.void else 'air' if sim.open else 'closed'
        items = [('gravity', 'Gravity' if not compact else 'Grav', 78 if not compact else 56),
                 ('edges', f'Edges: {edge}' if not compact else edge.title(), 118 if not compact else 64),
                 ('smooth', 'Smooth', 70),
                 ('view', f'View: {G_VIEWS[self.view]}' if not compact else G_VIEWS[self.view].title(), 132 if not compact else 92)]
        lim = W - 60
        for act, lab, w in items:
            if x + w > lim:
                break
            b.append((pygame.Rect(x, y, w, h), act, lab, 'toggle'))
            x += w + 6
        b.append((pygame.Rect(W - 14 - 34, y, 34, h), 'help', '', 'help'))
        return b

    def g_action(self, act):
        sim = self.sim
        if act == 'tab_circuit':
            self.save()
            self.app.mode = 'circuit'
        elif act == 'pause':
            self.paused = not self.paused
        elif act == 'step':
            if not self.paused:
                self.paused = True
            sim.step()
            sim.move_debris(1, 1 / 60)
        elif act == 'speed-':
            self.speed = max(1, self.speed // 2)
        elif act == 'speed+':
            self.speed = min(32, self.speed * 2)
        elif act == 'gravity':
            sim.gravity = not sim.gravity
            sim.update_ambient()
            self.dirty = True
        elif act == 'edges':
            if sim.open and not sim.void:
                sim.open = False
            elif not sim.open:
                sim.open, sim.void = True, True
            else:
                sim.void = False
            self.dirty = True
        elif act == 'smooth':
            self.smooth = not self.smooth
        elif act == 'view':
            self.view = (self.view + 1) % len(G_VIEWS)
        elif act == 'help':
            self.help_open = not self.help_open
        elif act == 'phys':
            self.toggle_physics()
        elif act == 'copy':
            (ax, ay), (bx, by) = self.sel
            self.clip = sim.copy_region(ax + 1, ay + 1, bx + 1, by + 1)
            self.app.say(f"copied {self.clip['w']} x {self.clip['h']}, ctrl+v to paste")
        elif act == 'delete':
            self.delete_selection()

    def start_slide(self, d):
        try:
            self.slide_img = pygame.display.get_surface().subsurface(self.view_rect).copy()
            self.slide, self.slide_dir = 1.0, d
        except (pygame.error, ValueError):
            self.slide_img = None

    def world_scroll(self, d):
        err = self.sim.scroll_world(d)
        if err:
            self.app.say(err)
            return False
        self.start_slide(d)
        amt = G_SLAB * d
        self.sel = None
        self.drag = None
        self.pasting = False
        self.pins = [(x - amt, y) for (x, y) in self.pins if 0 <= x - amt < GW]
        self.hist = {}
        self.dirty = True
        return True

    def edge_buttons(self):
        vr = self.view_rect
        return [(pygame.Rect(vr.x + 6, vr.centery - 30, 26, 60), -1), (pygame.Rect(vr.right - 32, vr.centery - 30, 26, 60), 1)]

    def delete_selection(self):
        if not self.sel:
            return
        mask = self.rect_mask(self.sel[0], self.sel[1], False)
        self.sim.erase(mask)
        self.dirty = True

    def select_mat(self, m):
        self.mat = m
        if self.tool in ('SELECT', 'ERASE'):
            self.tool = 'BRUSH'
        if m not in ('VALVE', 'IGNITER', 'CONTROL ROD'):
            self.link_sensor = None
        if m != 'LINK':
            self.link_target = None
        if m != 'ROD':
            self.rod_first = None
        if m != 'CHAIN':
            self.chain_first = None

    def sel_buttons(self):
        if not self.sel or self.pasting:
            return []
        (ax, ay), (bx, by) = self.sel
        cs = self.cs
        r = pygame.Rect(self.x0 + min(ax, bx) * cs, self.y0 + min(ay, by) * cs, (abs(bx - ax) + 1) * cs, (abs(by - ay) + 1) * cs)
        items = [('phys', 'Physics  R', 100), ('copy', 'Copy', 56), ('delete', 'Delete', 62)]
        tw = sum(w for _, _, w in items) + 6 * (len(items) - 1)
        vr = self.view_rect
        x = max(vr.x + 4, min(vr.right - tw - 4, r.centerx - tw // 2))
        y = r.y - 38
        if y < vr.y + 4:
            y = min(vr.bottom - 36, r.bottom + 8)
        out = []
        for act, lab, w in items:
            out.append((pygame.Rect(x, y, w, 28), act, lab))
            x += w + 6
        return out

    def chrome_event(self, e):
        W, H = pygame.display.get_surface().get_size()
        mp = getattr(e, 'pos', None) or pygame.mouse.get_pos()
        if e.type == pygame.KEYDOWN and self.search_focus:
            k = e.key
            if k in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.search_focus = False
            elif k == pygame.K_BACKSPACE:
                self.search = self.search[:-1]
            elif e.unicode and e.unicode.isprintable() and len(self.search) < 24:
                self.search += e.unicode
            self.pal_scroll = 0
            return True
        if e.type == pygame.KEYDOWN and e.key == pygame.K_f and (e.mod & pygame.KMOD_CTRL):
            self.search_focus = True
            return True
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and self.help_open:
            self.help_open = False
            return True
        if self.help_open and e.type == pygame.MOUSEBUTTONDOWN:
            self.help_open = False
            return True
        if e.type == pygame.MOUSEWHEEL and self.right_rect.collidepoint(pygame.mouse.get_pos()):
            self.pal_scroll -= e.y * 48
            self.pal_clamp()
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for r, act, lab, kind in self.g_top(W):
                if r.collidepoint(e.pos) and act != 'noop':
                    self.g_action(act)
                    return True
            if e.pos[1] < TOPH:
                return True
            for r, d_ in self.edge_buttons():
                if r.collidepoint(e.pos) and self.view_rect.collidepoint(e.pos):
                    self.world_scroll(d_)
                    return True
            for r, act, lab in self.sel_buttons():
                if r.collidepoint(e.pos):
                    self.g_action(act)
                    return True
            if self.right_rect.collidepoint(e.pos):
                tools, size, search, area = self.g_geom()
                self.search_focus = False
                for r, t in tools:
                    if r.collidepoint(e.pos):
                        self.tool = t
                        return True
                if size[0].collidepoint(e.pos):
                    self.size = max(0, self.size - 1)
                elif size[2].collidepoint(e.pos):
                    self.size = min(36, self.size + 1)
                elif search.collidepoint(e.pos):
                    self.search_focus = True
                elif area.collidepoint(e.pos):
                    rows, _ = self.pal_clamp()
                    for row in rows:
                        r = row['rect'].move(area.x, area.y - self.pal_scroll)
                        if r.collidepoint(e.pos):
                            if row['t'] == 'hdr':
                                self.cat_open[row['cat']] = not row['open']
                            else:
                                self.select_mat(row['mat'])
                            break
                return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 3 and self.right_rect.collidepoint(e.pos):
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and self.right_rect.collidepoint(e.pos):
            return True
        return False

    def mat_color(self, m):
        comp = dict(G_MATS).get(m)
        if m in G_SENSOR_TYPES:
            return G_SENSOR_COLOR[G_SENSOR_TYPES[m]]
        if m == 'LINK':
            return G_SOLIDS[G_LINK][2]
        if m == 'THRUST PROBE':
            return (255, 170, 60)
        if m == 'WATER':
            return (60, 130, 230)
        if m in G_MECH:
            return (200, 204, 214)
        if comp:
            sw = tuple(int(sum(G_COLOR[G_IDX[s_]][ch] * f for s_, f in comp.items()) * 1.4) for ch in range(3))
            return tuple(min(255, x) for x in sw)
        if m in G_SOLID_MATS:
            return G_SOLIDS[G_SOLID_MATS[m]][2]
        return G_BLOCK_COLOR if m == 'BLOCK' else (90, 96, 120)

    def mat_icon(self, m, w, h):
        key = (m, w, h, id(PANEL))
        ic = self.icons.get(key)
        if ic is not None:
            return ic
        ic = pygame.Surface((w, h), pygame.SRCALPHA)
        col = self.mat_color(m)
        dark = tuple(int(v * 0.55) for v in col)
        cx, cy = w // 2, h // 2
        if m in G_SOLID_MATS or m == 'BLOCK':
            r = pygame.Rect(0, 0, 34, 26)
            r.center = (cx, cy)
            pygame.draw.rect(ic, col, r, border_radius=5)
            pygame.draw.rect(ic, dark, r, 2, border_radius=5)
            if m in ('VALVE', 'RELIEF VALVE'):
                pygame.draw.polygon(ic, dark, [(cx - 8, cy - 7), (cx, cy), (cx - 8, cy + 7)])
                pygame.draw.polygon(ic, dark, [(cx + 8, cy - 7), (cx, cy), (cx + 8, cy + 7)])
            elif m in ('PUMP', 'CHECK VALVE'):
                pygame.draw.polygon(ic, dark, [(cx - 7, cy - 7), (cx + 8, cy), (cx - 7, cy + 7)])
            elif m == 'FILTER':
                for dx in (-8, 0, 8):
                    pygame.draw.line(ic, dark, (cx + dx, cy - 8), (cx + dx, cy + 8), 2)
            elif m in ('HEATER', 'COOLER'):
                for dx in (-8, 0, 8):
                    pygame.draw.lines(ic, dark, False, [(cx + dx, cy - 8), (cx + dx + 3, cy - 3), (cx + dx - 3, cy + 3), (cx + dx, cy + 8)], 2)
            elif m == 'IGNITER':
                pygame.draw.polygon(ic, dark, [(cx + 2, cy - 9), (cx - 6, cy + 2), (cx, cy + 2), (cx - 3, cy + 9), (cx + 7, cy - 2), (cx + 1, cy - 2)])
            elif m == 'TURBINE':
                for a_ in range(3):
                    an = a_ * 2.09
                    pygame.draw.line(ic, dark, (cx, cy), (cx + 10 * math.cos(an), cy + 10 * math.sin(an)), 3)
            elif m == 'URANIUM':
                pygame.draw.circle(ic, dark, (cx, cy), 7, 2)
                pygame.draw.circle(ic, dark, (cx, cy), 2)
            elif m == 'SOURCE':
                pygame.draw.circle(ic, dark, (cx, cy), 7, 2)
                pygame.draw.line(ic, dark, (cx, cy - 4), (cx, cy + 4), 2)
                pygame.draw.line(ic, dark, (cx - 4, cy), (cx + 4, cy), 2)
        elif m in G_MECH:
            if m in ('SHAFT', 'WHEEL', 'COG'):
                if m == 'WHEEL':
                    pygame.draw.circle(ic, (24, 24, 30), (cx, cy), 15)
                    pygame.draw.circle(ic, (90, 90, 104), (cx, cy), 15, 2)
                if m == 'COG':
                    for k in range(8):
                        an = k * math.pi / 4
                        pygame.draw.circle(ic, col, (cx + 12 * math.cos(an), cy + 12 * math.sin(an)), 3)
                pygame.draw.circle(ic, (52, 58, 76), (cx, cy), 10)
                pygame.draw.circle(ic, col, (cx, cy), 10, 2)
                for k in range(4):
                    an = k * math.pi / 2
                    pygame.draw.line(ic, (90, 98, 120), (cx, cy), (cx + 9 * math.cos(an), cy + 9 * math.sin(an)), 1)
                pygame.draw.circle(ic, col, (cx, cy), 2)
            elif m == 'HINGE':
                pygame.draw.circle(ic, (20, 22, 28), (cx, cy), 8)
                pygame.draw.circle(ic, (235, 235, 245), (cx, cy), 5)
            elif m == 'ROD':
                pygame.draw.line(ic, (30, 32, 40), (cx - 16, cy + 6), (cx + 16, cy - 6), 7)
                pygame.draw.line(ic, col, (cx - 16, cy + 6), (cx + 16, cy - 6), 3)
                for px, py in ((cx - 16, cy + 6), (cx + 16, cy - 6)):
                    pygame.draw.circle(ic, (235, 235, 245), (px, py), 4)
            elif m == 'CHAIN':
                pygame.draw.circle(ic, (52, 58, 76), (cx - 12, cy), 7)
                pygame.draw.circle(ic, (52, 58, 76), (cx + 12, cy), 5)
                for sg in (-1, 1):
                    pygame.draw.line(ic, (24, 26, 32), (cx - 12, cy + sg * 7), (cx + 12, cy + sg * 5), 4)
                    for t in range(5):
                        pygame.draw.circle(ic, (210, 214, 224), (cx - 10 + t * 5, cy + sg * (7 - t * 0.5)), 1)
        elif m in G_SENSOR_TYPES or m in ('LINK', 'THRUST PROBE'):
            pygame.draw.circle(ic, col, (cx, cy), 12)
            pygame.draw.circle(ic, dark, (cx, cy), 12, 2)
            pygame.draw.circle(ic, dark, (cx, cy), 4)
            if m == 'THRUST PROBE':
                pygame.draw.line(ic, dark, (cx, cy), (cx + 14, cy - 8), 2)
        elif m == 'VACUUM':
            for k in range(12):
                an = k * math.pi / 6
                pygame.draw.circle(ic, TEXT_DIM, (cx + 12 * math.cos(an), cy + 12 * math.sin(an)), 1)
        elif m == 'WATER':
            for k in range(3):
                pts = [(cx - 16 + i * 4, cy - 8 + k * 8 + (3 if i % 2 else 0)) for i in range(9)]
                pygame.draw.lines(ic, col, False, pts, 3)
        else:
            comp = dict(G_MATS).get(m) or {}
            cols = [G_COLOR[G_IDX[s_]] for s_ in comp] or [col]
            for i, (ox, oy, rr) in enumerate(((-9, 3, 10), (8, 4, 9), (0, -6, 10))):
                c_ = tuple(min(255, int(v * 1.5 + 20)) for v in cols[i % len(cols)])
                pygame.draw.circle(ic, (*c_, 200), (cx + ox, cy + oy), rr)
        self.icons[key] = ic
        return ic

    def draw_chrome(self, surf):
        W, H = surf.get_size()
        mp = pygame.mouse.get_pos()
        app = self.app
        rp = self.right_rect
        # right panel
        pygame.draw.rect(surf, PANEL, rp)
        pygame.draw.line(surf, PANEL_LINE, (rp.x, rp.y), (rp.x, rp.bottom))
        surf.blit(app.ui_h.render('Tools', True, TEXT), (rp.x + 14, rp.y + 8))
        tools, size, search, area = self.g_geom()
        for r, t in tools:
            on = t == self.tool
            hov = r.collidepoint(mp)
            pygame.draw.rect(surf, ACTIVE if on else (CARD_HI if hov else CARD), r, border_radius=8)
            pygame.draw.rect(surf, ON if on else (PART_LINE if hov else PANEL_LINE), r, 1, border_radius=8)
            s_ = app.ui.render(t.title(), True, ON if on else TEXT)
            surf.blit(s_, s_.get_rect(center=r.center))
        s_ = app.ui_s.render('brush size', True, TEXT_DIM)
        surf.blit(s_, (rp.x + 14, size[1].centery - s_.get_height() // 2))
        for r, ic in ((size[0], 'minus'), (size[2], 'plus')):
            pygame.draw.rect(surf, CARD_HI if r.collidepoint(mp) else CARD, r, border_radius=7)
            pygame.draw.rect(surf, PANEL_LINE, r, 1, border_radius=7)
            app.draw_icon(surf, ic, r, TEXT)
        s_ = app.ui.render(str(self.size), True, TEXT)
        surf.blit(s_, s_.get_rect(center=size[1].center))
        pygame.draw.rect(surf, BG, search, border_radius=8)
        pygame.draw.rect(surf, ON if self.search_focus else PANEL_LINE, search, 1, border_radius=8)
        if self.search or self.search_focus:
            s_ = app.ui.render(self.search + ('|' if self.search_focus and (pygame.time.get_ticks() // 450) % 2 == 0 else ''), True, TEXT)
        else:
            s_ = app.ui.render('search materials', True, TEXT_DIM)
        surf.blit(s_, (search.x + 10, search.centery - s_.get_height() // 2))
        rows, total = self.pal_clamp()
        old = surf.get_clip()
        surf.set_clip(area.clip(old))
        for row in rows:
            r = row['rect'].move(area.x, area.y - self.pal_scroll)
            if r.bottom < area.y or r.top > area.bottom:
                continue
            if row['t'] == 'hdr':
                arrow = [(r.x + 6, r.centery - 3), (r.x + 14, r.centery - 3), (r.x + 10, r.centery + 3)] if row['open'] \
                    else [(r.x + 7, r.centery - 5), (r.x + 7, r.centery + 5), (r.x + 13, r.centery)]
                pygame.draw.polygon(surf, TEXT_DIM, arrow)
                s_ = app.ui_s.render(row['cat'], True, TEXT_DIM)
                surf.blit(s_, (r.x + 22, r.centery - s_.get_height() // 2))
                n_ = app.ui_s.render(str(row['n']), True, TEXT_DIM)
                surf.blit(n_, (r.right - n_.get_width() - 4, r.centery - n_.get_height() // 2))
                continue
            m = row['mat']
            on = m == self.mat
            hov = r.collidepoint(mp) and area.collidepoint(mp)
            pygame.draw.rect(surf, ACTIVE if on else (CARD_HI if hov else CARD), r, border_radius=10)
            pygame.draw.rect(surf, ON if on else (PART_LINE if hov else PANEL_LINE), r, 1, border_radius=10)
            ic = self.mat_icon(m, r.w - 8, 36)
            surf.blit(ic, (r.x + 4, r.y + 4))
            nm = self.mat_nice(m)
            while len(nm) > 3 and app.ui_s.size(nm)[0] > r.w - 10:
                nm = nm[:-2] + '…'
            s_ = app.ui_s.render(nm, True, ON if on else TEXT)
            surf.blit(s_, s_.get_rect(midtop=(r.centerx, r.y + 42)))
        surf.set_clip(old)
        if total > area.h:
            th = max(24, int(area.h * area.h / total))
            ty = area.y + int((area.h - th) * self.pal_scroll / max(1, total - area.h))
            pygame.draw.rect(surf, PANEL_LINE, (rp.right - 5, ty, 3, th), border_radius=2)
        ct = app.ui_s.render(_CR_A, True, TEXT_DIM)
        while ct.get_width() > rp.w - 16 and len(_CR_A) > 4:
            ct = pygame.transform.smoothscale(ct, (rp.w - 16, ct.get_height()))
        surf.blit(ct, (rp.x + 8, rp.bottom - 20))
        # top bar
        top = pygame.Rect(0, 0, W, TOPH)
        pygame.draw.rect(surf, PANEL, top)
        pygame.draw.line(surf, PANEL_LINE, (0, top.bottom - 1), (top.right, top.bottom - 1))
        if W >= 940:
            t = app.ui_h.render('logic sandbox', True, TEXT)
            surf.blit(t, (16, top.centery - t.get_height() // 2))
        sim = self.sim
        for r, act, label, kind in self.g_top(W):
            icon = {'pause': 'pause', 'step': 'step', 'minus': 'minus', 'plus': 'plus', 'help': 'help'}.get(kind)
            active = (kind == 'pause' and self.paused) or (act == 'gravity' and sim.gravity) or (act == 'smooth' and self.smooth) \
                or (act == 'view' and self.view) or (kind == 'help' and self.help_open) or (act == 'edges' and not sim.open)
            app.draw_btn(surf, r, label, 'toggle' if kind == 'toggle' else kind, mp, active, icon)
        st = ('paused' if self.paused else f'{self.sps:.0f} steps/s') + ('' if not self.sym else ' · mirror ' + 'xyb'[self.sym - 1])
        s_ = app.ui_s.render(st, True, SEL if self.paused else TEXT_DIM)
        surf.blit(s_, (W - 14 - 34 - 12 - s_.get_width(), top.centery - s_.get_height() // 2))
        # world edges
        for r, d_ in self.edge_buttons():
            hov = r.collidepoint(mp)
            pygame.draw.rect(surf, CARD_HI if hov else PANEL, r, border_radius=10)
            pygame.draw.rect(surf, PART_LINE if hov else PANEL_LINE, r, 1, border_radius=10)
            cx, cy = r.center
            sg = 1 if d_ > 0 else -1
            pygame.draw.lines(surf, TEXT if hov else TEXT_DIM, False, [(cx - 4 * sg, cy - 8), (cx + 4 * sg, cy), (cx - 4 * sg, cy + 8)], 3)
        lo_x = self.sim.wx
        s_ = app.ui_s.render(f'world x {lo_x:,} to {lo_x + GW:,}   (arrow keys scroll)', True, TEXT_DIM)
        surf.blit(s_, (self.view_rect.x + 10, self.view_rect.bottom - 22))
        # selection actions
        for r, act, lab in self.sel_buttons():
            hov = r.collidepoint(mp)
            hot = act == 'phys'
            pygame.draw.rect(surf, ON if hot else (CARD_HI if hov else PANEL), r, border_radius=8)
            pygame.draw.rect(surf, ON if hot else PART_LINE, r, 1, border_radius=8)
            s_ = app.ui.render(lab, True, (8, 16, 30) if hot else TEXT)
            surf.blit(s_, s_.get_rect(center=r.center))
        # toast
        msg, until = app.toast
        if msg and time.time() < until:
            t = app.font.render(msg, True, TEXT)
            tr = pygame.Rect(0, 0, t.get_width() + 24, t.get_height() + 14)
            tr.midtop = (self.view_rect.centerx, TOPH + 12)
            pygame.draw.rect(surf, PANEL, tr, border_radius=10)
            pygame.draw.rect(surf, SEL, tr, 1, border_radius=10)
            surf.blit(t, t.get_rect(center=tr.center))
        if self.help_open:
            self.draw_ghelp(surf)

    def draw_ghelp(self, surf):
        W, H = surf.get_size()
        app = self.app
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((*DIM, 150))
        surf.blit(dim, (0, 0))
        lines = G_HELP
        half = (len(lines) + 1) // 2
        bw, bh = 620, 62 + half * 22 + 40
        box = pygame.Rect(0, 0, bw, bh)
        box.center = (W // 2, H // 2)
        pygame.draw.rect(surf, PANEL, box, border_radius=14)
        pygame.draw.rect(surf, PART_LINE, box, 1, border_radius=14)
        t = app.ui_h.render('gas lab keys', True, TEXT)
        surf.blit(t, (box.x + 24, box.y + 18))
        for i, ln in enumerate(lines):
            col, row = divmod(i, half)
            s_ = app.ui.render(ln, True, TEXT)
            surf.blit(s_, (box.x + 24 + col * 300, box.y + 58 + row * 22))
        t = app.ui_s.render('click anywhere to close', True, TEXT_DIM)
        surf.blit(t, (box.x + 24, box.bottom - 28))

    # masks over the padded grid
    def seg_mask(self, a, b, r):
        ax, ay, bx, by = a[0] + 1, a[1] + 1, b[0] + 1, b[1] + 1
        X, Y = self.sim.X, self.sim.Y
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 == 0:
            d2 = (X - ax) ** 2 + (Y - ay) ** 2
        else:
            t = np.clip(((X - ax) * dx + (Y - ay) * dy) / l2, 0, 1)
            d2 = (X - ax - t * dx) ** 2 + (Y - ay - t * dy) ** 2
        return (d2 <= r * r + 0.5) & ~self.sim.ring

    def rect_mask(self, a, b, outline):
        x0, x1 = sorted((a[0] + 1, b[0] + 1))
        y0, y1 = sorted((a[1] + 1, b[1] + 1))
        m = np.zeros(self.sim.solid.shape, bool)
        m[x0:x1 + 1, y0:y1 + 1] = True
        if outline:
            t = max(1, self.size)
            m[x0 + t:x1 + 1 - t, y0 + t:y1 + 1 - t] = False
        return m & ~self.sim.ring

    def flood(self, c):
        sol = self.sim.solid
        start = (c[0] + 1, c[1] + 1)
        m = np.zeros(sol.shape, bool)
        if sol[start]:
            return m
        q = deque([start])
        m[start] = True
        W2, H2 = sol.shape
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 1 <= nx < W2 - 1 and 1 <= ny < H2 - 1 and not m[nx, ny] and not sol[nx, ny]:
                    m[nx, ny] = True
                    q.append((nx, ny))
        return m

    def mirror(self, m):
        if not self.sym:
            return m
        out = m.copy()
        if self.sym in (1, 3):
            out |= m[::-1, :]
        if self.sym in (2, 3):
            out |= m[:, ::-1]
        if self.sym == 3:
            out |= m[::-1, ::-1]
        return out & ~self.sim.ring

    def flood_erase(self, c):
        # erase tool + FILL: wipes the whole connected chunk under the cursor (all linked solids, or the gas pocket)
        sim = self.sim
        start = (c[0] + 1, c[1] + 1)
        solid_hit = sim.kind[start] > 0 or sim.cogmask[start]
        m = np.zeros(sim.kind.shape, bool)
        q = deque([start])
        m[start] = True
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 1 <= nx < sim.W2 - 1 and 1 <= ny < sim.H2 - 1 and not m[nx, ny]:
                    here = sim.kind[nx, ny] > 0
                    if here == solid_hit and (here or not sim.solid[nx, ny]):
                        m[nx, ny] = True
                        q.append((nx, ny))
        if solid_hit:
            sim.erase(self.mirror(m))
        else:
            sim.drain(self.mirror(m), 0.0)
        self.dirty = True

    def apply(self, mask, amount, erase=False):
        mask = self.mirror(mask)
        sim = self.sim
        if erase or self.tool == 'ERASE':
            sim.erase(mask)
        elif self.mat in G_SOLID_MATS:
            link = -1
            if self.link_sensor and self.mat in ('VALVE', 'IGNITER', 'CONTROL ROD'):
                link = self.link_sensor[0] * sim.H2 + self.link_sensor[1]
            sim.set_solid(mask, G_SOLID_MATS[self.mat], link)
        elif self.mat in G_SENSOR_TYPES or self.mat in ('LINK', 'THRUST PROBE') + G_MECH:
            pass        # sensors and links are placed one click at a time
        elif self.mat == 'BLOCK':
            self.app.say('draw blocks with RECT')
        elif self.mat == 'VACUUM':
            sim.drain(mask, 0.5 if amount < 1 else 0.0)
        elif self.mat == 'WATER':
            m = mask & ~sim.solid
            sim.liq[m] = np.minimum(G_LIQ_CAP, sim.liq[m] + amount * 6)
        else:
            sim.add_gas(mask, dict(G_MATS)[self.mat], amount)
        self.dirty = True

    # input
    def handle(self, e):
        # returns 'quit' when esc should close the game
        if self.chrome_event(e):
            return None
        if e.type == pygame.KEYDOWN:
            k = e.key
            ctrl = bool(e.mod & pygame.KMOD_CTRL)
            shift = bool(e.mod & pygame.KMOD_SHIFT)
            if k == pygame.K_ESCAPE:
                if self.drag:
                    self.drag = None
                elif self.cog_prev:
                    self.cog_prev = None
                elif self.pasting:
                    self.pasting = False
                elif self.sel:
                    self.sel = None
                elif self.link_sensor or self.link_target or self.rod_first or self.chain_first:
                    self.link_sensor = self.link_target = self.rod_first = self.chain_first = None
                    self.app.say('stopped linking')
                else:
                    return 'quit'
            elif k == pygame.K_TAB:
                self.save()
                self.app.mode = 'circuit'
            elif ctrl and shift and k == pygame.K_DELETE:
                self.sim.clear()
                self.dirty = True
            elif ctrl and k == pygame.K_c:
                if self.sel:
                    (ax, ay), (bx, by) = self.sel
                    self.clip = self.sim.copy_region(ax + 1, ay + 1, bx + 1, by + 1)
                    self.app.say(f"copied {self.clip['w']} x {self.clip['h']}, ctrl+v to paste")
                else:
                    self.app.say('use the SELECT tool first')
            elif ctrl and k == pygame.K_v:
                if self.clip:
                    self.pasting = True
                    self.app.say('click to paste, esc or rmb to stop')
                else:
                    self.app.say('nothing copied yet')
            elif k == pygame.K_r and not ctrl:
                self.toggle_physics(shift)
            elif k in (pygame.K_LEFT, pygame.K_RIGHT) and not ctrl:
                self.world_scroll(-1 if k == pygame.K_LEFT else 1)
            elif k == pygame.K_DELETE and self.sel and not (ctrl and shift):
                self.delete_selection()
            elif k == pygame.K_m:
                self.sym = (self.sym + 1) % 4
                self.app.say(['symmetry off', 'mirror left/right', 'mirror up/down', 'mirror both'][self.sym])
            elif k == pygame.K_k:
                self.sim.starter = True
            elif k == pygame.K_PERIOD:
                if self.paused:
                    self.sim.step()
                    self.sim.move_debris(1, 1 / 60)
            elif k == pygame.K_i:
                hv = self.cell(pygame.mouse.get_pos(), clamp=False)
                if hv:
                    if hv in self.pins:
                        self.pins.remove(hv)
                    elif len(self.pins) < 6:
                        self.pins.append(hv)
            elif k == pygame.K_e:
                self.sim.ignite()
            elif k == pygame.K_SPACE:
                self.paused = not self.paused
            elif k == pygame.K_UP:
                self.speed = min(32, self.speed * 2)
            elif k == pygame.K_DOWN:
                self.speed = max(1, self.speed // 2)
            elif k == pygame.K_o:
                # open air -> closed box -> open to empty space -> ...
                sim = self.sim
                if sim.open and not sim.void:
                    sim.open = False
                elif not sim.open:
                    sim.open, sim.void = True, True
                else:
                    sim.void = False
                self.app.say('edges: open to space (gas that leaves is gone)' if sim.void else 'edges: open to air' if sim.open else 'edges: closed box')
                self.dirty = True
            elif k == pygame.K_t and not ctrl:
                self.view = (self.view + 1) % len(G_VIEWS)
                self.app.say('view: ' + G_VIEWS[self.view])
            elif k == pygame.K_v and not ctrl:
                self.smooth = not self.smooth
                self.app.say('smooth gas on' if self.smooth else 'smooth gas off')
            elif k == pygame.K_p:
                self.sim.set_valves(True)
            elif k == pygame.K_g:
                self.sim.gravity = not self.sim.gravity
                self.sim.update_ambient()
                self.dirty = True
            elif k == pygame.K_a:
                self.sim.reset_air()
                self.dirty = True
            elif k == pygame.K_RIGHTBRACKET:
                self.size = min(36, self.size + 1)
            elif k == pygame.K_LEFTBRACKET:
                self.size = max(0, self.size - 1)
        elif e.type == pygame.KEYUP and e.key == pygame.K_p:
            self.sim.set_valves(False)
        elif e.type == pygame.KEYUP and e.key == pygame.K_k:
            self.sim.starter = False
        elif e.type == pygame.MOUSEWHEEL:
            if self.cog_prev:
                self.cog_prev['n'] = max(4, min(60, self.cog_prev['n'] + e.y))
            elif not self.in_view(pygame.mouse.get_pos()):
                pass
            elif pygame.key.get_mods() & pygame.KMOD_CTRL:
                self.zoom_at(pygame.mouse.get_pos(), e.y)
            else:
                self.size = max(0, min(36, self.size + e.y))
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 2:
            if self.in_view(e.pos) and self.zcs is not None:
                self.pan_from = (e.pos, self.panx, self.pany)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 2:
            self.pan_from = None
        elif e.type == pygame.MOUSEMOTION and self.pan_from:
            (mx, my), px, py = self.pan_from
            self.panx = px + e.pos[0] - mx
            self.pany = py + e.pos[1] - my
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
            if not self.in_view(e.pos):
                return None
            c = self.cell(e.pos)
            if self.pasting:
                if e.button == 1:
                    if self.sim.paste(self.clip, c[0] + 1, c[1] + 1):
                        self.dirty = True
                    else:
                        self.app.say("doesn't fit there")
                else:
                    self.pasting = False
                return None
            erase = e.button == 3
            key = (c[0] + 1, c[1] + 1)
            sn = self.sim.sensors.get(key)
            kd = int(self.sim.kind[key])
            fx = (e.pos[0] - self.x0) / self.cs + 1
            fy = (e.pos[1] - self.y0) / self.cs + 1
            if self.cog_prev:
                cp_ = self.cog_prev
                if e.button == 1:
                    if any([self.sim.add_cog(px, py, cp_['R'], cp_['tl'], cp_['n']) for px, py in self.sim.mirror_pts(cp_['x'], cp_['y'], self.sym)]):
                        self.dirty = True
                        self.app.say(f"cog: {cp_['n']} teeth")
                    else:
                        self.app.say('a shaft is already there')
                self.cog_prev = None
                return None
            if self.mat == 'COG' and not erase and self.tool != 'SELECT':
                self.drag = dict(start=c, cur=c, last=c, erase=False, tool='COG')
                return None
            if self.tool == 'SELECT' and not erase:
                self.drag = dict(start=c, cur=c, last=c, erase=False, tool='SELECT')
                return None
            if not erase and self.tool != 'ERASE':
                if self.mat == 'SHAFT':
                    self.drag = dict(start=c, cur=c, last=c, erase=False, tool='SHAFT')
                    return None
                if self.mat == 'HINGE':
                    self.app.say(self.sim.add_hinge(fx, fy))
                    self.dirty = True
                    return None
                if self.mat == 'ROD':
                    h = self.sim.near_hinge(fx, fy)
                    if h is None:
                        self.app.say('click a hinge')
                    elif self.rod_first is None:
                        self.rod_first = h
                        self.app.say('now click the other hinge (esc to cancel)')
                    else:
                        if self.sim.add_rod(self.rod_first, h):
                            self.app.say('rod connected')
                            self.dirty = True
                        else:
                            self.app.say('pick a different hinge')
                        self.rod_first = None
                    return None
                if self.mat == 'WHEEL':
                    self.app.say(self.sim.toggle_wheel(fx, fy))
                    self.dirty = True
                    return None
                if self.mat == 'CHAIN':
                    sh_ = self.sim.near_shaft(fx, fy)
                    if sh_ is None:
                        self.app.say('click a shaft or cog')
                    elif self.chain_first is None:
                        self.chain_first = sh_
                        self.app.say('now click the other shaft (esc to cancel)')
                    else:
                        self.app.say(self.sim.add_chain(self.chain_first, sh_))
                        self.chain_first = None
                        self.dirty = True
                    return None
                if self.mat == 'LINK':
                    if kd == G_LINK:
                        lk = self.sim.glinks.get(key)
                        if lk:
                            lk['id'] = lk['id'] % 16 + 1
                            self.link_id = lk['id']
                            self.dirty = True
                            self.app.say(self.sim.describe(*key))
                    elif sn or kd in (G_VALVE, G_IGNITER, G_CTRL):
                        self.link_target = key
                        self.app.say('now place a link cell, it connects to this (esc to stop)')
                    elif self.link_target is None:
                        self.app.say('click a sensor, valve or igniter first, then place the link')
                    elif not self.sim.add_link(key[0], key[1], self.link_id, self.link_target):
                        self.app.say('links go on empty cells')
                    else:
                        self.dirty = True
                        self.app.say(f'link {self.link_id} placed (click it to change the id)')
                    return None
                if kd >= G_FILTER and kd != G_LINK and G_SOLID_MATS.get(self.mat) == kd and kd != G_VENT:
                    self.app.say(self.sim.cycle(key[0], key[1]))
                    self.dirty = True
                    return None
                if sn and self.mat in ('VALVE', 'IGNITER', 'CONTROL ROD'):
                    # click a sensor first, then whatever valves / igniters you draw follow it
                    if self.link_sensor == key:
                        self.link_sensor = None
                        self.app.say('stopped linking')
                    else:
                        self.link_sensor = key
                        self.app.say(f'new {self.mat.lower()}s will follow this sensor (esc to stop)')
                    return None
                if sn and G_SENSOR_TYPES.get(self.mat) == sn['type']:
                    # clicking a sensor with its own type picked tweaks it
                    if sn['type'] == 'timer' and pygame.key.get_mods() & pygame.KMOD_CTRL:
                        sn['dir'] = (sn['dir'] + 1) % 4
                    elif sn['type'] == 'timer':
                        sn['level'] = (sn['level'] + 1) % 5
                    elif sn['type'] in ('block', 'hinge'):
                        sn['dir'] = (sn['dir'] + 1) % 4
                    else:
                        sn['level'] = (sn['level'] + 1) % 5
                    self.dirty = True
                    self.app.say(self.sim.info(*c))
                    return None
                if self.mat == 'THRUST PROBE':
                    self.app.say(self.sim.add_probe(key[0], key[1]))
                    self.dirty = True
                    return None
                if self.mat in G_SENSOR_TYPES:
                    if not self.sim.add_sensor(key[0], key[1], G_SENSOR_TYPES[self.mat]):
                        self.app.say('sensors go on empty cells')
                    self.dirty = True
                    return None
            if self.tool == 'FILL' and not erase:
                amount = 1.0
                self.apply(self.flood(c), amount)
                return None
            if erase and self.tool == 'FILL':
                self.flood_erase(c)
                return None
            # erasing (right click) uses the selected tool: line erases a line, rect a filled box
            self.drag = dict(start=c, cur=c, last=c, erase=erase,
                             tool=self.tool if erase and self.tool in ('LINE', 'RECT') else ('BRUSH' if erase else self.tool))
        elif e.type == pygame.MOUSEMOTION and self.cog_prev:
            cp_ = self.cog_prev
            fx = (e.pos[0] - self.x0) / self.cs + 1
            fy = (e.pos[1] - self.y0) / self.cs + 1
            cp_['tl'] = max(1.0, min(14.0, math.hypot(fx - cp_['x'], fy - cp_['y']) - cp_['R']))
        elif e.type == pygame.MOUSEMOTION and self.drag:
            self.drag['cur'] = self.cell(e.pos)
        elif e.type == pygame.MOUSEBUTTONUP and self.drag and e.button in (1, 3):
            d, self.drag = self.drag, None
            if d['tool'] == 'COG':
                (ax, ay), (bx, by) = d['start'], d['cur']
                R = max(3.0, math.hypot(bx - ax, by - ay))
                self.cog_prev = dict(x=ax + 1.5, y=ay + 1.5, R=R, tl=3.0, n=max(4, int(2 * math.pi * R / 4)))
                self.app.say('move out for tooth length, wheel = tooth count, click to place')
            elif d['tool'] == 'SHAFT':
                (ax, ay), (bx, by) = d['start'], d['cur']
                R = math.hypot(bx - ax, by - ay)
                if any([self.sim.add_shaft(px, py, R) for px, py in self.sim.mirror_pts(ax + 1.5, ay + 1.5, self.sym)]):
                    self.app.say(f'shaft, radius {max(3, R):.0f}: bigger = heavier flywheel')
                    self.dirty = True
            elif d['tool'] == 'SELECT':
                self.sel = (d['start'], d['cur'])
            elif d['tool'] == 'LINE':
                self.apply(self.seg_mask(d['start'], d['cur'], self.size), 1.0, erase=d['erase'])
            elif d['tool'] == 'RECT':
                if d['erase']:
                    self.apply(self.rect_mask(d['start'], d['cur'], False), 1.0, erase=True)
                elif self.mat == 'BLOCK':
                    (ax, ay), (bx, by) = d['start'], d['cur']
                    if not self.sim.add_body(ax + 1, ay + 1, bx + 1, by + 1):
                        self.app.say('block needs empty space')
                    W2, H2 = self.sim.W2, self.sim.H2
                    if self.sym in (1, 3):
                        self.sim.add_body(W2 - 1 - (ax + 1), ay + 1, W2 - 1 - (bx + 1), by + 1)
                    if self.sym in (2, 3):
                        self.sim.add_body(ax + 1, H2 - 1 - (ay + 1), bx + 1, H2 - 1 - (by + 1))
                    if self.sym == 3:
                        self.sim.add_body(W2 - 1 - (ax + 1), H2 - 1 - (ay + 1), W2 - 1 - (bx + 1), H2 - 1 - (by + 1))
                    self.dirty = True
                else:
                    solid = self.mat in G_SOLID_MATS
                    self.apply(self.rect_mask(d['start'], d['cur'], solid), 1.0)
        return None

    def toggle_physics(self, shift=False):
        if not self.sel:
            self.app.say('use the SELECT tool on something first, then R')
            return
        (ax, ay), (bx, by) = self.sel
        sim = self.sim
        n = sim.release_frames(ax + 1, ay + 1, bx + 1, by + 1) + sim.release_rbodies(ax + 1, ay + 1, bx + 1, by + 1)
        if n:
            self.app.say('physics off')
            self.sel = None
        else:
            rb = None if shift else sim.make_rbody(ax + 1, ay + 1, bx + 1, by + 1)
            if rb:
                self.app.say('free body: it falls, tumbles and spins (R again to freeze it)')
                self.sel = None
            else:
                err = sim.make_frame(ax + 1, ay + 1, bx + 1, by + 1)
                self.app.say(err or 'physics object: shafts, blocks and gas inside ride along (R again to turn it off)')
                if not err:
                    self.sel = None
        self.dirty = True

    def update(self, dt):
        if self.sel and self.tool != 'SELECT' and not self.pasting:
            self.sel = None         # the selection box goes away once you pick another tool
        d = self.drag
        if d and d['tool'] in ('BRUSH', 'ERASE'):
            # brush paints every frame it's held, so holding gas pumps pressure up
            self.apply(self.seg_mask(d['last'], d['cur'], self.size), 0.12, erase=d['erase'])
            d['last'] = d['cur']
        if not self.paused:
            t0 = time.perf_counter()
            done = 0
            for _ in range(self.speed):
                self.sim.step()
                done += 1
                if time.perf_counter() - t0 > 0.022:
                    break       # slow pc: keep the frame rate, run the sim slower
            self.sim.move_debris(done, dt)
            fd = self.sim.follow_frame() if self.sim.frames else 0
            if fd:
                self.start_slide(fd)
                self.pins = [(x - G_SLAB * fd, y) for (x, y) in self.pins if 0 <= x - G_SLAB * fd < GW]
                self.hist = {}
                self.sel = None
            while self.sim.news:
                self.app.say(self.sim.news.pop(0))
            self.hist_n += 1
            if self.pins and self.hist_n % 4 == 0:
                for pc in self.pins:
                    x, y = pc[0] + 1, pc[1] + 1
                    tot = float(self.sim.n[:, x, y].sum())
                    T_ = float(self.sim.T[x, y])
                    h = self.hist.setdefault(pc, deque(maxlen=200))
                    h.append((tot * T_ / 293, T_ - 273))
            self._steps += done
            if time.time() - self._t0 >= 1.0:
                self.sps = self._steps / (time.time() - self._t0)
                self._steps, self._t0 = 0, time.time()
            self.dirty = True

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.sim.save(self.path)
            self.sim.save_world(self.world_path)
        except OSError as err:
            print('gas save failed:', err)
        self.dirty = False
        self.last_save = time.time()

    def autosave(self):
        if self.dirty and time.time() - self.last_save >= 10:
            self.save()

    def smooth_img(self, arr, vx0, vx1, vy0, vy1):
        # gas colors are blended between cells (only with other gas cells, so nothing bleeds through a wall),
        # parts like walls, valves and blocks keep their sharp cell edges
        sim, cs = self.sim, self.cs
        w, h = vx1 - vx0, vy1 - vy0
        obj = (sim.kind[1 + vx0:1 + vx1, 1 + vy0:1 + vy1] > 0) | sim.solid[1 + vx0:1 + vx1, 1 + vy0:1 + vy1]
        gas = ~obj
        # parts get the average color of the gas next to them first, so the blend near them stays gas-colored
        f = arr.astype(np.float32)
        g = gas.astype(np.float32)
        acc = np.zeros_like(f)
        cnt = np.zeros(g.shape, np.float32)
        for sl_d, sl_s in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                           ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                           ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                           ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            acc[sl_d] += f[sl_s] * g[sl_s][..., None]
            cnt[sl_d] += g[sl_s]
        fill = acc / np.maximum(cnt, 1)[..., None]
        base = np.where(gas[..., None], f, fill).astype(np.uint8)
        img = pygame.transform.smoothscale(pygame.surfarray.make_surface(base), (w * cs, h * cs))
        if obj.any():
            key = (255, 0, 255)
            solid_arr = np.where(obj[..., None], arr, np.array(key, np.uint8))
            top = pygame.transform.scale(pygame.surfarray.make_surface(solid_arr), (w * cs, h * cs))
            top.set_colorkey(key)
            img.blit(top, (0, 0))
        return img

    def smooth_objects(self, surf):
        # blocks and physics objects move in whole cells inside the sim, but are drawn where they really are:
        # the picture of the object is lifted off the grid and put back shifted by its sub-cell offset
        sim, cs = self.sim, self.cs
        sw, sh_ = surf.get_size()
        objs = [(f['x0'], f['y0'], f['w'], f['h'], f['fx'], f['fy']) for f in sim.frames]
        for b in sim.bodies:
            if sim.frame_at(b['x'] + b['w'] / 2.0, b['y'] + b['h'] / 2.0, 0) is None:
                objs.append((b['x'], b['y'], b['w'], b['h'], b['fx'], b['fy']))
        for cx, cy, w, h, fx, fy in objs:
            if abs(fx) < 0.02 and abs(fy) < 0.02:
                continue
            R = pygame.Rect(self.x0 + int((cx - 1) * cs), self.y0 + int((cy - 1) * cs), w * cs, h * cs)
            if not R.inflate(2 * cs, 2 * cs).colliderect((0, 0, sw, sh_)):
                continue
            spr = pygame.Surface(R.size)
            spr.blit(surf, (0, 0), R)
            ox, oy = int(round(fx * cs)), int(round(fy * cs))
            # the strip the object leaves behind gets the gas colors from just outside of it
            if ox:
                col_x = R.x - 1 if ox > 0 else R.right
                if 0 <= col_x < sw:
                    line = pygame.Surface((1, R.h))
                    line.blit(surf, (0, 0), (col_x, R.y, 1, R.h))
                    strip = pygame.transform.scale(line, (abs(ox), R.h))
                    surf.blit(strip, (R.x if ox > 0 else R.right - abs(ox), R.y))
            if oy:
                row_y = R.y - 1 if oy > 0 else R.bottom
                if 0 <= row_y < sh_:
                    line = pygame.Surface((R.w, 1))
                    line.blit(surf, (0, 0), (R.x, row_y, R.w, 1))
                    strip = pygame.transform.scale(line, (R.w, abs(oy)))
                    surf.blit(strip, (R.x, R.y if oy > 0 else R.bottom - abs(oy)))
            surf.blit(spr, (R.x + ox, R.y + oy))

    def draw_rbodies(self, surf):
        sim, cs = self.sim, self.cs
        for rb in sim.rbs:
            key = (id(rb), cs)
            spr = self.rb_spr.get(key)
            if spr is None:
                S = int((rb['r'] + 2) * 2 * cs)
                spr = pygame.Surface((S, S), pygame.SRCALPHA)
                ii, jj = np.nonzero(rb['grid'] >= 0)
                for a, b, i in zip(ii.tolist(), jj.tolist(), rb['grid'][ii, jj].tolist()):
                    spr.fill(tuple(int(v) for v in rb['col'][i]),
                             (S // 2 + int(round((a - rb['cmx'] + 0.5 - 0.5) * cs)) - 0, S // 2 + int(round((b - rb['cmy'] + 0.5 - 0.5) * cs)), cs + 1, cs + 1))
                if len(self.rb_spr) > 64:
                    self.rb_spr.clear()
                self.rb_spr[key] = spr
            rot = pygame.transform.rotozoom(spr, -math.degrees(rb['th']), 1.0)
            c = (self.x0 + int((rb['x'] - 1) * cs), self.y0 + int((rb['y'] - 1) * cs))
            surf.blit(rot, rot.get_rect(center=c))

    def draw_chain(self, surf, ch, scr):
        sim, cs = self.sim, self.cs
        a, b = ch['a'], ch['b']
        oa, ob = sim.foff(a['x'], a['y']), sim.foff(b['x'], b['y'])
        A = scr(a['x'], a['y'], oa)
        B = scr(b['x'], b['y'], ob)
        ra, rb = (a['R'] + a.get('tl', 0) / 2 + 0.6) * cs, (b['R'] + b.get('tl', 0) / 2 + 0.6) * cs
        dx, dy = B[0] - A[0], B[1] - A[1]
        L = math.hypot(dx, dy)
        if L < abs(ra - rb) + 2:
            return
        phi = math.atan2(dy, dx)
        al = math.acos((ra - rb) / L)
        gap = max(5, cs + 2)
        for sgn in (1, -1):
            n = phi + sgn * al
            cn, sn = math.cos(n), math.sin(n)
            p1 = (A[0] + ra * cn, A[1] + ra * sn)
            p2 = (B[0] + rb * cn, B[1] + rb * sn)
            pygame.draw.line(surf, (24, 26, 32), p1, p2, max(4, cs))
            pygame.draw.line(surf, (150, 156, 170), p1, p2, 2)
            ln = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if ln < 2:
                continue
            ux, uy = (p2[0] - p1[0]) / ln, (p2[1] - p1[1]) / ln
            off = (a['th'] * sim.cpitch(a) * cs * sgn) % gap
            t = off
            while t < ln:
                q = (p1[0] + ux * t, p1[1] + uy * t)
                pygame.draw.circle(surf, (210, 214, 224), (int(q[0]), int(q[1])), 2)
                t += gap
        for sh, P, r_ in ((a, A, ra), (b, B, rb)):
            pygame.draw.circle(surf, (150, 156, 170), P, int(r_), 1)

    # drawing
    def draw(self, surf):
        W, H = surf.get_size()
        self.layout(W, H)
        surf.fill(BG)
        arr = self.sim.render(self.view)
        cs0 = self.cs
        vr = self.view_rect
        surf.set_clip(vr)
        vx0, vx1 = max(0, (vr.x - self.x0) // cs0), min(GW, -(-(vr.right - self.x0) // cs0))
        vy0, vy1 = max(0, (vr.y - self.y0) // cs0), min(GH, -(-(vr.bottom - self.y0) // cs0))
        arr = np.ascontiguousarray(arr[vx0:vx1, vy0:vy1])
        if self.smooth and cs0 >= 3:
            img = self.smooth_img(arr, vx0, vx1, vy0, vy1)
        else:
            img = pygame.surfarray.make_surface(arr)
            if cs0 != 1:
                img = pygame.transform.scale(img, ((vx1 - vx0) * cs0, (vy1 - vy0) * cs0))
        surf.blit(img, (self.x0 + vx0 * cs0, self.y0 + vy0 * cs0))
        self.smooth_objects(surf)
        self.draw_rbodies(surf)
        ds = max(2, self.cs)
        for d in self.sim.debris:
            surf.fill(d[5], (self.x0 + int((d[0] - 1) * self.cs), self.y0 + int((d[1] - 1) * self.cs), ds, ds))
        pygame.draw.rect(surf, PANEL_LINE if self.sim.open else SEL,
                         (self.x0 - 1, self.y0 - 1, GW * self.cs + 2, GH * self.cs + 2), 1)
        cs = self.cs
        mp = pygame.mouse.get_pos()
        d = self.drag
        if d and d['tool'] == 'LINE':
            a = (self.x0 + d['start'][0] * cs + cs // 2, self.y0 + d['start'][1] * cs + cs // 2)
            b = (self.x0 + d['cur'][0] * cs + cs // 2, self.y0 + d['cur'][1] * cs + cs // 2)
            pygame.draw.line(surf, SEL, a, b, max(1, (2 * self.size + 1) * cs))
        elif d and d['tool'] in ('RECT', 'SELECT'):
            (ax, ay), (bx, by) = d['start'], d['cur']
            r = pygame.Rect(self.x0 + min(ax, bx) * cs, self.y0 + min(ay, by) * cs,
                            (abs(bx - ax) + 1) * cs, (abs(by - ay) + 1) * cs)
            pygame.draw.rect(surf, SEL, r, 1)
        if self.sym:
            mx_ = self.x0 + GW * cs // 2
            my_ = self.y0 + GH * cs // 2
            if self.sym in (1, 3):
                pygame.draw.line(surf, (90, 120, 160), (mx_, self.y0), (mx_, self.y0 + GH * cs), 1)
            if self.sym in (2, 3):
                pygame.draw.line(surf, (90, 120, 160), (self.x0, my_), (self.x0 + GW * cs, my_), 1)
        # selection, paste ghost, pinned cells
        if self.sel:
            (ax, ay), (bx, by) = self.sel
            pygame.draw.rect(surf, (120, 220, 255), pygame.Rect(self.x0 + min(ax, bx) * cs, self.y0 + min(ay, by) * cs,
                                                                (abs(bx - ax) + 1) * cs, (abs(by - ay) + 1) * cs), 1)
        if self.pasting and self.clip:
            gc = self.cell(mp, clamp=False)
            if gc:
                pygame.draw.rect(surf, (120, 255, 160), pygame.Rect(self.x0 + gc[0] * cs, self.y0 + gc[1] * cs,
                                                                    self.clip['w'] * cs, self.clip['h'] * cs), 1)
        # shafts, rods and hinges
        sim = self.sim
        def scr(px, py, off=(0.0, 0.0)):
            return (int(self.x0 + (px + off[0] - 1) * cs), int(self.y0 + (py + off[1] - 1) * cs))
        def draw_teeth(sh):
            P = 2 * math.pi / sh['teeth']
            fo = sim.foff(sh['x'], sh['y'])
            for i in range(sh['teeth']):
                a0 = sh['th'] + i * P
                a1 = a0 + P / 2
                Ri, Ro = sh['R'] - 0.5, sh['R'] + sh['tl']
                pts = [scr(sh['x'] + Ri * math.cos(a), sh['y'] + Ri * math.sin(a), fo) for a in (a0, a1)] + \
                      [scr(sh['x'] + Ro * math.cos(a), sh['y'] + Ro * math.sin(a), fo) for a in (a1, a0)]
                pygame.draw.polygon(surf, (70, 78, 100), pts)
                pygame.draw.polygon(surf, (150, 160, 182), pts, 1)
        for sh in sim.shafts:
            so = sim.foff(sh['x'], sh['y'])
            c0 = scr(sh['x'], sh['y'], so)
            R = int(sh['R'] * cs)
            if sh.get('teeth'):
                draw_teeth(sh)
            if sh.get('wheel'):
                RT = int((sh['R'] + G_WHEEL_T) * cs)
                pygame.draw.circle(surf, (22, 22, 26), c0, RT)
                pygame.draw.circle(surf, (70, 70, 80), c0, RT, 1)
                for k in range(14):
                    a_ = sh['th'] + k * 2 * math.pi / 14
                    pygame.draw.line(surf, (60, 60, 70), (c0[0] + (R + 1) * math.cos(a_), c0[1] + (R + 1) * math.sin(a_)),
                                     (c0[0] + (RT - 1) * math.cos(a_), c0[1] + (RT - 1) * math.sin(a_)), max(2, cs // 2))
            pygame.draw.circle(surf, (52, 58, 76), c0, R)
            pygame.draw.circle(surf, (150, 160, 182), c0, R, 2)
            for k in range(4):
                a_ = sh['th'] + k * math.pi / 2
                pygame.draw.line(surf, (90, 98, 120), c0, (c0[0] + R * math.cos(a_), c0[1] + R * math.sin(a_)), 1)
            pygame.draw.circle(surf, (150, 160, 182), c0, 3)
            rpm = sh['om'] / (2 * math.pi) * self.sps * 60
            t = self.app.tiny.render(f'{rpm:.0f} rpm', True, (200, 205, 220))
            surf.blit(t, (c0[0] - t.get_width() // 2, c0[1] + R + 3 + (int(G_WHEEL_T * cs) if sh.get('wheel') else 0)))
        for ch in sim.chains:
            self.draw_chain(surf, ch, scr)
        for r in sim.rods:
            pa, pb = sim.hinge_pos(r['a']), sim.hinge_pos(r['b'])
            oa, ob = sim.hoff(r['a']), sim.hoff(r['b'])
            pygame.draw.line(surf, (30, 32, 40), scr(pa[0], pa[1], oa), scr(pb[0], pb[1], ob), max(4, cs + 1))
            pygame.draw.line(surf, (200, 204, 214), scr(pa[0], pa[1], oa), scr(pb[0], pb[1], ob), max(2, cs - 1))
        for h in sim.hinges:
            hp = scr(*sim.hinge_pos(h)[:2], sim.hoff(h))
            pygame.draw.circle(surf, (20, 22, 28), hp, max(4, cs))
            pygame.draw.circle(surf, SEL if h is self.rod_first else (235, 235, 245), hp, max(3, cs - 1))
        if self.cog_prev:
            q = dict(self.cog_prev, th=0.0, teeth=self.cog_prev['n'])
            draw_teeth(q)
            pygame.draw.circle(surf, SEL, scr(q['x'], q['y']), int(q['R'] * cs), 1)
        d_ = self.drag
        if d_ and d_['tool'] in ('SHAFT', 'COG'):
            (ax, ay), (bx, by) = d_['start'], d_['cur']
            pygame.draw.circle(surf, SEL, scr(ax + 1.5, ay + 1.5), int(max(3, math.hypot(bx - ax, by - ay)) * cs), 1)
        if self.chain_first:
            q = self.chain_first
            pygame.draw.circle(surf, SEL, scr(q['x'], q['y'], sim.foff(q['x'], q['y'])), int((q['R'] + 1) * cs), 2)
        # circuit links: line to whatever they're connected to, with their id
        for (x, y), lk in self.sim.glinks.items():
            if lk['tgt'] is None:
                continue
            a = (self.x0 + (x - 1) * cs + cs // 2, self.y0 + (y - 1) * cs + cs // 2)
            b = (self.x0 + (lk['tgt'][0] - 1) * cs + cs // 2, self.y0 + (lk['tgt'][1] - 1) * cs + cs // 2)
            colr = (90, 220, 255) if lk['role'] == 'tx' else (255, 120, 220)
            if lk['on'] or (lk['role'] == 'tx' and (self.sim.sensors.get(lk['tgt']) or {}).get('on')):
                colr = (255, 255, 120)
            pygame.draw.line(surf, colr, a, b, 1)
            t = self.app.tiny.render(str(lk['id']), True, colr)
            surf.blit(t, (a[0] + cs, a[1] - cs - 4))
        if self.link_target:
            tx_, ty_ = self.link_target
            pygame.draw.rect(surf, SEL, (self.x0 + (tx_ - 2) * cs, self.y0 + (ty_ - 2) * cs, cs * 3, cs * 3), 1)
        # sensor ranges and links
        hover = self.cell(mp, clamp=False)
        hkey = (hover[0] + 1, hover[1] + 1) if hover else None
        for (x, y), sn in self.sim.sensors.items():
            sx, sy = self.x0 + (x - 1) * cs + cs // 2, self.y0 + (y - 1) * cs + cs // 2
            if sn['type'] in ('block', 'hinge'):
                dx, dy = G_DIRS[sn['dir']]
                end = (sx + dx * G_SENSE_RANGE * cs, sy + dy * G_SENSE_RANGE * cs)
                pygame.draw.line(surf, G_SENSOR_COLOR['block'] if not sn['on'] else SEL, (sx, sy), end, 1)
            if (x, y) == self.link_sensor or (x, y) == hkey:
                pygame.draw.rect(surf, SEL, (sx - cs, sy - cs, cs * 2 + 1, cs * 2 + 1), 1)
                xs, ys = np.nonzero(self.sim.link == x * self.sim.H2 + y)
                for lx, ly in zip(xs.tolist(), ys.tolist()):
                    r = (self.x0 + (lx - 1) * cs, self.y0 + (ly - 1) * cs, cs, cs)
                    pygame.draw.rect(surf, SEL, r, 1)
        if self.in_view(mp) and self.tool != 'FILL' and not any(r_.collidepoint(mp) for r_, _, _ in self.sel_buttons()):
            rr = max(7, int((self.size + 0.5) * cs))
            pts = [mp]
            if self.sym:
                cx_, cy_ = self.x0 + GW * cs // 2, self.y0 + GH * cs // 2
                if self.sym in (1, 3): pts.append((2 * cx_ - mp[0], mp[1]))
                if self.sym in (2, 3): pts.append((mp[0], 2 * cy_ - mp[1]))
                if self.sym == 3: pts.append((2 * cx_ - mp[0], 2 * cy_ - mp[1]))
            for q in pts:
                pygame.draw.circle(surf, SEL, q, rr, 2)
                pygame.draw.line(surf, SEL, (q[0] - rr - 5, q[1]), (q[0] - rr + 2, q[1]), 2)
                pygame.draw.line(surf, SEL, (q[0] + rr - 2, q[1]), (q[0] + rr + 5, q[1]), 2)
                pygame.draw.line(surf, SEL, (q[0], q[1] - rr - 5), (q[0], q[1] - rr + 2), 2)
                pygame.draw.line(surf, SEL, (q[0], q[1] + rr - 2), (q[0], q[1] + rr + 5), 2)
        # hover readout
        c = self.cell(mp, clamp=False)
        if c and self.in_view(mp):
            t = self.app.small.render(self.sim.info(*c), True, TEXT)
            r = pygame.Rect(0, 0, t.get_width() + 12, t.get_height() + 6)
            r.bottomright = (vr.right - 8, vr.bottom - 8)
            pygame.draw.rect(surf, PANEL, r)
            pygame.draw.rect(surf, PART_LINE, r, 1)
            surf.blit(t, (r.x + 6, r.y + 3))
        if self.view:
            lw, lx, ly = 300, vr.centerx - 150, vr.bottom - 46
            stops = (G_RAMP_P, G_RAMP_T, G_RAMP_S)[self.view - 1]
            strip = ramp(np.linspace(0, 1, lw)[:, None] * np.ones((1, 12)), stops).astype(np.uint8)
            surf.blit(pygame.surfarray.make_surface(strip), (lx, ly))
            pygame.draw.rect(surf, PANEL_LINE, (lx - 1, ly - 1, lw + 2, 14), 1)
            if self.view == 1:
                marks = [(2.0 ** k, f'{2.0 ** k:g}') for k in (-3, 0, 3, 6)]
                posf = lambda a: (math.log2(a) + 3) / 9
                unit = 'atm'
            elif self.view == 2:
                marks = [(t_, f'{t_ - 273}') for t_ in (293, 1000, 2000, 3500, 5000)]
                posf = lambda a: ((a - 200) / 4800) ** 0.7 if a > 200 else 0
                unit = 'C'
            else:
                marks = [(G_UMAX * f_, f'{G_UMAX * f_:.2f}') for f_ in (0, 0.25, 0.5, 1)]
                posf = lambda a: (a / G_UMAX) ** 0.6
                unit = 'cells/step'
            for a, lab in marks:
                mx_ = lx + int(posf(a) * (lw - 1))
                pygame.draw.line(surf, TEXT, (mx_, ly + 12), (mx_, ly + 16), 1)
                t_ = self.app.tiny.render(lab, True, TEXT)
                surf.blit(t_, (mx_ - t_.get_width() // 2, ly + 17))
            t_ = self.app.small.render(f'{G_VIEWS[self.view]} ({unit})   t = next view', True, TEXT_DIM)
            surf.blit(t_, (vr.centerx - t_.get_width() // 2, ly - 20))
        # thrust probes
        if self.sim.probes:
            by = vr.y + 10
            for i, ((px_, py_), pr) in enumerate(self.sim.probes.items()):
                fx, fy = pr['f']
                mag = math.hypot(fx, fy)
                sx, sy = self.x0 + (px_ - 1) * cs + cs // 2, self.y0 + (py_ - 1) * cs + cs // 2
                pygame.draw.circle(surf, (255, 170, 60), (sx, sy), max(3, cs // 2 + 1), 1)
                if mag > 0.05:
                    ln = min(110, 14 + mag * 0.6)
                    ex, ey = sx + fx / mag * ln, sy + fy / mag * ln
                    pygame.draw.line(surf, (255, 170, 60), (sx, sy), (ex, ey), 2)
                    ang = math.atan2(fy, fx)
                    for da in (2.6, -2.6):
                        pygame.draw.line(surf, (255, 170, 60), (ex, ey), (ex + 9 * math.cos(ang + da), ey + 9 * math.sin(ang + da)), 2)
                dirs = []
                if abs(fy) > 0.25 * mag:
                    dirs.append('down' if fy > 0 else 'up')
                if abs(fx) > 0.25 * mag:
                    dirs.append('right' if fx > 0 else 'left')
                imp = math.hypot(*pr['imp'])
                gx, gy, gw_, gh_ = vr.x + 10, by, 250, 74
                pygame.draw.rect(surf, PANEL, (gx, gy, gw_, gh_))
                pygame.draw.rect(surf, PANEL_LINE, (gx, gy, gw_, gh_), 1)
                surf.blit(self.app.small.render(f'T{i + 1}  thrust {mag:.1f}  {" + ".join(dirs) or "-"}', True, (255, 190, 90)), (gx + 6, gy + 4))
                surf.blit(self.app.tiny.render(f'peak {pr["peak"]:.1f}    impulse {imp:.0f}    (click probe = reset)', True, TEXT_DIM), (gx + 6, gy + 22))
                h = pr['hist']
                if len(h) > 1:
                    vals = [math.hypot(a_, b_) for a_, b_ in h]
                    hi_ = max(max(vals), 1e-6)
                    pts = [(gx + 6 + k * (gw_ - 12) / (len(vals) - 1), gy + gh_ - 5 - v_ / hi_ * 28) for k, v_ in enumerate(vals)]
                    pygame.draw.lines(surf, (255, 170, 60), False, pts, 1)
                by += gh_ + 6
        # pinned readouts
        for i, pc in enumerate(self.pins):
            px, py = self.x0 + pc[0] * cs + cs // 2, self.y0 + pc[1] * cs + cs // 2
            pygame.draw.line(surf, SEL, (px - 4, py), (px + 4, py), 1)
            pygame.draw.line(surf, SEL, (px, py - 4), (px, py + 4), 1)
            surf.blit(self.app.tiny.render(str(i + 1), True, SEL), (px + 4, py - 14))
        if self.pins:
            lines = [f'{i + 1}: {self.sim.info(*pc)}' for i, pc in enumerate(self.pins)]
            rs = [self.app.small.render(t, True, TEXT) for t in lines]
            bw = max(r_.get_width() for r_ in rs) + 16
            bh = len(rs) * 17 + 8
            box = pygame.Rect(vr.right - bw - 10, vr.y + 10, bw, bh)
            pygame.draw.rect(surf, PANEL, box)
            pygame.draw.rect(surf, PANEL_LINE, box, 1)
            for i, r_ in enumerate(rs):
                surf.blit(r_, (box.x + 8, box.y + 5 + i * 17))
            gy = box.bottom + 8
            for i, pc in enumerate(self.pins):
                h = self.hist.get(pc)
                if not h or len(h) < 2:
                    continue
                gw, gh = 240, 58
                gr = pygame.Rect(vr.right - gw - 10, gy, gw, gh)
                pygame.draw.rect(surf, PANEL, gr)
                pygame.draw.rect(surf, PANEL_LINE, gr, 1)
                for col_, idx, nm in (((110, 180, 255), 0, 'atm'), ((255, 140, 90), 1, 'C')):
                    vals = [q[idx] for q in h]
                    lo_, hi_ = min(vals), max(vals)
                    span = max(hi_ - lo_, 1e-6 if idx == 0 else 5.0)
                    pts = [(gr.x + 4 + k * (gw - 8) / (len(vals) - 1), gr.bottom - 4 - (v_ - lo_) / span * (gh - 18))
                           for k, v_ in enumerate(vals)]
                    pygame.draw.lines(surf, col_, False, pts, 1)
                    t_ = self.app.tiny.render(f'{vals[-1]:.2f} {nm}' if idx == 0 else f'{vals[-1]:.0f} {nm}', True, col_)
                    surf.blit(t_, (gr.x + 6 + idx * 110, gr.y + 3))
                surf.blit(self.app.tiny.render(str(i + 1), True, SEL), (gr.right - 12, gr.y + 3))
                gy += gh + 6
        if self.slide > 0.02 and self.slide_img is not None:
            S = G_SLAB * self.cs * self.slide_dir
            new = surf.subsurface(vr).copy()
            surf.set_clip(vr)
            surf.blit(self.slide_img, (vr.x + (self.slide - 1) * S, vr.y))
            surf.blit(new, (vr.x + self.slide * S, vr.y))
            self.slide *= 0.8
        else:
            self.slide, self.slide_img = 0.0, None
        surf.set_clip(None)
        self.draw_chrome(surf)


def main():
    pygame.init()
    pygame.display.set_caption('logic sandbox  |  ' + AUTHOR)
    pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    app = App()
    app.load()
    app.scan_chips()
    app.updater = Updater()
    if not credits_ok():
        locked_screen(pygame.display.get_surface())
        pygame.time.wait(6000)
        pygame.quit()
        return
    running = True
    restart = False
    frame = 0
    gas = None
    if np is not None and os.path.exists(os.path.join(os.path.dirname(save_path()), 'gas.npz')):
        gas = GasMode(app)      # loaded now so its circuit links keep working from the circuit screen
    while running:
        dt = clock.tick(60) / 1000
        frame += 1
        if frame % 300 == 0 and not credits_ok():
            locked_screen(pygame.display.get_surface())
            pygame.time.wait(6000)
            break
        modal = app.updater.modal()
        if app.mode == 'gas' and gas is None:
            gas = GasMode(app)
        in_gas = app.mode == 'gas' and not modal
        if app.updater.note:
            app.say(app.updater.note)
            app.updater.note = ''
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F5 and not modal:
                app.updater = Updater(manual=True)      # check for updates again
                app.say('checking for updates...')
            elif in_gas:
                if gas.handle(e) == 'quit':
                    running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and not app.editing:
                if not app.on_escape():
                    running = False
            else:
                app.handle(e)
        if in_gas and app.mode == 'gas':
            gas.update(dt)
            gas.autosave()
            if gas.sim.glinks:
                app.update(dt)      # circuits keep running so links work from here too
        else:
            app.update(dt)
            if gas is not None and gas.sim.glinks and not modal:
                gas.update(dt)      # ...and the gas keeps running behind the circuits
        app.autosave()
        if app.updater.state == 'restart':
            running = False
            restart = True
        if app.mode == 'gas' and gas is not None and not modal:
            gas.draw(pygame.display.get_surface())
        else:
            app.draw(pygame.display.get_surface())
        pygame.display.flip()
    if app.editing:
        app.finish_edit(True)
    if gas is not None:
        gas.save()
    app.save()
    pygame.quit()
    if restart:     # run the freshly installed version
        try:
            if FROZEN:
                env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')   # fresh unpack for the new process
                subprocess.Popen([sys.executable] + sys.argv[1:], env=env)
            else:
                subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
        except Exception as err:
            log_update(f'restart failed: {err!r}, start the game again by hand')


if __name__ == '__main__':
    main()
