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
GLOW = 0.07         # lamps/displays stay lit this long (s) so fast blinks are visible
MAX_RATE = 4000
SAVE_EVERY = 0.5    # min seconds between autosaves
MAX_LABEL = 20
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

BG = (9, 9, 11)             # cells
GRID = (150, 150, 156)      # grid lines
PANEL = (16, 16, 20)
PARTFILL = (28, 28, 34)
WHITE = (255, 255, 255)     # signal on
BLUEW = (170, 205, 255)     # signal off
FLOAT = (85, 85, 92)        # nothing driving it
SHORT = (200, 50, 50)       # on and off fighting
BLACK = (0, 0, 0)
PREVIEW = (190, 190, 196)   # wire while placing

def set_theme(light):
    # light mode swaps black and white (and goes navy instead of blueish white)
    global BG, GRID, PANEL, PARTFILL, WHITE, BLUEW, FLOAT, BLACK, PREVIEW
    if light:
        BG, GRID, PANEL = (246, 246, 243), (110, 110, 104), (239, 239, 235)
        PARTFILL, WHITE, BLUEW = (227, 227, 221), (0, 0, 0), (50, 100, 175)
        FLOAT, BLACK, PREVIEW = (170, 170, 163), (255, 255, 255), (65, 65, 59)
    else:
        BG, GRID, PANEL = (9, 9, 11), (150, 150, 156), (16, 16, 20)
        PARTFILL, WHITE, BLUEW = (28, 28, 34), (255, 255, 255), (170, 205, 255)
        FLOAT, BLACK, PREVIEW = (85, 85, 92), (0, 0, 0), (190, 190, 196)


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
    'NOT': ONE_IN, 'BUF': ONE_IN,
    'SR LATCH': TWO_IN, 'NV LATCH': TWO_IN,    # NV keeps its state in the save file
    'AND': TWO_IN, 'NAND': TWO_IN, 'OR': TWO_IN,
    'NOR': TWO_IN, 'XOR': TWO_IN, 'XNOR': TWO_IN,
}
NAMES = {'DISPLAY': ['R', 'G', 'B', 'ON'], 'GATE': ['IN', 'OUT', 'EN'],
         'SR LATCH': ['S', 'R', 'Q'], 'NV LATCH': ['S', 'R', 'Q']}

PAL_ITEMS = ['SOURCE', 'SWITCH', 'BUTTON', 'CLOCK', 'GATE', 'LAMP', 'DISPLAY', 'NOT', 'BUF',
             'AND', 'NAND', 'OR', 'NOR', 'XOR', 'XNOR', 'SR LATCH', 'NV LATCH', 'LABEL']


def f_w(font, text):
    return font.size(text)[0]


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
        self.rgb = (0, 0, 0)    # display color
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


