#!/usr/bin/env python3
# logic gate sandbox
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import pygame

C = 24              # cell size
PAL_W = 144         # palette width (multiple of C so the grid lines up)
HDR = 14            # part header height
GLOW = 0.07         # lamps/displays stay lit this long (s) so fast blinks are visible
MAX_RATE = 4000
SAVE_EVERY = 0.5    # min seconds between autosaves
MAX_LABEL = 20
TUBE_SPEED = 60     # px/s, the little signal tubes sliding along wires
PERIODS = [5, 10, 25, 50, 100, 250, 500, 1000]   # clock half-periods in ticks
MONO = 'dejavusansmono,consolas,couriernew,menlo,monospace'
FONT = None         # set by App, used to size LABEL parts


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
    try:
        with open(os.path.join(APP_DIR, 'token.txt')) as f:
            return f.read().strip()
    except OSError:
        return ''


# ---------------------------------------------------------------- themes
THEMES = {
    'dark': dict(
        BG=(11, 19, 36), GRID=(21, 35, 58), GRID2=(29, 48, 80),
        PANEL=(13, 22, 40), PANEL_LINE=(44, 72, 118),
        PART_BG=(17, 27, 48), PART_LINE=(74, 112, 172),
        TEXT=(214, 228, 248), TEXT_DIM=(104, 130, 170),
        ON=(72, 210, 255), OFF=(62, 156, 100), FLOAT=(58, 76, 108), SHORT=(232, 72, 72),
        SEL=(255, 208, 80), ACTIVE=(22, 64, 96), LAMP_ON=(255, 226, 120),
        SEG_OFF=(27, 40, 68), SEG_DEFAULT=(240, 245, 255), PREVIEW=(150, 190, 235),
        HDR_LOGIC=(92, 70, 160), HDR_INPUT=(176, 112, 38), HDR_OUTPUT=(28, 128, 140),
        HDR_MEM=(160, 58, 120), HDR_TEXT=(255, 255, 255), DIM=(0, 0, 0)),
    'light': dict(
        BG=(234, 240, 248), GRID=(214, 223, 236), GRID2=(196, 208, 226),
        PANEL=(222, 230, 242), PANEL_LINE=(140, 162, 196),
        PART_BG=(250, 252, 255), PART_LINE=(84, 114, 166),
        TEXT=(20, 32, 54), TEXT_DIM=(112, 126, 152),
        ON=(0, 118, 214), OFF=(34, 140, 80), FLOAT=(160, 174, 198), SHORT=(212, 52, 52),
        SEL=(226, 140, 0), ACTIVE=(206, 230, 250), LAMP_ON=(255, 200, 40),
        SEG_OFF=(214, 222, 236), SEG_DEFAULT=(20, 30, 50), PREVIEW=(70, 110, 170),
        HDR_LOGIC=(132, 112, 206), HDR_INPUT=(222, 150, 60), HDR_OUTPUT=(60, 164, 176),
        HDR_MEM=(200, 100, 166), HDR_TEXT=(255, 255, 255), DIM=(20, 30, 50)),
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
    'LAMP':    dict(w=2, h=2, pins=[(0, 1, 'in')]),
    'LABEL':   dict(w=1, h=1, pins=[]),                 # just text, no ports
    'DISPLAY': dict(w=1, h=1, pins=[(0, 0, 'in'), (1, 0, 'in'), (0, 1, 'in'), (1, 1, 'in')]),
    # 7 segments on the left, then red green blue along the bottom
    '7SEG':    dict(w=5, h=8, pins=[(0, k, 'in') for k in range(1, 8)]
                    + [(1, 8, 'in'), (2, 8, 'in'), (3, 8, 'in')]),
    'NOT': ONE_IN, 'BUF': ONE_IN,
    'SR LATCH': TWO_IN, 'NV LATCH': TWO_IN,    # NV keeps its state in the save file
    'AND': TWO_IN, 'NAND': TWO_IN, 'OR': TWO_IN,
    'NOR': TWO_IN, 'XOR': TWO_IN, 'XNOR': TWO_IN,
}
NAMES = {'DISPLAY': ['R', 'G', 'B', 'ON'], 'GATE': ['IN', 'OUT', 'EN'],
         'SR LATCH': ['S', 'R', 'Q'], 'NV LATCH': ['S', 'R', 'Q'],
         '7SEG': ['SEG A', 'SEG B', 'SEG C', 'SEG D', 'SEG E', 'SEG F', 'SEG G',
                  'RED', 'GREEN', 'BLUE']}

