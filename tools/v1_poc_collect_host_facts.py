"""Collect bounded read-only Ubuntu facts for the disabled V1 POC admission gate."""

from __future__ import annotations

import argparse
import grp
import json
import os
import platform
import pwd
import shutil
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_REQUIRED_PATHS = (
    "/srv/asklegal/sql",
    "/srv/asklegal/vault-primary",
    "/srv/asklegal/vault-recovery",
)
_COMMAND_ENV = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
}
_MAX_COMMAND_OUTPUT = 1_000_000
_SS_MIN_FIELDS = 4


class HostFactsSource(Protocol):
    """Semantic read-only facts supplied by an Ubuntu probe or a deterministic fake."""

    def operating_system(self) -> dict[str, JsonValue]:
        """Return exact ID and VERSION_ID facts."""
        ...

    def architecture(self) -> str:
        """Return the kernel-reported machine architecture."""
        ...

    def memory_bytes(self) -> int:
        """Return physical memory size in bytes."""
        ...

    def physical_disks(self) -> list[JsonValue]:
        """Return bounded physical-disk identity and size facts."""
        ...

    def path_facts(self) -> list[JsonValue]:
        """Return exact facts for only the three required storage paths."""
        ...

    def time_facts(self) -> dict[str, JsonValue]:
        """Return time-synchronization state."""
        ...

    def credential_facts(self) -> dict[str, JsonValue]:
        """Return credential mechanism and file-mode facts without values."""
        ...

    def firewall_facts(self) -> dict[str, JsonValue]:
        """Return default policy and public-listener facts."""
        ...

    def journal_facts(self) -> dict[str, JsonValue]:
        """Return persistent and forward-secure journal facts."""
        ...

    def container_runtime_facts(self) -> dict[str, JsonValue]:
        """Return Docker service and group-boundary facts."""
        ...


def _parse_os_release(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key] = value.strip().strip('"')
    return values


def _json_object(raw: str, label: str) -> dict[str, object]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError(label)
    return value


