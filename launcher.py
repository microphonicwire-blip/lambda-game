import os
import runpy
import sys
import traceback

import guard


def data_dir():
    p = os.environ.get('LOGICSIM_SAVE')
    if p:
        return os.path.dirname(p)
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'logicsim')


def log_crash(text):
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(os.path.join(data_dir(), 'crash.log'), 'w') as f:
            f.write(text)
    except OSError:
        pass


def drop(*paths):
    for p in paths:
        try:
            os.replace(p, p + '.bad')
        except OSError:
            pass
    try:
        os.remove(os.path.join(data_dir(), 'version.txt'))
    except OSError:
        pass


def run():
    # downloaded game if it is the signed one, otherwise the copy compiled into the exe
    code = os.path.join(data_dir(), 'code')
    ext = os.path.join(code, 'current.py')
    if os.path.exists(ext):
        if guard.install_ok(code):
            sys.path.insert(0, code)
            try:
                runpy.run_path(ext, run_name='__main__')
                return
            except Exception:
                log_crash(traceback.format_exc())
                drop(ext, os.path.join(code, 'check.txt'))
                sys.path.remove(code)
        else:
            drop(ext, os.path.join(code, 'check.txt'))
    import current
    current.main()


def main():
    try:
        run()
    except Exception:
        log_crash(traceback.format_exc())
        raise
