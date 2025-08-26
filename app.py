import os, re, json, ipaddress, tempfile, subprocess, pathlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ====== CONFIG (edit if you change anything) ======
WG_IFACE   = "wg0y"
WG_CONF    = f"/etc/wireguard/{WG_IFACE}.conf"
V4_NET     = ipaddress.ip_network("10.66.66.0/24")
SERVER_IP  = "67.217.243.136"
ENDPOINT   = f"{SERVER_IP}:8477"
DNS        = "1.1.1.1,1.0.0.1"
PUBLIC_ROOT = pathlib.Path("/var/www/wg/clients")
# ==================================================

app = FastAPI()

class NewReq(BaseModel):
    name: str
    allowed_ips: str | None = "0.0.0.0/0,::/0"
    keepalive: int | None = 25

def _run(cmd, input_bytes=None):
    return subprocess.check_output(cmd, input=input_bytes)

def server_pubkey():
    return _run(["wg", "show", WG_IFACE, "public-key"]).decode().strip()

def used_ips():
    used = set()
    if not os.path.exists(WG_CONF):
        return used
    with open(WG_CONF) as f:
        for line in f:
            m = re.search(r"AllowedIPs\s*=\s*(\d+\.\d+\.\d+\.\d+)/32", line)
            if m:
                used.add(ipaddress.ip_address(m.group(1)))
    return used

def next_ip():
    taken = used_ips()
    for host in V4_NET.hosts():
        if host == list(V4_NET.hosts())[0]:  # skip .1 (server)
            continue
        if host not in taken:
            return str(host)
    raise RuntimeError("No free IPs left in pool")

def gen_keys():
    priv = _run(["wg", "genkey"]).decode().strip()
    pub  = _run(["wg", "pubkey"], input_bytes=(priv+"\n").encode()).decode().strip()
    psk  = _run(["wg", "genpsk"]).decode().strip()
    return priv, pub, psk

def append_peer_to_conf(pub, psk, ip, name):
    block = f"""
### Client {name}
[Peer]
PublicKey = {pub}
PresharedKey = {psk}
AllowedIPs = {ip}/32
"""
    with open(WG_CONF, "a") as f:
        f.write(block)

def wg_add_runtime(pub, psk, ip):
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(psk+"\n"); tf.flush()
        subprocess.check_call(["wg", "set", WG_IFACE, "peer", pub, "preshared-key", tf.name, "allowed-ips", f"{ip}/32"])
    os.unlink(tf.name)

def write_client_files(name, priv, pub_svr, ip, allowed_ips, keepalive):
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    conf_text = f"""[Interface]
PrivateKey = {priv}
Address = {ip}/32
DNS = {DNS}

[Peer]
PublicKey = {pub_svr}
PresharedKey = {{PSK_PLACEHOLDER}}
Endpoint = {ENDPOINT}
AllowedIPs = {allowed_ips}
PersistentKeepalive = {keepalive}
"""
    # Replace placeholder after we know PSK (done by caller)
    conf_path = PUBLIC_ROOT / f"{name}.conf"
    qr_path   = PUBLIC_ROOT / f"{name}.png"
    return conf_path, qr_path, conf_text

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/new")
def new(req: NewReq):
    name = re.sub(r"[^a-zA-Z0-9_-]", "", req.name)[:15]
    if not name:
        raise HTTPException(400, "Invalid name")
    ip = next_ip()
    priv, pub, psk = gen_keys()
    pub_svr = server_pubkey()
    # Write client config
    conf_path, qr_path, conf_text = write_client_files(name, priv, pub_svr, ip, req.allowed_ips or "0.0.0.0/0,::/0", req.keepalive or 25)
    conf_text = conf_text.replace("{PSK_PLACEHOLDER}", psk)
    conf_path.write_text(conf_text)
    # QR (qrencode reads config from stdin)
    subprocess.check_call(["qrencode", "-t", "PNG", "-o", str(qr_path)], input=conf_text.encode())
    # Add to running interface + persist in server conf
    wg_add_runtime(pub, psk, ip)
    append_peer_to_conf(pub, psk, ip, name)
    base = "https://vpn.spraxxx.net/clients"
    return {"name": name, "ip": ip, "conf_url": f"{base}/{name}.conf", "qr_url": f"{base}/{name}.png"}