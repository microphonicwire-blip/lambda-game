import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import guard

secret = os.urandom(32)
pub = guard.public_key(secret)
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'guard.py')
src = open(path).read()
src = re.sub(r"PUBKEY = bytes.fromhex\('[0-9a-f]+'\)", f"PUBKEY = bytes.fromhex('{pub.hex()}')", src)
open(path, 'w').write(src)
print('SIGN_KEY (keep secret, only put it in the github secret):', secret.hex())