def draw_poly(surf, pts, color, w):
    for p, q in zip(pts, pts[1:]):
        pygame.draw.line(surf, color, p, q, w)
    for p in pts:
        pygame.draw.rect(surf, color, (p[0] - w // 2, p[1] - w // 2, w, w))


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    cx, cy = ax + t * dx, ay + t * dy
    return ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5


def git_blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def safe_repo_path(path):
    parts = path.split('/')
    return all(p and p not in ('.', '..') and not p.startswith('.') for p in parts)


class Updater:
    # checks github on boot, installs the repo's .py files if they differ
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


class App:
    def __init__(self):
        self.parts = []
        self.wires = []     # (partA, pinA, partB, pinB)
        self.drag = None
        self.paused = False
        self.rate = 500     # ticks per second
        self.acc = 0.0
        self.dirty = False
        self.last_save = 0.0
        self.path = save_path()
        self.font = pygame.font.SysFont(MONO, 16, bold=True)
        self.small = pygame.font.SysFont(MONO, 13)
        global FONT
        FONT = self.font
        self.light = False
        self.updater = None
        self.editing = None     # part being renamed
        self.edit_on = False
        self.edit_text = ''
        self.edit_fresh = False
        self.last_click = (None, 0)

    # sim
    def netstate(self):
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for pa, ia, pb, ib in self.wires:
            ra, rb = find((pa.uid, ia)), find((pb.uid, ib))
            parent[ra] = rb
        drv = {}
        for p in self.parts:
            for i, (_, _, role) in enumerate(p.d['pins']):
                if role == 'out':
                    if p.kind == 'GATE' and not p.drive:
                        continue        # open gate puts nothing on the wire
                    v = 1 if p.kind == 'SOURCE' else p.out
                    drv.setdefault(find((p.uid, i)), set()).add(v)
        return find, drv

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
        for p in self.parts:
            p.glow = max(0.0, p.glow - dt)
        self.acc += dt
        tick = 1.0 / self.rate
        n = 0
        while self.acc >= tick and n < 400:
            self.step()
            self.acc -= tick
            n += 1
        if n == 400:
            self.acc = 0.0

    # saving
    def save(self):
        idx = {p.uid: i for i, p in enumerate(self.parts)}
        data = dict(
            version=1, rate=self.rate, light=self.light,
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
            self.rate = max(1, min(MAX_RATE, int(data.get('rate', self.rate))))
            self.light = bool(data.get('light'))
            set_theme(self.light)
        except (KeyError, TypeError, ValueError, IndexError):
            try:
                os.replace(self.path, self.path + '.bad')   # keep the broken file
            except OSError:
                pass

    # helpers
    def pal_rect(self, i):
        return pygame.Rect(12, 40 + i * 30, PAL_W - 24, 24)

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
        self.wires = [w for w in self.wires if w[0] is not p and w[2] is not p]

    def snap(self, p, mx, my, ox, oy):
        p.gx = max(0, round((mx - ox - PAL_W) / C))
        p.gy = max(0, round((my - oy) / C))

    # overlap
    def collides(self, p):
        r = p.rect()
        return any(q is not p and r.colliderect(q.rect()) for q in self.parts)

    def label_fits(self, p, text):
        r0 = p.rect()
        r = pygame.Rect(r0.x, r0.y, label_w(text + '_') * C, C)
        return not any(q is not p and r.colliderect(q.rect()) for q in self.parts)

    # renaming
    def base_label(self, p):
        if p.kind == 'SWITCH':
            t = p.label_on if p.on else p.label_off
            return t if t is not None else ('ON' if p.on else 'OFF')
        if p.label is not None:
            return p.label
        k = p.kind
        if k == 'SOURCE':
            return 'ON'
        if k == 'SWITCH':
            return 'ON' if p.on else 'OFF'
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

    # input
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
            if e.key == pygame.K_SPACE:
                self.paused = not self.paused
            elif e.key == pygame.K_c:
                self.parts.clear()
                self.wires.clear()
                self.dirty = True
            elif e.key == pygame.K_l:
                self.light = not self.light
                set_theme(self.light)
                self.dirty = True
            elif e.key == pygame.K_UP:
                self.rate = min(MAX_RATE, self.rate * 2)
                self.dirty = True
            elif e.key == pygame.K_DOWN:
                self.rate = max(1, self.rate // 2)
                self.dirty = True
            elif e.key == pygame.K_n and self.paused:
                for p in self.parts:
                    p.glow = 0.0
                self.step()
        elif e.type == pygame.MOUSEBUTTONDOWN:
            mx, my = e.pos
            if e.button == 1:
                if mx < PAL_W:
                    for i, k in enumerate(PAL_ITEMS):
                        if self.pal_rect(i).collidepoint(e.pos):
                            p = Part(k)
                            ox, oy = p.d['w'] * C // 2, p.d['h'] * C // 2
                            self.snap(p, mx, my, ox, oy)
                            self.parts.append(p)
                            self.drag = dict(kind='part', part=p, ox=ox, oy=oy,
                                             start=e.pos, moved=True, new=True)
                    return
                hit = self.pin_at(e.pos)
                if hit:
                    self.drag = dict(kind='wire', a=hit)
                    return
                p = self.part_at(e.pos)
                if p:
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
                    r = p.rect()
                    self.parts.remove(p)
                    self.parts.append(p)    # bring to front
                    self.drag = dict(kind='part', part=p, ox=mx - r.x, oy=my - r.y,
                                     start=e.pos, moved=False, new=False,
                                     orig=(p.gx, p.gy))
            elif e.button == 3:
                p = self.part_at(e.pos)
                if p:
                    self.remove_part(p)
                    self.dirty = True
                else:
                    w = self.wire_at(e.pos)
                    if w:
                        self.wires.remove(w)
                        self.dirty = True
        elif e.type == pygame.MOUSEMOTION and self.drag and self.drag['kind'] == 'part':
            d = self.drag
            if abs(e.pos[0] - d['start'][0]) + abs(e.pos[1] - d['start'][1]) > 4:
                d['moved'] = True
            if d['moved']:
                self.snap(d['part'], e.pos[0], e.pos[1], d['ox'], d['oy'])
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            d, self.drag = self.drag, None
            if d['kind'] == 'wire':
                hit = self.pin_at(e.pos)
                if hit and hit != d['a']:
                    (pa, ia), (pb, ib) = d['a'], hit
                    dup = any((w[0] is pa and w[1] == ia and w[2] is pb and w[3] == ib) or
                              (w[0] is pb and w[1] == ib and w[2] is pa and w[3] == ia)
                              for w in self.wires)
                    if not dup:
                        self.wires.append((pa, ia, pb, ib))
                        self.dirty = True
            else:
                self.dirty = True
                p = d['part']
                if d['moved']:
                    self.last_click = (None, 0)     # a drag isn't half a double-click
                if self.collides(p):
                    if d['new']:
                        self.remove_part(p)
                    else:
                        p.gx, p.gy = d['orig']
                if p not in self.parts:
                    pass
                elif e.pos[0] < PAL_W:
                    self.remove_part(p)     # dropped back on palette
                elif not d['moved']:
                    if p.kind == 'SWITCH':
                        p.on = not p.on
                    elif p.kind == 'BUTTON':
                        p.pulse = True
                        p.flash = 0.15
                    elif p.kind == 'CLOCK':
                        p.pidx = (p.pidx + 1) % len(PERIODS)
                        p.counter = 0

    # draw
    def label(self, surf, text, color, center):
        t = self.font.render(text, True, color)
        surf.blit(t, t.get_rect(center=center))

    def draw(self, surf):
        W, H = surf.get_size()
        surf.fill(BG)
        for x in range(PAL_W, W, C):
            pygame.draw.line(surf, GRID, (x, 0), (x, H))
        for y in range(0, H, C):
            pygame.draw.line(surf, GRID, (PAL_W, y), (W, y))

        find, drv = self.netstate()

        def col(p, i):
            s = drv.get(find((p.uid, i)))
            if not s:
                return FLOAT
            if len(s) == 2:
                return SHORT
            return WHITE if 1 in s else BLUEW

        for w in self.wires:
            pts = wire_pts(w[0].pin_pos(w[1]), w[2].pin_pos(w[3]))
            draw_poly(surf, pts, BLACK, 7)
            draw_poly(surf, pts, col(w[0], w[1]), 3)

        if self.drag and self.drag['kind'] == 'wire':
            pa, ia = self.drag['a']
            a, m = pa.pin_pos(ia), pygame.mouse.get_pos()
            pts = wire_pts(a, m)
            draw_poly(surf, pts, BLACK, 7)
            draw_poly(surf, pts, PREVIEW, 3)

        for p in self.parts:
            r = p.rect()
            fill, txt = PARTFILL, WHITE
            if p.kind == 'LAMP' and p.glow > 0:
                fill, txt = WHITE, BLACK
            elif p.kind == 'DISPLAY' and p.glow > 0:
                fill = p.rgb
            elif p.kind == 'SOURCE' or (p.kind == 'SWITCH' and p.on) or (p.kind == 'CLOCK' and p.out) \
                    or (p.kind == 'BUTTON' and p.flash > 0):
                fill, txt = BLUEW, BLACK
            editing = p is self.editing
            if p.kind == 'LABEL':
                text = self.label_text(p)
                r = pygame.Rect(r.x, r.y, label_w(text) * C, C)
                pygame.draw.rect(surf, BLACK, r)
                if editing or not text.strip():
                    pygame.draw.rect(surf, BLUEW if editing else FLOAT, r, 1)
                self.label(surf, text, BLUEW if editing and self.edit_fresh else WHITE, r.center)
                continue
            pygame.draw.rect(surf, fill, r)
            small = p.d['w'] == 1
            pygame.draw.rect(surf, BLUEW if editing else (FLOAT if small else WHITE),
                             r, 1 if small else 2)
            if p.kind != 'DISPLAY':
                text = self.label_text(p)
                if text.strip():
                    f = self.font if f_w(self.font, text) <= r.w - 8 else self.small
                    t = f.render(text, True, BLUEW if editing and self.edit_fresh else txt)
                    surf.set_clip(r.inflate(-4, -4))
                    surf.blit(t, t.get_rect(center=r.center))
                    surf.set_clip(None)
            o, i_ = (8, 4) if small else (10, 6)
            for i in range(len(p.d['pins'])):
                q = p.pin_pos(i)
                pygame.draw.rect(surf, BLACK, (q[0] - o // 2, q[1] - o // 2, o, o))
                pygame.draw.rect(surf, col(p, i), (q[0] - i_ // 2, q[1] - i_ // 2, i_, i_))

        # red tint while a dragged part is over another part (can't be placed there)
        if self.drag and self.drag['kind'] == 'part' and self.collides(self.drag['part']):
            r = self.drag['part'].rect()
            tint = pygame.Surface(r.size, pygame.SRCALPHA)
            tint.fill((220, 40, 40, 120))
            surf.blit(tint, r.topleft)

        # palette
        pygame.draw.rect(surf, PANEL, (0, 0, PAL_W, H))
        pygame.draw.line(surf, WHITE, (PAL_W - 1, 0), (PAL_W - 1, H))
        self.label(surf, 'PARTS', WHITE, (PAL_W // 2, 20))
        mp = pygame.mouse.get_pos()
        for i, k in enumerate(PAL_ITEMS):
            r = self.pal_rect(i)
            pygame.draw.rect(surf, PARTFILL, r)
            pygame.draw.rect(surf, WHITE if r.collidepoint(mp) else FLOAT, r, 2)
            self.label(surf, k, WHITE, r.center)
        help_lines = ['drag out parts', 'pin-pin = wire', 'click switch/btn', 'rmb = delete',
                      'dbl-click: name', 'l = light mode', 'space = pause', 'n = step', 'up/dn = speed',
                      'c = clear']
        y0 = H - len(help_lines) * 16 - 8
        for i, t in enumerate(help_lines):
            surf.blit(self.small.render(t, True, FLOAT), (12, y0 + i * 16))
        surf.blit(self.small.render(f"{self.rate} ticks/s", True, WHITE), (12, y0 - 20))
        if self.paused:
            self.label(surf, 'PAUSED', WHITE, (PAL_W + 50, 16))

        # pin label on hover
        if mp[0] >= PAL_W:
            hit = self.pin_at(mp)
            if hit:
                p, i = hit
                t = self.small.render(f"{p.kind} {pin_name(p.kind, i)}", True, WHITE)
                w, h = t.get_width() + 10, t.get_height() + 6
                x, y = mp[0] + 14, mp[1] + 14
                if x + w > W:
                    x = mp[0] - w - 6
                if y + h > H:
                    y = mp[1] - h - 6
                pygame.draw.rect(surf, BLACK, (x, y, w, h))
                pygame.draw.rect(surf, WHITE, (x, y, w, h), 1)
                surf.blit(t, (x + 5, y + 3))

        u = self.updater
        if u and u.state in ('prompt', 'installing', 'failed'):
            dim = pygame.Surface((W, H), pygame.SRCALPHA)
            dim.fill((*BLACK, 170))
            surf.blit(dim, (0, 0))
            box, btn = self.modal_rects(W, H)
            pygame.draw.rect(surf, PANEL, box)
            pygame.draw.rect(surf, WHITE, box, 2)
            self.label(surf, 'UPDATE', WHITE, (box.centerx, box.y + 26))
            if u.state == 'prompt':
                self.label(surf, 'new update:', FLOAT, (box.centerx, box.y + 62))
                for i, line in enumerate(wrap(self.font, u.message, box.w - 40)[:3]):
                    self.label(surf, line, BLUEW, (box.centerx, box.y + 88 + i * 20))
            elif u.state == 'installing':
                self.label(surf, 'installing...', WHITE, (box.centerx, box.centery))
            else:
                self.label(surf, 'update failed, keeping this version', WHITE, (box.centerx, box.y + 80))
            if u.state != 'installing':
                pygame.draw.rect(surf, PARTFILL, btn)
                pygame.draw.rect(surf, WHITE, btn, 2)
                self.label(surf, 'OK', WHITE, btn.center)


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
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE
                                            and not app.editing):
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
