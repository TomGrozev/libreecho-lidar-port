#!/usr/bin/env python3
"""Minimal authenticated LibreEcho API client for the step33 sweep."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18090/api/v1"


class Client:
    def __init__(self):
        self.token = None
        self.csrf = None

    def call(self, method, path, body=None, timeout=30, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        if method not in ("GET", "HEAD") and self.csrf:
            req.add_header("X-LibreEcho-CSRF", self.csrf)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw_body = r.read()
                if raw:
                    return r.status, dict(r.headers), raw_body
                try:
                    return r.status, json.loads(raw_body.decode() or "{}")
                except ValueError:
                    return r.status, {"raw": raw_body[:2000].decode("latin1")}
        except urllib.error.HTTPError as e:
            raw_body = e.read()
            if raw:
                return e.code, dict(e.headers), raw_body
            try:
                return e.code, json.loads(raw_body.decode())
            except ValueError:
                return e.code, {"raw": raw_body[:500].decode("latin1")}
        except Exception as e:  # noqa: BLE001
            return 0, {"client_error": str(e)}

    def login(self, user, password):
        st, body = self.call("GET", "/config")
        self.csrf = (body.get("data") or {}).get("csrf_token", "")
        st, body = self.call("POST", "/auth/login",
                             {"username": user, "password": password})
        self.token = (body.get("data") or {}).get("token", "")
        if not self.token:
            raise SystemExit("login failed: %s %s" % (st, body))
        st, body = self.call("GET", "/config")
        self.csrf = (body.get("data") or {}).get("csrf_token") or self.csrf
        return self


def dump(name, status, body):
    with open("api/%s.json" % name, "w") as f:
        json.dump({"status": status, "body": body}, f, indent=1, sort_keys=True)
    err = (body or {}).get("error") if isinstance(body, dict) else None
    print("%-30s %s %s" % (name, status, json.dumps(err) if err else "ok"))
