"""Bounded deterministic encodings and file operations; no execution helpers."""
from __future__ import annotations
from pmrh.domain.primitives import (
    MAX_JSON,
    PMRSError,
    ResearchStudioError,
    canonical,
    identity,
    loads,
    require,
    sha,
    sha256_bytes,
)
import hashlib
import errno
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from datetime import datetime, timezone


from pmrh.adapters.storage.io import now as now


from pmrh.adapters.storage.io import safe_path as safe_path

from pmrh.adapters.storage.io import read as read

from pmrh.adapters.storage.io import fsync_dir as fsync_dir

from pmrh.adapters.storage.io import _same_file_bytes as _same_file_bytes

from pmrh.adapters.storage.io import _publication_temp as _publication_temp

def immutable(path: Path, data: bytes):
    from pmrh.adapters.storage.io import immutable as publish
    return publish(path, data)

from pmrh.adapters.storage.io import atomic as atomic
