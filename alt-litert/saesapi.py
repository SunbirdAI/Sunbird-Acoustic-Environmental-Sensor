"""Tiny shared HTTP helper: retrying session, JSON POST that never raises."""
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API = os.environ.get("SAES_API", "https://noise-api.sunbird.ai").rstrip("/")
DEVICE_ID = os.environ.get("SAES_DEVICE_ID", "SEAS-3")
UPLOAD = os.environ.get("SAES_UPLOAD", "1") == "1"

_s = requests.Session()
_s.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1,
         status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"])))

def post_json(path, payload):
    """Returns (ok, detail). Never raises, so a network outage can't kill a service."""
    if not UPLOAD:
        return False, "upload disabled"
    try:
        r = _s.post(API + path, json=payload, timeout=10)
        return r.ok, "%s %s" % (r.status_code, r.text[:160].replace("\n", " "))
    except Exception as e:
        return False, str(e)[:160]
