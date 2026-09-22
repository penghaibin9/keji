"""OIDC ID-token verification; only configured issuer and RSA SHA-256 keys."""
import base64, hashlib, hmac, json, time, math
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from .contracts import AdapterContractError

def b64(value):
    return base64.urlsafe_b64decode(value+'='*(-len(value)%4))

def login_proof(state,credential):
    verifier=base64.urlsafe_b64encode(hmac.new(credential.encode(),state.encode(),hashlib.sha256).digest()).decode().rstrip('=')
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return verifier,challenge,hashlib.sha256(state.encode()).hexdigest()

def verify_id_token(token,*,issuer,client_id,nonce,jwks,access_token):
    try:
        if not issuer or not isinstance(token,str) or len(token)>32768:raise ValueError()
        head,payload,signature=token.split('.')
        header=json.loads(b64(head));claims=json.loads(b64(payload))
        if header.get('alg')!='RS256' or header.get('crit'):raise ValueError()
        keys=[k for k in jwks['keys'] if k.get('kty')=='RSA' and k.get('use','sig')=='sig' and k.get('alg','RS256')=='RS256' and k.get('kid')==header.get('kid')]
        if len(keys)!=1:raise ValueError()
        key=keys[0];n=int.from_bytes(b64(key['n']),'big');e=int.from_bytes(b64(key['e']),'big')
        if n.bit_length()<2048 or n.bit_length()>8192:raise ValueError()
        rsa.RSAPublicNumbers(e,n).public_key().verify(b64(signature),(head+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())
        now=time.time();aud=claims.get('aud');aud=[aud] if isinstance(aud,str) else aud
        if claims.get('iss')!=issuer or not isinstance(aud,list) or client_id not in aud:raise ValueError()
        if (len(aud)>1 or 'azp' in claims) and claims.get('azp')!=client_id:raise ValueError()
        if type(claims.get('exp')) not in (int,float) or not math.isfinite(claims['exp']) or claims['exp']<=now:raise ValueError()
        if type(claims.get('iat')) not in (int,float) or not math.isfinite(claims['iat']) or claims['iat']>now+60:raise ValueError()
        if 'nbf' in claims and (type(claims['nbf']) not in (int,float) or not math.isfinite(claims['nbf']) or claims['nbf']>now+60):raise ValueError()
        if not nonce or not hmac.compare_digest(str(claims.get('nonce','')),nonce):raise ValueError()
        if not isinstance(claims.get('sub'),str) or not claims['sub']:raise ValueError()
        if 'at_hash' in claims:
            expected=base64.urlsafe_b64encode(hashlib.sha256(access_token.encode()).digest()[:16]).decode().rstrip('=')
            if not hmac.compare_digest(str(claims['at_hash']),expected):raise ValueError()
        return claims
    except Exception:
        raise AdapterContractError('SSO_ID_TOKEN_INVALID') from None
