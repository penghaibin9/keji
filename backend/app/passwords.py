"""Argon2id hashes for new/reset credentials. Unknown legacy encodings fail shut."""
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
import secrets
from fastapi import HTTPException
HASHER=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1)
DUMMY_HASH=HASHER.hash(secrets.token_urlsafe(32))

def validate_password(password):
    if len(password)<12 or len(password)>256 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(422,'密码至少12位，须同时包含字母和数字')
    if any(ord(c)<32 for c in password): raise HTTPException(422,'密码不能包含控制字符')

def hash_password(password):
    validate_password(password)
    return HASHER.hash(password)

def verify_password(encoded,password):
    try: return HASHER.verify(encoded,password)
    except (VerificationError,InvalidHashError): return False
