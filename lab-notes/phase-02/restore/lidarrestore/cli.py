"""Command line interface for the Lidar boot-chain restore tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .atomic import atomic_write_json
from .backends import (
    DEFAULT_MTKCLIENT_ROOT,
    Backend,
    MtkclientBackend,
    SyntheticBackend,
    faults_from_dict,
    load_identity_file,
)
from .core import apply_plan, build_plan, load_plan, verify_manifest, write_plan
from .errors import RestoreError
from .manifest import load_manifest


def _workdir_path(value: str) -> Path:
    if not value.strip():
        raise argparse.ArgumentTypeError("mtkclient working directory must not be empty")
    return Path(value)


def _add_backend_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("backend")
    group.add_argument(
        "--backend",
        choices=("synthetic", "mtkclient"),
        default="synthetic",
        help="synthetic partition files or the mtkclient adapter",
    )
    group.add_argument(
        "--root",
        type=Path,
        help="synthetic backend directory containing boot1/, boot2/, user/, identity.json",
    )
    group.add_argument(
        "--faults",
        help="JSON fault injection for the synthetic backend, for host experiments only",
    )
    group.add_argument(
        "--mtkclient-root",
        type=Path,
        default=DEFAULT_MTKCLIENT_ROOT,
        help=f"mtkclient checkout (default: {DEFAULT_MTKCLIENT_ROOT})",
    )
    group.add_argument(
        "--mtkclient-python",
        type=Path,
        help="python interpreter for mtkclient (default: <root>/.venv/bin/python)",
    )
    group.add_argument(
        "--mtkclient-workdir",
        type=_workdir_path,
        help=(
            "mtk.py working directory shared by plan, apply, and verify of one hardware "
            "session; a fresh BROM session needs a new empty directory"
        ),
    )
    group.add_argument(
        "--identity-json",
        type=Path,
        help="captured identity JSON for the mtkclient backend; avoids a live identity read",
    )
    group.add_argument(
        "--allow-device-read",
        action="store_true",
        help="permit read-only mtkclient commands against the device",
    )
    group.add_argument(
        "--allow-device-write",
        action="store_true",
        help="permit mtkclient data writes against the device; still needs --allow-write",
    )
    group.add_argument(
        "--partition-offsets",
        type=Path,
        help="JSON object of name to absolute user-area byte offset, for writes at a nonzero offset",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lidar-restore",
        description="Experimental host-side restore/preparation planner for the Lidar boot chain",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="validate a manifest and write an ordered write plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True, help="plan JSON output path")
    _add_backend_args(plan)

    apply = sub.add_parser("apply", help="execute a plan; dry-run unless --allow-write")
    apply.add_argument("--manifest", type=Path, required=True)
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--journal", type=Path, required=True)
    apply.add_argument("--state", type=Path, help="state JSON path (default: <journal>.state.json)")
    apply.add_argument("--result", type=Path, help="result JSON path (default: <journal>.result.json)")
    apply.add_argument(
        "--allow-write",
        action="store_true",
        help="actually write; without this flag apply only validates and prints the plan",
    )
    apply.add_argument("--resume", action="store_true", help="continue a validated journal prefix")
    _add_backend_args(apply)

    verify = sub.add_parser("verify", help="read-only readback comparison against expected hashes")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--report", type=Path, help="write the JSON report atomically to this path")
    _add_backend_args(verify)

    return parser


def _load_partition_offsets(path: Path) -> dict[str, int]:
    try:
        doc = json.loads(Path(path).read_bytes())
    except OSError as exc:
        raise RestoreError(f"cannot read partition offsets {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RestoreError(f"partition offsets {path} are not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise RestoreError("partition offsets must be a JSON object of name to byte offset")
    offsets: dict[str, int] = {}
    for name, value in doc.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RestoreError(f"partition offset for {name!r} must be a non-negative integer")
        offsets[name] = value
    return offsets


def build_backend(args: argparse.Namespace) -> Backend:
    if args.backend == "synthetic":
        if args.root is None:
            raise RestoreError("the synthetic backend requires --root")
        faults = None
        if args.faults:
            try:
                faults = faults_from_dict(json.loads(args.faults))
            except json.JSONDecodeError as exc:
                raise RestoreError(f"--faults is not valid JSON: {exc}") from exc
        return SyntheticBackend(args.root, faults=faults)

    identity = load_identity_file(args.identity_json) if args.identity_json else None
    known_names = identity.get("partitions") if identity else None
    partition_offsets = None
    if args.partition_offsets:
        partition_offsets = _load_partition_offsets(args.partition_offsets)
    return MtkclientBackend(
        mtkclient_root=args.mtkclient_root,
        python_executable=args.mtkclient_python,
        identity=identity,
        mtkclient_workdir=args.mtkclient_workdir,
        allow_device_read=args.allow_device_read,
        allow_device_write=args.allow_device_write,
        partition_offsets=partition_offsets,
        known_names=known_names,
    )


def main(argv: Sequence[str] | None = None, backend: Backend | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        backend = backend or build_backend(args)

        if args.command == "plan":
            plan = build_plan(manifest, backend)
            write_plan(args.out, plan)
            print(
                json.dumps(
                    {
                        "plan": str(args.out),
                        "manifest_sha256": plan["manifest_sha256"],
                        "plan_sha256": plan["plan_sha256"],
                        "items": len(plan["items"]),
                        "skipped": plan["skipped"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "apply":
            plan = load_plan(args.plan)
            result = apply_plan(
                manifest,
                plan,
                backend,
                journal_path=args.journal,
                state_path=args.state,
                result_path=args.result,
                allow_write=args.allow_write,
                resume=args.resume,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "verify":
            report = verify_manifest(manifest, backend)
            if args.report:
                atomic_write_json(args.report, report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["ok"] else 1

        raise RestoreError(f"unknown command {args.command!r}")
    except RestoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
