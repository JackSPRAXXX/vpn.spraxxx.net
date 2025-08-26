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
from pathlib import Path
from typing import Dict, Set, Optional
from subprocess import run, CalledProcessError, PIPE

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import qrcode

# Config
WG = "/usr/bin/wg"
SUDO = "/usr/bin/sudo"
WG_IFACE = os.getenv('WG_IFACE', 'wg0')
WG_CONF = Path(os.getenv('WG_CONF', '/etc/wireguard/wg0.conf'))
V4_NET = os.getenv('V4_NET', '10.66.66.0/24')
ENDPOINT = os.getenv('ENDPOINT', '')
DNS = os.getenv('DNS', '1.1.1.1')
PUBLIC_ROOT = Path(os.getenv('PUBLIC_ROOT', '/var/www/wg/clients'))
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')
RATE_LIMIT_PER_MIN = int(os.getenv('RATE_LIMIT_PER_MIN', '10'))

ALLOC_FILE = PUBLIC_ROOT / 'allocations.json'
LOCKFILE = PUBLIC_ROOT / '.lock'

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('dcvpn')
app = FastAPI()

class NewReq(BaseModel):
    name: str

class RevokeReq(BaseModel):
    name: str

# rate limiter
_tokens = RATE_LIMIT_PER_MIN
_last_refill = time.time()

def _refill():
    global _tokens, _last_refill
    now = time.time()
    if now - _last_refill >= 60:
        _tokens = RATE_LIMIT_PER_MIN
        _last_refill = now

def take_token():
    _refill()
    global _tokens
    if _tokens <= 0:
        return False
    _tokens -= 1
    return True

# utils

def run_cmd(cmd, input_text: Optional[str] = None):
    try:
        r = run(cmd, input=input_text, text=True, stdout=PIPE, stderr=PIPE, check=True)
        return r.stdout.strip()
    except CalledProcessError as e:
        log.error('cmd failed: %s stdout=%s stderr=%s', cmd, e.stdout, e.stderr)
        raise


def ensure_public_root():
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)


def file_lock(f):
    fcntl.flock(f, fcntl.LOCK_EX)


def load_alloc():
    ensure_public_root()
    if not ALLOC_FILE.exists():
        return {}
    try:
        return json.loads(ALLOC_FILE.read_text())
    except Exception:
        return {}


def save_alloc(data):
    ensure_public_root()
    tmp = ALLOC_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(str(tmp), str(ALLOC_FILE))


def sanitize_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name):
        raise HTTPException(status_code=400, detail='invalid name')
    return name


def harvest_used_ips() -> Set[str]:
    used = set()
    # from allocations.json
    alloc = load_alloc()
    for v in alloc.values():
        used.add(v.get('ip'))
    # from wg runtime
    try:
        out = run_cmd([WG, 'show', WG_IFACE, 'allowed-ips'])
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                for ip in parts[1].split(','):
                    used.add(ip.split('/')[0])
    except Exception:
        pass
    # from WG_CONF AllowedIPs lines
    try:
        txt = WG_CONF.read_text()
        for m in re.finditer(r'AllowedIPs\s*=\s*([^\n]+)', txt):
            for ip in m.group(1).split(','):
                used.add(ip.split('/')[0].strip())
    except Exception:
        pass
    return {u for u in used if u}


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


def gen_keypair():
    priv = run_cmd([WG, 'genkey'])
    pub = run_cmd(['bash', '-c', f'echo "{priv}" | {WG} pubkey'])
    return priv, pub


def gen_psk():
    return run_cmd([WG, 'genpsk'])


