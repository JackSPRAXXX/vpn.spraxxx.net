# app.py
#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv()
import os
import re
import json
import time
import uuid
import fcntl
import ipaddress
import tempfile
import logging
import secrets
import pathlib
import subprocess
from pathlib import Path
from typing import Dict, Set, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import qrcode

# Config - allow overrides via env
WG_BIN = os.getenv('WG_BIN', '/usr/bin/wg')
SUDO_BIN = os.getenv('SUDO_BIN', '/usr/bin/sudo')
WG_IFACE = os.getenv('WG_IFACE', 'wg0y')
WG_CONF = Path(os.getenv('WG_CONF', '/etc/wireguard/wg0.conf'))
V4_NET = os.getenv('V4_NET', '10.66.66.0/24')
ENDPOINT_HOST = os.getenv('ENDPOINT_HOST', '')
ENDPOINT_PORT = os.getenv('ENDPOINT_PORT', '')
ENDPOINT = f"{ENDPOINT_HOST}:{ENDPOINT_PORT}" if ENDPOINT_HOST and ENDPOINT_PORT else os.getenv('ENDPOINT', '')
DNS = os.getenv('DNS', '1.1.1.1')
PUBLIC_ROOT = Path(os.getenv('PUBLIC_ROOT', '/var/www/wg/clients'))
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')
RATE_LIMIT_PER_MIN = int(os.getenv('RATE_LIMIT_PER_MIN', '10'))
ALLOC = Path(os.getenv('ALLOC_FILE', '/opt/dcvpn/allocations.json'))

LOCKFILE = PUBLIC_ROOT / '.lock'

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('dcvpn')
app = FastAPI()

bearer = HTTPBearer(auto_error=False)

def require_admin(creds: HTTPAuthorizationCredentials = Security(bearer)):
    if not creds or not secrets.compare_digest(creds.credentials, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail='Unauthorized')

class NewReq(BaseModel):
    name: str

class RevokeReq(BaseModel):
    name: str

# in-process rate limiter keyed by IP
_tokens = {}
_last_refill = {}

def _refill_for(ip: str):
    now = int(time.time())
    last = _last_refill.get(ip, 0)
    if now - last >= 60:
        _tokens[ip] = RATE_LIMIT_PER_MIN
        _last_refill[ip] = now

def take_token_for(ip: str) -> bool:
    _refill_for(ip)
    if _tokens.get(ip, 0) <= 0:
        return False
    _tokens[ip] -= 1
    return True

# helper to run commands with controlled env
def sh(*args, input_bytes: Optional[bytes] = None) -> str:
    env = {"PATH": "/usr/bin:/bin"}
    r = subprocess.run(list(args), input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env)
    return r.stdout.decode().strip()

# allocation persistence

def load_alloc():
    if ALLOC.exists():
        try:
            return json.loads(ALLOC.read_text())
        except Exception:
            return {}
    return {}


def save_alloc(d):
    tmp = ALLOC.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, indent=2))
    os.replace(str(tmp), str(ALLOC))

# name sanitizer/normalizer
RESERVED_NAMES = {'server', 'wg0', 'wg0y'}

def normalize_name(name: str) -> str:
    n = re.sub(r'[^a-z0-9_-]', '', name.lower())[:32]
    if not n or n in RESERVED_NAMES:
        raise HTTPException(status_code=400, detail='invalid name')
    return n

# harvest used IPs from ledger + runtime

def harvest_used_ips() -> Set[str]:
    used = set()
    alloc = load_alloc()
    for v in alloc.values():
        ip = v.get('ip')
        if ip:
            used.add(ip)
    # runtime
    try:
        out = sh(SUDO_BIN, WG_BIN, 'show', WG_IFACE, 'allowed-ips')
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                for ip in parts[1].split(','):
                    used.add(ip.split('/')[0])
    except Exception:
        log.debug('wg show allowed-ips failed')
    return {u for u in used if u}

# pick next IP from V4_NET skipping server

