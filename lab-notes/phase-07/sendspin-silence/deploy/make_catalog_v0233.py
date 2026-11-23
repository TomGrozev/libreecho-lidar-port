#!/usr/bin/env python3
"""Write the v0.2.33 feature catalog: the phase-06 Lidar catalog with the
airplay2 entry replaced by the payload rebuilt from Platform 3fce9b077 and
UI 715dd4f."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SOC = ROOT / 'artifacts/phase-07/v0233'
PAYLOAD = next(SOC.glob('libreecho-lidar-base-airplay2-*.payload.squashfs'))
MANIFEST = next(SOC.glob('libreecho-lidar-base-airplay2-*.manifest.json'))
TEMPLATE = ROOT / 'artifacts/phase-06/features-airplay2-latency/feature-catalog.json'
OUT = SOC / 'feature-catalog.json'

catalog = json.loads(TEMPLATE.read_text())
airplay2 = catalog['features']['airplay2']
airplay2['payload'] = str(PAYLOAD)
airplay2['payload_sha256'] = hashlib.sha256(PAYLOAD.read_bytes()).hexdigest()
airplay2['payload_size'] = PAYLOAD.stat().st_size
airplay2['manifest'] = str(MANIFEST)
airplay2['manifest_sha256'] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
airplay2['manifest_size'] = MANIFEST.stat().st_size
OUT.write_text(json.dumps(catalog, indent=2, sort_keys=True) + '\n')
print('catalog=' + str(OUT))
print('airplay2_payload_sha256=' + airplay2['payload_sha256'])
print('airplay2_manifest_sha256=' + airplay2['manifest_sha256'])
