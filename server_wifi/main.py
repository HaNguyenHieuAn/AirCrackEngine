#!/usr/bin/env python3
"""server_wifi - Hashcat & WPA2/PMKID/EAPOL cracking server for ACNG AirCrack workflow."""
import os
import glob
import subprocess
import shutil
import time
import json
import hashlib
import hmac
from typing import Optional, Tuple, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="ACNG server-wifi")
BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")
CRACKED_DB = os.path.join(BASE, "cracked.json")
DEFAULT_WORDLIST = os.path.join(BASE, "rockyou.txt")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def load_cracked() -> List[Dict[str, Any]]:
    if os.path.exists(CRACKED_DB):
        try:
            with open(CRACKED_DB, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_cracked(data: List[Dict[str, Any]]) -> None:
    with open(CRACKED_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def upsert_cracked_entry(ssid: str, bssid: str, password: str, filename: str) -> None:
    db = load_cracked()
    for item in db:
        if (ssid and item.get("ssid") == ssid) or (filename and item.get("file") == filename):
            item["ssid"] = ssid or item.get("ssid", "")
            item["bssid"] = bssid or item.get("bssid", "")
            item["password"] = password
            item["file"] = filename or item.get("file", "")
            item["time"] = time.time()
            save_cracked(db)
            return
    db.append({
        "ssid": ssid,
        "bssid": bssid,
        "password": password,
        "file": filename,
        "time": time.time(),
    })
    save_cracked(db)


def _prf512(key: bytes, label: bytes, data: bytes) -> bytes:
    out = b""
    for i in range(4):
        out += hmac.new(key, label + b"\x00" + data + bytes([i]), hashlib.sha1).digest()
    return out[:64]


def crack_hc22000_python(hc_path: str, wordlist_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Giai ma nhanh file .hc22000 (WPA*01* PMKID & WPA*02* EAPOL 4-way handshake)
    theo chuan IEEE 802.11i. Tra ve (ssid, bssid, password).
    """
    if not os.path.exists(hc_path):
        return None, None, None

    records = []
    ssid_found = None
    bssid_found = None
    with open(hc_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line.startswith("WPA*"):
                continue
            parts = line.split("*")
            if len(parts) < 8:
                continue
            htype = parts[1]
            mic_or_pmkid = bytes.fromhex(parts[2])
            mac_ap = bytes.fromhex(parts[3])
            mac_sta = bytes.fromhex(parts[4])
            essid_bytes = bytes.fromhex(parts[5])
            essid_str = essid_bytes.decode("utf-8", errors="replace")
            bssid_str = ":".join(f"{b:02X}" for b in mac_ap)
            if not ssid_found:
                ssid_found = essid_str
                bssid_found = bssid_str
            if htype == "01":
                records.append(("01", mic_or_pmkid, mac_ap, mac_sta, essid_bytes, essid_str, bssid_str, b"", b""))
            elif htype == "02" and len(parts) >= 8:
                nonce_ap = bytes.fromhex(parts[6])
                eapol = bytes.fromhex(parts[7])
                records.append(("02", mic_or_pmkid, mac_ap, mac_sta, essid_bytes, essid_str, bssid_str, nonce_ap, eapol))

    if not records:
        return ssid_found, bssid_found, None

    candidates = []
    if os.path.exists(wordlist_path):
        with open(wordlist_path, "r", encoding="utf-8", errors="ignore") as wf:
            for wline in wf:
                pw = wline.rstrip("\r\n")
                if 8 <= len(pw) <= 63 and pw not in candidates:
                    candidates.append(pw)

    essids = {}
    for rec in records:
        essids.setdefault(rec[4], []).append(rec)

    for pw in candidates:
        pw_bytes = pw.encode("utf-8")
        for essid_bytes, recs in essids.items():
            pmk = hashlib.pbkdf2_hmac("sha1", pw_bytes, essid_bytes, 4096, 32)
            for htype, target_hash, mac_ap, mac_sta, _, essid_str, bssid_str, nonce_ap, eapol in recs:
                if htype == "01":
                    pmkid = hmac.new(pmk, b"PMK Name" + mac_ap + mac_sta, hashlib.sha1).digest()[:16]
                    if pmkid == target_hash:
                        return essid_str, bssid_str, pw
                elif htype == "02" and len(eapol) >= 49:
                    nonce_sta = eapol[17:49]
                    data = min(mac_ap, mac_sta) + max(mac_ap, mac_sta) + min(nonce_ap, nonce_sta) + max(nonce_ap, nonce_sta)
                    ptk = _prf512(pmk, b"Pairwise key expansion", data)
                    kck = ptk[:16]
                    key_ver = eapol[6] & 0x07
                    if key_ver == 1:
                        calc_mic = hmac.new(kck, eapol, hashlib.md5).digest()[:16]
                    else:
                        calc_mic = hmac.new(kck, eapol, hashlib.sha1).digest()[:16]
                    if calc_mic == target_hash:
                        return essid_str, bssid_str, pw

    return ssid_found, bssid_found, None


def find_hashcat_bin() -> Optional[str]:
    """
    Tim binary hashcat theo thu tu uu tien:
    1. Bien moi truong HASHCAT_PATH
    2. Thu muc server_wifi/hashcat/ (hashcat.exe hoac hashcat.bin / hashcat)
    3. Bat ky thu muc server_wifi/hashcat*/ nao chua hashcat.exe / hashcat.bin
    4. hashcat trong PATH he thong
    """
    env_hc = os.environ.get("HASHCAT_PATH", "").strip()
    if env_hc and os.path.exists(env_hc):
        return env_hc

    local_candidates = [
        os.path.join(BASE, "hashcat", "hashcat.exe"),
        os.path.join(BASE, "hashcat", "hashcat.bin"),
        os.path.join(BASE, "hashcat", "hashcat"),
    ]
    for pattern in ["hashcat*/hashcat.exe", "hashcat*/*/hashcat.exe", "hashcat*/hashcat.bin", "hashcat*/hashcat"]:
        local_candidates.extend(sorted(glob.glob(os.path.join(BASE, pattern))))

    for c in local_candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    found = shutil.which("hashcat")
    if found:
        return found
    return None


@app.get("/status")
def status():
    db = load_cracked()
    return {
        "status": "online",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "queued": 0,
        "cracked_count": len(db),
        "hashcat_available": bool(find_hashcat_bin()),
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    safe_name = os.path.basename(file.filename or "capture.hc22000")
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"success": True, "filename": safe_name, "path": path}


@app.post("/hash")
async def run_hash(
    request: Request,
    filename: Optional[str] = Form(None),
    wordlist: str = Form("rockyou.txt"),
):
    if not filename:
        try:
            body = await request.json()
            if isinstance(body, dict):
                filename = body.get("filename")
                wordlist = body.get("wordlist", wordlist)
        except Exception:
            pass

    if not filename:
        return JSONResponse(status_code=400, content={"success": False, "error": "filename required"})

    safe_name = os.path.basename(filename)
    path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"success": False, "error": "file not found"})

    wl_path = wordlist if os.path.isabs(wordlist) else os.path.join(BASE, wordlist)
    if not os.path.exists(wl_path):
        wl_path = DEFAULT_WORDLIST

    # 1. Giai ma bang GPU/CPU Hashcat neu co thu muc server_wifi/hashcat hoac hashcat trong PATH
    ssid, bssid, password = None, None, None
    hc_bin = find_hashcat_bin()
    if hc_bin and os.path.exists(wl_path):
        out_file = os.path.join(UPLOAD_DIR, safe_name + ".pot")
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
            subprocess.run(
                [hc_bin, "-m", "22000", path, wl_path, "-o", out_file, "--potfile-disable"],
                cwd=os.path.dirname(hc_bin) if os.path.isabs(hc_bin) else None,
                timeout=120,
                capture_output=True,
            )
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f.read().splitlines() if l.strip()]
                    if lines:
                        parts = lines[-1].split(":")
                        password = parts[-1]
                        if len(parts) >= 2:
                            ssid = parts[-2]
                        if len(parts) >= 4:
                            raw_bssid = parts[1]
                            if len(raw_bssid) == 12:
                                bssid = ":".join(raw_bssid[i:i+2].upper() for i in range(0, 12, 2))
        except Exception as e:
            print(f"[SERVER_WIFI] hashcat subprocess err: {e}")

    # 2. Fallback / xac minh bang IEEE 802.11i PBKDF2/PMKID/EAPOL verifier thuan Python
    if not password:
        ssid, bssid, password = crack_hc22000_python(path, wl_path)
    elif not ssid or not bssid:
        parsed_ssid, parsed_bssid, _ = crack_hc22000_python(path, "")
        ssid = ssid or parsed_ssid
        bssid = bssid or parsed_bssid

    if password:
        upsert_cracked_entry(ssid or "", bssid or "", password, safe_name)

    return {
        "success": True,
        "status": "cracked" if password else "exhausted",
        "filename": safe_name,
        "ssid": ssid,
        "bssid": bssid,
        "password": password,
    }


@app.get("/wifi")
def list_wifi():
    return {"items": load_cracked()}


@app.post("/wifi")
async def add_wifi(
    request: Request,
    ssid: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
):
    if not ssid or not password:
        try:
            body = await request.json()
            if isinstance(body, dict):
                ssid = body.get("ssid", ssid)
                password = body.get("password", password)
        except Exception:
            pass
    if not ssid or not password:
        return JSONResponse(status_code=400, content={"success": False, "error": "ssid and password required"})
    upsert_cracked_entry(ssid, "", password, "manual")
    return {"success": True, "ssid": ssid, "password": password}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