def parse_server_ip():
    try:
        txt = WG_CONF.read_text()
        m = re.search(r'Address\s*=\s*([0-9.]+)/\d+', txt)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def pick_next_ip(used_ips: Set[str]) -> str:
    net = ipaddress.ip_network(V4_NET)
    server_ip = parse_server_ip()
    for h in net.hosts():
        s = str(h)
        if server_ip and s == server_ip:
            continue
        if s in used_ips:
            continue
        return s
    raise HTTPException(status_code=500, detail='no available ips')

# key generation helpers

def gen_keypair():
    priv = sh(WG_BIN, 'genkey')
    pub = sh('bash', '-c', f'echo "{priv}" | {WG_BIN} pubkey')
    return priv, pub

def gen_psk():
    return sh(WG_BIN, 'genpsk')

# locking helper

def file_lock(f):
    fcntl.flock(f, fcntl.LOCK_EX)

@app.post('/new')
async def new_client(request: Request, body: NewReq, _=Depends(require_admin)):
    # rate limit by forwarded IP
    ip = request.headers.get('x-forwarded-for', request.client.host if request.client else '127.0.0.1')
    if not take_token_for(ip):
        raise HTTPException(status_code=429, detail='rate limit')

    name = normalize_name(body.name)
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)

    with open(LOCKFILE, 'w') as lf:
        file_lock(lf)
        used = harvest_used_ips()
        ipaddr = pick_next_ip(used)
        priv, pub = gen_keypair()
        psk = gen_psk()

        # build conf
        try:
            server_pub = sh(SUDO_BIN, WG_BIN, 'show', WG_IFACE, 'public-key')
        except Exception:
            server_pub = ''
        conf_lines = [
            '[Interface]',
            f'PrivateKey = {priv}',
            f'Address = {ipaddr}/32',
            f'DNS = {DNS}',
            '',
            '[Peer]',
            f'PublicKey = {server_pub}',
            f'PresharedKey = {psk}',
            f'Endpoint = {ENDPOINT}',
            'AllowedIPs = 0.0.0.0/0, ::/0',
        ]
        conf_text = '\n'.join(conf_lines) + '\n'

        # add runtime
        tmp_psk = None
        try:
            tf = tempfile.NamedTemporaryFile(delete=False)
            tf.write(psk.encode())
            tf.flush()
            tf.close()
            tmp_psk = tf.name
            sh(SUDO_BIN, WG_BIN, 'set', WG_IFACE, 'peer', pub, 'preshared-key', tmp_psk, 'allowed-ips', f'{ipaddr}/32')
        except Exception:
            if tmp_psk and Path(tmp_psk).exists():
                Path(tmp_psk).unlink()
            raise HTTPException(status_code=500, detail='failed to add peer to runtime')

        # persist in peers.d if exists, else append to WG_CONF (no surgical edits on revoke)
        wrote_peer_file = False
        peer_block = '\n'.join([f'# ---- peer {name} ----','[Peer]',f'PublicKey = {pub}',f'PresharedKey = {psk}',f'AllowedIPs = {ipaddr}/32',''])
        try:
            peersd = WG_CONF.parent / 'peers.d'
            if peersd.exists() and peersd.is_dir():
                peersd.mkdir(parents=True, exist_ok=True)
                peerfile = peersd / f"{name}-{uuid.uuid4().hex}.conf"
                tmpf = peerfile.with_suffix('.tmp')
                tmpf.write_text(peer_block)
                os.replace(str(tmpf), str(peerfile))
                wrote_peer_file = True
            else:
                with open(WG_CONF, 'a') as w:
                    w.write('\n' + peer_block)
        except Exception:
            try:
                sh(SUDO_BIN, WG_BIN, 'set', WG_IFACE, 'peer', pub, 'remove')
            except Exception:
                pass
            if tmp_psk and Path(tmp_psk).exists():
                Path(tmp_psk).unlink()
            raise HTTPException(status_code=500, detail='failed to persist peer')

        # write files atomically and generate QR using qrcode
        uid = secrets.token_urlsafe(6)
        conf_name = f"{name}-{uid}.conf"
        qr_name = f"{name}-{uid}.png"
        conf_path = PUBLIC_ROOT / conf_name
        qr_path = PUBLIC_ROOT / qr_name
        try:
            tmpc = conf_path.with_suffix('.tmp')
            tmpc.write_text(conf_text)
            os.replace(str(tmpc), str(conf_path))
            os.chmod(conf_path, 0o640)
            img = qrcode.make(conf_text)
            img.save(str(qr_path))
            os.chmod(qr_path, 0o640)
        except Exception:
            try:
                sh(SUDO_BIN, WG_BIN, 'set', WG_IFACE, 'peer', pub, 'remove')
            except Exception:
                pass
            if wrote_peer_file:
                try:
                    peerfile.unlink(missing_ok=True)
                except Exception:
                    pass
            if tmp_psk and Path(tmp_psk).exists():
                Path(tmp_psk).unlink()
            raise HTTPException(status_code=500, detail='failed to write client files')

        # record allocation
        alloc = load_alloc()
        alloc[name] = {'ip': ipaddr, 'pubkey': pub, 'psk': psk, 'conf': conf_name, 'qr': qr_name}
        save_alloc(alloc)
        if tmp_psk and Path(tmp_psk).exists():
            Path(tmp_psk).unlink()
        return JSONResponse(status_code=201, content={'ok': True, 'data': {'conf_url': f'/clients/{conf_name}', 'qr_url': f'/clients/{qr_name}'}, 'preview': conf_text})

