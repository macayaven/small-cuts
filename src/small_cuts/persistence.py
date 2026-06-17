from __future__ import annotations

import os
from pathlib import Path

BUCKET_MOUNT_PATH_ENV = "SMALL_CUTS_BUCKET_MOUNT_PATH"


def bucket_mount_path() -> Path | None:
    raw = os.environ.get(BUCKET_MOUNT_PATH_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def persistent_path(*parts: str) -> Path | None:
    mount = bucket_mount_path()
    if mount is None:
        return None
    return mount.joinpath("space", *parts)