def _json_objects(value: object, label: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(label)
    return tuple(item for item in value if isinstance(item, dict))


class UbuntuHostFactsSource:
    """Strict read-only collector; unavailable or ambiguous facts fail closed."""

    def __init__(self) -> None:
        """Reject non-Linux execution before any command is issued."""
        if platform.system() != "Linux":
            message = "host fact collection requires Linux"
            raise RuntimeError(message)
        self._disk_ids: dict[str, str] = {}

    def _run(self, command: Sequence[str]) -> str:
        result = subprocess.run(  # noqa: S603
            tuple(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=_COMMAND_ENV,
        )
        if result.returncode != 0 or len(result.stdout.encode()) > _MAX_COMMAND_OUTPUT:
            message = f"read-only probe failed: {command[0]}"
            raise RuntimeError(message)
        return result.stdout.strip()

    def operating_system(self) -> dict[str, JsonValue]:
        """Read the bounded operating-system release file."""
        values = _parse_os_release(Path("/etc/os-release").read_text(encoding="utf-8"))
        return {
            "id": values.get("ID", "UNKNOWN"),
            "version_id": values.get("VERSION_ID", "UNKNOWN"),
        }

    def architecture(self) -> str:
        """Read the machine architecture without executing a command."""
        return platform.machine()

    def memory_bytes(self) -> int:
        """Compute physical memory from kernel page counters."""
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        if not isinstance(page_size, int) or not isinstance(page_count, int):
            message = "memory fact unavailable"
            raise TypeError(message)
        return page_size * page_count

    def physical_disks(self) -> list[JsonValue]:
        """Read physical disk paths and sizes through lsblk JSON."""
        raw = self._run(("lsblk", "--json", "--bytes", "--output", "PATH,TYPE,SIZE,WWN,SERIAL"))
        document = _json_object(raw, "lsblk document")
        devices = _json_objects(document.get("blockdevices"), "lsblk devices")
        disks: list[JsonValue] = []
        for device in devices:
            if device.get("type") != "disk":
                continue
            path = device.get("path")
            size = device.get("size")
            if not isinstance(path, str) or not isinstance(size, int):
                message = "physical disk fact"
                raise TypeError(message)
            stable_value = device.get("wwn") or device.get("serial") or path
            if not isinstance(stable_value, str) or not stable_value:
                message = "physical disk identity"
                raise TypeError(message)
            stable_id = f"disk:{stable_value}"
            self._disk_ids[path] = stable_id
            disks.append({"stable_id": stable_id, "size_bytes": size})
        return disks

    def _physical_disk_id(self, source: str) -> str:
        parent = self._run(("lsblk", "--noheadings", "--output", "PKNAME", source)).splitlines()
        disk_path = f"/dev/{parent[-1].strip()}" if parent and parent[-1].strip() else source
        return self._disk_ids.get(disk_path, f"UNRESOLVED:{disk_path}")

    def path_facts(self) -> list[JsonValue]:
        """Read filesystem and backing-disk facts for required paths only."""
        if not self._disk_ids:
            self.physical_disks()
        facts: list[JsonValue] = []
        for path_text in _REQUIRED_PATHS:
            path = Path(path_text)
            real_path = path.resolve(strict=False).as_posix()
            filesystem = self._run(
                ("findmnt", "--json", "--target", path_text, "--output", "FSTYPE,SOURCE")
            )
            document = _json_object(filesystem, "findmnt document")
            filesystems = _json_objects(document.get("filesystems"), "findmnt filesystems")
            if len(filesystems) != 1:
                message = f"ambiguous filesystem: {path_text}"
                raise TypeError(message)
            fs_type = filesystems[0].get("fstype")
            source = filesystems[0].get("source")
            if not isinstance(fs_type, str) or not isinstance(source, str):
                message = f"filesystem fact: {path_text}"
                raise TypeError(message)
            facts.append(
                {
                    "path": path_text,
                    "real_path": real_path,
                    "fs_type": fs_type,
                    "physical_disk_id": self._physical_disk_id(source),
                    "symlink": path.is_symlink(),
                    "writable": path.is_dir() and os.access(path, os.W_OK),
                }
            )
        return facts

    def time_facts(self) -> dict[str, JsonValue]:
        """Read systemd's NTP synchronization fact."""
        synchronized = self._run(("timedatectl", "show", "--property=NTPSynchronized", "--value"))
        return {"synchronized": synchronized.lower() == "yes"}

    def credential_facts(self) -> dict[str, JsonValue]:
        """Inspect only credential mechanisms, modes, and suspicious path names."""
        credential_root = Path("/etc/asklegal/credentials")
        encrypted_blobs = tuple(credential_root.glob("*.cred")) if credential_root.is_dir() else ()
        modes = {stat.S_IMODE(path.stat().st_mode) for path in encrypted_blobs}
        encrypted_mode = "0400" if encrypted_blobs and modes == {0o400} else "UNPROVED"
        plaintext_names: list[str] = []
        config_root = Path("/etc/asklegal")
        if config_root.is_dir():
            for path in config_root.rglob("*"):
                lowered = path.name.lower()
                if (
                    path.is_file()
                    and path.suffix != ".cred"
                    and any(
                        marker in lowered
                        for marker in ("credential", "password", "secret", "token")
                    )
                ):
                    plaintext_names.append(path.as_posix())
        protection_mode = (
            "TPM2_PLUS_HOST_KEY"
            if Path("/dev/tpmrm0").exists() or Path("/dev/tpm0").exists()
            else "HOST_KEY_ONLY"
        )
        return {
            "systemd_creds_available": shutil.which("systemd-creds") is not None,
            "protection_mode": protection_mode,
            "encrypted_blob_mode": encrypted_mode,
            "persistent_plaintext_credential_paths": sorted(plaintext_names),
        }

    def _nft_defaults(self) -> tuple[bool, str, str, str]:
        nft_available = shutil.which("nft") is not None
        input_default = "UNPROVED"
        forward_default = "UNPROVED"
        egress_default = "UNPROVED"
        if nft_available:
            ruleset = _json_object(self._run(("nft", "--json", "list", "ruleset")), "nft")
            entries = ruleset.get("nftables")
            if isinstance(entries, list):
                for entry in entries:
                    chain = entry.get("chain") if isinstance(entry, dict) else None
                    if not isinstance(chain, dict):
                        continue
                    hook = chain.get("hook")
                    name = chain.get("name")
                    policy = chain.get("policy")
                    if hook == "input":
                        input_default = str(policy).upper()
                    elif hook == "forward":
                        forward_default = str(policy).upper()
                    if name == "asklegal-container-egress":
                        egress_default = str(policy).upper()
        return nft_available, input_default, forward_default, egress_default

    def _public_tcp_ports(self) -> list[int]:
        public_ports: list[int] = []
        for line in self._run(
            ("ss", "--no-header", "--tcp", "--listening", "--numeric")
        ).splitlines():
            fields = line.split()
            if len(fields) < _SS_MIN_FIELDS:
                continue
            endpoint = fields[3]
            host, _, port_text = endpoint.rpartition(":")
            if host not in {"127.0.0.1", "[::1]", "::1"} and port_text.isdigit():
                public_ports.append(int(port_text))
        return sorted(set(public_ports))

    def firewall_facts(self) -> dict[str, JsonValue]:
        """Read nftables default policies and non-loopback TCP listeners."""
        nft_available, input_default, forward_default, egress_default = self._nft_defaults()
        return {
            "nftables_available": nft_available,
            "input_default": input_default,
            "forward_default": forward_default,
            "direct_container_egress_default": egress_default,
            "public_tcp_ports": self._public_tcp_ports(),
        }

    def journal_facts(self) -> dict[str, JsonValue]:
        """Inspect persistent journal and sealing-key presence without reading logs."""
        journal_root = Path("/var/log/journal")
        return {
            "storage": "PERSISTENT" if journal_root.is_dir() else "VOLATILE",
            "forward_secure_sealing": bool(tuple(journal_root.glob("*/fss"))),
        }

    def container_runtime_facts(self) -> dict[str, JsonValue]:
        """Inspect Docker presence, systemd activity, and non-root group membership."""
        try:
            docker_group = grp.getgrnam("docker")
        except KeyError:
            members: set[str] = set()
        else:
            members = set(docker_group.gr_mem)
            members.update(
                entry.pw_name
                for entry in pwd.getpwall()
                if entry.pw_gid == docker_group.gr_gid and entry.pw_uid != 0
            )
        docker_active = self._run(("systemctl", "is-active", "docker")) == "active"
        return {
            "name": "docker"
            if shutil.which("docker") is not None and docker_active
            else "UNPROVED",
            "service_manager": "systemd" if Path("/run/systemd/system").is_dir() else "UNPROVED",
            "docker_group_non_root_members": sorted(members),
        }


def collect_host_facts(source: HostFactsSource) -> dict[str, JsonValue]:
    """Build the exact secret-free fact document consumed by host admission."""
    return {
        "schema_version": 1,
        "source": "READ_ONLY_HOST_FACTS",
        "os": source.operating_system(),
        "architecture": source.architecture(),
        "memory_bytes": source.memory_bytes(),
        "physical_disks": source.physical_disks(),
        "paths": source.path_facts(),
        "time": source.time_facts(),
        "credentials": source.credential_facts(),
        "firewall": source.firewall_facts(),
        "journal": source.journal_facts(),
        "container_runtime": source.container_runtime_facts(),
        "host_packages": {},
        "private_subnets": {},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acknowledge-read-only-host-inspection",
        action="store_true",
        help="required acknowledgement; performs no provisioning or credential reads",
    )
    return parser


def main() -> None:
    """Print facts to stdout only after explicit read-only inspection acknowledgement."""
    arguments = _parser().parse_args()
    if not arguments.acknowledge_read_only_host_inspection:
        message = "explicit read-only host-inspection acknowledgement required"
        raise SystemExit(message)
    print(  # noqa: T201
        json.dumps(collect_host_facts(UbuntuHostFactsSource()), indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
