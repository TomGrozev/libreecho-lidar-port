#!/usr/bin/env python3
"""Fetch the five armv7 feature payloads named by a signed upstream v3 manifest.

The upstream signature is checked before any asset is downloaded, and every
asset is checked against the size and hash that signed manifest carries.
Run with: uv run --with pynacl python3 fetch_lab_assets.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.request

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

FEATURES = ('airplay2', 'tts', 'wakeword', 'stt', 'assistant')


def field(manifest: str, key: str) -> str:
    for line in manifest.splitlines():
        name, _, value = line.partition('=')
        if name == key:
            return value
    raise SystemExit(f'ERROR: upstream manifest has no {key}')


def download(url: str, destination: pathlib.Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'libreecho-lab'})
    with urllib.request.urlopen(request, timeout=1800) as response, \
            destination.open('wb') as stream:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            stream.write(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=pathlib.Path, required=True,
                        help='directory holding the signed upstream manifest and key')
    parser.add_argument('--release-base', required=True,
                        help='https://github.com/<owner>/<repo>/releases/download/<tag>')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()

    key_file = next(args.upstream.glob('*-ota-public-key.hex'))
    manifest = (args.upstream / 'upstream-target.manifest').read_text()
    signature = bytes.fromhex((args.upstream / 'upstream-target.manifest.sig').read_text().strip())
    try:
        VerifyKey(bytes.fromhex(key_file.read_text().strip())).verify(
            manifest.encode(), signature)
    except BadSignatureError:
        raise SystemExit('ERROR: upstream manifest signature does not verify')
    key_sha256 = hashlib.sha256(key_file.read_bytes()).hexdigest()
    if field(manifest, 'format') != 'libreecho-ota-v3' or \
            field(manifest, 'architecture') != 'armv7':
        raise SystemExit('ERROR: upstream manifest is not a v3 armv7 target')
    release = field(manifest, 'release')

    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for feature in FEATURES:
        for kind, asset_key, hash_key, size_key in (
                ('payload', f'feature_{feature}_asset',
                 f'feature_{feature}_sha256', f'feature_{feature}_size'),
                ('manifest', f'feature_{feature}_manifest_asset',
                 f'feature_{feature}_manifest_sha256',
                 f'feature_{feature}_manifest_size')):
            name = field(manifest, asset_key)
            expected_sha = field(manifest, hash_key)
            expected_size = int(field(manifest, size_key))
            destination = args.output / name
            if destination.is_file():
                got_sha = hashlib.sha256(destination.read_bytes()).hexdigest()
                got_size = destination.stat().st_size
            else:
                print(f'fetch {name}', file=sys.stderr)
                got_sha, got_size = download(f'{args.release_base}/{name}', destination)
            if (got_sha, got_size) != (expected_sha, expected_size):
                destination.unlink()
                raise SystemExit(f'ERROR: {name} does not match the signed manifest')
            records.append({'feature_id': feature, 'kind': kind, 'name': name,
                            'sha256': got_sha, 'size': got_size})
    provenance = {'upstream_release': release,
                  'upstream_manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest(),
                  'upstream_public_key_sha256': key_sha256,
                  'assets': records}
    (args.output / 'provenance.json').write_text(json.dumps(provenance, indent=1) + '\n')
    for record in records:
        print(f"{record['kind']} {record['feature_id']} {record['sha256']} {record['size']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
