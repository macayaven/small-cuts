"""Promote real Modal-narrated uploads into the relay manifest (the persistent public library).

Replaces the hand-authored demo seed with genuine pipeline output. SAFE BY DESIGN: it writes ONLY
``relay/manifest.json`` as a single file via HfFileSystem — never a mirror ``sync_bucket`` that
could delete the ``relay/uploads/`` media. It snapshots the uploads/ folder count before and after
every write and aborts loudly if anything was removed. UI/viewer code is never touched.

Usage:
    uv run python scripts/promote_uploads_to_library.py --self-test
    uv run python scripts/promote_uploads_to_library.py --list
    uv run python scripts/promote_uploads_to_library.py --latest 1 --dry-run
    uv run python scripts/promote_uploads_to_library.py --scene-ids modal-abc... [--keep-seed]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from huggingface_hub import HfFileSystem

BUCKET = "macayaven/small-cuts-scenes-dev"
PREFIX = "relay"


def root() -> str:
    return f"hf://buckets/{BUCKET}/{PREFIX}"


def upload_folder_count(fs: HfFileSystem) -> int:
    try:
        return len([e for e in fs.ls(f"{root()}/uploads", detail=False) if "/uploads/" in e])
    except FileNotFoundError:
        return 0


def list_uploads(fs: HfFileSystem) -> dict[str, dict | None]:
    try:
        entries = fs.ls(f"{root()}/uploads", detail=False)
    except FileNotFoundError:
        return {}
    out: dict[str, dict | None] = {}
    for e in entries:
        if "/uploads/" not in e:
            continue
        sid = e.rstrip("/").split("/")[-1]
        try:
            out[sid] = json.loads(fs.read_text(f"{e.rstrip('/')}/scene.json"))
        except Exception:
            out[sid] = None
    return out


def read_manifest(fs: HfFileSystem) -> dict:
    try:
        return json.loads(fs.read_text(f"{root()}/manifest.json"))
    except Exception:
        return {"contract_version": "1.1.0", "scenes": []}


def write_manifest_safely(fs: HfFileSystem, manifest: dict) -> bool:
    before = upload_folder_count(fs)
    fs.write_text(f"{root()}/manifest.json", json.dumps(manifest, indent=2) + "\n")
    after = upload_folder_count(fs)
    if after < before:
        print(
            f"!!! DANGER: relay/uploads/ dropped {before} -> {after} after write — media may be "
            "gone. Stop and investigate.",
            file=sys.stderr,
        )
        return False
    print(
        f"OK: wrote manifest.json ({len(manifest.get('scenes', []))} scenes); "
        f"uploads/ intact ({after})."
    )
    return True


def self_test(fs: HfFileSystem) -> bool:
    scratch = f"{root()}/_promote_safety_check.json"
    before = upload_folder_count(fs)
    print(f"self-test: uploads/ folders before = {before}")
    fs.write_text(scratch, json.dumps({"test": True}))
    back = json.loads(fs.read_text(scratch))
    after = upload_folder_count(fs)
    print(f"self-test: wrote+read scratch (ok={back.get('test')}); uploads/ after = {after}")
    try:
        fs.rm(scratch)
        print("self-test: scratch removed.")
    except Exception as exc:
        print(
            f"self-test: could not remove scratch ({exc}); "
            "delete relay/_promote_safety_check.json by hand."
        )
    ok = after == before
    verdict = (
        "PASS — single-file write is safe (uploads untouched)"
        if ok
        else "FAIL — uploads count changed!"
    )
    print("SELF-TEST:", verdict)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list uploads + current manifest")
    ap.add_argument("--self-test", action="store_true", help="verify single-file write is safe")
    ap.add_argument("--scene-ids", nargs="*", default=None, help="upload scene_ids to publish")
    ap.add_argument("--latest", type=int, default=0, help="publish the N most recent uploads")
    ap.add_argument(
        "--keep-seed", action="store_true", help="keep existing manifest scenes (default: replace)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="build + print the manifest, do not write"
    )
    args = ap.parse_args()

    fs = HfFileSystem()
    if args.self_test:
        return 0 if self_test(fs) else 1

    uploads = list_uploads(fs)
    manifest = read_manifest(fs)

    if args.list:
        print(f"manifest.json: {len(manifest.get('scenes', []))} published (the library)")
        for s in manifest.get("scenes", []):
            print(f"   [lib] {s.get('scene_id')} | {s.get('title')!r} | source={s.get('source')}")
        print(f"relay/uploads/: {len(uploads)} clip(s)")
        for sid, raw in sorted(uploads.items(), key=lambda kv: (kv[1] or {}).get("created_at", "")):
            sc = raw or {}
            print(f"   [upl] {sid} | {sc.get('title', '?')!r} | {sc.get('created_at', '?')}")
        return 0

    chosen: list[dict] = []
    if args.scene_ids:
        for sid in args.scene_ids:
            if uploads.get(sid):
                chosen.append(uploads[sid])
            else:
                print(f"WARN: {sid} not found / unreadable", file=sys.stderr)
    elif args.latest:
        ordered = sorted(
            ((sid, sc) for sid, sc in uploads.items() if sc),
            key=lambda kv: kv[1].get("created_at", ""),
        )
        chosen = [sc for _, sc in ordered[-args.latest :]]
    else:
        print(
            "Nothing to do. Use --list / --self-test / --scene-ids ... / --latest N.",
            file=sys.stderr,
        )
        return 2

    kept = manifest.get("scenes", []) if args.keep_seed else []
    chosen_ids = {s.get("scene_id") for s in chosen}
    merged = [s for s in kept if s.get("scene_id") not in chosen_ids] + chosen
    new_manifest = {
        "contract_version": "1.1.0",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_engine": "promote-uploads",
        "scenes": merged,
    }
    mode = "kept seed + promoted" if args.keep_seed else "REPLACING seed"
    print(f"promoting {len(chosen)} scene(s); manifest -> {len(merged)} total ({mode}):")
    for s in chosen:
        print(f"   + {s.get('scene_id')} | {s.get('title')!r}")
    if args.dry_run:
        print("\n[dry-run] manifest NOT written. Re-run without --dry-run to publish.")
        return 0
    return 0 if write_manifest_safely(fs, new_manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
