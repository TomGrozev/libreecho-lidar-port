#!/usr/bin/env python3
"""Write the v0.2.35 feature catalog: the phase-06 Lidar catalog with the
airplay2 entry repointed at the freshly built payload in this directory."""
import hashlib
import json
import sys
from pathlib import Path

d = Path(sys.argv[1]).resolve()
payload = next(d.glob("libreecho-lidar-base-airplay2-*.payload.squashfs"))
manifest = next(d.glob("libreecho-lidar-base-airplay2-*.manifest.json"))
catalog = json.loads(
    Path("private/artifacts/phase-06/features-airplay2-latency/feature-catalog.json").read_text()
)
entry = catalog["features"]["airplay2"]
entry["payload"] = str(payload)
entry["payload_sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
entry["payload_size"] = payload.stat().st_size
entry["manifest"] = str(manifest)
entry["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
entry["manifest_size"] = manifest.stat().st_size
(d / "feature-catalog.json").write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")
print("payload", entry["payload_sha256"], entry["payload_size"])
