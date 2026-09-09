"""Disabled, zero-network Hong Kong V1 external-source admission preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Never, TypedDict, cast
from urllib.parse import urlsplit

from asklegal_contracts import ContractViolation, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_reporting import (
    DueCycleKind,
    DueRegisterBundle,
    HongKongV1DueCycleInstruction,
    HongKongV1DueRequirement,
    derive_hk_v1_due_cycle_plan,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_due_register_bundle,
)

from tools.hk_v1_hkex_history import HistoricalHKEXReplayPin, historical_hkex_replay_pin
from tools.hk_v1_hkex_policy import execution_policy_fingerprint as hkex_policy_fingerprint
from tools.hk_v1_judiciary_policy import (
    execution_policy_fingerprint as judiciary_policy_fingerprint,
)

if __name__ == "__main__":
    from tools import hk_v1_source_admission as _canonical_admission  # noqa: PLW0406

    raise SystemExit(_canonical_admission.main())

_MAX_DOCUMENT_BYTES = 1_000_000
_MAX_HISTORICAL_JUDICIARY_REPORT_BYTES = 6_000_000
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VERSION = re.compile(r"v[0-9a-f]{64}\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_LOGICAL_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,511}\Z")
_SAFE_TEXT = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|credential[_-]?value|password|private[_-]?key|secret|token)\Z", re.IGNORECASE
)
_SECRET_VALUE = re.compile(
    r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@|(?:sessionid|cookie|csrf|bearer)=[^\s]+)",
    re.IGNORECASE,
)
_UTC_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00\Z")
_CAPABILITY_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,159}\Z")
_SENSITIVE_CAPABILITY_NAME = re.compile(r"(?:bearer|cookie|csrf|secret|token)", re.IGNORECASE)
_CAPABILITY_TYPES = {
    "credentials": frozenset(
        {"CREDENTIAL_REFERENCE", "CLIENT_CERTIFICATE_REFERENCE", "NO_CREDENTIAL_REQUIRED"}
    ),
    "sessions": frozenset({"SESSION_REFERENCE"}),
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REGISTER_ROOT = Path("packages/source-connectors/src/asklegal_source_connectors")
_REGISTER_PATHS = {
    "LEGISLATION": _REGISTER_ROOT / "hk_legislation_source_register.json",
    "CASES": _REGISTER_ROOT / "hk_cases_source_register.json",
    "REGULATORY": _REGISTER_ROOT / "hk_regulatory_source_register.json",
}
_V1_DUE_FAMILIES = frozenset({"CASES", "LEGISLATION"})
_CHECKED_IN_RAW_SHA256 = {
    "LEGISLATION": "3acc5951db39b0709662d8da31df2dfd3ac7894a4b34f4c8929f91158d260f26",
    "CASES": "64a32d7d6fb54a1f42f475d01fcb75f56cc484f7175bda46d289941bdecebb63",
    "REGULATORY": "404039ce835b9f891aed03f5e9a45f28cbf3620f599fcf434eda271515d59d5a",
}
_MATRIX_PATH = Path("packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json")
_CHECKED_IN_MATRIX_RAW_SHA256 = "2a4a8021b12d1adb52decfd8b007c8610d0eb20c2185b322315b265355de9c29"
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "authority_id",
        "scope",
        "provenance",
        "effective_date",
        "expires_on",
        "fingerprint",
        "matrix",
        "registers",
        "selected_sources",
        "publisher_permissions",
        "user_reports",
        "terms",
        "observation_window",
        "credentials",
        "sessions",
    }
)
_TERMS_STATES = frozenset(
    {
        "NOT_EXPECTED",
        "EXPECTED_NOT_ACCEPTED",
        "ALREADY_ACCEPTED_WITH_EVIDENCE",
        "PRESENTATION_REQUIRES_USER_ACTION",
    }
)
_AUTHORITY_PROVENANCES = frozenset(
    {
        "PROJECT_USER_AUTHORITY_REQUEST",
        "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
    }
)


@dataclass(slots=True)
class _AuthorityContext:
    """Validated read-only facts shared by selected-source checks."""

    matrix_sources: set[tuple[str, str]]
    registers: dict[str, dict[str, object]]
    permissions: dict[str, dict[str, object]]
    terms: dict[str, dict[str, object]]
    codes: set[str]
    due_source_ids: set[str]
    due_requirements: dict[str, HongKongV1DueRequirement]


class AdmissionReport(TypedDict):
    """Canonical no-effect preflight terminal."""

    execute_authorized: bool
    limitation_codes: list[str]
    missing_codes: list[str]
    result: str


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """Exact local authority proof that must exist before transport construction."""

    authority_manifest_fingerprint: str
    source_family: str
    source_ids: tuple[str, ...]
    observation_cutoff: str
    allowed_urls: tuple[str, ...]
    register_identity: tuple[str, str, str]
    binding_fingerprint: str
    historical_replay: bool


_EXECUTION_SOURCE_IDS = {
    "GLD": frozenset({"HK-LEG-GLD-EGAZETTE"}),
    "HKEL": frozenset(
        {
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        }
    ),
    "JUDICIARY": frozenset({"HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"}),
    "HKEX": frozenset(
        {
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "HK-REG-HKEX-FEES-RULES",
            "HK-REG-HKEX-REGULATORY-FORMS",
            "HK-REG-HKEX-RULE-UPDATES",
            "HK-REG-HKEX-RULEBOOK-CATALOGUE",
        }
    ),
}
_POST_V1_DORMANT_SOURCE_IDS = _EXECUTION_SOURCE_IDS["HKEX"]
_OPERATIONAL_ATTESTATION_CODES = frozenset(
    {
        "MATRIX_RIGHTS_ADMISSION_MISSING",
        "MATRIX_TECHNICAL_ADMISSION_MISSING",
        "SOURCE_BLOCKERS_PRESENT",
        "SOURCE_OPERATIONAL_ADMISSION_MISSING",
    }
)
_HISTORICAL_REPLAY_MISMATCH_CODES = frozenset(
    {
        "CASES_REGISTER_CHECKED_IN_BYTES_DRIFT",
        "CASES_REGISTER_IDENTITY_MISMATCH",
        "ENDPOINT_PATH_UNREGISTERED",
        "LEGISLATION_REGISTER_IDENTITY_MISMATCH",
        "MATRIX_IDENTITY_MISMATCH",
        "SELECTED_SOURCE_ENDPOINT_MEMBERSHIP_INCOMPLETE",
    }
)
_HISTORICAL_JUDICIARY_REPLAY_MISMATCH_CODES = frozenset(
    {
        "DUE_SOURCE_UNIVERSE_INVALID",
        "ENDPOINT_HOST_UNREGISTERED",
        "REGULATORY_REGISTER_CHECKED_IN_BYTES_DRIFT",
        "REGULATORY_REGISTER_IDENTITY_MISMATCH",
        "SELECTED_SOURCE_NOT_DUE",
    }
)
_JUDICIARY_UNRELATED_REGULATORY_DRIFT_CODES = frozenset(
    {
        "ENDPOINT_HOST_UNREGISTERED",
        "ENDPOINT_PATH_UNREGISTERED",
        "REGULATORY_REGISTER_CHECKED_IN_BYTES_DRIFT",
        "REGULATORY_REGISTER_IDENTITY_MISMATCH",
        "SELECTED_SOURCE_ENDPOINT_MEMBERSHIP_INCOMPLETE",
    }
)
_HISTORICAL_HKEX_REPLAY_MISMATCH_CODES = frozenset(
    {
        "ENDPOINT_HOST_UNREGISTERED",
        "MATRIX_IDENTITY_MISMATCH",
        "REGULATORY_REGISTER_CHECKED_IN_BYTES_DRIFT",
        "REGULATORY_REGISTER_IDENTITY_MISMATCH",
    }
)
_HISTORICAL_HKEL_REGISTER_IDENTITY = (
    "hsr_000000000000000000000000000000000000000000000001",
    "2026-08-28.2",
    "sha256:4ab32818f0b273307503e28d7158cd877c52432ab0c7ca39eb7de4ad5a30160f",
)
_HISTORICAL_HKEL_ALLOWED_URLS_FINGERPRINT = (
    "sha256:a4ca7c67fd387af95529c179515d64f46e2658f3bdc3dc0c4d3a272bdb30086a"
)
_HISTORICAL_JUDICIARY_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-27.1",
    "sha256:02700ad98a04acef07fb299b4494659c9dae4d2c5466509c51a6b674f6a17375",
)
_HISTORICAL_JUDICIARY_ALLOWED_URLS_FINGERPRINT = (
    "sha256:62974911bf9f07eca4f2c5d4e9be7ee6e4600d28863223e5b3684d1d8d2619dc"
)
_HISTORICAL_JUDICIARY_ATTEMPT_ID = "judiciary-live-baseline-20260828a"
_HISTORICAL_JUDICIARY_CUTOFF = "2026-08-28T22:20:23+08:00"
_HISTORICAL_JUDICIARY_AUTHORITY_FINGERPRINT = (
    "sha256:ef67b8dd0a6f00d23ca4ec1e8ac157d3fdd6423bf88dbd4f6b4346c0df296c66"
)
_HISTORICAL_JUDICIARY_REPORT_SHA256 = (
    "262e7c9447802df3a76ceca29bc6d3986fd14116788ddee48b868eccd5d06296"
)
_HISTORICAL_JUDICIARY_ATTEMPT_B_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.1",
    "sha256:d4fe3977563b11d776e6e597ade103f68f5140eaa6638d9da5bcb03a68c49ce6",
)
_HISTORICAL_JUDICIARY_ATTEMPT_B_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_B_ID = "judiciary-live-baseline-20260830b"
_HISTORICAL_JUDICIARY_ATTEMPT_B_CUTOFF = "2026-08-30T07:18:07+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_B_AUTHORITY_FINGERPRINT = (
    "sha256:7ddc8b454d8bb1cc1b05f8be0006f3ee2a914f190436271a64afaaf282a93c52"
)
_HISTORICAL_JUDICIARY_ATTEMPT_B_REPORT_SHA256 = (
    "1617c6f37ea553078587ce7d9bbd404a0d35f0e53ca002b91657eece538a0df6"
)
_HISTORICAL_JUDICIARY_ATTEMPT_C_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.2",
    "sha256:9550ac6c95de33db715ccdd2a51225995e43cdac2bd207b29e01276e63d992f8",
)
_HISTORICAL_JUDICIARY_ATTEMPT_C_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_C_ID = "judiciary-live-baseline-20260830c"
_HISTORICAL_JUDICIARY_ATTEMPT_C_CUTOFF = "2026-08-30T08:46:02+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_C_AUTHORITY_FINGERPRINT = (
    "sha256:a5d1e7c7ea0b6167d4f4d367e1063b6be69646e326979bdf01499c3153fc16dd"
)
_HISTORICAL_JUDICIARY_ATTEMPT_C_REPORT_SHA256 = (
    "482cf5c615688e10f39886cdfab7a03eaf1604e5ca29cb27aff907ec6ce06a2d"
)
_HISTORICAL_JUDICIARY_ATTEMPT_D_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.3",
    "sha256:e9ee797df0bf0b3ea58195a693a1df411c7a6d2fb5274675ec769422b862ec9a",
)
_HISTORICAL_JUDICIARY_ATTEMPT_D_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_D_ID = "judiciary-live-baseline-20260830d"
_HISTORICAL_JUDICIARY_ATTEMPT_D_CUTOFF = "2026-08-30T10:00:10+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_D_AUTHORITY_FINGERPRINT = (
    "sha256:b789ef648af2d212cc118a5a1ab256c3b48861d766394743fd3d7023de307dc3"
)
_HISTORICAL_JUDICIARY_ATTEMPT_D_REPORT_SHA256 = (
    "210e3818e68c4703cc4afa9030f81cdaccdb951def5ce086fe9e6050576ec9e4"
)
_HISTORICAL_JUDICIARY_ATTEMPT_E_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.4",
    "sha256:bdf10411a8c3d275c162060919d916e6b417cd4aa8f35c5529bb516087ead3b6",
)
_HISTORICAL_JUDICIARY_ATTEMPT_E_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_E_ID = "judiciary-live-baseline-20260830e"
_HISTORICAL_JUDICIARY_ATTEMPT_E_CUTOFF = "2026-08-30T11:26:32+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_E_AUTHORITY_FINGERPRINT = (
    "sha256:a70aea17a1dc238d7132ee06b97aefa274c7377a2bb52f65c11803239d856951"
)
_HISTORICAL_JUDICIARY_ATTEMPT_E_REPORT_SHA256 = (
    "16206775ab262bd969f802c15fcfc3af1a47a06c821584ad20a23c1aa46188a1"
)
_HISTORICAL_JUDICIARY_ATTEMPT_F_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.5",
    "sha256:e5bc2d233907098a18801d20f0160c0076088b5d4e3c139ff58d56c28e86ba72",
)
_HISTORICAL_JUDICIARY_ATTEMPT_F_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_F_ID = "judiciary-live-baseline-20260830f"
_HISTORICAL_JUDICIARY_ATTEMPT_F_CUTOFF = "2026-08-30T13:08:05+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_F_AUTHORITY_FINGERPRINT = (
    "sha256:ddb7553bb73f5b6b1c5e302af609005e248c27fad8975e74e67adabcc5262105"
)
_HISTORICAL_JUDICIARY_ATTEMPT_F_REPORT_SHA256 = (
    "ea768746b1b9d497cab97a52274df0acd32b03d20d1fdfdcd1cb701c3dbc6456"
)
_HISTORICAL_JUDICIARY_ATTEMPT_G_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.6",
    "sha256:6b7c4e73d0549c0ac3d8f1767323f8289f62f01b8bb357a319932b10870e9df4",
)
_HISTORICAL_JUDICIARY_ATTEMPT_G_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_G_ID = "judiciary-live-baseline-20260830g"
_HISTORICAL_JUDICIARY_ATTEMPT_G_CUTOFF = "2026-08-30T14:26:56+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_G_AUTHORITY_FINGERPRINT = (
    "sha256:864bb0e6903ebcfb3ff0d6765e4b0a02bc0e465064d6e2167f7d4a8552c3993a"
)
_HISTORICAL_JUDICIARY_ATTEMPT_G_REPORT_SHA256 = (
    "853e12c69864016f49aa2222763ec2b8291966e691336ec4769dd236d430318c"
)
_HISTORICAL_JUDICIARY_ATTEMPT_H_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.7",
    "sha256:fc1646375f89cceb8f7476e08b9619787cd4bc1160a12f0e6d829885460b4324",
)
_HISTORICAL_JUDICIARY_ATTEMPT_H_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_H_ID = "judiciary-live-baseline-20260830h"
_HISTORICAL_JUDICIARY_ATTEMPT_H_CUTOFF = "2026-08-30T15:33:12+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_H_AUTHORITY_FINGERPRINT = (
    "sha256:dc0a1011decc0834e53f1bf4fa9fe8e0d629ca92dd92436f9e93d9a1b43f4d97"
)
_HISTORICAL_JUDICIARY_ATTEMPT_H_REPORT_SHA256 = (
    "88672a88dbdd3f76867a5d322e491ffa890ba145eab44ec25588e854e1f4905e"
)
_HISTORICAL_JUDICIARY_ATTEMPT_I_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.8",
    "sha256:d99f67eb6e993c1654e6033555d2e145a5eb62525de3576291c9eaabe11e36d9",
)
_HISTORICAL_JUDICIARY_ATTEMPT_I_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_I_ID = "judiciary-live-baseline-20260830i"
_HISTORICAL_JUDICIARY_ATTEMPT_I_CUTOFF = "2026-08-30T17:07:10+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_I_AUTHORITY_FINGERPRINT = (
    "sha256:855e7840a718bc9202b4899abb25be64e2d2f7b1f9c2ab2f891d581a625b9f0f"
)
_HISTORICAL_JUDICIARY_ATTEMPT_I_REPORT_SHA256 = (
    "c39c7d1e9323648d22ef46617493e850dfc10922a43d2c76d55466eee6eaea76"
)
_HISTORICAL_JUDICIARY_ATTEMPT_J_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.9",
    "sha256:72a07543a191652108d479f73dc4f545a31f453356aafe9767a6ead8c62a0ec1",
)
_HISTORICAL_JUDICIARY_ATTEMPT_J_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_J_ID = "judiciary-live-baseline-20260830j"
_HISTORICAL_JUDICIARY_ATTEMPT_J_CUTOFF = "2026-08-30T18:23:17+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_J_AUTHORITY_FINGERPRINT = (
    "sha256:7092606aa9791902568a7fff63d994a85c37bd123d39d4369659eaf26bd90c2d"
)
_HISTORICAL_JUDICIARY_ATTEMPT_J_REPORT_SHA256 = (
    "a8c0be2da723aa45d89e95b33283e116f12ffc7bfcd37d7e88c2e178a73caca3"
)
_HISTORICAL_JUDICIARY_ATTEMPT_K_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.10",
    "sha256:cfb4eb10a12b9358162d5fc01834bce82038838a313ad8dd9f5fa62065400285",
)
_HISTORICAL_JUDICIARY_ATTEMPT_K_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_K_ID = "judiciary-live-baseline-20260830k"
_HISTORICAL_JUDICIARY_ATTEMPT_K_CUTOFF = "2026-08-30T20:22:35+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_K_AUTHORITY_FINGERPRINT = (
    "sha256:14eac34bae71ffa8fdf400465387e084c631cd60a2f941797463749303153119"
)
_HISTORICAL_JUDICIARY_ATTEMPT_K_REPORT_SHA256 = (
    "363aa365f8fdc4cc2ca08b0fcb623a6ddc0e2f67d7f7b8db3388c1163f558d04"
)
_HISTORICAL_JUDICIARY_ATTEMPT_L_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-30.11",
    "sha256:2ff13c0f113ab3790d174897ac14485f758afded2cd9a02932df18ef9cc59f54",
)
_HISTORICAL_JUDICIARY_ATTEMPT_L_ALLOWED_URLS_FINGERPRINT = (
    "sha256:066c782a782040e8e2d788e38b7535c9834abaf34412e0b9e7013f7346e438a8"
)
_HISTORICAL_JUDICIARY_ATTEMPT_L_ID = "judiciary-live-baseline-20260830l"
_HISTORICAL_JUDICIARY_ATTEMPT_L_CUTOFF = "2026-08-30T21:55:51+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_L_AUTHORITY_FINGERPRINT = (
    "sha256:abfc119e3a0326ea408e6308fdc09676169202c87de79634969900cf85e57d27"
)
_HISTORICAL_JUDICIARY_ATTEMPT_L_REPORT_SHA256 = (
    "9803075a2bf092743a97080d8adc1dc91eafe3e68ed8172f166cfdf32b3eab31"
)
_HISTORICAL_JUDICIARY_ATTEMPT_M_REGISTER_IDENTITY = (
    _HISTORICAL_JUDICIARY_ATTEMPT_L_REGISTER_IDENTITY
)
_HISTORICAL_JUDICIARY_ATTEMPT_M_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_L_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_M_ID = "judiciary-live-baseline-20260830m"
_HISTORICAL_JUDICIARY_ATTEMPT_M_CUTOFF = "2026-08-30T22:12:07+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_M_AUTHORITY_FINGERPRINT = (
    "sha256:9122149c1d9660ee4847c5f627ca5f3cabaf0a76a6eb1277a3555c13d27782e7"
)
_HISTORICAL_JUDICIARY_ATTEMPT_M_REPORT_SHA256 = (
    "eb382465f907cfd6bff216e8c7412e21f70d718a7ee4180282e64fb80c2b51c0"
)
_HISTORICAL_JUDICIARY_ATTEMPT_N_REGISTER_IDENTITY = (
    _HISTORICAL_JUDICIARY_ATTEMPT_L_REGISTER_IDENTITY
)
_HISTORICAL_JUDICIARY_ATTEMPT_N_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_L_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_N_ID = "judiciary-live-baseline-20260831n"
_HISTORICAL_JUDICIARY_ATTEMPT_N_CUTOFF = "2026-08-31T02:58:45+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_N_AUTHORITY_FINGERPRINT = (
    "sha256:3b5bce2967f2ec8e1e5ed073e6848000044a98d83616a05ba60a145ccee46f5f"
)
_HISTORICAL_JUDICIARY_ATTEMPT_N_REPORT_SHA256 = (
    "1213a1edb85870f053f86f63bb6fc3544a9b6181bea76175e4083da3149d4660"
)
_HISTORICAL_JUDICIARY_ATTEMPT_O_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-31.12",
    "sha256:9ba0809d837459b341dd57fec23d857bc839a6c0ffbbbfc14f839c3176c88245",
)
_HISTORICAL_JUDICIARY_ATTEMPT_O_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_L_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_O_ID = "judiciary-live-baseline-20260831o"
_HISTORICAL_JUDICIARY_ATTEMPT_O_CUTOFF = "2026-08-31T06:27:06+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_O_AUTHORITY_FINGERPRINT = (
    "sha256:fd04e3943ee3d9a2de0b734adc780c515c841c5a66e309a775f9e9a4269cc2ae"
)
_HISTORICAL_JUDICIARY_ATTEMPT_O_REPORT_SHA256 = (
    "7d61c67d83696af61f78594a69282668c045b744437f31fa40897d3db5fe514d"
)
_HISTORICAL_JUDICIARY_ATTEMPT_P_REGISTER_IDENTITY = (
    "hcr_000000000000000000000000000000000000000000000001",
    "2026-08-31.13",
    "sha256:a5e35954d6d030f5b073c33b1b5006c71c8181388289870e05be15aac54c072b",
)
_HISTORICAL_JUDICIARY_ATTEMPT_P_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_L_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_P_ID = "judiciary-live-baseline-20260831p"
_HISTORICAL_JUDICIARY_ATTEMPT_P_CUTOFF = "2026-08-31T11:05:35+08:00"
_HISTORICAL_JUDICIARY_ATTEMPT_P_AUTHORITY_FINGERPRINT = (
    "sha256:66bc570014539cc9ec14ee2b56cb4f64c0b651a27ff8596704810887013ae352"
)
_HISTORICAL_JUDICIARY_ATTEMPT_P_REPORT_SHA256 = (
    "e8cc1c5e11a4c25f7a23e89b8889761c14aca240f5f717dc6f29966a3a96e918"
)
_HISTORICAL_JUDICIARY_ATTEMPT_Q_REGISTER_IDENTITY = (
    _HISTORICAL_JUDICIARY_ATTEMPT_P_REGISTER_IDENTITY
)
_HISTORICAL_JUDICIARY_ATTEMPT_Q_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_P_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_Q_ID = "judiciary-live-baseline-20260831q"
_HISTORICAL_JUDICIARY_ATTEMPT_Q_PREDECESSOR_ID = _HISTORICAL_JUDICIARY_ATTEMPT_P_ID
_HISTORICAL_JUDICIARY_ATTEMPT_Q_CUTOFF = _HISTORICAL_JUDICIARY_ATTEMPT_P_CUTOFF
_HISTORICAL_JUDICIARY_ATTEMPT_Q_AUTHORITY_FINGERPRINT = (
    "sha256:08c2fb878c11b00cb8b76107cdcdab33f77720aca9dfadb0342fb65e932d31bf"
)
_HISTORICAL_JUDICIARY_ATTEMPT_Q_REPORT_SHA256 = (
    "7e5f8d86a289f6ca0581e869a51b6e89831bdf42896b50d822c7c87eec2883c9"
)
_HISTORICAL_JUDICIARY_ATTEMPT_R_REGISTER_IDENTITY = (
    _HISTORICAL_JUDICIARY_ATTEMPT_P_REGISTER_IDENTITY
)
_HISTORICAL_JUDICIARY_ATTEMPT_R_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_P_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_R_ID = "judiciary-live-baseline-20260831r"
_HISTORICAL_JUDICIARY_ATTEMPT_R_PREDECESSOR_ID = _HISTORICAL_JUDICIARY_ATTEMPT_Q_ID
_HISTORICAL_JUDICIARY_ATTEMPT_R_CUTOFF = _HISTORICAL_JUDICIARY_ATTEMPT_P_CUTOFF
_HISTORICAL_JUDICIARY_ATTEMPT_R_AUTHORITY_FINGERPRINT = (
    "sha256:85360be62646366d8b56eafe6191e776fa8077a7c6390d78760846b1c498f333"
)
_HISTORICAL_JUDICIARY_ATTEMPT_R_REPORT_SHA256 = (
    "ab67805a5bde97f6f0903e452c38b9e2e95f822516445a36e1ce93d9347016fd"
)
_HISTORICAL_JUDICIARY_ATTEMPT_S_REGISTER_IDENTITY = (
    _HISTORICAL_JUDICIARY_ATTEMPT_P_REGISTER_IDENTITY
)
_HISTORICAL_JUDICIARY_ATTEMPT_S_ALLOWED_URLS_FINGERPRINT = (
    _HISTORICAL_JUDICIARY_ATTEMPT_P_ALLOWED_URLS_FINGERPRINT
)
_HISTORICAL_JUDICIARY_ATTEMPT_S_ID = "judiciary-live-baseline-20260831s"
_HISTORICAL_JUDICIARY_ATTEMPT_S_PREDECESSOR_ID = "judiciary-live-baseline-20260831r"
_HISTORICAL_JUDICIARY_ATTEMPT_S_CUTOFF = _HISTORICAL_JUDICIARY_ATTEMPT_P_CUTOFF
_HISTORICAL_JUDICIARY_ATTEMPT_S_AUTHORITY_FINGERPRINT = (
    "sha256:e46f3c393c0e154fb98b821ef8df19f78da0c12c688ae7ef56ef85797ab5c284"
)
_HISTORICAL_JUDICIARY_ATTEMPT_S_REPORT_SHA256 = (
    "6b9345452d0b75f16b6393e98b91bf61422a5f2f9e4c835a15c275934a1dfe66"
)
_HISTORICAL_JUDICIARY_POLICY_100_FINGERPRINT = (
    "sha256:9993c64e7cc62654d773cf1e860699cd9b56737d1cea4c4c17ee016308bf8353"
)
_HISTORICAL_JUDICIARY_POLICY_110_FINGERPRINT = (
    "sha256:d42d817e27d08896358a0fcf218833b1feaf9b285e5f71fc902731dff136a349"
)
_HISTORICAL_JUDICIARY_POLICY_120_FINGERPRINT = (
    "sha256:6e3f5849e2e7fb60a56b8b5adad35b370c123f017b0cb5854db9e8aeb656590a"
)
_EXECUTION_DEPENDENCY_SOURCE_IDS = frozenset({"HK-LEG-HKEL-CURRENT-DATA"})
_PRE_EFFECT_PREDECESSOR_ERRORS = frozenset(
    {
        "PREDECESSOR_ATTEMPT_INVALID",
        "PREDECESSOR_ATTEMPT_REQUIRED",
        "PREDECESSOR_EVIDENCE_READBACK_INVALID",
        "PREDECESSOR_REPORT_BINDING_INVALID",
        "PREDECESSOR_REPORT_MALFORMED",
    }
)
_PRE_EFFECT_ATTEMPT_CLAIM_ERRORS = frozenset(
    {"SOURCE_ATTEMPT_IN_PROGRESS", "SOURCE_ATTEMPT_LOCK_UNSAFE"}
)


def _object(value: object) -> dict[str, object] | None:
    try:
        checked = checked_json_value(value)
    except ContractViolation:
        return None
    if type(checked) is not dict:
        return None
    result: dict[str, object] = {}
    result.update(checked)
    return result


def _execution_fail(code: str) -> Never:
    raise ValueError(code)


def _list(value: object) -> list[object] | None:
    try:
        checked = checked_json_value(value)
    except ContractViolation:
        return None
    return list(checked) if type(checked) is list else None


def _text(value: object) -> str | None:
    if type(value) is not str or not value or _SAFE_TEXT.search(value):
        return None
    return value


def _valid_date(value: str | None) -> bool:
    if value is None or _DATE.fullmatch(value) is None:
        return False
    try:
        parsed = date.fromisoformat(value)
        return parsed.isoformat() == value
    except ValueError:
        return False


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return _read_json_bytes(raw, require_canonical=True)


def _read_json_bytes(raw: bytes, *, require_canonical: bool = False) -> dict[str, object] | None:
    if len(raw) > _MAX_DOCUMENT_BYTES:
        return None
    try:
        value: object = parse_json_bytes(raw, max_bytes=_MAX_DOCUMENT_BYTES)
    except ContractViolation, TypeError, ValueError:
        return None
    document = _object(value)
    if document is None:
        return None
    if require_canonical and _canonical_bytes(document) != raw:
        return None
    return document


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def canonical_report_bytes(report: AdmissionReport) -> bytes:
    """Render a stdout preflight report as one stable line."""
    return _canonical_bytes(report) + b"\n"


def _fingerprint(document: dict[str, object]) -> str | None:
    declared = _text(document.get("fingerprint"))
    if declared is None or _FINGERPRINT.fullmatch(declared) is None:
        return None
    unsigned = dict(document)
    unsigned.pop("fingerprint", None)
    actual = "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    return declared if declared == actual else None


def _valid_authority_manifest(manifest: dict[str, object]) -> bool:
    if _fingerprint(manifest) is None:
        return False
    effective_date = _text(manifest.get("effective_date"))
    expires_on = _text(manifest.get("expires_on"))
    return (
        _text(manifest.get("schema_version")) == "1.0.0"
        and _text(manifest.get("authority_id")) is not None
        and _text(manifest.get("scope")) == "HK_V1_SOURCE_ADMISSION_PREFLIGHT"
        and _text(manifest.get("provenance")) in _AUTHORITY_PROVENANCES
        and _valid_date(effective_date)
        and expires_on is not None
        and (expires_on == "NO_EXPIRY" or _valid_date(expires_on))
        and (
            expires_on == "NO_EXPIRY"
            or (effective_date is not None and effective_date <= expires_on)
        )
    )


def _safe_output_root(output_root: Path, repository_root: Path) -> bool:
    try:
        root = repository_root.resolve(strict=True)
        lexical = output_root if output_root.is_absolute() else root / output_root
        relative = lexical.relative_to(root)
        if ".." in relative.parts:
            return False
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return False
        lexical.relative_to(root / "var")
        candidate = lexical.resolve(strict=False)
        var_root = (root / "var").resolve(strict=False)
        var_root.relative_to(root)
        candidate.relative_to(var_root)
    except OSError, ValueError:
        return False
    if candidate == var_root or output_root.name in {"", ".", ".."}:
        return False
    return not candidate.exists() or candidate.is_dir()


def _contains_secret(value: object) -> bool:
    document = _object(value)
    items = _list(value)
    if document is not None:
        return any(
            _SECRET_KEY.fullmatch(key) is not None or _contains_secret(child)
            for key, child in document.items()
        )
    if items is not None:
        return any(_contains_secret(item) for item in items)
    return type(value) is str and _SECRET_VALUE.search(value) is not None


def _require_keys(document: dict[str, object], keys: frozenset[str]) -> bool:
    return frozenset(document) == keys


def _identity(document: dict[str, object], keys: tuple[str, ...]) -> tuple[str, ...] | None:
    values: list[str] = []
    for key in keys:
        value = _text(document.get(key))
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _load_registers(
    repository_root: Path, codes: set[str]
) -> tuple[dict[str, dict[str, object]], tuple[DueRegisterBundle, ...]]:
    registers: dict[str, dict[str, object]] = {}
    bundles: list[DueRegisterBundle] = []
    for family, relative_path in _REGISTER_PATHS.items():
        try:
            content = (repository_root / relative_path).read_bytes()
        except OSError:
            codes.add(f"{family}_REGISTER_FINGERPRINT_DRIFT")
            continue
        if hashlib.sha256(content).hexdigest() != _CHECKED_IN_RAW_SHA256[family]:
            codes.add(f"{family}_REGISTER_CHECKED_IN_BYTES_DRIFT")
            continue
        document = _read_json_bytes(content)
        if document is None or _fingerprint(document) is None:
            codes.add(f"{family}_REGISTER_FINGERPRINT_DRIFT")
            continue
        registers[family] = document
        if family in _V1_DUE_FAMILIES:
            try:
                bundle = parse_hk_v1_due_register_bundle(content)
            except TypeError, ValueError:
                codes.add(f"{family}_REGISTER_POLICY_INVALID")
                continue
            bundles.append(bundle)
    return registers, tuple(bundles)


def _load_due_requirements(  # noqa: C901, PLR0911
    *,
    matrix_path: Path,
    repository_root: Path,
    bundles: tuple[DueRegisterBundle, ...],
    codes: set[str],
) -> tuple[dict[str, HongKongV1DueRequirement], set[str], dict[str, object] | None]:
    expected_path = repository_root / _MATRIX_PATH
    try:
        supplied = matrix_path.resolve(strict=True)
        expected = expected_path.resolve(strict=True)
        supplied_bytes = supplied.read_bytes()
        expected_bytes = expected.read_bytes()
        if supplied != expected or supplied_bytes != expected_bytes:
            codes.add("MATRIX_NOT_CHECKED_IN_SNAPSHOT")
            return {}, set(), _read_json_bytes(supplied_bytes)
        if hashlib.sha256(supplied_bytes).hexdigest() != _CHECKED_IN_MATRIX_RAW_SHA256:
            codes.add("MATRIX_CHECKED_IN_BYTES_DRIFT")
            return {}, set(), _read_json_bytes(supplied_bytes)
        matrix = load_hk_v1_coverage_matrix(supplied)
        if supplied.read_bytes() != supplied_bytes:
            codes.add("MATRIX_SNAPSHOT_CHANGED")
            return {}, set(), _read_json_bytes(supplied_bytes)
    except OSError, TypeError, ValueError:
        codes.add("DUE_AUTHORITY_POLICY_INVALID")
        return {}, set(), None
    requirements: dict[str, HongKongV1DueRequirement] = {}
    expected_counts = {
        DueCycleKind.DAILY_CURRENT_LAW: 4,
        DueCycleKind.WEEKLY_RELEASE: 6,
        DueCycleKind.MONTHLY_CROSS_CHECK: 1,
        DueCycleKind.FULL_PERIODIC: 7,
    }
    try:
        for kind, expected_count in expected_counts.items():
            plan = derive_hk_v1_due_cycle_plan(
                HongKongV1DueCycleInstruction(
                    f"hk-v1-admission-{kind.value.lower()}-20260826",
                    kind,
                    "2026-08-26T00:00:00Z",
                    "2026-08-26T00:00:00Z",
                    matrix.revision,
                    matrix.fingerprint,
                ),
                matrix,
                bundles,
            )
            if len(plan.requirements) != expected_count:
                codes.add("DUE_SOURCE_UNIVERSE_INVALID")
                return {}, set(), _read_json_bytes(supplied_bytes)
            for requirement in plan.requirements:
                prior = requirements.get(requirement.source_id)
                if prior is not None and prior != requirement:
                    codes.add("DUE_SOURCE_UNIVERSE_INVALID")
                    return {}, set(), _read_json_bytes(supplied_bytes)
                requirements[requirement.source_id] = requirement
    except TypeError, ValueError:
        codes.add("DUE_SOURCE_UNIVERSE_INVALID")
        return {}, set(), _read_json_bytes(supplied_bytes)
    if len(requirements) != expected_counts[DueCycleKind.FULL_PERIODIC]:
        codes.add("DUE_SOURCE_UNIVERSE_INVALID")
        return {}, set(), _read_json_bytes(supplied_bytes)
    if len(bundles) != len(_V1_DUE_FAMILIES):
        codes.add("DUE_AUTHORITY_POLICY_INVALID")
    return requirements, set(requirements), _read_json_bytes(supplied_bytes)


def _register_sources(register: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_sources = _list(register.get("sources"))
    if raw_sources is None:
        return {}
    result: dict[str, dict[str, object]] = {}
    for raw_source in raw_sources:
        source = _object(raw_source)
        if source is None:
            return {}
        source_id = _text(source.get("source_id"))
        if source_id is None or source_id in result:
            return {}
        result[source_id] = source
    return result


def _register_endpoints(register: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_endpoints = _list(register.get("endpoints"))
    if raw_endpoints is None:
        return {}
    result: dict[str, dict[str, object]] = {}
    for raw_endpoint in raw_endpoints:
        endpoint = _object(raw_endpoint)
        if endpoint is None:
            return {}
        endpoint_id = _text(endpoint.get("endpoint_id"))
        if endpoint_id is None or endpoint_id in result:
            return {}
        result[endpoint_id] = endpoint
    return result


def _check_manifest_identity(
    manifest: dict[str, object],
    matrix: dict[str, object],
    registers: dict[str, dict[str, object]],
    codes: set[str],
) -> None:
    matrix_binding = _object(manifest.get("matrix"))
    matrix_identity = _identity(matrix, ("revision", "fingerprint"))
    if (
        matrix_binding is None
        or not _require_keys(matrix_binding, frozenset({"revision", "fingerprint"}))
        or _identity(matrix_binding, ("revision", "fingerprint")) != matrix_identity
    ):
        codes.add("MATRIX_IDENTITY_MISMATCH")
    bindings = _list(manifest.get("registers"))
    if bindings is None:
        codes.add("REGISTER_IDENTITIES_MALFORMED")
        return
    by_family: dict[str, dict[str, object]] = {}
    for raw_binding in bindings:
        binding = _object(raw_binding)
        if binding is None or not _require_keys(
            binding, frozenset({"family", "register_id", "register_version", "fingerprint"})
        ):
            codes.add("REGISTER_IDENTITIES_MALFORMED")
            continue
        family = _text(binding.get("family"))
        if family is None or family in by_family:
            codes.add("REGISTER_IDENTITIES_MALFORMED")
            continue
        by_family[family] = binding
    if set(by_family) != set(_REGISTER_PATHS) or len(bindings) != len(_REGISTER_PATHS):
        codes.add("REGISTER_IDENTITIES_MALFORMED")
    for family, register in registers.items():
        if _identity(
            by_family.get(family, {}), ("register_id", "register_version", "fingerprint")
        ) != _identity(register, ("register_id", "register_version", "fingerprint")):
            codes.add(f"{family}_REGISTER_IDENTITY_MISMATCH")


def is_immutable_reference(value: object) -> bool:
    """Recognize an immutable local evidence locator without opening it."""
    reference = _object(value)
    if reference is None:
        return False
    required = frozenset(
        {
            "vault",
            "logical_key",
            "version_id",
            "fingerprint",
            "byte_length",
            "publisher",
            "scope",
            "effective_date",
            "expires_on",
            "provenance",
        }
    )
    if not _require_keys(reference, required):
        return False
    if not all(_text(reference.get(key)) is not None for key in required - {"byte_length"}):
        return False
    fingerprint = _text(reference.get("fingerprint"))
    vault = _text(reference.get("vault"))
    logical_key = _text(reference.get("logical_key"))
    version_id = _text(reference.get("version_id"))
    effective_date = _text(reference.get("effective_date"))
    expires_on = _text(reference.get("expires_on"))
    byte_length = reference.get("byte_length")
    if type(byte_length) is not int:
        return False
    return (
        fingerprint is not None
        and _FINGERPRINT.fullmatch(fingerprint) is not None
        and vault in {"PRIMARY", "RECOVERY"}
        and logical_key is not None
        and _LOGICAL_KEY.fullmatch(logical_key) is not None
        and "//" not in logical_key
        and "/../" not in f"/{logical_key}/"
        and version_id is not None
        and _VERSION.fullmatch(version_id) is not None
        and _valid_date(effective_date)
        and expires_on is not None
        and (expires_on == "NO_EXPIRY" or _valid_date(expires_on))
        and (
            expires_on == "NO_EXPIRY"
            or (effective_date is not None and effective_date <= expires_on)
        )
        and byte_length > 0
    )


def _strict_text_list(value: object) -> tuple[str, ...] | None:
    entries = _list(value)
    if entries is None:
        return None
    result: list[str] = []
    for entry in entries:
        text = _text(entry)
        if text is None:
            return None
        result.append(text)
    sorted_result = tuple(sorted(result))
    if len(set(result)) != len(result) or tuple(result) != sorted_result:
        return None
    return sorted_result


def _reference_covers_window(
    reference: dict[str, object], window: tuple[datetime, datetime, datetime]
) -> bool:
    effective_date = _text(reference.get("effective_date"))
    expires_on = _text(reference.get("expires_on"))
    if effective_date is None or expires_on is None:
        return False
    start, _end, cutoff = window
    return effective_date <= start.date().isoformat() and (
        expires_on == "NO_EXPIRY" or expires_on >= cutoff.date().isoformat()
    )


def _publisher_terms_reference(
    value: object,
    window: tuple[datetime, datetime, datetime] | None,
    *,
    allow_user_attested: bool,
) -> bool:
    reference = _object(value)
    return (
        reference is not None
        and is_immutable_reference(reference)
        and reference.get("provenance")
        in ({"PUBLISHER_ISSUED", "USER_REPORTED"} if allow_user_attested else {"PUBLISHER_ISSUED"})
        and reference.get("scope") == "PUBLISHER_TERMS_EVIDENCE"
        and (window is None or _reference_covers_window(reference, window))
    )


def _permission_map(
    manifest: dict[str, object],
    codes: set[str],
    window: tuple[datetime, datetime, datetime] | None,
    *,
    allow_user_attested: bool,
) -> dict[str, dict[str, object]]:
    entries = _list(manifest.get("publisher_permissions"))
    if entries is None:
        codes.add("PUBLISHER_PERMISSION_EVIDENCE_MISSING")
        return {}
    result: dict[str, dict[str, object]] = {}
    for raw_entry in entries:
        entry = _object(raw_entry)
        required = frozenset({"permission_id", "source_ids", "hosts", "procedure_ids", "reference"})
        if entry is None or not _require_keys(entry, required):
            codes.add("PUBLISHER_PERMISSION_EVIDENCE_MALFORMED")
            continue
        permission_id = _text(entry.get("permission_id"))
        reference = _object(entry.get("reference"))
        if (
            permission_id is None
            or permission_id in result
            or _strict_text_list(entry.get("source_ids")) is None
            or _strict_text_list(entry.get("hosts")) is None
            or _strict_text_list(entry.get("procedure_ids")) is None
            or not is_immutable_reference(reference)
            or reference is None
            or reference.get("provenance")
            not in (
                {"PUBLISHER_ISSUED", "USER_REPORTED"}
                if allow_user_attested
                else {"PUBLISHER_ISSUED"}
            )
            or reference.get("scope") != "READ_ONLY_SOURCE_ADMISSION"
            or (window is not None and not _reference_covers_window(reference, window))
        ):
            codes.add("PUBLISHER_PERMISSION_EVIDENCE_MALFORMED")
            continue
        result[permission_id] = entry
    return result


def _terms_map(  # noqa: C901
    manifest: dict[str, object],
    codes: set[str],
    window: tuple[datetime, datetime, datetime] | None,
    *,
    allow_user_attested: bool,
) -> dict[str, dict[str, object]]:
    entries = _list(manifest.get("terms"))
    if entries is None:
        codes.add("TERMS_STATE_MISSING")
        return {}
    result: dict[str, dict[str, object]] = {}
    for raw_entry in entries:
        entry = _object(raw_entry)
        if entry is None:
            codes.add("TERMS_STATE_MALFORMED")
            continue
        host = _text(entry.get("host"))
        state = _text(entry.get("state"))
        if host is None or state not in _TERMS_STATES or host in result:
            codes.add("TERMS_STATE_MALFORMED")
            continue
        required = frozenset({"host", "state", "terms_reference"})
        if state == "ALREADY_ACCEPTED_WITH_EVIDENCE":
            required = required | {"acceptance_evidence"}
        elif state == "NOT_EXPECTED":
            required = required | {"basis_reference"}
        if not _require_keys(entry, required) or not _publisher_terms_reference(
            entry.get("terms_reference"), window, allow_user_attested=allow_user_attested
        ):
            codes.add("TERMS_STATE_MALFORMED")
            continue
        if state == "ALREADY_ACCEPTED_WITH_EVIDENCE" and not _publisher_terms_reference(
            entry.get("acceptance_evidence"),
            window,
            allow_user_attested=allow_user_attested,
        ):
            codes.add("TERMS_STATE_MALFORMED")
            continue
        if state == "NOT_EXPECTED" and not _publisher_terms_reference(
            entry.get("basis_reference"), window, allow_user_attested=allow_user_attested
        ):
            codes.add("TERMS_STATE_MALFORMED")
            continue
        if state in {"EXPECTED_NOT_ACCEPTED", "PRESENTATION_REQUIRES_USER_ACTION"}:
            codes.add("TERMS_ACTION_REQUIRED")
        result[host] = entry
    return result


def _validate_user_reports(manifest: dict[str, object], codes: set[str]) -> None:
    entries = _list(manifest.get("user_reports"))
    if entries is None:
        codes.add("USER_REPORT_REFERENCES_MALFORMED")
        return
    report_ids: set[str] = set()
    for raw_entry in entries:
        entry = _object(raw_entry)
        if entry is None or not _require_keys(entry, frozenset({"report_id", "reference"})):
            codes.add("USER_REPORT_REFERENCES_MALFORMED")
            continue
        report_id = _text(entry.get("report_id"))
        reference = _object(entry.get("reference"))
        if (
            report_id is None
            or report_id in report_ids
            or not is_immutable_reference(reference)
            or reference is None
            or reference.get("provenance") != "USER_REPORTED"
        ):
            codes.add("USER_REPORT_REFERENCES_MALFORMED")
            continue
        report_ids.add(report_id)


def _permission_covers(
    permission: dict[str, object], source_id: str, endpoints: list[object]
) -> bool:
    source_ids = _strict_text_list(permission.get("source_ids"))
    hosts = _strict_text_list(permission.get("hosts"))
    procedures = _strict_text_list(permission.get("procedure_ids"))
    if source_ids is None or hosts is None or procedures is None or source_id not in source_ids:
        return False
    endpoint_hosts: set[str] = set()
    endpoint_procedures: set[str] = set()
    for raw_endpoint in endpoints:
        endpoint = _object(raw_endpoint)
        if endpoint is None:
            return False
        host = _text(endpoint.get("host"))
        procedure = _text(endpoint.get("procedure_id"))
        if host is None or procedure is None:
            return False
        endpoint_hosts.add(host)
        endpoint_procedures.add(procedure)
    return endpoint_hosts.issubset(hosts) and endpoint_procedures.issubset(procedures)


def _window_bounds(value: object) -> tuple[datetime, datetime, datetime] | None:
    window = _object(value)
    if window is None or not _require_keys(
        window, frozenset({"start", "end", "cutoff", "timezone"})
    ):
        return None
    start = _text(window.get("start"))
    end = _text(window.get("end"))
    cutoff = _text(window.get("cutoff"))
    if start is None or end is None or cutoff is None or window.get("timezone") != "Asia/Hong_Kong":
        return None
    if not all(_UTC_TIMESTAMP.fullmatch(item) for item in (start, end, cutoff)):
        return None
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        cutoff_time = datetime.fromisoformat(cutoff)
    except ValueError:
        return None
    return (start_time, end_time, cutoff_time) if start_time < end_time <= cutoff_time else None


def _check_capability_references(manifest: dict[str, object], codes: set[str]) -> None:
    for key in ("credentials", "sessions"):
        entries = _list(manifest.get(key))
        if entries is None:
            codes.add("CAPABILITY_REFERENCES_MALFORMED")
            continue
        seen: set[tuple[str, str]] = set()
        for raw_entry in entries:
            entry = _object(raw_entry)
            if entry is None or not _require_keys(entry, frozenset({"name", "type"})):
                codes.add("CAPABILITY_REFERENCES_MALFORMED")
                continue
            name = _text(entry.get("name"))
            capability_type = _text(entry.get("type"))
            if (
                name is None
                or capability_type is None
                or (name, capability_type) in seen
                or _CAPABILITY_NAME.fullmatch(name) is None
                or _SENSITIVE_CAPABILITY_NAME.search(name) is not None
                or capability_type not in _CAPABILITY_TYPES[key]
            ):
                codes.add("CAPABILITY_REFERENCES_MALFORMED")
            else:
                seen.add((name, capability_type))


def _endpoint_mismatch_codes(endpoint: dict[str, object], claimed: dict[str, object]) -> set[str]:
    expected = frozenset(
        {"endpoint_id", "host", "method", "path", "procedure_id", "redirect_policy"}
    )
    if not _require_keys(claimed, expected):
        return {"ENDPOINT_CONTRACT_MALFORMED"}
    identity = _identity(
        claimed, ("endpoint_id", "host", "method", "path", "procedure_id", "redirect_policy")
    )
    endpoint_id = _text(endpoint.get("endpoint_id"))
    url = _text(endpoint.get("url"))
    methods = _list(endpoint.get("methods"))
    if identity is None or endpoint_id is None or url is None or methods is None:
        return {"ENDPOINT_CONTRACT_MALFORMED"}
    parsed = urlsplit(url)
    canonical_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    codes: set[str] = set()
    if parsed.scheme != "https" or identity[0] != endpoint_id:
        codes.add("ENDPOINT_CONTRACT_UNREGISTERED")
    if identity[1] != parsed.netloc:
        codes.add("ENDPOINT_HOST_UNREGISTERED")
    if identity[2] not in methods:
        codes.add("ENDPOINT_METHOD_UNREGISTERED")
    if identity[3] != canonical_path:
        codes.add("ENDPOINT_PATH_UNREGISTERED")
    if identity[4] != endpoint_id:
        codes.add("ENDPOINT_PROCEDURE_UNREGISTERED")
    if identity[5] != "NO_REDIRECT":
        codes.add("ENDPOINT_REDIRECT_UNREGISTERED")
    return codes


def _check_selected_endpoints(
    *,
    source: dict[str, object],
    endpoints: list[object],
    register: dict[str, object],
    context: _AuthorityContext,
) -> None:
    source_id = _text(source.get("source_id"))
    registered_ids = _list(source.get("endpoint_ids"))
    if (
        source_id is None
        or registered_ids is None
        or not all(_text(value) is not None for value in registered_ids)
    ):
        context.codes.add("SOURCE_ENDPOINT_POLICY_INVALID")
        return
    registered_endpoints = _register_endpoints(register)
    if not endpoints:
        context.codes.add("SELECTED_SOURCE_ENDPOINTS_MISSING")
    endpoint_ids: set[str] = set()
    for raw_endpoint in endpoints:
        endpoint = _object(raw_endpoint)
        if endpoint is None:
            context.codes.add("ENDPOINT_CONTRACT_MALFORMED")
            continue
        endpoint_id = _text(endpoint.get("endpoint_id"))
        if endpoint_id is None or endpoint_id in endpoint_ids:
            context.codes.add("ENDPOINT_CONTRACT_MALFORMED")
            continue
        endpoint_ids.add(endpoint_id)
        registered = registered_endpoints.get(endpoint_id)
        if registered is None or _text(registered.get("source_id")) != source_id:
            context.codes.add("ENDPOINT_CONTRACT_UNREGISTERED")
            continue
        mismatch_codes = _endpoint_mismatch_codes(registered, endpoint)
        if mismatch_codes:
            context.codes.update(mismatch_codes)
            continue
        if _text(endpoint.get("host")) not in context.terms:
            context.codes.add("TERMS_STATE_MISSING")
    if endpoint_ids != set(registered_ids):
        context.codes.add("SELECTED_SOURCE_ENDPOINT_MEMBERSHIP_INCOMPLETE")


def _check_current_source_state(
    source: dict[str, object], requirement: HongKongV1DueRequirement, codes: set[str]
) -> None:
    if requirement.technical_state != "ADMITTED":
        codes.add("MATRIX_TECHNICAL_ADMISSION_MISSING")
    if requirement.rights_state != "ADMITTED":
        codes.add("MATRIX_RIGHTS_ADMISSION_MISSING")
    if _text(source.get("operational_state")) != "CONFIGURED":
        codes.add("SOURCE_OPERATIONAL_ADMISSION_MISSING")
    blockers = _list(source.get("blockers"))
    if blockers is None or not all(_text(blocker) is not None for blocker in blockers):
        codes.add("SOURCE_BLOCKER_POLICY_INVALID")
    elif blockers:
        codes.add("SOURCE_BLOCKERS_PRESENT")


def _check_selected_source(  # noqa: C901, PLR0911 - closed authority decision tree.
    entry: dict[str, object], seen: set[tuple[str, str]], context: _AuthorityContext
) -> None:
    required = frozenset({"family", "source_id", "endpoints", "publisher_permission_id"})
    if not _require_keys(entry, required):
        context.codes.add("SELECTED_SOURCES_MALFORMED")
        return
    family = _text(entry.get("family"))
    source_id = _text(entry.get("source_id"))
    permission_id = _text(entry.get("publisher_permission_id"))
    endpoints = _list(entry.get("endpoints"))
    if family is None or source_id is None or permission_id is None or endpoints is None:
        context.codes.add("SELECTED_SOURCES_MALFORMED")
        return
    identity = (family, source_id)
    if identity in seen:
        context.codes.add("SELECTED_SOURCE_DUPLICATE")
        return
    seen.add(identity)
    requirement = context.due_requirements.get(source_id)
    if requirement is None:
        if source_id not in _EXECUTION_DEPENDENCY_SOURCE_IDS | _POST_V1_DORMANT_SOURCE_IDS:
            context.codes.add("SELECTED_SOURCE_NOT_DUE")
            return
        register = context.registers.get(family)
        if register is None:
            context.codes.add("SELECTED_SOURCE_UNKNOWN")
            return
        sources = _register_sources(register)
        source = sources.get(source_id)
        if source is None:
            context.codes.add("SELECTED_SOURCE_UNKNOWN")
            return
        permission = context.permissions.get(permission_id)
        if permission is None or not _permission_covers(permission, source_id, endpoints):
            context.codes.add("PUBLISHER_PERMISSION_EVIDENCE_MISSING")
        _check_selected_endpoints(
            source=source, endpoints=endpoints, register=register, context=context
        )
        return
    register = context.registers.get(family)
    if register is None:
        context.codes.add("SELECTED_SOURCE_UNKNOWN")
        return
    sources = _register_sources(register)
    if identity not in context.matrix_sources or source_id not in sources:
        context.codes.add("SELECTED_SOURCE_UNKNOWN")
        return
    permission = context.permissions.get(permission_id)
    if permission is None or not _permission_covers(permission, source_id, endpoints):
        context.codes.add("PUBLISHER_PERMISSION_EVIDENCE_MISSING")
    source = sources[source_id]
    _check_current_source_state(source, requirement, context.codes)
    _check_selected_endpoints(
        source=source, endpoints=endpoints, register=register, context=context
    )
    if not _register_endpoints(register):
        context.codes.add(f"{family}_ENDPOINT_CONTRACT_MISSING")


def _check_selected_sources(manifest: dict[str, object], context: _AuthorityContext) -> None:
    entries = _list(manifest.get("selected_sources"))
    if entries is None:
        context.codes.add("SELECTED_SOURCES_MALFORMED")
        return
    seen: set[tuple[str, str]] = set()
    for raw_entry in entries:
        entry = _object(raw_entry)
        if entry is None:
            context.codes.add("SELECTED_SOURCES_MALFORMED")
            continue
        _check_selected_source(entry, seen, context)
    if not seen:
        context.codes.add("SELECTED_SOURCES_MISSING")
    selected_source_ids = {source_id for _family, source_id in seen}
    missing_due = context.due_source_ids - selected_source_ids
    if missing_due:
        context.codes.add("DUE_SOURCE_MEMBERSHIP_MISSING")
    for source_id in context.due_source_ids:
        requirement = context.due_requirements[source_id]
        if requirement.technical_state != "ADMITTED":
            context.codes.add("MATRIX_TECHNICAL_ADMISSION_MISSING")
        if requirement.rights_state != "ADMITTED":
            context.codes.add("MATRIX_RIGHTS_ADMISSION_MISSING")
        register = context.registers.get(requirement.material_family)
        if register is None or not _register_endpoints(register):
            context.codes.add(f"{requirement.material_family}_ENDPOINT_CONTRACT_MISSING")


def _check_manifest(  # noqa: C901
    manifest: dict[str, object] | None,
    matrix_document: dict[str, object] | None,
    context: _AuthorityContext,
) -> None:
    if (
        manifest is None
        or not _require_keys(manifest, _MANIFEST_KEYS)
        or _contains_secret(manifest)
    ):
        context.codes.add("AUTHORITY_MANIFEST_MALFORMED")
        if manifest is not None and _contains_secret(manifest):
            context.codes.add("SECRET_OR_SESSION_VALUE_FORBIDDEN")
        if manifest is not None and _require_keys(manifest, _MANIFEST_KEYS):
            _check_capability_references(manifest, context.codes)
        return
    window = _window_bounds(manifest.get("observation_window"))
    if not _valid_authority_manifest(manifest):
        context.codes.add("AUTHORITY_MANIFEST_MALFORMED")
    elif window is not None and not _reference_covers_window(manifest, window):
        context.codes.add("AUTHORITY_TIME_WINDOW_INVALID")
    allow_user_attested = manifest.get("provenance") == "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
    if allow_user_attested:
        context.codes.add("PERMISSION_DOCUMENT_PENDING")
    if matrix_document is not None:
        _check_manifest_identity(manifest, matrix_document, context.registers, context.codes)
    permissions = _permission_map(
        manifest, context.codes, window, allow_user_attested=allow_user_attested
    )
    terms = _terms_map(manifest, context.codes, window, allow_user_attested=allow_user_attested)
    _validate_user_reports(manifest, context.codes)
    if window is None:
        context.codes.add("OBSERVATION_WINDOW_MISSING")
    _check_capability_references(manifest, context.codes)
    context.permissions = permissions
    context.terms = terms
    _check_selected_sources(manifest, context)
    if not permissions:
        context.codes.add("PUBLISHER_PERMISSION_EVIDENCE_MISSING")
    if not terms:
        context.codes.add("TERMS_STATE_MISSING")


def preflight(
    *,
    authority_manifest: Path,
    matrix: Path,
    output_root: Path,
    repository_root: Path = _REPOSITORY_ROOT,
) -> AdmissionReport:
    """Validate frozen local bytes and return a no-effect admission verdict."""
    codes: set[str] = set()
    root = repository_root.resolve(strict=False)
    if not _safe_output_root(output_root, root):
        codes.add("OUTPUT_ROOT_UNSAFE")
    registers, bundles = _load_registers(root, codes)
    requirements, due_source_ids, matrix_document = _load_due_requirements(
        matrix_path=matrix,
        repository_root=root,
        bundles=bundles,
        codes=codes,
    )
    context = _AuthorityContext(
        {
            (requirement.material_family, requirement.source_id)
            for requirement in requirements.values()
        },
        registers,
        {},
        {},
        codes,
        due_source_ids,
        requirements,
    )
    manifest = _read_json(authority_manifest)
    _check_manifest(manifest, matrix_document, context)
    limitations: set[str] = set()
    if (
        manifest is not None
        and manifest.get("provenance") == "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
    ):
        codes.discard("PERMISSION_DOCUMENT_PENDING")
        limitations.add("PERMISSION_DOCUMENT_PENDING")
    return {
        "execute_authorized": False,
        "limitation_codes": sorted(limitations),
        "missing_codes": sorted(codes),
        "result": "NOT_ADMITTED",
    }


def _execution_binding_fingerprint(  # noqa: PLR0913 - every bound field is explicit.
    *,
    authority_manifest_fingerprint: str,
    source_family: str,
    source_ids: tuple[str, ...],
    observation_cutoff: str,
    allowed_urls: tuple[str, ...],
    register_identity: tuple[str, str, str],
    historical_replay: bool,
    policy_bound: bool | None = None,
    policy_fingerprint: str | None = None,
) -> str:
    binding: dict[str, object] = {
        "allowed_urls": list(allowed_urls),
        "authority_manifest_fingerprint": authority_manifest_fingerprint,
        "historical_replay": historical_replay,
        "observation_cutoff": observation_cutoff,
        "register_identity": list(register_identity),
        "source_family": source_family,
        "source_ids": list(source_ids),
    }
    if policy_bound is None:
        policy_bound = source_family in {"HKEX", "JUDICIARY"} and not historical_replay
    if policy_fingerprint is not None:
        binding["execution_policy_fingerprint"] = policy_fingerprint
    elif policy_bound:
        policy_for_family = {
            "HKEX": hkex_policy_fingerprint,
            "JUDICIARY": judiciary_policy_fingerprint,
        }.get(source_family)
        if policy_for_family is None:
            _execution_fail("EXECUTION_POLICY_SOURCE_FAMILY_INVALID")
        binding["execution_policy_fingerprint"] = policy_for_family()
    return "sha256:" + hashlib.sha256(_canonical_bytes(binding)).hexdigest()


def _authorize_execution(  # noqa: C901, PLR0912, PLR0913, PLR0915 - closed authority gate.
    *,
    authority_manifest: Path,
    matrix: Path,
    output_root: Path,
    source_family: str,
    observation_cutoff: str,
    repository_root: Path = _REPOSITORY_ROOT,
    historical_replay: bool,
) -> ExecutionAuthorization:
    """Bind one operationally attested family before any transport is constructed."""
    expected_source_ids = _EXECUTION_SOURCE_IDS.get(source_family)
    if expected_source_ids is None:
        _execution_fail("EXECUTION_SOURCE_FAMILY_INVALID")
    report = preflight(
        authority_manifest=authority_manifest,
        matrix=matrix,
        output_root=output_root,
        repository_root=repository_root,
    )
    unexpected = set(report["missing_codes"]) - _OPERATIONAL_ATTESTATION_CODES
    if source_family == "JUDICIARY":
        # A multi-family authority may retain an older HKEX register. Current
        # Judiciary URL equality is enforced again by the executor before any
        # transport, so unrelated Regulatory evolution must not invalidate it.
        unexpected -= _JUDICIARY_UNRELATED_REGULATORY_DRIFT_CODES
    if historical_replay:
        unexpected -= _HISTORICAL_REPLAY_MISMATCH_CODES
        if source_family == "JUDICIARY":
            unexpected -= _HISTORICAL_JUDICIARY_REPLAY_MISMATCH_CODES
        elif source_family == "HKEX":
            unexpected -= _HISTORICAL_HKEX_REPLAY_MISMATCH_CODES
    manifest = _read_json(authority_manifest)
    if unexpected or manifest is None:
        _execution_fail("EXECUTION_NOT_AUTHORIZED:" + ",".join(sorted(unexpected)))
    if manifest.get("provenance") != "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING":
        _execution_fail("EXECUTION_NOT_AUTHORIZED:AUTHORITY_PROVENANCE_INVALID")
    window = _object(manifest.get("observation_window"))
    if window is None or window.get("cutoff") != observation_cutoff:
        _execution_fail("EXECUTION_NOT_AUTHORIZED:OBSERVATION_CUTOFF_BINDING_INVALID")
    entries = _list(manifest.get("selected_sources"))
    if entries is None:
        _execution_fail("EXECUTION_NOT_AUTHORIZED:SELECTED_SOURCES_MALFORMED")
    selected: set[str] = set()
    allowed_urls: set[str] = set()
    for raw_entry in entries:
        entry = _object(raw_entry)
        if entry is None:
            _execution_fail("EXECUTION_NOT_AUTHORIZED:SELECTED_SOURCES_MALFORMED")
        source_id = _text(entry.get("source_id"))
        if source_id not in expected_source_ids:
            continue
        selected.add(source_id)
        endpoints = _list(entry.get("endpoints"))
        if endpoints is None:
            _execution_fail("EXECUTION_NOT_AUTHORIZED:ENDPOINT_CONTRACT_MALFORMED")
        for raw_endpoint in endpoints:
            endpoint = _object(raw_endpoint)
            if endpoint is None:
                _execution_fail("EXECUTION_NOT_AUTHORIZED:ENDPOINT_CONTRACT_MALFORMED")
            host = _text(endpoint.get("host"))
            path = _text(endpoint.get("path"))
            if host is None or path is None or not path.startswith("/"):
                _execution_fail("EXECUTION_NOT_AUTHORIZED:ENDPOINT_CONTRACT_MALFORMED")
            allowed_urls.add(f"https://{host}{path}")
    if selected != set(expected_source_ids) or not allowed_urls:
        _execution_fail("EXECUTION_NOT_AUTHORIZED:SOURCE_PROCEDURE_BINDING_INCOMPLETE")
    fingerprint = _text(manifest.get("fingerprint"))
    if fingerprint is None or _FINGERPRINT.fullmatch(fingerprint) is None:
        _execution_fail("EXECUTION_NOT_AUTHORIZED:AUTHORITY_MANIFEST_MALFORMED")
    register_family = {
        "GLD": "LEGISLATION",
        "HKEL": "LEGISLATION",
        "JUDICIARY": "CASES",
        "HKEX": "REGULATORY",
    }[source_family]
    register_bindings = _list(manifest.get("registers"))
    register_binding: dict[str, object] | None = None
    for raw_binding in register_bindings or []:
        candidate = _object(raw_binding)
        if candidate is not None and candidate.get("family") == register_family:
            register_binding = candidate
            break
    if register_binding is None:
        _execution_fail("EXECUTION_NOT_AUTHORIZED:REGISTER_IDENTITIES_MALFORMED")
    register_id = _text(register_binding.get("register_id"))
    register_version = _text(register_binding.get("register_version"))
    register_fingerprint = _text(register_binding.get("fingerprint"))
    if (
        register_id is None
        or register_version is None
        or register_fingerprint is None
        or _FINGERPRINT.fullmatch(register_fingerprint) is None
    ):
        _execution_fail("EXECUTION_NOT_AUTHORIZED:REGISTER_IDENTITIES_MALFORMED")
    source_ids = tuple(sorted(selected))
    exact_allowed_urls = tuple(sorted(allowed_urls))
    exact_register_identity = (register_id, register_version, register_fingerprint)
    binding_fingerprint = _execution_binding_fingerprint(
        authority_manifest_fingerprint=fingerprint,
        source_family=source_family,
        source_ids=source_ids,
        observation_cutoff=observation_cutoff,
        allowed_urls=exact_allowed_urls,
        register_identity=exact_register_identity,
        historical_replay=historical_replay,
    )
    return ExecutionAuthorization(
        fingerprint,
        source_family,
        source_ids,
        observation_cutoff,
        exact_allowed_urls,
        exact_register_identity,
        binding_fingerprint,
        historical_replay,
    )


def authorize_execution(  # noqa: PLR0913 - exact public authority gate.
    *,
    authority_manifest: Path,
    matrix: Path,
    output_root: Path,
    source_family: str,
    observation_cutoff: str,
    repository_root: Path = _REPOSITORY_ROOT,
) -> ExecutionAuthorization:
    """Bind one current operationally attested family before transport construction."""
    return _authorize_execution(
        authority_manifest=authority_manifest,
        matrix=matrix,
        output_root=output_root,
        source_family=source_family,
        observation_cutoff=observation_cutoff,
        repository_root=repository_root,
        historical_replay=False,
    )


def authorize_retained_replay(  # noqa: C901, PLR0912, PLR0913 - exact replay-only gate.
    *,
    authority_manifest: Path,
    matrix: Path,
    output_root: Path,
    source_family: str,
    observation_cutoff: str,
    attempt_id: str | None = None,
    predecessor_attempt_id: str | None = None,
    repository_root: Path = _REPOSITORY_ROOT,
) -> ExecutionAuthorization:
    """Bind only an exact allocated frozen replay identity."""
    if source_family not in {"HKEL", "JUDICIARY", "HKEX"}:
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    judiciary_expected: tuple[tuple[str, str, str], str, str, str | None] | None = None
    hkex_expected: HistoricalHKEXReplayPin | None = None
    if source_family == "JUDICIARY":
        judiciary_expected = _require_exact_historical_judiciary_attempt(
            output_root=output_root,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            observation_cutoff=observation_cutoff,
        )
    elif source_family == "HKEX":
        hkex_expected = _require_exact_historical_hkex_attempt(
            output_root=output_root,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            observation_cutoff=observation_cutoff,
        )
    authorization = _authorize_execution(
        authority_manifest=authority_manifest,
        matrix=matrix,
        output_root=output_root,
        source_family=source_family,
        observation_cutoff=observation_cutoff,
        repository_root=repository_root,
        historical_replay=True,
    )
    allowed_fingerprint = (
        "sha256:" + hashlib.sha256(_canonical_bytes(list(authorization.allowed_urls))).hexdigest()
    )
    if source_family == "HKEL":
        expected: tuple[tuple[str, str, str], str] = (
            _HISTORICAL_HKEL_REGISTER_IDENTITY,
            _HISTORICAL_HKEL_ALLOWED_URLS_FINGERPRINT,
        )
    elif source_family == "JUDICIARY":
        if judiciary_expected is None:
            _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
        expected = (judiciary_expected[0], judiciary_expected[1])
    else:
        if hkex_expected is None:
            _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
        expected = (hkex_expected.register_identity, hkex_expected.allowed_urls_fingerprint)
    if (authorization.register_identity, allowed_fingerprint) != expected:
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    if source_family == "JUDICIARY":
        if judiciary_expected is None:
            _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
        if authorization.authority_manifest_fingerprint != judiciary_expected[2]:
            _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    elif source_family == "HKEX":
        if (
            hkex_expected is None
            or authorization.authority_manifest_fingerprint != hkex_expected.authority_fingerprint
        ):
            _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    # The retained report predates the replay-only marker, so it is bound to
    # the exact original execution fingerprint.  Keep that immutable identity
    # while exposing the separate replay-only capability to the executor.
    legacy_binding = _execution_binding_fingerprint(
        authority_manifest_fingerprint=authorization.authority_manifest_fingerprint,
        source_family=authorization.source_family,
        source_ids=authorization.source_ids,
        observation_cutoff=authorization.observation_cutoff,
        allowed_urls=authorization.allowed_urls,
        register_identity=authorization.register_identity,
        historical_replay=False,
        policy_bound=(
            (judiciary_expected is not None and judiciary_expected[3] is not None)
            or (
                hkex_expected is not None and hkex_expected.execution_policy_fingerprint is not None
            )
        ),
        policy_fingerprint=(
            judiciary_expected[3]
            if judiciary_expected is not None
            else (hkex_expected.execution_policy_fingerprint if hkex_expected is not None else None)
        ),
    )
    if (
        hkex_expected is not None
        and legacy_binding != hkex_expected.execution_authorization_fingerprint
    ):
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    return ExecutionAuthorization(
        authorization.authority_manifest_fingerprint,
        authorization.source_family,
        authorization.source_ids,
        authorization.observation_cutoff,
        authorization.allowed_urls,
        authorization.register_identity,
        legacy_binding,
        historical_replay=True,
    )


def _require_exact_historical_hkex_attempt(
    *,
    output_root: Path,
    attempt_id: str | None,
    predecessor_attempt_id: str | None,
    observation_cutoff: str,
) -> HistoricalHKEXReplayPin:
    """Accept only one exact frozen HKEX report binding."""
    try:
        pin = historical_hkex_replay_pin(attempt_id or "")
    except KeyError:
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    if predecessor_attempt_id is not None or observation_cutoff != pin.observation_cutoff:
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    report_path = output_root / "attempts" / cast("str", attempt_id) / "report.json"
    raw = b""
    try:
        raw = report_path.read_bytes()
        document = _object(parse_json_bytes(raw, max_bytes=_MAX_HISTORICAL_JUDICIARY_REPORT_BYTES))
    except ContractViolation, OSError, TypeError, ValueError:
        document = None
    if (
        hashlib.sha256(raw).hexdigest() != pin.report_sha256
        or document is None
        or document.get("attempt_id") != attempt_id
        or document.get("source_family") != "HKEX"
        or document.get("observation_cutoff") != pin.observation_cutoff
        or document.get("predecessor_attempt_id") is not None
        or document.get("authority_manifest_fingerprint") != pin.authority_fingerprint
        or document.get("execution_authorization_fingerprint")
        != pin.execution_authorization_fingerprint
        or document.get("result") != pin.expected_result
    ):
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    return pin


def _require_exact_historical_judiciary_attempt(
    *,
    output_root: Path,
    attempt_id: str | None,
    predecessor_attempt_id: str | None,
    observation_cutoff: str,
) -> tuple[tuple[str, str, str], str, str, str | None]:
    """Accept only an exact retained Judiciary report and authority binding."""
    historical: dict[str, tuple[str, str, str, tuple[str, str, str], str, bool]] = {
        _HISTORICAL_JUDICIARY_ATTEMPT_ID: (
            _HISTORICAL_JUDICIARY_CUTOFF,
            _HISTORICAL_JUDICIARY_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_B_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_B_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_B_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_B_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_B_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_B_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_C_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_C_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_C_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_C_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_C_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_C_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_D_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_D_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_D_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_D_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_D_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_D_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_E_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_E_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_E_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_E_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_E_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_E_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_F_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_F_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_F_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_F_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_F_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_F_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_G_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_G_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_G_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_G_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_G_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_G_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_H_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_H_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_H_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_H_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_H_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_H_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_I_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_I_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_I_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_I_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_I_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_I_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_J_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_J_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_J_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_J_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_J_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_J_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_K_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_K_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_K_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_K_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_K_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_K_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_L_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_L_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_L_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_L_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_L_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_L_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_M_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_M_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_M_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_M_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_M_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_M_ALLOWED_URLS_FINGERPRINT,
            False,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_N_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_N_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_N_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_N_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_N_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_N_ALLOWED_URLS_FINGERPRINT,
            True,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_O_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_O_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_O_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_O_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_O_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_O_ALLOWED_URLS_FINGERPRINT,
            True,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_P_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_P_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_P_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_P_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_P_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_P_ALLOWED_URLS_FINGERPRINT,
            True,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_Q_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_Q_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_Q_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_Q_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_Q_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_Q_ALLOWED_URLS_FINGERPRINT,
            True,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_R_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_R_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_R_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_R_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_R_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_R_ALLOWED_URLS_FINGERPRINT,
            True,
        ),
        _HISTORICAL_JUDICIARY_ATTEMPT_S_ID: (
            _HISTORICAL_JUDICIARY_ATTEMPT_S_CUTOFF,
            _HISTORICAL_JUDICIARY_ATTEMPT_S_REPORT_SHA256,
            _HISTORICAL_JUDICIARY_ATTEMPT_S_AUTHORITY_FINGERPRINT,
            _HISTORICAL_JUDICIARY_ATTEMPT_S_REGISTER_IDENTITY,
            _HISTORICAL_JUDICIARY_ATTEMPT_S_ALLOWED_URLS_FINGERPRINT,
            True,
        ),
    }
    if attempt_id is None:
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    values = historical.get(attempt_id)
    expected_predecessor = {
        _HISTORICAL_JUDICIARY_ATTEMPT_Q_ID: _HISTORICAL_JUDICIARY_ATTEMPT_Q_PREDECESSOR_ID,
        _HISTORICAL_JUDICIARY_ATTEMPT_R_ID: _HISTORICAL_JUDICIARY_ATTEMPT_R_PREDECESSOR_ID,
        _HISTORICAL_JUDICIARY_ATTEMPT_S_ID: _HISTORICAL_JUDICIARY_ATTEMPT_S_PREDECESSOR_ID,
    }.get(attempt_id)
    if (
        values is None
        or predecessor_attempt_id != expected_predecessor
        or observation_cutoff != values[0]
    ):
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    (
        cutoff,
        report_sha256,
        authority_fingerprint,
        register_identity,
        allowed_fingerprint,
        policy_bound,
    ) = values
    report_path = output_root / "attempts" / attempt_id / "report.json"
    try:
        raw = report_path.read_bytes()
    except OSError:
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    try:
        document = _object(parse_json_bytes(raw, max_bytes=_MAX_HISTORICAL_JUDICIARY_REPORT_BYTES))
    except ContractViolation, TypeError, ValueError:
        document = None
    if (
        hashlib.sha256(raw).hexdigest() != report_sha256
        or document is None
        or document.get("attempt_id") != attempt_id
        or document.get("source_family") != "JUDICIARY"
        or document.get("observation_cutoff") != cutoff
        or document.get("predecessor_attempt_id") != expected_predecessor
        or document.get("authority_manifest_fingerprint") != authority_fingerprint
    ):
        _execution_fail("EXECUTION_REPLAY_BINDING_INVALID")
    policy_fingerprint = {
        _HISTORICAL_JUDICIARY_ATTEMPT_Q_ID: _HISTORICAL_JUDICIARY_POLICY_110_FINGERPRINT,
        _HISTORICAL_JUDICIARY_ATTEMPT_R_ID: _HISTORICAL_JUDICIARY_POLICY_120_FINGERPRINT,
        _HISTORICAL_JUDICIARY_ATTEMPT_S_ID: _HISTORICAL_JUDICIARY_POLICY_120_FINGERPRINT,
    }.get(
        attempt_id,
        _HISTORICAL_JUDICIARY_POLICY_100_FINGERPRINT if policy_bound else None,
    )
    return register_identity, allowed_fingerprint, authority_fingerprint, policy_fingerprint


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-manifest", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("preflight", "execute"))
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--source-family", choices=("GLD", "HKEL", "JUDICIARY", "HKEX"))
    parser.add_argument("--source-id", choices=("HK-LEG-GLD-EGAZETTE",))
    parser.add_argument("--attempt-id")
    parser.add_argument("--predecessor-attempt-id")
    parser.add_argument("--observation-cutoff")
    return parser


def _cli_execution_authorization(
    arguments: argparse.Namespace, source_family: str
) -> ExecutionAuthorization:
    """Prefer current capture authority, then one exact retained replay authority."""
    try:
        return authorize_execution(
            authority_manifest=arguments.authority_manifest,
            matrix=arguments.matrix,
            output_root=arguments.output_root,
            source_family=source_family,
            observation_cutoff=arguments.observation_cutoff,
            repository_root=_REPOSITORY_ROOT,
        )
    except ValueError:
        report_path = arguments.output_root / "attempts" / arguments.attempt_id / "report.json"
        if not report_path.is_file():
            raise
        return authorize_retained_replay(
            authority_manifest=arguments.authority_manifest,
            matrix=arguments.matrix,
            output_root=arguments.output_root,
            source_family=source_family,
            observation_cutoff=arguments.observation_cutoff,
            attempt_id=arguments.attempt_id,
            predecessor_attempt_id=arguments.predecessor_attempt_id,
            repository_root=_REPOSITORY_ROOT,
        )


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0911
    """Run pure preflight or an explicitly bound authentic capture attempt."""
    arguments = _parser().parse_args(argv)
    if arguments.mode == "execute":
        source_family = arguments.source_family
        if arguments.source_id is not None and source_family not in {None, "GLD"}:
            sys.stdout.buffer.write(
                _canonical_bytes(
                    {"execute_authorized": False, "result": "EXECUTION_INPUT_CONFLICT"}
                )
                + b"\n"
            )
            return 2
        if arguments.source_id == "HK-LEG-GLD-EGAZETTE":
            source_family = "GLD"
        if not all((source_family, arguments.attempt_id, arguments.observation_cutoff)):
            sys.stdout.buffer.write(
                _canonical_bytes(
                    {"execute_authorized": False, "result": "EXECUTION_INPUT_REQUIRED"}
                )
                + b"\n"
            )
            return 2
        from tools.hk_v1_source_execution import (  # noqa: PLC0415
            PredecessorValidationError,
            SourceAttemptClaimError,
            SourceEvidenceIntegrityError,
            UrllibReadOnlyTransport,
            execute_source_family,
            source_attempt_claim,
        )

        try:
            with source_attempt_claim(
                output_root=arguments.output_root,
                attempt_id=arguments.attempt_id,
                repository_root=_REPOSITORY_ROOT,
            ) as attempt_claim:
                try:
                    authorization = _cli_execution_authorization(
                        arguments, cast("str", source_family)
                    )
                except ValueError as error:
                    detail = str(error)
                    raw_codes = detail.partition(":")[2]
                    codes = sorted(code for code in raw_codes.split(",") if code)
                    sys.stdout.buffer.write(
                        _canonical_bytes(
                            {
                                "execute_authorized": False,
                                "missing_codes": codes,
                                "result": "EXECUTION_NOT_AUTHORIZED",
                            }
                        )
                        + b"\n"
                    )
                    return 2
                transport = UrllibReadOnlyTransport(
                    allowed_redirect_urls=frozenset(
                        cast("tuple[str, ...]", getattr(authorization, "allowed_urls", ()))
                    )
                )
                try:
                    try:
                        report = execute_source_family(
                            authority_manifest=arguments.authority_manifest,
                            source_family=cast("str", source_family),
                            output_root=arguments.output_root,
                            attempt_id=arguments.attempt_id,
                            predecessor_attempt_id=arguments.predecessor_attempt_id,
                            observation_cutoff=arguments.observation_cutoff,
                            repository_root=_REPOSITORY_ROOT,
                            transport=transport,
                            authorization=authorization,
                            matrix_path=arguments.matrix,
                            attempt_claim=attempt_claim,
                        )
                    except SourceEvidenceIntegrityError:
                        sys.stdout.buffer.write(
                            _canonical_bytes(
                                {
                                    "attempt_id": arguments.attempt_id,
                                    "execute_authorized": True,
                                    "result": "SOURCE_EVIDENCE_INTEGRITY_FAILURE",
                                    "source_attempted": True,
                                }
                            )
                            + b"\n"
                        )
                        return 2
                    except PredecessorValidationError as error:
                        code = str(error)
                        if code not in _PRE_EFFECT_PREDECESSOR_ERRORS:
                            raise
                        sys.stdout.buffer.write(
                            _canonical_bytes(
                                {
                                    "attempt_id": arguments.attempt_id,
                                    "execute_authorized": True,
                                    "result": code,
                                    "source_attempted": False,
                                }
                            )
                            + b"\n"
                        )
                        return 2
                finally:
                    close = getattr(transport, "close", None)
                    if callable(close):
                        close()
        except SourceAttemptClaimError as error:
            code = str(error)
            if code not in _PRE_EFFECT_ATTEMPT_CLAIM_ERRORS:
                raise
            sys.stdout.buffer.write(
                _canonical_bytes(
                    {
                        "attempt_id": arguments.attempt_id,
                        "execute_authorized": False,
                        "result": code,
                        "source_attempted": False,
                    }
                )
                + b"\n"
            )
            return 2
        sys.stdout.buffer.write(_canonical_bytes(report) + b"\n")
        return 0 if report["result"] == "COMPLETE" else 1
    report = preflight(
        authority_manifest=arguments.authority_manifest,
        matrix=arguments.matrix,
        output_root=arguments.output_root,
    )
    sys.stdout.buffer.write(canonical_report_bytes(report))
    return 0
