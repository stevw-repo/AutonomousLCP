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
from typing import TYPE_CHECKING, Protocol, cast

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
_LOCKED_HOST_PACKAGES = (
    "ca-certificates",
    "containerd.io",
    "docker-ce",
    "docker-ce-cli",
    "e2fsprogs",
    "nftables",
    "systemd",
    "systemd-timesyncd",
    "util-linux",
)
_DECLARED_NETWORK_IDS = (
    "asklegal-register",
    "asklegal-scheduler-general",
    "asklegal-scheduler-promotion",
    "asklegal-vault-primary",
    "asklegal-vault-recovery",
    "asklegal-review",
    "asklegal-telemetry",
    "asklegal-egress-source",
    "asklegal-egress-model",
    "asklegal-egress-promotion",
)


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

    def host_package_facts(self) -> dict[str, JsonValue]:
        """Return exact installed versions for only the locked host packages."""
        ...

    def observed_network_facts(self) -> dict[str, JsonValue]:
        """Return the declared container subnets and every other host network in use."""
        ...


def parse_os_release(raw: str) -> dict[str, str]:
    """Parse declared key/value facts from one bounded OS release document."""
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key] = value.strip().strip('"')
    return values


def _json_object(raw: str, label: str) -> dict[str, object]:
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        raise TypeError(label)
    return document


def _json_objects(value: object, label: str) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        raise ValueError(label)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            raise ValueError(label)
        result.append(document)
    return tuple(result)


def _string_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        return None
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


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

    def _absent_or_run(self, command: Sequence[str]) -> str | None:
        """Return output, or None when the inspected object simply does not exist yet."""
        try:
            return self._run(command)
        except RuntimeError:
            return None

    def operating_system(self) -> dict[str, JsonValue]:
        """Read the bounded operating-system release file."""
        values = parse_os_release(Path("/etc/os-release").read_text(encoding="utf-8"))
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
        plaintext_paths: list[JsonValue] = []
        plaintext_paths.extend(sorted(plaintext_names))
        return {
            "systemd_creds_available": shutil.which("systemd-creds") is not None,
            "protection_mode": protection_mode,
            "encrypted_blob_mode": encrypted_mode,
            "persistent_plaintext_credential_paths": plaintext_paths,
        }

    def _nft_defaults(self) -> tuple[bool, str, str, str]:
        nft_available = shutil.which("nft") is not None
        input_default = "UNPROVED"
        forward_default = "UNPROVED"
        egress_default = "UNPROVED"
        if nft_available:
            ruleset = _json_object(self._run(("nft", "--json", "list", "ruleset")), "nft")
            entries = ruleset.get("nftables")
            entry_items = _object_list(entries)
            if entry_items is not None:
                for raw_entry in entry_items:
                    entry = _string_object(raw_entry)
                    chain = None if entry is None else _string_object(entry.get("chain"))
                    if chain is None:
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
        public_ports: list[JsonValue] = []
        public_ports.extend(self._public_tcp_ports())
        return {
            "nftables_available": nft_available,
            "input_default": input_default,
            "forward_default": forward_default,
            "direct_container_egress_default": egress_default,
            "public_tcp_ports": public_ports,
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
        group_members: list[JsonValue] = []
        group_members.extend(sorted(members))
        return {
            "name": "docker"
            if shutil.which("docker") is not None and docker_active
            else "UNPROVED",
            "service_manager": "systemd" if Path("/run/systemd/system").is_dir() else "UNPROVED",
            "docker_group_non_root_members": group_members,
        }

    def host_package_facts(self) -> dict[str, JsonValue]:
        """Read exact installed versions for only the locked packages; absent means absent."""
        versions: dict[str, JsonValue] = {}
        for name in _LOCKED_HOST_PACKAGES:
            raw = self._absent_or_run(
                ("dpkg-query", "--showformat=${Version}|${Status}", "--show", name)
            )
            version, _, status = (raw or "").partition("|")
            if status.strip() != "install ok installed" or not version:
                versions[name] = "NOT_INSTALLED"
                continue
            versions[name] = version
        return versions

    def observed_network_facts(self) -> dict[str, JsonValue]:
        """Report the declared container subnets and every other IPv4 network on this host."""
        declared: dict[str, str] = {}
        for network_id in _DECLARED_NETWORK_IDS:
            raw = self._absent_or_run(
                (
                    "docker",
                    "network",
                    "inspect",
                    "--format",
                    "{{range .IPAM.Config}}{{.Subnet}}{{end}}",
                    network_id,
                )
            )
            if raw:
                declared[network_id] = raw
        declared_json: dict[str, JsonValue] = dict(declared)
        return {
            "declared": declared_json,
            "foreign": self._foreign_networks(set(declared.values())),
        }

    def _foreign_networks(self, declared: set[str]) -> list[JsonValue]:
        """Return every non-loopback IPv4 host network that is not a declared subnet."""
        interfaces = _json_objects(json.loads(self._run(("ip", "-json", "addr", "show"))), "ip")
        foreign: set[str] = set()
        for interface in interfaces:
            if interface.get("ifname") == "lo":
                continue
            addresses = _object_list(interface.get("addr_info"))
            if addresses is None:
                continue
            for raw_address in addresses:
                address = _string_object(raw_address)
                if address is None or address.get("family") != "inet":
                    continue
                local = address.get("local")
                prefix = address.get("prefixlen")
                if type(local) is not str or type(prefix) is not int:
                    continue
                cidr = f"{local}/{prefix}"
                if cidr not in declared:
                    foreign.add(cidr)
        result: list[JsonValue] = []
        result.extend(sorted(foreign))
        return result


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
        "host_packages": source.host_package_facts(),
        "private_subnets": source.observed_network_facts(),
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
