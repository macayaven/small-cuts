#!/usr/bin/env python3
"""Publish finished Small Cuts engine scenes into a Hugging Face bucket relay."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import time
from pathlib import Path

import httpx
from huggingface_hub import HfApi

from small_cuts.hf_relay import (
    DEFAULT_RELAY_PREFIX,
    DEFAULT_SCENE_LIMIT,
    RELAY_BUCKET_ENV,
    RELAY_PREFIX_ENV,
    prepare_relay_snapshot,
)
from small_cuts.observability import capture_exception, init_sentry
from small_cuts.space_hooks import RELAY_HOOK_TOKEN_ENV

RELAY_HOOK_URL_ENV = "SMALL_CUTS_RELAY_HOOK_URL"
HOOK_TIMEOUT_S = 5.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine-url",
        default=os.environ.get("SMALL_CUTS_ENGINE_URL", "http://127.0.0.1:8077"),
        help="Private engine base URL. Defaults to SMALL_CUTS_ENGINE_URL or local engine.",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get(RELAY_BUCKET_ENV, ""),
        help=(
            "HF bucket id, e.g. build-small-hackathon/small-cuts-scenes. "
            f"Can use {RELAY_BUCKET_ENV}."
        ),
    )
    parser.add_argument(
        "--prefix",
        default=os.environ.get(RELAY_PREFIX_ENV, DEFAULT_RELAY_PREFIX),
        help=f"Bucket prefix. Defaults to {DEFAULT_RELAY_PREFIX!r}.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_SCENE_LIMIT)
    parser.add_argument("--interval", type=float, default=2.0, help="Watch interval in seconds.")
    parser.add_argument("--watch", action="store_true", help="Keep publishing on an interval.")
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Publish private scenes too. Use only for an intentional controlled demo.",
    )
    parser.add_argument(
        "--source",
        default="",
        help='Optional public provenance marker for staged scenes, e.g. "glasses".',
    )
    parser.add_argument(
        "--delete-extra",
        action="store_true",
        help="Delete bucket files not present in the staged snapshot.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Stage locally without syncing.")
    parser.add_argument(
        "--hook-url",
        default=os.environ.get(RELAY_HOOK_URL_ENV, ""),
        help="Optional Space relay hook URL called once after a successful bucket sync.",
    )
    parser.add_argument(
        "--hook-token",
        default=os.environ.get(RELAY_HOOK_TOKEN_ENV, ""),
        help=f"Bearer token for --hook-url. Defaults to {RELAY_HOOK_TOKEN_ENV}.",
    )
    parser.add_argument(
        "--stage-dir",
        default=str(Path(tempfile.gettempdir()) / "small-cuts-relay-publish"),
        help="Local staging directory.",
    )
    return parser.parse_args()


def _clean_stage(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def publish_once(args: argparse.Namespace) -> None:
    if not args.bucket:
        raise SystemExit(f"--bucket or {RELAY_BUCKET_ENV} is required")
    stage_dir = Path(args.stage_dir)
    _clean_stage(stage_dir)
    snapshot = prepare_relay_snapshot(
        args.engine_url,
        stage_dir,
        limit=args.limit,
        include_private=args.include_private,
        source=args.source.strip() or None,
    )
    dest = f"hf://buckets/{args.bucket}/{args.prefix.strip('/')}"
    if args.dry_run:
        print(f"dry-run staged {snapshot.scene_count} scene(s) at {snapshot.path}")
        print(f"would sync to {dest}")
        return
    HfApi().sync_bucket(
        source=str(snapshot.path),
        dest=dest,
        delete=args.delete_extra,
        quiet=False,
    )
    print(f"published {snapshot.scene_count} scene(s) to {dest}")
    notify_relay_hook(args, snapshot, bucket=args.bucket, prefix=args.prefix.strip("/"))


def notify_relay_hook(
    args: argparse.Namespace,
    snapshot,
    *,
    bucket: str,
    prefix: str,
) -> None:
    hook_url = (args.hook_url or "").strip()
    if not hook_url:
        return
    hook_token = (args.hook_token or "").strip()
    headers = {"Authorization": f"Bearer {hook_token}"} if hook_token else {}
    response = httpx.post(
        hook_url,
        headers=headers,
        json={"bucket": bucket, "prefix": prefix, "scene_count": snapshot.scene_count},
        timeout=HOOK_TIMEOUT_S,
    )
    response.raise_for_status()
    print(f"notified relay hook {hook_url}")


def main() -> None:
    init_sentry()
    args = parse_args()
    while True:
        try:
            publish_once(args)
        except Exception as exc:
            capture_exception(exc)
            raise
        if not args.watch:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
