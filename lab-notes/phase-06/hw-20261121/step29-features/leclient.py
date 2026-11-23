#!/usr/bin/env python3
"""Login helper module for the step29 device sweep."""
import json
import os
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18080/api/v1"
USER = "phase6-sweep"
PASS = os.environ['LIBREECHO_WEB_PASSWORD']


def call(method, path, body=None, token=None, csrf=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if method not in ("GET", "HEAD") and csrf:
        req.add_header("X-LibreEcho-CSRF", csrf)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw}
    except Exception as e:  # connection refused etc.
        return 0, {"error": {"code": "client", "message": str(e)}}


def login():
    st, body = call("GET", "/config")
    csrf = (body.get("data") or {}).get("csrf_token", "")
    st, body = call("POST", "/auth/login", {"username": USER, "password": PASS}, csrf=csrf)
    token = (body.get("data") or {}).get("token", "")
    st, body = call("GET", "/config", token=token)
    csrf = (body.get("data") or {}).get("csrf_token") or csrf
    return token, csrf
