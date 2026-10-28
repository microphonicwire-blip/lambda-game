import hashlib
import os

AUTHOR = 'Max, Keaton Technologies'
PUBKEY = bytes.fromhex('715a78669e82ea99db945eb274a2ae00eef3cad9012498e5c3eb024166546bf2')
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _add(a, b):
    A, B = (a[1] - a[0]) * (b[1] - b[0]) % _P, (a[1] + a[0]) * (b[1] + b[0]) % _P
    C, D = 2 * a[3] * b[3] * _D % _P, 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _eq(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _compress(pt):
    zi = _inv(pt[2])
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _h(s):
    return int.from_bytes(hashlib.sha512(s).digest(), 'little') % _Q


def _expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret):
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret, msg):
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _h(prefix + msg)
    R = _compress(_mul(r, _G))
    s = (r + _h(R + A + msg) * a) % _Q
    return R + int.to_bytes(s, 32, 'little')


def verify(pub, msg, sig):
    if len(pub) != 32 or len(sig) != 64:
        return False
    A = _decompress(pub)
    if A is None:
        return False
    R = _decompress(sig[:32])
    if R is None:
        return False
    s = int.from_bytes(sig[32:], 'little')
    if s >= _Q:
        return False
    k = _h(sig[:32] + pub + msg)
    return _eq(_mul(s, _G), _add(R, _mul(k, A)))


def norm(data):
    return data.replace(b'\r\n', b'\n')


def make_check(secret, code):
    digest = hashlib.sha256(norm(code)).hexdigest()
    sig = sign(secret, b'logicsim-v1:' + digest.encode())
    return f'sha256:{digest}\nsig:{sig.hex()}\n'


def check_ok(code, check_txt):
    # code = bytes of current.py, check_txt = text of check.txt. true only if the owner's key signed exactly this code
    try:
        lines = dict(l.split(':', 1) for l in check_txt.strip().splitlines())
        digest = lines['sha256'].strip()
        if hashlib.sha256(norm(code)).hexdigest() != digest:
            return False
        return verify(PUBKEY, b'logicsim-v1:' + digest.encode(), bytes.fromhex(lines['sig'].strip()))
    except Exception:
        return False


def install_ok(code_dir):
    # the downloaded game on disk is untouched and really signed
    try:
        with open(os.path.join(code_dir, 'current.py'), 'rb') as f:
            code = f.read()
        with open(os.path.join(code_dir, 'check.txt'), encoding='utf-8') as f:
            return check_ok(code, f.read())
    except OSError:
        return False


_SEAL = {}


def seal(tag, text):
    # credit strings in several places must hash to what was signed off; any edit trips it
    want = hashlib.sha256(('logicsim|' + tag + '|' + AUTHOR).encode()).hexdigest()
    got = hashlib.sha256(('logicsim|' + tag + '|' + text).encode()).hexdigest()
    return want == got