@app.post('/new')
async def new_client(req: Request, body: NewReq):
    auth = req.headers.get('authorization','')
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail='server not configured')
    if not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='unauthorized')
    token = auth.split(' ',1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail='unauthorized')
    if not take_token():
        raise HTTPException(status_code=429, detail='rate limit')

    name = sanitize_name(body.name)
    ensure_public_root()
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCKFILE, 'w') as lf:
        file_lock(lf)
        used = harvest_used_ips()
        ip = pick_next_ip(used)
        priv, pub = gen_keypair()
        psk = gen_psk()
        # build client conf
        try:
            server_pub = run_cmd([WG, 'show', WG_IFACE, 'public-key'])
        except Exception:
            server_pub = ''
        conf_lines = [
            '[Interface]',
            f'PrivateKey = {priv}',
            f'Address = {ip}/32',
            f'DNS = {DNS}',
            '',
            '[Peer]',
            f'PublicKey = {server_pub}',
            f'PresharedKey = {psk}',
            f'Endpoint = {ENDPOINT}',
            'AllowedIPs = 0.0.0.0/0, ::/0',
        ]
        conf_text = '\n'.join(conf_lines) + '\n'

        # add runtime peer
        tmp_psk = None
        try:
            tf = tempfile.NamedTemporaryFile(delete=False)
            tf.write(psk.encode())
            tf.flush()
            tf.close()
            tmp_psk = tf.name
            run_cmd([SUDO, WG, 'set', WG_IFACE, 'peer', pub, 'preshared-key', tmp_psk, 'allowed-ips', f'{ip}/32'])
        except Exception:
            if tmp_psk and os.path.exists(tmp_psk):
                os.unlink(tmp_psk)
            raise HTTPException(status_code=500, detail='failed to add peer to runtime')

        # persist peer
        wrote_peer_file = False
        peer_block = '\n'.join([f'# ---- peer {name} ----','[Peer]',f'PublicKey = {pub}',f'PresharedKey = {psk}',f'AllowedIPs = {ip}/32',''])
        try:
            peersd = WG_CONF.parent / 'peers.d'
            if peersd.exists() and peersd.is_dir():
                peersd.mkdir(parents=True, exist_ok=True)
                peerfile = peersd / f"{name}-{uuid.uuid4().hex}.conf"
                tmp = peerfile.with_suffix('.tmp')
                tmp.write_text(peer_block)
                os.replace(str(tmp), str(peerfile))
                wrote_peer_file = True
            else:
                with tempfile.NamedTemporaryFile('w', delete=False) as t:
                    t.write('\n' + peer_block)
                    tmpname = t.name
                with open(WG_CONF, 'a') as w:
                    w.write('\n' + peer_block)
        except Exception:
            try:
                run_cmd([SUDO, WG, 'set', WG_IFACE, 'peer', pub, 'remove'])
            except Exception:
                pass
            if tmp_psk and os.path.exists(tmp_psk):
                os.unlink(tmp_psk)
            raise HTTPException(status_code=500, detail='failed to persist peer')

        # write files and QR using qrcode lib
        uid = uuid.uuid4().hex
        base = f"{name}-{uid}"
        conf_name = base + '.conf'
        qr_name = base + '.png'
        conf_path = PUBLIC_ROOT / conf_name
        qr_path = PUBLIC_ROOT / qr_name
        try:
            tmpconf = conf_path.with_suffix('.tmp')
            tmpconf.write_text(conf_text)
            os.replace(str(tmpconf), str(conf_path))
            os.chmod(conf_path, 0o640)
            img = qrcode.make(conf_text)
            img.save(str(qr_path))
            os.chmod(qr_path, 0o640)
        except Exception:
            try:
                run_cmd([SUDO, WG, 'set', WG_IFACE, 'peer', pub, 'remove'])
            except Exception:
                pass
            if wrote_peer_file:
                try:
                    peerfile.unlink(missing_ok=True)
                except Exception:
                    pass
            if tmp_psk and os.path.exists(tmp_psk):
                os.unlink(tmp_psk)
            raise HTTPException(status_code=500, detail='failed to write client files')

        # record allocation
        alloc = load_alloc()
        alloc[name] = {'ip': ip, 'pubkey': pub, 'psk': psk, 'conf': conf_name, 'qr': qr_name}
        save_alloc(alloc)
        if tmp_psk and os.path.exists(tmp_psk):
            os.unlink(tmp_psk)
        return JSONResponse(status_code=201, content={'conf_url': f'/clients/{conf_name}', 'qr_url': f'/clients/{qr_name}', 'preview': conf_text})


@app.post('/revoke')
async def revoke(req: Request, body: RevokeReq):
    auth = req.headers.get('authorization','')
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail='server not configured')
    if not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='unauthorized')
    token = auth.split(' ',1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail='unauthorized')

    name = sanitize_name(body.name)
    ensure_public_root()
    with open(LOCKFILE, 'w') as lf:
        file_lock(lf)
        alloc = load_alloc()
        entry = alloc.get(name)
        if not entry:
            raise HTTPException(status_code=404, detail='not found')
        pub = entry.get('pubkey')
        # remove runtime
        try:
            run_cmd([SUDO, WG, 'set', WG_IFACE, 'peer', pub, 'remove'])
        except Exception:
            pass
        # remove peers.d file if exists
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
        # remove from allocations
        alloc.pop(name, None)
        save_alloc(alloc)
        return {'status': 'ok'}


@app.get('/status')
async def status(req: Request):
    auth = req.headers.get('authorization','')
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail='server not configured')
    if not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='unauthorized')
    token = auth.split(' ',1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail='unauthorized')

    alloc = load_alloc()
    peers = []
    # try to get runtime peers
    try:
        out = run_cmd([WG, 'show', WG_IFACE, 'dump'])
        # wg dump format: iface privatekey publickey listenport fwmark \n then peers lines: public key, presharedkey, allowedips, endpoint, latest handshake ..., transfer
        for line in out.splitlines()[1:]:
            cols = line.split('\t')
            if len(cols) >= 5:
                pub = cols[0]
                allowed = cols[2]
                ips = [a.split('/')[0] for a in allowed.split(',') if a]
                # find allocation matching pub
                name = None
                for k, v in alloc.items():
                    if v.get('pubkey') == pub:
                        name = k
                        has_files = (Path(PUBLIC_ROOT) / v.get('conf')).exists()
                        peers.append({'name': name, 'ip': v.get('ip'), 'pubkey': pub, 'has_files': has_files})
                if name is None:
                    peers.append({'name': None, 'ip': ips[0] if ips else None, 'pubkey': pub, 'has_files': False})
    except Exception:
        # fallback: report allocations only
        for k, v in alloc.items():
            peers.append({'name': k, 'ip': v.get('ip'), 'pubkey': v.get('pubkey'), 'has_files': (Path(PUBLIC_ROOT) / v.get('conf')).exists()})

    return {'iface': WG_IFACE, 'peers': peers}


@app.get('/')
async def root():
    return {'status': 'ok', 'msg': 'DCVPN running'}