#!/usr/bin/env python3
"""Emit a signed OTA v3 bundle and its generation tree for a Lidar lab image.

The canonical key order, value grammar and asset identities match
tools/mt8163-arm32/initramfs/libreecho-target-manifest. Product's
build/ci/ota_v3_product.py cannot express a Lidar target: target_registry.py
KNOWS only radar_puffin and biscuit and validate_plan hardcodes soc=mt8163.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tarfile

from nacl.signing import SigningKey

FEATURES = ('airplay2', 'tts', 'wakeword', 'stt', 'assistant')
DAEMONS = {
    'airplay2': 'usr/local/sbin/libreecho-audio-engine',
    'tts': 'usr/local/sbin/libreecho-ttsd',
    'wakeword': 'usr/local/sbin/libreecho-waked',
    'stt': 'usr/local/sbin/libreecho-sttd',
    'assistant': 'usr/local/sbin/libreecho-agentd',
}
TOP = ('format', 'manifest_version', 'board', 'soc', 'architecture', 'image_profile',
       'transaction_type', 'transaction_id', 'release', 'version', 'update_channel',
       'service_profile', 'minimum_updater_schema', 'commit_policy', 'boot_filename',
       'boot_size', 'boot_sha256', 'feature_ids')
FIELDS = ('asset', 'size', 'sha256', 'manifest_asset', 'manifest_size',
          'manifest_sha256', 'daemon_path', 'daemon_sha256')
BOOT_SIZE = 16 * 1024 * 1024
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+~:-]{0,95}\Z')
VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def fail(message: str) -> None:
    raise SystemExit(f'ERROR: {message}')


def digest(path: pathlib.Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        fail(f'not a regular file: {path}')
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def load_catalog(path: pathlib.Path) -> dict:
    if path.is_symlink() or not path.is_file():
        fail(f'catalog is not a regular file: {path}')
    try:
        catalog = json.loads(path.read_text())
    except ValueError as exc:
        fail(f'catalog is malformed: {exc}')
    features = catalog.get('features') if isinstance(catalog, dict) else None
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        fail('catalog must name exactly the five features')
    return catalog


def feature_records(catalog: dict, catalog_dir: pathlib.Path) -> tuple[list[dict], dict]:
    records, sources = [], {}
    for feature in FEATURES:
        entry = catalog['features'][feature]
        if not isinstance(entry, dict) or not {'payload', 'manifest'} <= set(entry):
            fail(f'catalog entry for {feature} needs payload and manifest paths')
        payload = catalog_dir / entry['payload'] if not pathlib.Path(
            entry['payload']).is_absolute() else pathlib.Path(entry['payload'])
        manifest = catalog_dir / entry['manifest'] if not pathlib.Path(
            entry['manifest']).is_absolute() else pathlib.Path(entry['manifest'])
        payload_sha, payload_size = digest(payload)
        manifest_sha, manifest_size = digest(manifest)
        for key, value in (('payload_sha256', payload_sha), ('payload_size', payload_size),
                           ('manifest_sha256', manifest_sha), ('manifest_size', manifest_size)):
            if key in entry and entry[key] != value:
                fail(f'catalog {feature} {key} does not match the file')
        try:
            identity = json.loads(manifest.read_text())
        except ValueError as exc:
            fail(f'{feature} feature manifest is malformed: {exc}')
        daemon = DAEMONS[feature]
        if (identity.get('schema_version') != 1 or identity.get('feature_id') != feature
                or identity.get('format') != 'squashfs-lz4'
                or identity.get('payload', {}).get('sha256') != payload_sha
                or identity.get('payload', {}).get('size') != payload_size
                or identity.get('files', {}).get(daemon, {}).get('sha256') is None):
            fail(f'{feature} feature manifest does not identify its payload and daemon')
        records.append({
            'feature_id': feature,
            'asset': f'libreecho-lidar-base-{feature}-{payload_sha}.payload.squashfs',
            'size': payload_size,
            'sha256': payload_sha,
            'manifest_asset':
                f'libreecho-lidar-base-{feature}-{manifest_sha}.manifest.json',
            'manifest_size': manifest_size,
            'manifest_sha256': manifest_sha,
            'daemon_path': daemon,
            'daemon_sha256': identity['files'][daemon]['sha256'],
        })
        sources[feature] = (payload, manifest)
    for record in records:
        if not HEX64.fullmatch(record['daemon_sha256']):
            fail(f"{record['feature_id']} feature manifest has a malformed daemon hash")
        if record['size'] <= 0 or record['manifest_size'] <= 0:
            fail(f"{record['feature_id']} asset is empty")
        if len(record['asset']) > 128 or len(record['manifest_asset']) > 128:
            fail(f"{record['feature_id']} asset name exceeds the manifest grammar")
    return records, sources


def transaction_id(plan: dict) -> str:
    material = {key: value for key, value in plan.items() if key != 'transaction_id'}
    encoded = json.dumps(material, sort_keys=True, separators=(',', ':')).encode()
    return 'txn-' + hashlib.sha256(encoded).hexdigest()[:24]


def emit_manifest(plan: dict) -> bytes:
    lines = []
    for key in TOP:
        value = ','.join(FEATURES) if key == 'feature_ids' else plan[key]
        lines.append(f'{key}={value}')
    for record in plan['features']:
        for key in FIELDS:
            lines.append(f"feature_{record['feature_id']}_{key}={record[key]}")
    lines.append(f"config_schema={plan['config_schema']}")
    return ('\n'.join(lines) + '\n').encode('ascii')


def seal(path: pathlib.Path, mode: int) -> None:
    os.chmod(path, mode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--boot-image', type=pathlib.Path, required=True)
    parser.add_argument('--feature-catalog', type=pathlib.Path, required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--update-channel', choices=('dev', 'stable'), required=True)
    parser.add_argument('--service-profile', choices=('production', 'diagnostic'),
                        default='production')
    parser.add_argument('--config-schema', type=int, default=1)
    parser.add_argument('--signing-key', type=pathlib.Path, required=True,
                        help='file holding a 32-byte Ed25519 seed as 64 lowercase hex')
    parser.add_argument('--public-key', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True,
                        help='OTA tar path; the generation tree goes next to it')
    args = parser.parse_args()

    if not TOKEN.fullmatch(args.release) or not TOKEN.fullmatch(args.version):
        fail('release and version must be manifest tokens')
    if not VERSION.fullmatch(args.version):
        fail('version must be MAJOR.MINOR.PATCH')
    if not 1 <= args.config_schema < 2**31:
        fail('config schema must be a positive int')

    boot_sha, boot_size = digest(args.boot_image)
    if boot_size != BOOT_SIZE or not args.boot_image.read_bytes().startswith(b'ANDROID!'):
        fail('boot image must be a 16 MiB Android boot image')

    catalog = load_catalog(args.feature_catalog)
    if catalog.get('board') not in (None, 'lidar'):
        fail('catalog board is not lidar')
    records, sources = feature_records(catalog, args.feature_catalog.parent)

    plan = {
        'format': 'libreecho-ota-v3',
        'manifest_version': 1,
        'board': 'lidar',
        'soc': 'mt8167',
        'architecture': 'armv7',
        'image_profile': 'ota',
        'transaction_type': 'system',
        'transaction_id': '',
        'release': args.release,
        'version': args.version,
        'update_channel': args.update_channel,
        'service_profile': args.service_profile,
        'minimum_updater_schema': 3,
        'commit_policy': 'after-slot-confirm',
        'boot_filename': 'boot.img',
        'boot_size': BOOT_SIZE,
        'boot_sha256': boot_sha,
        'feature_ids': ','.join(FEATURES),
        'features': records,
        'config_schema': args.config_schema,
    }
    plan['transaction_id'] = transaction_id(plan)
    if not TOKEN.fullmatch(plan['transaction_id']):
        fail('derived transaction id is not a token')
    raw = emit_manifest(plan)

    key_text = args.signing_key.read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}', key_text):
        fail('signing key must be one 32-byte Ed25519 seed as lowercase hex')
    signing_key = SigningKey(bytes.fromhex(key_text))
    public_text = args.public_key.read_text()
    if not re.fullmatch(r'[0-9a-f]{64}\n', public_text):
        fail('public key must be 64 lowercase hex plus newline')
    if signing_key.verify_key.encode().hex() != public_text.strip():
        fail('signing key does not match the public key')
    signature = signing_key.sign(raw).signature.hex().encode() + b'\n'

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, blob in (('manifest', raw), ('manifest.sig', signature),
                           ('boot.img', args.boot_image.read_bytes())):
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(blob), 0o644
            archive.addfile(member, io.BytesIO(blob))

    generation = args.output.parent / 'generations' / plan['transaction_id']
    if generation.exists():
        for path in sorted(generation.rglob('*'), reverse=True):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        os.chmod(generation, 0o700)
        shutil.rmtree(generation)
    features_root = generation / 'features'
    features_root.mkdir(parents=True, exist_ok=True)
    (generation / 'target.manifest').write_bytes(raw)
    (generation / 'target.manifest.sig').write_bytes(signature)
    for record in records:
        directory = features_root / record['feature_id']
        directory.mkdir(mode=0o700)
        payload, identity = sources[record['feature_id']]
        (directory / 'payload.squashfs').write_bytes(payload.read_bytes())
        (directory / 'manifest.json').write_bytes(identity.read_bytes())
    (generation / 'COMPLETE').write_bytes(
        hashlib.sha256(raw).hexdigest().encode() + b'\n')
    for path in sorted(generation.rglob('*'), reverse=True):
        seal(path, 0o400 if path.is_file() else 0o500)
    seal(generation, 0o500)

    print(f"transaction_id={plan['transaction_id']}")
    print(f"boot_sha256={boot_sha}")
    print(f'ota={args.output}')
    print(f'generation={generation}')
    print(f'bundle_sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