PAL_ITEMS = ['SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GATE', 'LAMP', 'DISPLAY', '7SEG',
             'NOT', 'BUF', 'AND', 'NAND', 'OR', 'NOR', 'XOR', 'XNOR',
             'SR LATCH', 'NV LATCH', 'LABEL']

HELP = ['drag out parts', 'pin-pin = wire', 'bg drag = box', 'ctrl+click = add',
        'ctrl+c x v a', 'del = delete', 'rmb = delete', 'dbl-click: name',
        'space = pause', 'n = step', 'up/dn = speed', 'l = light mode', 't = tubes',
        'clr: ctrl+sh+del']
HELP_H = 8 + len(HELP) * 15 + 26
SEG_NAMES = 'abcdefg'


def cat_color(kind):
    if kind in ('SOURCE', 'SWITCH', 'BUTTON', 'CLOCK'):
        return HDR_INPUT
    if kind in ('LAMP', 'DISPLAY', '7SEG'):
        return HDR_OUTPUT
    if kind in ('SR LATCH', 'NV LATCH'):
        return HDR_MEM
    if kind == 'LABEL':
        return TEXT_DIM
    return HDR_LOGIC


def pin_name(kind, i):
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
        self.pidx = 4           # clock speed (index into PERIODS)
        self.counter = 0        # clock ticks since last flip
        self.label_on = None    # switch names, one per state
        self.label_off = None

    def rect(self):
        w = self.d['w'] * C
        if self.kind == 'LABEL':
            w = label_w(self.label if self.label is not None else 'LABEL') * C
        return pygame.Rect(PAL_W + self.gx * C, self.gy * C, w, self.d['h'] * C)

    def pin_pos(self, i):
        dx, dy, _ = self.d['pins'][i]
        return (PAL_W + (self.gx + dx) * C, (self.gy + dy) * C)


def wire_pts(a, b):
    if a[0] == b[0] or a[1] == b[1]:
        return [a, b]
    mx = PAL_W + round(((a[0] + b[0]) / 2 - PAL_W) / C) * C
    return [a, (mx, a[1]), (mx, b[1]), b]


def draw_wire(surf, pts, color, w):
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


