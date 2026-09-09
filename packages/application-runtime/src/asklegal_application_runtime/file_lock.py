"""Small Linux file lock shared by local multi-process application adapters."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_local_state_lock(state_path: Path) -> Generator[None]:
    """Hold one process-shared exclusive lock beside an exact local state file."""
    lock_path = state_path.with_suffix(f"{state_path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        message = "LOCAL_STATE_LOCK_INVALID"
        raise OSError(message)
    flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
