#!/usr/bin/env python3
# logic gate sandbox
import colorsys
import hashlib
import random
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
TUBE_SPEED = 60     # px/s, the little signal tubes sliding along wires
MAX_DEPTH = 5       # chips inside chips, this many levels
MIN_ZOOM, MAX_ZOOM = 0.25, 3.0
CAMX = CAMY = 0.0   # world pixel under the top-left of the work area
ZOOM = 1.0
DPER = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]   # delay / extender lengths
RU = 12             # wire router grid, half a cell
MARGIN = 15         # wires keep this far from parts when they can
PERIODS = [5, 10, 25, 50, 100, 250, 500, 1000]   # clock half-periods in ticks
MONO = 'dejavusansmono,consolas,couriernew,menlo,monospace'
FONT = None         # set by App, used to size LABEL parts


def w2s(x, y):
    # world pixels -> screen pixels
    return PAL_W + (x - CAMX) * ZOOM, (y - CAMY) * ZOOM


def s2w(x, y):
    return (x - PAL_W) / ZOOM + CAMX, y / ZOOM + CAMY


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
SKIP = ('launcher.py',)     # only used to build the exe


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
        HDR_MEM=(160, 58, 120), HDR_CHIP=(50, 112, 190), HDR_TEXT=(255, 255, 255), DIM=(0, 0, 0)),
    'light': dict(
        BG=(234, 240, 248), GRID=(214, 223, 236), GRID2=(196, 208, 226),
        PANEL=(222, 230, 242), PANEL_LINE=(140, 162, 196),
        PART_BG=(250, 252, 255), PART_LINE=(84, 114, 166),
        TEXT=(20, 32, 54), TEXT_DIM=(112, 126, 152),
        ON=(0, 118, 214), OFF=(34, 140, 80), FLOAT=(96, 110, 142), SHORT=(212, 52, 52),
        SEL=(226, 140, 0), ACTIVE=(206, 230, 250), LAMP_ON=(255, 200, 40),
        SEG_OFF=(214, 222, 236), SEG_DEFAULT=(20, 30, 50), PREVIEW=(70, 110, 170),
        HDR_LOGIC=(132, 112, 206), HDR_INPUT=(222, 150, 60), HDR_OUTPUT=(60, 164, 176),
        HDR_MEM=(200, 100, 166), HDR_CHIP=(70, 130, 210), HDR_TEXT=(255, 255, 255), DIM=(20, 30, 50)),
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

PAL_ITEMS = ['SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GATE', 'LAMP', 'DISPLAY', 'TOUCH', '7SEG',
             'NOT', 'BUF', 'TOGGLE', 'DELAY', 'EXTENDER', 'AND', 'NAND', 'OR', 'NOR', 'XOR', 'XNOR',
             'SR LATCH', 'NV LATCH', 'GAS IN', 'GAS OUT', 'PIN', 'LABEL']

RUN_KEYS = {pygame.K_SPACE, pygame.K_UP, pygame.K_DOWN, pygame.K_l, pygame.K_t,
            pygame.K_n, pygame.K_HOME, pygame.K_TAB, pygame.K_RETURN, pygame.K_KP_ENTER}
HELP = ['enter = compile / build', 'drag out parts', 'pin-pin = wire', 'drag bg = select', 'ctrl+click = add',
        'ctrl+c x v a', 'del = delete', 'g = make chip', 'u = open chip',
        'wheel = zoom', 'rmb drag = pan', 'home = reset', 'rmb click = del',
        'dbl-click: name', 'space / n', 'up/dn = speed', 'l light  t tubes',
        'clr: ctrl+sh+del', 'tab = gas lab', 'f5 = check update']
HELP_H = 8 + len(HELP) * 15 + 26
SEG_NAMES = 'abcdefg'
# kinds with an editable description in the body (double-click the empty space)
DESC_KINDS = set(GATES) | {'SOURCE', 'SWITCH', 'BUTTON', 'GATE', 'LAMP', 'SR LATCH', 'NV LATCH', 'TOGGLE'}
DEFAULT_DESC = {'AND': 'both high', 'OR': 'any high', 'NAND': 'not both', 'NOR': 'none high',
                'XOR': 'odd count', 'XNOR': 'even count', 'NOT': 'inverts', 'BUF': 'copies',
                'SOURCE': 'always on', 'LAMP': 'glows', 'GATE': 'EN opens it',
                'SR LATCH': 'S sets, R resets', 'NV LATCH': 'remembers', 'BUTTON': '1 pulse',
                'TOGGLE': 'flips each pulse'}
IND_KINDS = ('LAMP', 'DISPLAY', 'TOUCH', '7SEG')
WIDGET_KINDS = ('SWITCH', 'BUTTON')     # these draw a little control in the body


def cat_color(kind):
    if kind in ('SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GAS IN'):
        return HDR_INPUT
    if kind in ('LAMP', 'DISPLAY', 'TOUCH', '7SEG', 'GAS OUT'):
        return HDR_OUTPUT
    if kind in ('SR LATCH', 'NV LATCH'):
        return HDR_MEM
    if kind == 'LABEL':
        return TEXT_DIM
    if kind in ('CHIP', 'PIN'):
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