@app.post('/revoke')
async def revoke(body: RevokeReq, _=Depends(require_admin)):
    name = normalize_name(body.name)
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    with open(LOCKFILE, 'w') as lf:
        file_lock(lf)
        alloc = load_alloc()
        entry = alloc.get(name)
        if not entry:
            raise HTTPException(status_code=404, detail='not found')
        pub = entry.get('pubkey')
        try:
            sh(SUDO_BIN, WG_BIN, 'set', WG_IFACE, 'peer', pub, 'remove')
        except Exception:
            pass
        # remove peers.d files matching name prefix
        peersd = WG_CONF.parent / 'peers.d'
        if peersd.exists() and peersd.is_dir():
            for f in peersd.iterdir():
                if f.name.startswith(name + '-'):
                    try:
                        f.unlink()
                    except Exception:
                        pass
        # remove client files
        try:
            conf_path = PUBLIC_ROOT / entry.get('conf')
            qr_path = PUBLIC_ROOT / entry.get('qr')
            conf_path.unlink(missing_ok=True)
            qr_path.unlink(missing_ok=True)
        except Exception:
            pass
        alloc.pop(name, None)
        save_alloc(alloc)
        return {'ok': True}

@app.get('/status')
async def status(_=Depends(require_admin)):
    alloc = load_alloc()
    peers = []
    try:
        out = sh(SUDO_BIN, WG_BIN, 'show', WG_IFACE, 'dump')
        lines = out.splitlines()
        for line in lines[1:]:
            cols = line.split('\t')
            if len(cols) >= 5:
                pub = cols[0]
                allowed = cols[2]
                endpoint = cols[3] if len(cols) > 3 else ''
                latest = int(cols[4]) if cols[4].isdigit() else 0
                ips = [a.split('/')[0] for a in allowed.split(',') if a]
                name = None
                for k, v in alloc.items():
                    if v.get('pubkey') == pub:
                        name = k
                        has_files = (PUBLIC_ROOT / v.get('conf')).exists()
                        peers.append({'name': name, 'ip': v.get('ip'), 'pubkey': pub, 'has_files': has_files, 'endpoint': endpoint, 'latest_handshake': latest, 'is_connected': (time.time() - latest) < 180})
                if name is None:
                    peers.append({'name': None, 'ip': ips[0] if ips else None, 'pubkey': pub, 'has_files': False, 'endpoint': endpoint, 'latest_handshake': latest, 'is_connected': (time.time() - latest) < 180})
    except Exception:
        for k, v in alloc.items():
            peers.append({'name': k, 'ip': v.get('ip'), 'pubkey': v.get('pubkey'), 'has_files': (PUBLIC_ROOT / v.get('conf')).exists()})
    return {'ok': True, 'data': {'iface': WG_IFACE, 'peers': peers}}

@app.get('/')
async def root():
    return {'ok': True, 'msg': 'DCVPN running'}