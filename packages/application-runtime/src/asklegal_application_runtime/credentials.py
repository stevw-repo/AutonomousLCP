"""File-only systemd credential boundary with safe errors and bounded reads."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

_CREDENTIAL_DIRECTORY_VARIABLE = "CREDENTIALS_DIRECTORY"
_CREDENTIAL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_DEFAULT_MAX_BYTES = 65_536
_PRIVATE_READ_ONLY_MODE = 0o400


class CredentialErrorCode(StrEnum):
    """Closed safe reasons credential material cannot be admitted."""

    DIRECTORY = "CREDENTIAL_DIRECTORY_INVALID"
    EMPTY = "CREDENTIAL_EMPTY"
    FILE = "CREDENTIAL_FILE_INVALID"
    MODE = "CREDENTIAL_MODE_INVALID"
    NAME = "CREDENTIAL_NAME_INVALID"
    SIZE = "CREDENTIAL_SIZE_INVALID"


class CredentialError(ValueError):
    """Credential rejection that never includes a path or value."""

    code: CredentialErrorCode

    def __init__(self, code: CredentialErrorCode) -> None:
        """Create one safe credential failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True, repr=False)
class CredentialMaterial:
    """Opaque credential bytes whose representation is always redacted."""

    _value: bytes

    def __repr__(self) -> str:
        """Never expose the value or its size in diagnostics."""
        return "CredentialMaterial(<redacted>)"

    def reveal(self) -> bytes:
        """Return the exact bytes only to the adapter that needs them."""
        return self._value


@dataclass(frozen=True, slots=True)
class SystemdCredentialDirectory:
    """One already-mounted systemd credential directory descriptor."""

    path: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> SystemdCredentialDirectory:
        """Resolve only the standard non-secret directory path from an injected environment."""
        path = environment.get(_CREDENTIAL_DIRECTORY_VARIABLE)
        if path is None or not path.startswith("/") or "\x00" in path:
            raise CredentialError(CredentialErrorCode.DIRECTORY)
        return cls(path=path)

    def read(self, name: str, *, max_bytes: int = _DEFAULT_MAX_BYTES) -> CredentialMaterial:
        """Read one exact private file without path traversal or symlink following."""
        if not _CREDENTIAL_NAME.fullmatch(name):
            raise CredentialError(CredentialErrorCode.NAME)
        if type(max_bytes) is not int or max_bytes < 1:
            raise CredentialError(CredentialErrorCode.SIZE)
        directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
        file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            directory_fd = os.open(self.path, directory_flags)
        except OSError as error:
            raise CredentialError(CredentialErrorCode.DIRECTORY) from error
        try:
            try:
                credential_fd = os.open(name, file_flags, dir_fd=directory_fd)
            except OSError as error:
                raise CredentialError(CredentialErrorCode.FILE) from error
            try:
                details = os.fstat(credential_fd)
                if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                    raise CredentialError(CredentialErrorCode.FILE)
                if stat.S_IMODE(details.st_mode) != _PRIVATE_READ_ONLY_MODE:
                    raise CredentialError(CredentialErrorCode.MODE)
                value = os.read(credential_fd, max_bytes + 1)
            finally:
                os.close(credential_fd)
        finally:
            os.close(directory_fd)
        if not value:
            raise CredentialError(CredentialErrorCode.EMPTY)
        if len(value) > max_bytes:
            raise CredentialError(CredentialErrorCode.SIZE)
        return CredentialMaterial(value)