def draw_wire(surf, pts, color, w):
    # outline in the opposite color so a wire never melts into the background or grid
    inv = (255 - color[0], 255 - color[1], 255 - color[2])
    ow = w + 2
    pygame.draw.lines(surf, inv, False, pts, ow)
    for q in pts[1:-1]:
        pygame.draw.rect(surf, inv, (q[0] - ow // 2, q[1] - ow // 2, ow, ow))
    pygame.draw.lines(surf, color, False, pts, w)
    if w > 1:
        for q in pts[1:-1]:
            pygame.draw.rect(surf, color, (q[0] - w // 2, q[1] - w // 2, w, w))


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


class Updater:
    # checks github on boot (and on F5), installs the repo's files if they differ
    def __init__(self, start=True, manual=False):
        self.state = 'off'      # off idle checking prompt installing failed restart
        self.message = ''
        self.sha = ''
        self.todo = []
        self.raw = {}           # files already downloaded by the fallback check
        self.note = ''          # one-line status for the toast
        self.manual = manual
        if GITHUB_REPO:
            self.state = 'checking'
            if start:
                threading.Thread(target=self._check, daemon=True).start()

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
        msg = head['commit']['message'].strip().split('\n')[0]
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
        for t in tree['tree']:
            path = t['path']
            ext = os.path.splitext(path)[1].lower()
            if t['type'] != 'blob' or ext not in SYNC_EXT or not safe_repo_path(path) \
                    or os.path.basename(path) in SKIP:
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
        self.sha, self.message, self.todo = sha, msg, todo
        self.state = 'prompt'

    def _check_raw(self):
        # api down or rate limited (60 checks an hour): just compare the main file straight from github
        url = f'https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{REPO_MAIN}?t={int(time.time())}'
        data = self._get(url, raw=True)
        local = read_local(REPO_MAIN)
        if local is not None and local.replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n'):
            self.state = 'idle'
            return
        self.sha, self.message, self.todo = '', 'new version of the game', [REPO_MAIN]
        self.raw = {REPO_MAIN: data}
        self.state = 'prompt'

    def install(self):
        self.state = 'installing'
        threading.Thread(target=self._install, daemon=True).start()

    def _fetch(self, path):
        if path in self.raw:
            return self.raw[path]
        q = urllib.parse.quote(path)
        try:
            return self._get(f'https://api.github.com/repos/{GITHUB_REPO}/contents/{q}?ref={self.sha}', raw=True)
        except Exception as err:
            log_update(f'api download of {path} failed: {err!r}, trying raw')
            return self._get(f'https://raw.githubusercontent.com/{GITHUB_REPO}/{self.sha or GITHUB_BRANCH}/{q}', raw=True)

    def _install(self):
        try:
            files = []
            for path in self.todo:
                data = self._fetch(path)
                if path.endswith('.py'):
                    compile(data, path, 'exec')      # don't install something that can't even parse
                files.append((path, data))
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
        roots = {}
        root = app.root

        def nid(p, i):
            return roots.setdefault(root[(p.uid, i)], len(roots))

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
        self.N = max(1, len(roots))
        self.roots = [None] * self.N
        for r, n in roots.items():
            self.roots[n] = r
        self.sw_on = np.zeros(len(self.si), bool)
        self.b_pulse = np.zeros(len(self.bi), bool)
        self.t_pulse = np.zeros(len(self.ti), bool)
        self.tx = np.zeros(17, np.int8)
        self.prev = None
        self.last_out = self.out.copy()
        self.last_drive = self.drive.copy()
        self.nparts = P

    def nets(self):
        val = self.out[self.dp]
        act = self.drive[self.dp]
        n1 = np.bincount(self.dn[act & (val == 1)], minlength=self.N)
        n0 = np.bincount(self.dn[act & (val == 0)], minlength=self.N)
        return (n1 > 0) & (n0 == 0), (n0 > 0) & (n1 == 0)

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
        if app.tubes:
            st = np.where(hi, 1, np.where(lo, 0, -1)).astype(np.int8)
            if self.prev is not None:
                for n in np.flatnonzero((st != self.prev) & (st >= 0)):
                    for wi in app.root_wires.get(self.roots[n], ()):
                        q = app.pending.setdefault(wi, [])
                        if len(q) < 6:
                            q.append(int(st[n]))
            self.prev = st
        else:
            self.prev = None
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
        self.anim = 0.0     # drives the signal tubes, stops while paused
        self.dirty = False
        self.last_save = 0.0
        self.path = save_path()
        self.font = pygame.font.SysFont(MONO, 16, bold=True)
        self.small = pygame.font.SysFont(MONO, 13)
        self.tiny = pygame.font.SysFont(MONO, 11, bold=True)
        self.pillf = pygame.font.SysFont(MONO, 10, bold=True)
        self.descf = pygame.font.SysFont(MONO, 11)
        self.edit_field = 'title'
        global FONT
        FONT = self.font
        self.light = False
        self.tubes = True
        self.instant = True     # gates always settle inside one tick (no race glitches)
        self.running = False    # False = build mode (frozen, editable), True = compiled and running
        self.cmp = None
        self.updater = None
        self.editing = None     # part being renamed
        self.edit_on = False
        self.edit_text = ''
        self.edit_fresh = False
        self.last_click = (None, 0)
        self.sel = set()        # selected parts
        self.clip = None        # copied parts + the wires between them
        self.pal_scroll = 0
        self.topo_key = None    # cached net layout, rebuilt when parts/wires change
        self.root = {}
        self.out_pins = []
        self.flow = []
        self.grid_cache = None
        self.pill_cache = {}
        self.prev_state = None
        self.root_wires = {}
        self.wire_root = []
        self.pulses = {}
        self.pending = {}
        self.obs_ver = None     # wire routes are redone when parts move
        self.blocked = None
        self.routes = {}
        self.occ = None         # cells used by routed wires, so new wires lay next to them
        self.occ_key = None
        self.occ_ver = 0
        self.route_budget = 12
        self.tint_cache = {}
        self.sim_parts = []     # every real part, chip insides included
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

        adj = {}
        nw = len(self.wires)
        for wi, (pa, ia, pb, ib) in enumerate(all_wires):
            ka, kb = self.k(pa, ia), self.k(pb, ib)
            ra, rb = find(ka), find(kb)
            if ra != rb:
                parent[ra] = rb
            if wi < nw:     # only the wires you can see get a flow direction
                adj.setdefault(ka, []).append((kb, wi, True))
                adj.setdefault(kb, []).append((ka, wi, False))
        self.root = {k: find(k) for k in list(parent)}
        self.out_pins, queue = [], []
        for p in sim:
            for i, (_, _, role) in enumerate(p.d['pins']):
                if role == 'out':
                    self.out_pins.append((p, i, self.root[(p.uid, i)]))
        for p in self.parts:
            for i, (_, _, role) in enumerate(p.d['pins']):
                if role == 'out':
                    queue.append(self.k(p, i))
        # which way signals travel along each wire: away from the driving pin
        flow = [None] * len(self.wires)
        seen = set(queue)
        qi = 0
        while qi < len(queue):
            node = queue[qi]
            qi += 1
            for other, wi, fwd in adj.get(node, ()):
                if flow[wi] is None:
                    flow[wi] = fwd
                if other not in seen:
                    seen.add(other)
                    queue.append(other)
        self.flow = flow
        self.wire_root = [self.root[self.k(w[0], w[1])] for w in self.wires]
        self.root_wires = {}
        for wi, r in enumerate(self.wire_root):
            self.root_wires.setdefault(r, []).append(wi)
        self.prev_state = None      # no pulses for whatever changed with the layout
        self.pulses = {}            # wire index -> [[distance, value], ...]
        self.pending = {}           # wire index -> values waiting to leave the start
        self.topo_key = self.topo_sig()

    def netstate(self):
        if self.topo_key != self.topo_sig():
            self.build_topo()
        drv = {}
        for p, i, root in self.out_pins:
            k = p.kind
            if k == 'GATE' and not p.drive:
                continue        # open gate puts nothing on the wire
            v = 1 if k == 'SOURCE' else p.out
            s = drv.get(root)
            if s is None:
                drv[root] = {v}
            else:
                s.add(v)
        return self.root.__getitem__, drv

    def track_changes(self, drv):
        # a net that changes value sends one pulse down each of its wires
        cur = {r: next(iter(s)) for r, s in drv.items() if len(s) == 1}
        prev = self.prev_state
        self.prev_state = cur
        if prev is None or not self.tubes:
            return
        for r in set(cur) | set(prev):
            if cur.get(r) != prev.get(r) and r in cur:
                for wi in self.root_wires.get(r, ()):
                    q = self.pending.setdefault(wi, [])
                    if len(q) < 6:
                        q.append(cur[r])

    def move_pulses(self, dt):
        for wi in list(self.pending.keys() | self.pulses.keys()):
            if wi >= len(self.wires):
                continue
            pa, ia, pb, ib = self.wires[wi]
            length = poly_len(self.wire_screen(self.wires[wi]))
            ps = self.pulses.setdefault(wi, [])
            for p in ps:
                p[0] += TUBE_SPEED * dt
            ps[:] = [p for p in ps if p[0] < length + 14]
            q = self.pending.get(wi)
            # next pulse only leaves once the last one is clear of the start
            if q and (not ps or ps[-1][0] > 34):
                ps.append([0.0, q.pop(0)])
            if not ps and not q:
                self.pulses.pop(wi, None)
                self.pending.pop(wi, None)

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
        self.track_changes(drv)

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
        if self.topo_key == self.topo_sig():
            self.move_pulses(dt)
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
        if self.cmp:
            self.cmp.run(n)
        else:
            for _ in range(n):
                self.step()

    def toggle_run(self):
        if self.running:
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
            version=2, rate=self.rate, light=self.light, tubes=self.tubes,
            view=[CAMX, CAMY, ZOOM],
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
            self.tubes = bool(data.get('tubes', True))
            v = data.get('view')
            if isinstance(v, list) and len(v) == 3:
                CAMX, CAMY = float(v[0]), float(v[1])
                ZOOM = max(MIN_ZOOM, min(MAX_ZOOM, float(v[2])))
            set_theme(self.light)
            self.reset_caches()
        except (KeyError, TypeError, ValueError, IndexError):
            try:
                os.replace(self.path, self.path + '.bad')   # keep the broken file
            except OSError:
                pass

    def reset_caches(self):
        self.grid_cache = None
        self.pill_cache = {}

    # ------------------------------------------------------------ helpers
    def pal_area(self, H):
        return 36, H - HELP_H

    def pal_rect(self, i):
        return pygame.Rect(12, 40 + i * 26 - self.pal_scroll, PAL_W - 24, 22)

    def scroll_palette(self, dy):
        _, H = pygame.display.get_surface().get_size()
        top, bot = self.pal_area(H)
        most = max(0, 40 + len(PAL_ITEMS) * 26 - bot)
        self.pal_scroll = max(0, min(most, self.pal_scroll + dy))

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
        self.say('chip made, dbl-click to name it, u opens it')

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
        if self.group_collides(group):
            if d['new']:
                for p in group:
                    if p in self.parts:
                        self.remove_part(p)
            else:
                for p, (gx, gy) in zip(group, d['orig']):
                    p.gx, p.gy = gx, gy
        elif pos[0] < PAL_W and d['moved']:
            for p in group:             # dropped back on the palette
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
    def modal_rects(self, W, H):
        box = pygame.Rect(0, 0, 520, 190)
        box.center = (W // 2, H // 2)
        btn = pygame.Rect(0, 0, 90, 32)
        btn.midbottom = (box.centerx, box.bottom - 16)
        return box, btn

    def handle(self, e):
        u = self.updater
        if u and u.state in ('prompt', 'installing', 'failed'):
            if u.state != 'installing':
                _, btn = self.modal_rects(*pygame.display.get_surface().get_size())
                ok = (e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)) \
                    or (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and btn.collidepoint(e.pos))
                if ok:
                    u.install() if u.state == 'prompt' else u.dismiss()
            return
        if self.running:
            # run mode: nothing can be edited, only clicked
            if e.type == pygame.KEYDOWN:
                if e.key in RUN_KEYS and not (e.mod & pygame.KMOD_CTRL):
                    self.on_key(e)
                return
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if e.pos[0] >= PAL_W:
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
            if mp[0] < PAL_W:
                self.scroll_palette(-e.y * 26)
            else:
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
        CAMX = wx - (mp[0] - PAL_W) / ZOOM
        CAMY = wy - mp[1] / ZOOM
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
        elif k == pygame.K_t:
            self.tubes = not self.tubes
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
            if self.drag is None and mx >= PAL_W:
                self.drag = dict(kind='pan', start=e.pos, cam=(CAMX, CAMY), moved=False,
                                 button=e.button)
            return
        if e.button != 1:
            return
        if self.drag and self.drag.get('carry'):
            d, self.drag = self.drag, None
            self.finish_part_drag(d, e.pos)
            return
        _, H = pygame.display.get_surface().get_size()
        if mx < PAL_W:
            top, bot = self.pal_area(H)
            if top <= my <= bot:
                for i, k in enumerate(PAL_ITEMS):
                    if self.pal_rect(i).collidepoint(e.pos):
                        p = Part(k)
                        d = dict(kind='part', parts=[p], rel=[(0, 0)],
                                 ox=p.d['w'] * C * ZOOM // 2, oy=p.d['h'] * C * ZOOM // 2, start=e.pos,
                                 moved=True, new=True, carry=False, hit=None, orig=None)
                        self.place_group(d, mx, my)
                        self.parts.append(p)
                        self.topo_key = None
                        self.sel.clear()
                        self.drag = d
                        break
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
        x0, x1 = max(PAL_W, min(x0, x1)), max(PAL_W, max(x0, x1))
        return pygame.Rect(x0, min(y0, y1), x1 - x0, abs(y1 - y0))

    # ------------------------------------------------------------ draw
    def label(self, surf, text, color, center):
        t = self.font.render(text, True, color)
        surf.blit(t, t.get_rect(center=center))

    def draw_grid(self, surf, W, H):
        surf.fill(BG)
        step = C * ZOOM
        i0 = int(CAMX // C)
        i1 = int((CAMX + (W - PAL_W) / ZOOM) // C) + 1
        for i in range(i0, i1 + 1):
            major = i % 4 == 0
            if step < 9 and not major:
                continue
            x = round(PAL_W + (i * C - CAMX) * ZOOM)
            if x >= PAL_W:
                pygame.draw.line(surf, GRID2 if major else GRID, (x, 0), (x, H))
        j0 = int(CAMY // C)
        j1 = int((CAMY + H / ZOOM) // C) + 1
        for j in range(j0, j1 + 1):
            major = j % 4 == 0
            if step < 9 and not major:
                continue
            y = round((j * C - CAMY) * ZOOM)
            pygame.draw.line(surf, GRID2 if major else GRID, (PAL_W, y), (W, y))

    def pill(self, text):
        key = (text, self.light)
        s = self.pill_cache.get(key)
        if s is None:
            color = ON if text == 'ON' else OFF
            t = self.pillf.render(text, True, color)
            s = pygame.Surface((t.get_width() + 6, 11))
            s.fill(PANEL)
            pygame.draw.rect(s, color, s.get_rect(), 1)
            s.blit(t, (3, (11 - t.get_height()) // 2))
            self.pill_cache[key] = s
        return s

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
        txt = ZOOM >= 0.55          # skip text when zoomed way out
        if k == 'LABEL':
            text = self.label_text(p)
            r = pygame.Rect(r.x, r.y, round(label_w(text) * C * ZOOM), r.h)
            if editing or not text.strip():
                pygame.draw.rect(surf, SEL if editing else FLOAT, r, 1)
            if txt:
                self.label(surf, text, SEL if editing and self.edit_fresh else TEXT, r.center)
            return
        hdrh = sc(HDR)
        if k in ('DISPLAY', 'TOUCH'):
            pygame.draw.rect(surf, p.rgb if p.glow > 0 and p.rgb else PART_BG, r)
            pygame.draw.rect(surf, SEL if editing else (ON if p.flash > 0 else PART_LINE), r, 1)
        else:
            body = PART_BG
            if k == 'LAMP' and p.glow > 0:
                body = LAMP_ON
            elif k == 'SOURCE' or (k == 'SWITCH' and p.on) or (k == 'BUTTON' and p.flash > 0) \
                    or (k in ('CLOCK', 'SR LATCH', 'NV LATCH', 'GATE') and (p.out and (k != 'GATE' or p.drive))):
                body = ACTIVE
            pygame.draw.rect(surf, body, r)
            hdr = pygame.Rect(r.x, r.y, r.w, hdrh)
            pygame.draw.rect(surf, cat_color(k), hdr)
            if txt:
                text = self.label_text(p)
                if text.strip():
                    t = self.tiny.render(text, True, SEL if editing and self.edit_fresh else HDR_TEXT)
                    surf.set_clip(hdr.inflate(-4, 0))
                    surf.blit(t, t.get_rect(center=hdr.center))
                    surf.set_clip(None)
            pygame.draw.rect(surf, SEL if editing else PART_LINE, r, 1)
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
                pygame.draw.rect(surf, TEXT_DIM, track, 1)
                kx = track.right - sc(10) if p.on else track.x + sc(2)
                pygame.draw.rect(surf, ON if p.on else TEXT_DIM, (kx, track.y + sc(2), sc(8), sc(6)))
            elif k == 'BUTTON':
                b = pygame.Rect(cx - sc(10), cy - sc(5), sc(20), sc(10))
                pygame.draw.rect(surf, ON if p.flash > 0 else PART_BG, b)
                pygame.draw.rect(surf, TEXT_DIM, b, 1)
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
            elif k == 'CHIP' and p.inds:
                self.draw_chip_body(surf, p, r, hdrh)
        # pins
        small = k in ('DISPLAY', 'TOUCH')
        o, i_ = (sc(7, 3), sc(3, 2)) if small else (sc(9, 4), sc(5, 2))
        for i in range(len(p.d['pins'])):
            q = p.pin_pos(i)
            pygame.draw.rect(surf, BG, (q[0] - o // 2, q[1] - o // 2, o, o))
            pygame.draw.rect(surf, pcol(p, i), (q[0] - i_ // 2, q[1] - i_ // 2, i_, i_))
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

    def draw(self, surf):
        W, H = surf.get_size()
        self.draw_grid(surf, W, H)
        find, drv = self.netstate()
        mp = pygame.mouse.get_pos()

        k_ = self.k

        def pcol(p, i):
            return self.net_color(drv.get(find(k_(p, i))))

        # wires
        for wi, (pa, ia, pb, ib) in enumerate(self.wires):
            pts = self.wire_screen(self.wires[wi])
            s = drv.get(find(k_(pa, ia)))
            color = self.net_color(s)
            if len(s or ()) < 2:
                color = self.tint(self.wires[wi], 'float' if not s else ('on' if 1 in s else 'off'))
            w = 1 if not s else (2 if s == {0} else 3)
            draw_wire(surf, pts, color, w)

        # signal pulses: one per change, sliding away from the driver
        if self.tubes and self.topo_key == self.topo_sig():
            for wi, ps in self.pulses.items():
                if wi >= len(self.wires) or self.flow[wi] is None:
                    continue
                pts = self.wire_screen(self.wires[wi])
                path = pts if self.flow[wi] else pts[::-1]
                length = poly_len(pts)
                for dist, val in ps:
                    if dist > length:
                        continue
                    pill = self.pill('ON' if val == 1 else 'OFF')
                    x, y = point_at(path, dist)
                    surf.blit(pill, (int(x) - pill.get_width() // 2, int(y) - pill.get_height() // 2))

        if self.drag and self.drag['kind'] == 'wire':
            pa, ia = self.drag['a']
            draw_wire(surf, wire_pts(pa.pin_pos(ia), mp), PREVIEW, 2)

        view = pygame.Rect(PAL_W, 0, W - PAL_W, H)
        for p in self.parts:
            if p.rect().colliderect(view):
                self.draw_part(surf, p, pcol)

        for p in self.sel:
            pygame.draw.rect(surf, SEL, p.rect().inflate(6, 6), 2)

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

        # palette
        pygame.draw.rect(surf, PANEL, (0, 0, PAL_W, H))
        pygame.draw.line(surf, PANEL_LINE, (PAL_W - 1, 0), (PAL_W - 1, H))
        self.label(surf, 'PARTS', TEXT, (PAL_W // 2, 18))
        top, bot = self.pal_area(H)
        self.scroll_palette(0)
        surf.set_clip(pygame.Rect(0, top, PAL_W - 1, bot - top))
        for i, k in enumerate(PAL_ITEMS):
            r = self.pal_rect(i)
            if r.bottom < top or r.top > bot:
                continue
            hov = r.collidepoint(mp) and top <= mp[1] <= bot
            pygame.draw.rect(surf, PART_BG, r)
            pygame.draw.rect(surf, PART_LINE if hov else PANEL_LINE, r, 1)
            pygame.draw.rect(surf, cat_color(k), (r.x, r.y, 4, r.h))
            t = self.small.render(k, True, TEXT)
            surf.blit(t, (r.x + 10, r.centery - t.get_height() // 2))
        surf.set_clip(None)
        hy = H - HELP_H
        pygame.draw.line(surf, PANEL_LINE, (8, hy), (PAL_W - 8, hy))
        for i, t in enumerate(HELP):
            surf.blit(self.small.render(t, True, TEXT_DIM), (12, hy + 8 + i * 15))
        surf.blit(self.small.render(f"{self.rate} ticks/s", True, TEXT), (12, H - 22))
        W_ = surf.get_width()
        mt = self.font.render('RUN (compiled)' if self.running and self.cmp else 'RUN' if self.running else 'BUILD, enter = run',
                              True, ON if self.running else SEL)
        mr = pygame.Rect(W_ - mt.get_width() - 24, 8, mt.get_width() + 14, mt.get_height() + 6)
        pygame.draw.rect(surf, PANEL, mr)
        pygame.draw.rect(surf, ON if self.running else SEL, mr, 1)
        surf.blit(mt, (mr.x + 7, mr.y + 3))
        if self.paused:
            t = self.font.render('PAUSED', True, SEL)
            pr = pygame.Rect(PAL_W + 10, 8, t.get_width() + 14, t.get_height() + 6)
            pygame.draw.rect(surf, PANEL, pr)
            pygame.draw.rect(surf, SEL, pr, 1)
            surf.blit(t, (pr.x + 7, pr.y + 3))

        # pin label on hover
        if mp[0] >= PAL_W and not (d and d['kind'] in ('part', 'box')):
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
                pygame.draw.rect(surf, PANEL, (x, y, w, h))
                pygame.draw.rect(surf, PART_LINE, (x, y, w, h), 1)
                surf.blit(t, (x + 5, y + 3))

        if self.toast[0] and time.time() < self.toast[1]:
            t = self.font.render(self.toast[0], True, TEXT)
            tr = pygame.Rect(0, 0, t.get_width() + 24, t.get_height() + 14)
            tr.midtop = ((W + PAL_W) // 2, 12)
            pygame.draw.rect(surf, PANEL, tr)
            pygame.draw.rect(surf, SEL, tr, 1)
            surf.blit(t, t.get_rect(center=tr.center))

        u = self.updater
        if u and u.state in ('prompt', 'installing', 'failed'):
            dim = pygame.Surface((W, H), pygame.SRCALPHA)
            dim.fill((*DIM, 170))
            surf.blit(dim, (0, 0))
            box, btn = self.modal_rects(W, H)
            pygame.draw.rect(surf, PANEL, box)
            pygame.draw.rect(surf, PART_LINE, box, 2)
            self.label(surf, 'UPDATE', TEXT, (box.centerx, box.y + 26))
            if u.state == 'prompt':
                self.label(surf, 'new update:', TEXT_DIM, (box.centerx, box.y + 62))
                for i, line in enumerate(wrap(self.font, u.message, box.w - 40)[:3]):
                    self.label(surf, line, ON, (box.centerx, box.y + 88 + i * 20))
            elif u.state == 'installing':
                self.label(surf, 'installing...', TEXT, (box.centerx, box.centery))
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
             'Ar', 'Ne', 'NH3', 'CO', 'C4H10', 'C2H2', 'C2H5OH', 'Cl2', 'SF6']
G_IDX = {s: i for i, s in enumerate(G_SPECIES)}
G_MASS = [28, 32, 2, 44, 16, 44, 18, 4, 40, 20, 17, 28, 58, 26, 46, 71, 146]                 # g/mol
G_CV = [2.5, 2.5, 2.5, 8.0, 3.3, 3.5, 3.0, 1.5, 1.5, 1.5, 3.4, 2.5, 10.5, 4.0, 8.0, 3.1, 10.0]         # heat capacity, in units of R
G_COLOR = [(46, 66, 108), (60, 100, 160), (130, 70, 190), (170, 145, 40), (60, 140, 85),
           (110, 110, 110), (90, 150, 180), (180, 100, 150),
           (120, 90, 200), (230, 90, 110), (200, 215, 110), (150, 120, 90), (205, 130, 60),
           (240, 190, 90), (190, 120, 170), (150, 200, 60), (90, 205, 190)]
G_NICE = {'N2': 'N2', 'O2': 'O2', 'H2': 'H2', 'C3H8': 'propane', 'CH4': 'methane',
          'CO2': 'CO2', 'H2O': 'steam', 'He': 'He', 'Ar': 'argon', 'Ne': 'neon', 'NH3': 'ammonia',
          'CO': 'CO', 'C4H10': 'butane', 'C2H2': 'acetylene', 'C2H5OH': 'ethanol', 'Cl2': 'chlorine',
          'SF6': 'SF6'}
# fuel: (O2 needed per fuel, products, heat released / R per mol, activation temp K)
G_FUELS = {'H2': (0.5, {'H2O': 1}, 29100, 7000),
           'C3H8': (5, {'CO2': 3, 'H2O': 4}, 245800, 8500),
           'CH4': (2, {'CO2': 1, 'H2O': 2}, 96460, 9500),
           'CO': (0.5, {'CO2': 1}, 34000, 8500),
           'C4H10': (6.5, {'CO2': 4, 'H2O': 5}, 346000, 8500),
           'C2H2': (2.5, {'CO2': 2, 'H2O': 1}, 156000, 7000),
           'C2H5OH': (3, {'CO2': 2, 'H2O': 3}, 153600, 9000),
           'NH3': (0.75, {'N2': 0.5, 'H2O': 1.5}, 38000, 11000)}
G_AIR = {'N2': 0.79, 'O2': 0.21}
# solid kinds: (name, strength in atm per cell of thickness (0 = never breaks), color)
G_SOLIDS = [None, ('WALL', 60, (150, 160, 178)), ('STEEL', 0, (100, 108, 122)),
            ('GLASS', 4, (150, 210, 225)), ('IGNITER', 60, (235, 125, 30)),
            ('VALVE', 60, (200, 60, 60)), ('SENSOR', 60, (150, 90, 200)),
            ('FILTER', 60, (120, 200, 190)), ('CHECK VALVE', 60, (205, 175, 60)),
            ('HEATER', 60, (240, 90, 40)), ('COOLER', 60, (80, 170, 240)),
            ('PUMP', 60, (90, 200, 90)), ('SOURCE', 60, (230, 230, 110)),
            ('VENT', 60, (70, 70, 80)), ('LINK', 60, (235, 235, 245))]
G_WALL, G_STEEL, G_GLASS, G_IGNITER, G_VALVE, G_SENSOR = 1, 2, 3, 4, 5, 6
G_FILTER, G_CHECK, G_HEATER, G_COOLER, G_PUMP, G_SOURCE, G_VENT, G_LINK = 7, 8, 9, 10, 11, 12, 13, 14
G_PASS = (G_FILTER, G_CHECK, G_PUMP)    # gas flows through these cells
G_HEAT_LEVELS = [400, 600, 900, 1400, 2200]     # K
G_COOL_LEVELS = [270, 230, 180, 120, 77]        # K
G_RATE = 0.12       # source emit rate per step
G_PUMP_V = 0.15     # pump face speed
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
G_MECH = ('SHAFT', 'COG', 'HINGE', 'ROD')
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
          ('SHAFT', None), ('COG', None), ('HINGE', None), ('ROD', None),
          ('BLK SENSOR', None), ('TEMP SENSOR', None), ('PRES SENSOR', None), ('HINGE SENSOR', None), ('TIMER', None),
          ('AIR', G_AIR), ('HYDROGEN', {'H2': 1}),
          ('PROPANE', {'C3H8': 1}), ('METHANE', {'CH4': 1}), ('OXYGEN', {'O2': 1}),
          ('HELIUM', {'He': 1}), ('CO2', {'CO2': 1}),
          ('NITROGEN', {'N2': 1}), ('STEAM', {'H2O': 1}), ('ARGON', {'Ar': 1}), ('NEON', {'Ne': 1}),
          ('AMMONIA', {'NH3': 1}), ('CO', {'CO': 1}), ('BUTANE', {'C4H10': 1}),
          ('ACETYLENE', {'C2H2': 1}), ('ETHANOL', {'C2H5OH': 1}), ('CHLORINE', {'Cl2': 1}),
          ('SF6', {'SF6': 1}),
          ('H2+O2 2:1', {'H2': 2 / 3, 'O2': 1 / 3}), ('CH4+O2 1:2', {'CH4': 1 / 3, 'O2': 2 / 3}),
          ('C3H8+O2 1:5', {'C3H8': 1 / 6, 'O2': 5 / 6}), ('CO+O2 2:1', {'CO': 2 / 3, 'O2': 1 / 3}),
          ('VACUUM', None)]
G_SOLID_MATS = {'WALL': G_WALL, 'STEEL': G_STEEL, 'GLASS': G_GLASS, 'IGNITER': G_IGNITER,
                'VALVE': G_VALVE, 'FILTER': G_FILTER, 'CHECK VALVE': G_CHECK, 'HEATER': G_HEATER,
                'COOLER': G_COOLER, 'PUMP': G_PUMP, 'SOURCE': G_SOURCE, 'VENT': G_VENT}
G_DEFAULT_AUX = {G_FILTER: G_IDX['H2'], G_CHECK: 0, G_HEATER: 2, G_COOLER: 2, G_PUMP: 0, G_SOURCE: G_IDX['H2']}
G_TOOLS = ['BRUSH', 'LINE', 'RECT', 'FILL', 'ERASE', 'SELECT']
G_K = 0.08          # how hard pressure pushes
G_DAMP = 0.985      # flow friction
G_DIFF = 0.02       # gases mixing
G_HEAT = 0.05       # heat conduction
G_BURN = 0.35       # burn speed once lit
G_EFF = 0.6         # share of the reaction heat that stays (real flames lose some)
G_BURN_A = {f: 0.25 / math.exp(-v[3] / 1500) for f, v in G_FUELS.items()}   # 0.25/step at 1500K
G_BUOY = 1e-3       # how fast light / hot gas rises and heavy gas sinks
G_PDV = 0.35         # compression heating / expansion cooling
G_PUSH = 0.01       # how hard pressure shoves blocks
G_BODY_DENSITY = 1.0
G_BODY_G = 0.0015   # block gravity
G_COOL = 0.0004     # hot gas slowly radiating heat away
G_WALLCOOL = 0.01   # walls soak up heat from gas touching them
G_VISC = 0.03
G_ADV = 0.8         # flow carries its own momentum: speeds up in narrow pipes, pressure drops there (bernoulli)
G_HELP = ['tab = circuits', 'lmb = tool, rmb = erase', 'wheel = size / scroll', 'e = ignite',
          'space = pause, . = step', 'up/dn = speed', 'o = open edges', 'g = gravity',
          'hold p = valves', 'hold k = starter', 'i = pin readout', 'select + ctrl+c/v',
          'm = symmetry, rmb = erase with tool',
          'click block = cycle it', 'a = reset air', 'clr: ctrl+sh+del']


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
        self.open = True                        # edges open to the outside air
        self.gravity = True
        self.starter = False                    # hold k: motor spins the shafts up
        self.manual_valves = False              # P held: opens valves that aren't linked to a sensor
        self.valve_open = np.zeros(shape, bool)
        self.link = np.full(shape, -1, np.int32)    # valve/igniter -> sensor key (x * H2 + y), -1 = manual
        self.sensors = {}                       # (x, y) -> dict(type, dir, level, on)
        self.spark_t = np.zeros(shape, np.int16)
        self.aux = np.zeros(shape, np.int8)        # filter gas / direction / level / source gas
        self.glinks = {}                        # (x, y) -> dict(id, tgt, role, on) circuit links
        self.shafts = []                        # dict(x, y, R, th, om)
        self.hinges = []                        # dict(kind, ref, ox, oy, cx, cy)
        self.rods = []                          # dict(a, b, L) between two hinges
        self.meshes = []                        # dict(a, b, k): two cogs whose teeth touch turn together
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
        self.n[:] = self.amb_field
        self.T[:] = 293
        self.n[:, self.solid] = 0
        self.u[:] = 0
        self.v[:] = 0
        self.active = {0, 1}

    def clear(self):
        self.shafts, self.hinges, self.rods, self.meshes = [], [], [], []
        self.cogmask[:] = False
        self.sensors = {}
        self.glinks = {}
        self.aux[:] = 0
        self.comp_cache = {}
        self.link[:] = -1
        self.valve_open[:] = False
        self.spark_t[:] = 0
        self.kind[:] = 0
        self.strength[:] = 0
        self.bodies = []
        self.debris = []
        self.rebuild()
        self.reset_air()

    def rebuild(self):
        sol = (self.kind > 0) & ~self.valve_open & ~self.passable[self.kind]
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
        elif k in (G_HEATER, G_COOLER):
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
        self.link[mask] = link if kind in (G_VALVE, G_IGNITER) else -1
        self.valve_open[mask] = False
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

    def erase(self, mask):
        mask = mask & ~self.ring
        hit = mask & (self.kind > 0)
        self.comp_cache = {}
        self.remove_sensors(hit)
        self.aux[hit] = 0
        self.kind[hit] = 0
        self.strength[hit] = 0
        self.link[hit] = -1
        self.valve_open[hit] = False
        self.T[hit] = 293      # the hole starts empty and gas rushes in
        self.bodies = [b for b in self.bodies
                       if not mask[b['x']:b['x'] + b['w'], b['y']:b['y'] + b['h']].any()]
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
    def copy_region(self, x0, y0, x1, y1):
        x0, x1 = sorted((max(1, x0), min(self.W2 - 2, x1)))
        y0, y1 = sorted((max(1, y0), min(self.H2 - 2, y1)))
        sl = (slice(x0, x1 + 1), slice(y0, y1 + 1))
        inside = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
        clip = dict(w=x1 - x0 + 1, h=y1 - y0 + 1, x0=x0, y0=y0,
                    n=self.n[(slice(None),) + sl].copy(), T=self.T[sl].copy(), kind=self.kind[sl].copy(),
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
        self.comp_cache = {}
        self.rebuild()
        self.update_valves()
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
        if self.rods or self.meshes:
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
            n[:, ring] = self.amb_ring
            T[ring] = 293
        else:
            sol[ring] = True
            n[:, ring] = 0
        self.age += 1
        # blocks and cracking walls work on the whole grid before the gas moves
        if self.bodies or self.shafts or self.cogmask.any() or self.sensors or (self.age % 4 == 0 and self.strength.any()):
            p0 = n.sum(0) * T / 293
            if self.bodies or self.shafts:
                self.move_bodies(p0)
            if self.sensors:
                self.sense(p0)
            if self.age % 4 == 0:
                self.check_breaks(p0)    # walls crack when the pressure across them is too much
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
        np.clip(u, -0.4, 0.4, out=u)
        np.clip(v, -0.4, 0.4, out=v)
        # never move more than 70% of a cell out in one step
        up, un = np.maximum(u, 0), np.minimum(u, 0)
        vp, vn = np.maximum(v, 0), np.minimum(v, 0)
        out = np.zeros_like(T)
        out[:-1] += up
        out[1:] -= un
        out[:, :-1] += vp
        out[:, 1:] -= vn
        s = np.minimum(1.0, 0.7 / (out + 1e-9))
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
        E[:-1] -= ex
        E[1:] += ex
        E[:, :-1] -= ey
        E[:, 1:] += ey
        np.maximum(n, 0, out=n)
        C = (cvv @ n.reshape(S, -1)).reshape(T.shape)
        T[:] = np.where(C > 1e-5, E / np.maximum(C, 1e-5), 293)
        full[idx] = n
        n = full
        S = n.shape[0]
        if self.has & {G_FILTER, G_HEATER, G_COOLER, G_SOURCE, G_VENT}:
            self.devices(n, T, sol)
        # sparks from igniters
        if self.spark_t.any():
            sm = (self.spark_t > 0) & ~sol
            T[sm] = np.maximum(T[sm], 1900)
            self.spark_t[self.spark_t > 0] -= 1
        # burning: reaction speed climbs steeply with temperature (arrhenius)
        if (T > 650).any():
            o2 = G_IDX['O2']
            for f, (nu, prods, dh, ta) in G_FUELS.items():
                fi = G_IDX[f]
                m = (T > 650) & (n[fi] > 1e-5) & (n[o2] > 1e-5)
                if not m.any():
                    continue
                k = np.minimum(G_BURN, G_BURN_A[f] * np.exp(-ta / np.maximum(T, 1)))
                b = np.where(m, k * np.minimum(n[fi], n[o2] / nu), 0)
                e = (self.cvv @ n.reshape(S, -1)).reshape(T.shape) * T + b * dh * G_EFF
                n[fi] -= b
                n[o2] -= nu * b
                for pr, kk in prods.items():
                    n[G_IDX[pr]] += kk * b
                    self.active.add(G_IDX[pr])
                C = (self.cvv @ n.reshape(S, -1)).reshape(T.shape)
                T[:] = np.where(C > 1e-5, e / np.maximum(C, 1e-5), 293)
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
        T[sol] = 293

    def render(self):
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
        kind = self.kind[1:-1, 1:-1]
        for i in range(1, len(G_SOLIDS)):
            col[kind == i] = G_SOLIDS[i][2]
        aux = self.aux[1:-1, 1:-1]
        gx = np.arange(kind.shape[0])[:, None]
        gy = np.arange(kind.shape[1])[None, :]
        for kd in (G_CHECK, G_PUMP):
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
        col[self.cogmask[1:-1, 1:-1]] = (70, 78, 100)      # cog body, the drawn outline goes on top
        for (x, y), sn in self.sensors.items():
            c = G_SENSOR_COLOR[sn['type']]
            col[x - 1, y - 1] = tuple(min(255, v + 90) for v in c) if sn['on'] else c
        for b in self.bodies:
            x, y, w, h = b['x'] - 1, b['y'] - 1, b['w'], b['h']
            col[x:x + w, y:y + h] = G_BLOCK_EDGE
            if w > 2 and h > 2:
                col[x + 1:x + w - 1, y + 1:y + h - 1] = G_BLOCK_COLOR
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
        if tot < 1e-3:
            return 'vacuum'
        p = tot * float(self.T[x, y]) / 293
        parts = sorted(((float(a) / tot, G_NICE[s]) for s, a in zip(G_SPECIES, n)), reverse=True)
        mix = ' '.join(f'{name} {f * 100:.0f}%' for f, name in parts[:3] if f > 0.03)
        return f'{p:.2f} atm  {float(self.T[x, y]) - 273:.0f}C  {mix}'

    def save(self, path):
        tmp = path + '.tmp'
        bodies = np.array([[b['x'], b['y'], b['w'], b['h'], b['vx'], b['vy']] for b in self.bodies],
                          np.float32).reshape(-1, 6)
        with open(tmp, 'wb') as f:
            sens = np.array([[x, y, G_SENSOR_KINDS.index(v['type']), v['dir'], v['level']]
                             for (x, y), v in self.sensors.items()], np.int32).reshape(-1, 5)
            np.savez_compressed(f, n=self.n, T=self.T, kind=self.kind, strength=self.strength,
                                bodies=bodies, open=np.array(self.open), gravity=np.array(self.gravity),
                                sensors=sens, link=self.link, aux=self.aux,
                                shafts=np.array([[q['x'], q['y'], q['R'], q['th'], q['om'], q.get('teeth', 0), q.get('tl', 0)]
                                                 for q in self.shafts], np.float64).reshape(-1, 7),
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
            self.cogmask[:] = False
            if 'shafts' in d:
                for row in d['shafts'].tolist():
                    x, y, R, th, om = row[:5]
                    q = dict(x=x, y=y, R=R, th=th, om=om)
                    if len(row) > 5 and row[5]:
                        q['teeth'], q['tl'] = int(row[5]), row[6]
                    self.shafts.append(q)
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
            self.glinks = {}
            if 'glinks' in d:
                for x, y, lid, tx_, ty_, rx_ in d['glinks'].tolist():
                    self.glinks[(x, y)] = dict(id=lid, tgt=(tx_, ty_) if tx_ >= 0 else None,
                                               role='rx' if rx_ else 'tx', on=False)
            self.comp_cache = {}
            self.open = bool(d['open'])
            if 'gravity' in d:
                self.gravity = bool(d['gravity'])
            self.update_ambient()
            self.rebuild()
            live = self.n.reshape(self.n.shape[0], -1).max(1) > 1e-7
            self.active = set(np.nonzero(live)[0].tolist()) | {0, 1}


class GasMode:
    # the gas lab screen: same window, tab flips between this and the circuits
    def __init__(self, app):
        self.app = app
        self.sim = GasSim()
        self.tool = 'BRUSH'
        self.mat = 'WALL'
        self.size = 2
        self.speed = 4          # sim steps per frame
        self.paused = False
        self.drag = None
        self.dirty = False
        self.last_save = time.time()
        self.path = os.path.join(os.path.dirname(save_path()), 'gas.npz')
        self.cs, self.x0, self.y0 = 5, PAL_W, 0
        self.link_sensor = None     # sensor that new valves / igniters get hooked to
        self.link_target = None     # sensor / valve / igniter that the next LINK cell connects to
        self.link_id = 1
        self.rod_first = None       # first hinge of a rod being placed
        self.sym = 0                # mirror drawing: 0 off, 1 left/right, 2 up/down, 3 both
        self.cog_prev = None        # cog being sized: base chosen, now picking tooth length
        self.sel = None             # SELECT tool rectangle (cell corners)
        self.clip = None
        self.pasting = False
        self.pins = []              # cells with a live readout
        self.sps, self._steps, self._t0 = 240.0, 0, time.time()
        self.mat_scroll = 0
        self.list_bottom = 560
        try:
            if os.path.exists(self.path):
                self.sim.load(self.path)
        except Exception:
            try:
                os.replace(self.path, self.path + '.bad')
            except OSError:
                pass

    # layout
    def layout(self, W, H):
        self.cs = max(1, min((W - PAL_W) // GW, H // GH))
        self.x0 = PAL_W + ((W - PAL_W) - GW * self.cs) // 2
        self.y0 = (H - GH * self.cs) // 2

    def cell(self, pos, clamp=True):
        cx = (pos[0] - self.x0) // self.cs
        cy = (pos[1] - self.y0) // self.cs
        if clamp:
            return (max(0, min(GW - 1, cx)), max(0, min(GH - 1, cy)))
        return (cx, cy) if 0 <= cx < GW and 0 <= cy < GH else None

    def tool_rect(self, i):
        return pygame.Rect(12, 40 + i * 24, PAL_W - 24, 20)

    def mat_top(self):
        return 40 + len(G_TOOLS) * 24 + 26

    def mat_rect(self, i):
        return pygame.Rect(12, self.mat_top() + i * 21 - self.mat_scroll, PAL_W - 24, 19)

    def clamp_scroll(self):
        room = self.list_bottom - self.mat_top()
        self.mat_scroll = max(0, min(self.mat_scroll, len(G_MATS) * 21 - room))

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
            if self.link_sensor and self.mat in ('VALVE', 'IGNITER'):
                link = self.link_sensor[0] * sim.H2 + self.link_sensor[1]
            sim.set_solid(mask, G_SOLID_MATS[self.mat], link)
        elif self.mat in G_SENSOR_TYPES or self.mat in ('LINK',) + G_MECH:
            pass        # sensors and links are placed one click at a time
        elif self.mat == 'BLOCK':
            self.app.say('draw blocks with RECT')
        elif self.mat == 'VACUUM':
            sim.drain(mask, 0.5 if amount < 1 else 0.0)
        else:
            sim.add_gas(mask, dict(G_MATS)[self.mat], amount)
        self.dirty = True

    # input
    def handle(self, e):
        # returns 'quit' when esc should close the game
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
                elif self.link_sensor or self.link_target or self.rod_first:
                    self.link_sensor = self.link_target = self.rod_first = None
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
                self.speed = min(16, self.speed * 2)
            elif k == pygame.K_DOWN:
                self.speed = max(1, self.speed // 2)
            elif k == pygame.K_o:
                self.sim.open = not self.sim.open
                self.dirty = True
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
            elif pygame.mouse.get_pos()[0] < PAL_W:
                self.mat_scroll -= e.y * 42
                self.clamp_scroll()
            else:
                self.size = max(0, min(36, self.size + e.y))
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
            if e.pos[0] < PAL_W:
                for i, t in enumerate(G_TOOLS):
                    if self.tool_rect(i).collidepoint(e.pos):
                        self.tool = t
                for i, (m, _) in enumerate(G_MATS):
                    r = self.mat_rect(i)
                    if r.collidepoint(e.pos) and r.top >= self.mat_top() - 4 and r.bottom <= self.list_bottom + 2:
                        self.mat = m
                        if m not in ('VALVE', 'IGNITER'):
                            self.link_sensor = None
                        if m != 'LINK':
                            self.link_target = None
                        if m != 'ROD':
                            self.rod_first = None
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
                if self.mat == 'LINK':
                    if kd == G_LINK:
                        lk = self.sim.glinks.get(key)
                        if lk:
                            lk['id'] = lk['id'] % 16 + 1
                            self.link_id = lk['id']
                            self.dirty = True
                            self.app.say(self.sim.describe(*key))
                    elif sn or kd in (G_VALVE, G_IGNITER):
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
                if sn and self.mat in ('VALVE', 'IGNITER'):
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

    def update(self, dt):
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
                if time.perf_counter() - t0 > 0.014:
                    break       # slow pc: keep the frame rate, run the sim slower
            self.sim.move_debris(done, dt)
            self._steps += done
            if time.time() - self._t0 >= 1.0:
                self.sps = self._steps / (time.time() - self._t0)
                self._steps, self._t0 = 0, time.time()
            self.dirty = True

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.sim.save(self.path)
        except OSError as err:
            print('gas save failed:', err)
        self.dirty = False
        self.last_save = time.time()

    def autosave(self):
        if self.dirty and time.time() - self.last_save >= 10:
            self.save()

    # drawing
    def draw(self, surf):
        W, H = surf.get_size()
        self.layout(W, H)
        surf.fill(BG)
        img = pygame.surfarray.make_surface(self.sim.render())
        if self.cs != 1:
            img = pygame.transform.scale(img, (GW * self.cs, GH * self.cs))
        surf.blit(img, (self.x0, self.y0))
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
        def scr(px, py):
            return (int(self.x0 + (px - 1) * cs), int(self.y0 + (py - 1) * cs))
        def draw_teeth(sh):
            P = 2 * math.pi / sh['teeth']
            for i in range(sh['teeth']):
                a0 = sh['th'] + i * P
                a1 = a0 + P / 2
                Ri, Ro = sh['R'] - 0.5, sh['R'] + sh['tl']
                pts = [scr(sh['x'] + Ri * math.cos(a), sh['y'] + Ri * math.sin(a)) for a in (a0, a1)] + \
                      [scr(sh['x'] + Ro * math.cos(a), sh['y'] + Ro * math.sin(a)) for a in (a1, a0)]
                pygame.draw.polygon(surf, (70, 78, 100), pts)
                pygame.draw.polygon(surf, (150, 160, 182), pts, 1)
        for sh in sim.shafts:
            c0 = scr(sh['x'], sh['y'])
            R = int(sh['R'] * cs)
            if sh.get('teeth'):
                draw_teeth(sh)
            pygame.draw.circle(surf, (52, 58, 76), c0, R)
            pygame.draw.circle(surf, (150, 160, 182), c0, R, 2)
            for k in range(4):
                a_ = sh['th'] + k * math.pi / 2
                pygame.draw.line(surf, (90, 98, 120), c0, (c0[0] + R * math.cos(a_), c0[1] + R * math.sin(a_)), 1)
            pygame.draw.circle(surf, (150, 160, 182), c0, 3)
            rpm = sh['om'] / (2 * math.pi) * self.sps * 60
            t = self.app.tiny.render(f'{rpm:.0f} rpm', True, (200, 205, 220))
            surf.blit(t, (c0[0] - t.get_width() // 2, c0[1] + R + 3))
        for r in sim.rods:
            pa, pb = sim.hinge_pos(r['a']), sim.hinge_pos(r['b'])
            pygame.draw.line(surf, (30, 32, 40), scr(pa[0], pa[1]), scr(pb[0], pb[1]), max(4, cs + 1))
            pygame.draw.line(surf, (200, 204, 214), scr(pa[0], pa[1]), scr(pb[0], pb[1]), max(2, cs - 1))
        for h in sim.hinges:
            hp = scr(*sim.hinge_pos(h)[:2])
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
        if mp[0] >= PAL_W and self.tool != 'FILL':
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
        if c and mp[0] >= PAL_W:
            t = self.app.small.render(self.sim.info(*c), True, TEXT)
            r = pygame.Rect(0, 0, t.get_width() + 12, t.get_height() + 6)
            r.bottomright = (W - 8, H - 8)
            pygame.draw.rect(surf, PANEL, r)
            pygame.draw.rect(surf, PART_LINE, r, 1)
            surf.blit(t, (r.x + 6, r.y + 3))
        # palette
        pygame.draw.rect(surf, PANEL, (0, 0, PAL_W, H))
        pygame.draw.line(surf, PANEL_LINE, (PAL_W - 1, 0), (PAL_W - 1, H))
        self.app.label(surf, 'GAS LAB', TEXT, (PAL_W // 2, 18))
        for i, t in enumerate(G_TOOLS):
            r = self.tool_rect(i)
            on = t == self.tool
            pygame.draw.rect(surf, ACTIVE if on else PART_BG, r)
            pygame.draw.rect(surf, SEL if on else PANEL_LINE, r, 1)
            surf.blit(self.app.small.render(t, True, TEXT), (r.x + 8, r.y + 2))
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
            box = pygame.Rect(W - bw - 10, 10, bw, bh)
            pygame.draw.rect(surf, PANEL, box)
            pygame.draw.rect(surf, PANEL_LINE, box, 1)
            for i, r_ in enumerate(rs):
                surf.blit(r_, (box.x + 8, box.y + 5 + i * 17))
        self.list_bottom = H - (len(G_HELP) * 15 + 30) - 6
        self.clamp_scroll()
        surf.blit(self.app.small.render('MATERIAL  (scroll)', True, TEXT_DIM), (12, self.mat_top() - 20))
        surf.set_clip(pygame.Rect(0, self.mat_top() - 2, PAL_W - 1, self.list_bottom - self.mat_top() + 4))
        for i, (m, comp) in enumerate(G_MATS):
            r = self.mat_rect(i)
            if r.bottom < self.mat_top() or r.top > self.list_bottom:
                continue
            on = m == self.mat
            pygame.draw.rect(surf, ACTIVE if on else PART_BG, r)
            pygame.draw.rect(surf, SEL if on else PANEL_LINE, r, 1)
            if m in G_SENSOR_TYPES:
                sw = G_SENSOR_COLOR[G_SENSOR_TYPES[m]]
            elif m == 'LINK':
                sw = G_SOLIDS[G_LINK][2]
            elif m in G_MECH:
                sw = (200, 204, 214)
            elif comp:
                sw = tuple(int(sum(G_COLOR[G_IDX[s]][ch] * f for s, f in comp.items()) * 1.4) for ch in range(3))
                sw = tuple(min(255, x) for x in sw)
            else:
                sw = G_SOLIDS[G_SOLID_MATS[m]][2] if m in G_SOLID_MATS else \
                    (G_BLOCK_COLOR if m == 'BLOCK' else (6, 8, 16))
            pygame.draw.rect(surf, sw, (r.x, r.y, 4, r.h))
            surf.blit(self.app.small.render(m, True, TEXT), (r.x + 10, r.y + 2))
        surf.set_clip(None)
        hy = H - (len(G_HELP) * 15 + 30)
        for i, t in enumerate(G_HELP):
            surf.blit(self.app.small.render(t, True, TEXT_DIM), (12, hy + i * 15))
        st = f"x{self.speed}" + ('  PAUSED' if self.paused else '') + ('' if not self.sym else '  sym ' + 'xyb'[self.sym - 1]) + ('' if self.sim.open else '  closed') \
            + ('' if self.sim.gravity else '  no g')
        surf.blit(self.app.small.render(st, True, SEL if self.paused else TEXT), (12, H - 22))
        msg, until = self.app.toast
        if msg and time.time() < until:
            t = self.app.font.render(msg, True, TEXT)
            tr = pygame.Rect(0, 0, t.get_width() + 24, t.get_height() + 14)
            tr.midtop = ((W + PAL_W) // 2, 12)
            pygame.draw.rect(surf, PANEL, tr)
            pygame.draw.rect(surf, SEL, tr, 1)
            surf.blit(t, t.get_rect(center=tr.center))


def main():
    pygame.init()
    pygame.display.set_caption("logic sandbox")
    pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    app = App()
    app.load()
    app.updater = Updater()
    running = True
    restart = False
    gas = None
    if np is not None and os.path.exists(os.path.join(os.path.dirname(save_path()), 'gas.npz')):
        gas = GasMode(app)      # loaded now so its circuit links keep working from the circuit screen
    while running:
        dt = clock.tick(60) / 1000
        modal = app.updater.state in ('prompt', 'installing', 'failed')
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
