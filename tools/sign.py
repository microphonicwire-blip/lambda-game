import os
import sys

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, root)
import guard

secret = bytes.fromhex(os.environ['SIGN_KEY'].strip())
if guard.public_key(secret) != guard.PUBKEY:
    sys.exit('SIGN_KEY does not match the public key in guard.py')
code = open(os.path.join(root, 'current.py'), 'rb').read()
out = guard.make_check(secret, code)
open(os.path.join(root, 'check.txt'), 'w').write(out)
print(out)