class Updater:
    # checks github on boot, installs the repo's files if they differ
    def __init__(self, start=True):
        self.state = 'off'      # off idle checking prompt installing failed restart
        self.message = ''
        self.sha = ''
        self.todo = []
        if GITHUB_REPO:
            self.state = 'checking'
            if start:
                threading.Thread(target=self._check, daemon=True).start()

    def _get(self, url, raw=False):
        req = urllib.request.Request(url, headers={
            'User-Agent': 'logicsim',
            'Accept': 'application/vnd.github.raw' if raw else 'application/vnd.github+json'})
        tok = github_token()
        if tok:
            req.add_header('Authorization', 'Bearer ' + tok)
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read()

    def _write_version(self, sha):
        try:
            os.makedirs(os.path.dirname(version_path()), exist_ok=True)
            with open(version_path(), 'w') as f:
                f.write(sha)
        except OSError:
            pass

    def _check(self):
        api = f'https://api.github.com/repos/{GITHUB_REPO}'
        try:
            head = json.loads(self._get(f'{api}/commits/{GITHUB_BRANCH}'))
            sha = head['sha']
            msg = head['commit']['message'].strip().split('\n')[0]
            try:
                with open(version_path()) as f:
                    cur = f.read().strip()
            except OSError:
                cur = ''
            if cur == sha:
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
        except Exception:
            self.state = 'idle'              # offline or no access, just play

    def install(self):
        self.state = 'installing'
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        api = f'https://api.github.com/repos/{GITHUB_REPO}'
        try:
            files = []
            for path in self.todo:
                data = self._get(f'{api}/contents/{urllib.parse.quote(path)}?ref={self.sha}', raw=True)
                if path.endswith('.py'):
                    compile(data, path, 'exec')      # don't install something that can't even parse
                files.append((path, data))
            for path, data in files:
                dst = local_path(path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst + '.new', 'wb') as f:
                    f.write(data)
                os.replace(dst + '.new', dst)
            self._write_version(self.sha)
            self.state = 'restart'
        except Exception:
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
        global FONT
        FONT = self.font
        self.light = False
        self.tubes = True
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

    # ------------------------------------------------------------ sim
    def topo_sig(self):
        return (id(self.parts), len(self.parts), id(self.wires), len(self.wires))

    def build_topo(self):
        parent = {}
        for p in self.parts:
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
        for wi, (pa, ia, pb, ib) in enumerate(self.wires):
            ka, kb = (pa.uid, ia), (pb.uid, ib)
            ra, rb = find(ka), find(kb)
            if ra != rb:
                parent[ra] = rb
            adj.setdefault(ka, []).append((kb, wi, True))
            adj.setdefault(kb, []).append((ka, wi, False))
        self.root = {k: find(k) for k in list(parent)}
        self.out_pins, queue = [], []
        for p in self.parts:
            for i, (_, _, role) in enumerate(p.d['pins']):
                if role == 'out':
                    self.out_pins.append((p, i, self.root[(p.uid, i)]))
                    queue.append((p.uid, i))
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

    def step(self):
        find, drv = self.netstate()

        def hi(p, i):
            return drv.get(find((p.uid, i))) == {1}

        new = []
        passes = []
        for p in self.parts:
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
            elif k in ('SR LATCH', 'NV LATCH'):
                # reset wins if both are high
                new.append((p, 0 if hi(p, 1) else (1 if hi(p, 0) else p.out)))
            elif k == 'LAMP':
                if hi(p, 0):
                    p.glow = GLOW
            elif k == 'DISPLAY':
                if hi(p, 3):
                    p.rgb = tuple(255 if hi(p, i) else 0 for i in range(3))
                    p.glow = GLOW
            elif k == '7SEG':
                col = tuple(255 if hi(p, i) else 0 for i in (7, 8, 9))
                p.rgb = col if any(col) else None
                for i in range(7):
                    if hi(p, i):
                        p.seg_glow[i] = GLOW
        for p, drive, v in passes:
            p.drive, p.out = drive, v
        for p, v in new:
            if p.kind == 'NV LATCH' and p.out != v:
                self.dirty = True
            p.out = v
            if p.kind == 'BUTTON':
                p.pulse = False

    def update(self, dt):
        for p in self.parts:
            p.flash = max(0.0, p.flash - dt)
        if self.paused:
            return
        self.anim += dt
        for p in self.parts:
            if p.glow > 0:
                p.glow = max(0.0, p.glow - dt)
            if p.kind == '7SEG':
                p.seg_glow = [max(0.0, g - dt) for g in p.seg_glow]
        self.acc += dt
        tick = 1.0 / self.rate
        n = 0
        while self.acc >= tick and n < 400:
            self.step()
            self.acc -= tick
            n += 1
        if n == 400:
            self.acc = 0.0

    # ------------------------------------------------------------ saving
    def save(self):
        idx = {p.uid: i for i, p in enumerate(self.parts)}
        data = dict(
            version=1, rate=self.rate, light=self.light, tubes=self.tubes,
            parts=[dict(kind=p.kind, gx=p.gx, gy=p.gy, on=p.on, label=p.label, pidx=p.pidx,
                        label_on=p.label_on, label_off=p.label_off,
                        q=p.out if p.kind == 'NV LATCH' else 0) for p in self.parts],
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
            parts = []
            for d in data['parts']:
                if d['kind'] not in DEFS:
                    parts.append(None)
                    continue
                p = Part(d['kind'], int(d['gx']), int(d['gy']))
                p.on = bool(d.get('on'))
                p.pidx = max(0, min(len(PERIODS) - 1, int(d.get('pidx', 4))))
                if isinstance(d.get('label'), str):
                    p.label = d['label'][:MAX_LABEL]
                    if p.kind == 'SWITCH':      # old saves: one name for both states
                        p.label_on = p.label_off = p.label
                        p.label = None
                if isinstance(d.get('label_on'), str):
                    p.label_on = d['label_on'][:MAX_LABEL]
                if isinstance(d.get('label_off'), str):
                    p.label_off = d['label_off'][:MAX_LABEL]
                if p.kind == 'NV LATCH':
                    p.out = int(bool(d.get('q')))
                parts.append(p)
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
            pts = wire_pts(w[0].pin_pos(w[1]), w[2].pin_pos(w[3]))
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
        r = pygame.Rect(r0.x, r0.y, label_w(text + '_') * C, C)
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
            parts=[dict(kind=p.kind, rx=p.gx - minx, ry=p.gy - miny, on=p.on, label=p.label,
                        label_on=p.label_on, label_off=p.label_off, pidx=p.pidx,
                        q=p.out if p.kind == 'NV LATCH' else 0) for p in group],
            wires=[[idx[a.uid], ia, idx[b.uid], ib] for a, ia, b, ib in self.wires
                   if a.uid in idx and b.uid in idx])

    def paste(self):
        if not self.clip:
            return
        if self.drag and self.drag.get('carry'):
            self.cancel_carry()
        clones = []
        for d in self.clip['parts']:
            p = Part(d['kind'], d['rx'], d['ry'])
            p.on, p.label, p.pidx = d['on'], d['label'], d['pidx']
            p.label_on, p.label_off = d['label_on'], d['label_off']
            if p.kind == 'NV LATCH':
                p.out = d['q']
            clones.append(p)
        self.parts.extend(clones)
        for a, ia, b, ib in self.clip['wires']:
            self.wires.append((clones[a], ia, clones[b], ib))
        self.topo_key = None
        self.sel = set(clones)
        bw = max(p.rect().right for p in clones) - PAL_W
        bh = max(p.rect().bottom for p in clones)
        d = dict(kind='part', parts=clones, rel=[(p.gx, p.gy) for p in clones],
                 ox=bw // 2, oy=bh // 2, start=pygame.mouse.get_pos(), moved=True,
                 new=True, carry=True, hit=None, orig=None)
        self.place_group(d, *pygame.mouse.get_pos())
        self.drag = d       # follows the mouse until you click to drop it

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
        gx0 = max(0, round((mx - d['ox'] - PAL_W) / C))
        gy0 = max(0, round((my - d['oy']) / C))
        for p, (rx, ry) in zip(d['parts'], d['rel']):
            p.gx, p.gy = gx0 + rx, gy0 + ry

    def begin_part_drag(self, group, pos, hit):
        minx, miny = min(p.gx for p in group), min(p.gy for p in group)
        self.drag = dict(kind='part', parts=group,
                         rel=[(p.gx - minx, p.gy - miny) for p in group],
                         ox=pos[0] - (PAL_W + minx * C), oy=pos[1] - miny * C,
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
            elif h.kind == 'BUTTON':
                h.pulse = True
                h.flash = 0.15
            elif h.kind == 'CLOCK':
                h.pidx = (h.pidx + 1) % len(PERIODS)
                h.counter = 0

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
        if k == 'DISPLAY':
            return ''
        return k

    def label_text(self, p):
        if p is self.editing:
            return self.edit_text + ('_' if (pygame.time.get_ticks() // 400) % 2 == 0 else ' ')
        return self.base_label(p)

    def start_edit(self, p):
        self.editing = p
        self.edit_text = self.base_label(p)
        self.edit_on = p.on
        self.edit_fresh = True      # first key replaces everything
        pygame.key.set_repeat(400, 35)

    def finish_edit(self, commit):
        p = self.editing
        self.editing = None
        pygame.key.set_repeat()
        if p and commit and p in self.parts:
            if p.kind == 'SWITCH':
                if self.edit_on:
                    p.label_on = self.edit_text
                else:
                    p.label_off = self.edit_text
            else:
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
            if len(self.edit_text) < MAX_LABEL:
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
        if e.type == pygame.KEYDOWN and self.editing:
            self.edit_key(e)
            return
        if e.type == pygame.MOUSEBUTTONDOWN and self.editing:
            self.finish_edit(True)
        if e.type == pygame.KEYDOWN:
            self.on_key(e)
        elif e.type == pygame.MOUSEWHEEL:
            if pygame.mouse.get_pos()[0] < PAL_W:
                self.scroll_palette(-e.y * 26)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.on_down(e)
        elif e.type == pygame.MOUSEMOTION:
            self.on_motion(e)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.on_up(e)

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
        elif k == pygame.K_UP:
            self.rate = min(MAX_RATE, self.rate * 2)
            self.dirty = True
        elif k == pygame.K_DOWN:
            self.rate = max(1, self.rate // 2)
            self.dirty = True
        elif k == pygame.K_n and self.paused:
            for p in self.parts:
                p.glow = 0.0
                p.seg_glow = [0.0] * 7
            self.step()

    def on_down(self, e):
        mx, my = e.pos
        if e.button == 3:
            if self.drag and self.drag.get('carry'):
                self.cancel_carry()
                return
            p = self.part_at(e.pos)
            if p:
                self.remove_part(p)
                self.dirty = True
            else:
                w = self.wire_at(e.pos)
                if w:
                    self.wires.remove(w)
                    self.topo_key = None
                    self.dirty = True
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
                                 ox=p.d['w'] * C // 2, oy=p.d['h'] * C // 2, start=e.pos,
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
                    and p.kind != 'DISPLAY':
                self.last_click = (None, 0)
                if p.kind == 'SWITCH':
                    p.on = not p.on     # undo the first click's toggle
                elif p.kind == 'CLOCK':
                    p.pidx = (p.pidx - 1) % len(PERIODS)
                self.start_edit(p)
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
        if not d or d.get('carry'):
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
        if self.grid_cache is None or self.grid_cache.get_size() != (W, H):
            g = pygame.Surface((W, H))
            g.fill(BG)
            for n, x in enumerate(range(PAL_W, W, C)):
                pygame.draw.line(g, GRID2 if n % 4 == 0 else GRID, (x, 0), (x, H))
            for n, y in enumerate(range(0, H, C)):
                pygame.draw.line(g, GRID2 if n % 4 == 0 else GRID, (PAL_W, y), (W, y))
            self.grid_cache = g
        surf.blit(self.grid_cache, (0, 0))

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

    def draw_7seg(self, surf, p, r):
        x0, y0 = r.x + 34, r.y + HDR + 10
        dw, dh, t = 68, r.h - HDR - 10 - 28, 9
        vl = (dh - 3 * t) // 2
        segs = [(x0 + t, y0, dw - 2 * t, t),                     # a
                (x0 + dw - t, y0 + t, t, vl),                    # b
                (x0 + dw - t, y0 + 2 * t + vl, t, vl),           # c
                (x0 + t, y0 + dh - t, dw - 2 * t, t),            # d
                (x0, y0 + 2 * t + vl, t, vl),                    # e
                (x0, y0 + t, t, vl),                             # f
                (x0 + t, y0 + t + vl, dw - 2 * t, t)]            # g
        color = p.rgb or SEG_DEFAULT
        for i, rect in enumerate(segs):
            pygame.draw.rect(surf, color if p.seg_glow[i] > 0 else SEG_OFF, rect)

    def draw_part(self, surf, p, pcol):
        r = p.rect()
        k = p.kind
        editing = p is self.editing
        if k == 'LABEL':
            text = self.label_text(p)
            r = pygame.Rect(r.x, r.y, label_w(text) * C, C)
            pygame.draw.rect(surf, BG, r)
            if editing or not text.strip():
                pygame.draw.rect(surf, SEL if editing else FLOAT, r, 1)
            self.label(surf, text, SEL if editing and self.edit_fresh else TEXT, r.center)
            return
        if k == 'DISPLAY':
            pygame.draw.rect(surf, p.rgb if p.glow > 0 and p.rgb else PART_BG, r)
            pygame.draw.rect(surf, SEL if editing else PART_LINE, r, 1)
        else:
            body = PART_BG
            if k == 'LAMP' and p.glow > 0:
                body = LAMP_ON
            elif k == 'SOURCE' or (k == 'SWITCH' and p.on) or (k == 'BUTTON' and p.flash > 0) \
                    or (k in ('CLOCK', 'SR LATCH', 'NV LATCH', 'GATE') and (p.out and (k != 'GATE' or p.drive))):
                body = ACTIVE
            pygame.draw.rect(surf, body, r)
            hdr = pygame.Rect(r.x, r.y, r.w, HDR)
            pygame.draw.rect(surf, cat_color(k), hdr)
            text = self.label_text(p)
            if text.strip():
                t = self.tiny.render(text, True, SEL if editing and self.edit_fresh else HDR_TEXT)
                surf.set_clip(hdr.inflate(-4, 0))
                surf.blit(t, t.get_rect(center=hdr.center))
                surf.set_clip(None)
            pygame.draw.rect(surf, SEL if editing else PART_LINE, r, 1)
            cx, cy = r.centerx, r.y + HDR + (r.h - HDR) // 2
            if k == 'SWITCH':
                track = pygame.Rect(cx - 12, cy - 5, 24, 10)
                pygame.draw.rect(surf, TEXT_DIM, track, 1)
                kx = track.right - 10 if p.on else track.x + 2
                pygame.draw.rect(surf, ON if p.on else TEXT_DIM, (kx, track.y + 2, 8, 6))
            elif k == 'BUTTON':
                b = pygame.Rect(cx - 10, cy - 5, 20, 10)
                pygame.draw.rect(surf, ON if p.flash > 0 else PART_BG, b)
                pygame.draw.rect(surf, TEXT_DIM, b, 1)
            elif k == 'CLOCK':
                t = self.tiny.render(f'{PERIODS[p.pidx]} ticks', True, TEXT_DIM)
                surf.blit(t, t.get_rect(center=(cx, cy)))
            elif k == '7SEG':
                self.draw_7seg(surf, p, r)
        # pins
        small = k == 'DISPLAY'
        o, i_ = (7, 3) if small else (9, 5)
        for i in range(len(p.d['pins'])):
            q = p.pin_pos(i)
            pygame.draw.rect(surf, BG, (q[0] - o // 2, q[1] - o // 2, o, o))
            pygame.draw.rect(surf, pcol(p, i), (q[0] - i_ // 2, q[1] - i_ // 2, i_, i_))
            if k == '7SEG':
                if i < 7:
                    t = self.tiny.render(SEG_NAMES[i], True, TEXT_DIM)
                    surf.blit(t, t.get_rect(center=(q[0] + 11, q[1])))
                else:
                    t = self.tiny.render('RGB'[i - 7], True, TEXT_DIM)
                    surf.blit(t, t.get_rect(center=(q[0], q[1] - 10)))

    def draw(self, surf):
        W, H = surf.get_size()
        self.draw_grid(surf, W, H)
        find, drv = self.netstate()
        mp = pygame.mouse.get_pos()

        def pcol(p, i):
            return self.net_color(drv.get(find((p.uid, i))))

        # wires
        jobs = []
        for wi, (pa, ia, pb, ib) in enumerate(self.wires):
            pts = wire_pts(pa.pin_pos(ia), pb.pin_pos(ib))
            s = drv.get(find((pa.uid, ia)))
            color = self.net_color(s)
            w = 1 if not s else (2 if s == {0} else 3)
            draw_wire(surf, pts, color, w)
            if self.tubes and s in ({0}, {1}) and wi < len(self.flow) and self.flow[wi] is not None:
                jobs.append((wi, pts, s))

        # little signal tubes sliding along the wires, away from whatever drives them
        for wi, pts, s in jobs:
            length = poly_len(pts)
            if length < 30:
                continue
            n = max(1, int(length // 96))
            gap = length / n
            base = (self.anim * TUBE_SPEED + wi * 53) % gap
            path = pts if self.flow[wi] else pts[::-1]
            pill = self.pill('ON' if s == {1} else 'OFF')
            hw, hh = pill.get_width() // 2, pill.get_height() // 2
            for k in range(n):
                x, y = point_at(path, base + k * gap)
                surf.blit(pill, (int(x) - hw, int(y) - hh))

        if self.drag and self.drag['kind'] == 'wire':
            pa, ia = self.drag['a']
            draw_wire(surf, wire_pts(pa.pin_pos(ia), mp), PREVIEW, 2)

        for p in self.parts:
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
                t = self.small.render(f"{p.kind} {pin_name(p.kind, i)}", True, TEXT)
                w, h = t.get_width() + 10, t.get_height() + 6
                x, y = mp[0] + 14, mp[1] + 14
                if x + w > W:
                    x = mp[0] - w - 6
                if y + h > H:
                    y = mp[1] - h - 6
                pygame.draw.rect(surf, PANEL, (x, y, w, h))
                pygame.draw.rect(surf, PART_LINE, (x, y, w, h), 1)
                surf.blit(t, (x + 5, y + 3))

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
                self.label(surf, 'update failed, keeping this version', TEXT, (box.centerx, box.y + 80))
            if u.state != 'installing':
                pygame.draw.rect(surf, PART_BG, btn)
                pygame.draw.rect(surf, PART_LINE, btn, 2)
                self.label(surf, 'OK', TEXT, btn.center)


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
    while running:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and not app.editing:
                if not app.on_escape():
                    running = False
            else:
                app.handle(e)
        app.update(dt)
        app.autosave()
        if app.updater.state == 'restart':
            running = False
            restart = True
        app.draw(pygame.display.get_surface())
        pygame.display.flip()
    if app.editing:
        app.finish_edit(True)
    app.save()
    pygame.quit()
    if restart:     # run the freshly installed version
        if FROZEN:
            env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')   # fresh unpack for the new process
            subprocess.Popen([sys.executable] + sys.argv[1:], env=env)
        else:
            subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:])


if __name__ == '__main__':
    main()
