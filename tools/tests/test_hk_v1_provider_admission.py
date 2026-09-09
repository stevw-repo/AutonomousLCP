"""Focused two-clean-run provider-admission contract tests."""

# ruff: noqa: D103, SLF001
# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false
# pyright: reportUnknownArgumentType=false, reportUnnecessaryCast=false

from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from collections.abc import Callable
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Never, cast

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_processing import semantic_effect_receipt_id, semantic_evaluation_request_id
from asklegal_promotion import (
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingReceipt,
    EmbeddingRequest,
    TargetDefinition,
    TargetRecord,
    query_readback_receipt_id,
    retrieval_embedding_request_id,
    retrieval_query_request_id,
    retrieval_setup_request_id,
)

import tools.hk_v1_provider_admission as provider_admission
from tools.hk_v1_provider_admission import (
    ProviderAdmissionError,
    issue_provider_admission_evidence,
    main,
    parse_provider_admission_evidence,
)

_CUTOFF = "2026-09-08T12:00:00+08:00"
_PROPOSAL = "sha256:" + "1" * 64
_SEMANTIC_PROFILE = "sha256:" + "2" * 64
_EMBEDDING_PROFILE = "sha256:" + "3" * 64
_SERVING_PROFILE = "sha256:" + "4" * 64
_TARGET = "asklegal-v1-hk-local-20260908t120000"
_TARGET_FP = "sha256:" + "5" * 64
_SUITE_PATH = Path(__file__).parents[2] / "contracts/hk-v1-provider-golden-suite.json"
_SUITE = cast("dict[str, object]", json.loads(_SUITE_PATH.read_bytes()))
_SUITE_FP = cast("str", _SUITE["fingerprint"])


def _fingerprint(document: object) -> str:
    return "sha256:" + sha256(canonicalize(checked_json_value(document))).hexdigest()


def _decision(
    run_id: str,
    case_id: str,
    task: str,
    phase: str,
    expected: dict[str, object],
) -> dict[str, object]:
    request_id = semantic_evaluation_request_id(run_id, case_id, phase)
    document: dict[str, object] = {
        "challenge_code": expected["challenge_code"],
        "decision_code": expected["decision_code"],
        "phase": phase,
        "request_id": request_id,
        "supporting_evidence_refs": expected["supporting_evidence_refs"],
        "task": task,
        "unresolved_facts": expected["unresolved_facts"],
    }
    output_fingerprint = _fingerprint(document)
    provider_request_id = f"azure-{run_id}-{case_id}-{phase}"
    return {
        **document,
        "effect_receipt_id": semantic_effect_receipt_id(
            request_id, provider_request_id, output_fingerprint
        ),
        "output_fingerprint": output_fingerprint,
        "provider": "AZURE_OPENAI",
        "provider_request_id": provider_request_id,
    }


def _semantic(run_id: str, *, drift_code: str | None = None) -> bytes:
    cases: list[dict[str, object]] = []
    for index, raw_case in enumerate(cast("list[object]", _SUITE["semantic_cases"])):
        golden = cast("dict[str, object]", raw_case)
        case_id = cast("str", golden["case_id"])
        primary_expected = deepcopy(cast("dict[str, object]", golden["expected_primary"]))
        challenge_expected = deepcopy(cast("dict[str, object]", golden["expected_challenge"]))
        if index == 0 and drift_code is not None:
            primary_expected["decision_code"] = drift_code
            challenge_expected["decision_code"] = drift_code
        primary_task = cast("str", golden["primary_task"])
        challenge_task = cast("str", golden["challenge_task"])
        cases.append(
            {
                "case_id": case_id,
                "challenge": _decision(
                    run_id, case_id, challenge_task, "CHALLENGE", challenge_expected
                ),
                "challenge_profile_id": "prf_" + sha256(challenge_task.encode()).hexdigest()[:48],
                "evidence_refs": golden["evidence_refs"],
                "expected_decision_code": primary_expected["decision_code"],
                "input_fingerprint": golden["input_fingerprint"],
                "package_fingerprint": golden["package_fingerprint"],
                "primary": _decision(run_id, case_id, primary_task, "DECISION", primary_expected),
                "primary_profile_id": "prf_" + sha256(primary_task.encode()).hexdigest()[:48],
                "suite_case_fingerprint": golden["case_fingerprint"],
            }
        )
    document: dict[str, object] = {
        "cases": sorted(cases, key=lambda item: cast("str", item["case_id"])),
        "observation_cutoff": _CUTOFF,
        "proposal_fingerprint": _PROPOSAL,
        "result": "PASSED",
        "run_id": run_id,
        "schema_id": "asklegal.hk-v1-live-semantic-evaluation/v1",
        "semantic_profile_fingerprint": _SEMANTIC_PROFILE,
        "serving_profile_fingerprint": _SERVING_PROFILE,
        "suite_fingerprint": _SUITE_FP,
    }
    document["fingerprint"] = _fingerprint(document)
    return canonicalize(checked_json_value(document))


def _retrieval(
    run_id: str,
    *,
    drift_score: float | None = None,
    authority_fingerprint: str | None = None,
    plan_fingerprint: str | None = None,
    reconciled: bool = False,
) -> bytes:
    cases: list[dict[str, object]] = []
    setup_records: list[dict[str, object]] = []
    for index, raw_case in enumerate(cast("list[object]", _SUITE["retrieval_cases"])):
        golden = cast("dict[str, object]", raw_case)
        case_id = cast("str", golden["case_id"])
        expected = cast("dict[str, object]", cast("list[object]", golden["expected_records"])[0])
        embed_request = retrieval_embedding_request_id(run_id, case_id)
        query_request = retrieval_query_request_id(run_id, case_id)
        score = drift_score if index == 0 and drift_score is not None else 0.99 - index / 100
        returned = [
            {
                "payload_fingerprint": expected["payload_fingerprint"],
                "record_id": expected["record_id"],
                "score": score,
            }
        ]
        result_fingerprint = _fingerprint(returned)
        query_provider_id = f"pinecone-{run_id}-{case_id}"
        cases.append(
            {
                "case_id": case_id,
                "embedding_receipt": {
                    "dimensions": 4,
                    "input_tokens": 4,
                    "latency_milliseconds": 12 + index,
                    "provider_request_id": f"embedding-{run_id}-{case_id}",
                    "receipt_id": "emc_" + sha256(embed_request.encode()).hexdigest()[:48],
                    "request_id": embed_request,
                    "result": "SUCCEEDED",
                    "vector_fingerprint": "sha256:" + sha256(case_id.encode()).hexdigest(),
                },
                "expected_record_ids": [expected["record_id"]],
                "query_receipt": {
                    "provider_request_id": query_provider_id,
                    "receipt_id": query_readback_receipt_id(
                        query_request, query_provider_id, result_fingerprint
                    ),
                    "request_id": query_request,
                    "result": "SUCCEEDED",
                    "result_fingerprint": result_fingerprint,
                },
                "query_request_fingerprint": golden["query_fingerprint"],
                "returned": returned,
                "suite_case_fingerprint": golden["case_fingerprint"],
                "top_k": golden["top_k"],
            }
        )
        setup_records.append(
            {
                "case_id": case_id,
                "embedding_receipt": {
                    "dimensions": 4,
                    "input_tokens": 4,
                    "latency_milliseconds": 7 + index,
                    "provider_request_id": f"setup-embedding-{run_id}-{case_id}",
                    "receipt_id": "emc_"
                    + sha256(f"setup-{run_id}-{case_id}".encode()).hexdigest()[:48],
                    "request_id": retrieval_setup_request_id(run_id, case_id),
                    "result": "SUCCEEDED",
                    "vector_fingerprint": "sha256:"
                    + sha256(f"setup-vector-{case_id}".encode()).hexdigest(),
                },
                "payload_fingerprint": expected["payload_fingerprint"],
                "record_id": expected["record_id"],
            }
        )
    setup_inventory = [
        {
            "payload_fingerprint": item["payload_fingerprint"],
            "record_id": item["record_id"],
            "vector_fingerprint": cast("dict[str, object]", item["embedding_receipt"])[
                "vector_fingerprint"
            ],
        }
        for item in setup_records
    ]
    setup: dict[str, object] = {
        "readback_inventory_fingerprint": _fingerprint(setup_inventory),
        "record_count": len(setup_records),
        "records": setup_records,
        "run_id": run_id,
        "target_fingerprint": _TARGET_FP,
        "target_name": _TARGET,
    }
    setup["fingerprint"] = _fingerprint(setup)
    operation_methods = [
        ("INDEX_DESCRIBE_OR_LIST", "GET", "describe-1"),
        ("INDEX_CREATE", "POST", "create"),
        ("INDEX_DESCRIBE_OR_LIST", "GET", "describe-2"),
        ("INDEX_DESCRIBE_OR_LIST", "GET", "describe-3"),
        ("VECTOR_UPSERT", "POST", "upsert-1"),
        ("VECTOR_UPSERT", "POST", "upsert-2"),
        ("INDEX_STATS", "POST", "stats"),
        ("VECTOR_LIST", "GET", "list"),
        ("VECTOR_FETCH", "GET", "fetch-1"),
        ("VECTOR_FETCH", "GET", "fetch-2"),
        *[("VECTOR_QUERY", "POST", cast("str", case["case_id"])) for case in cases],
    ]
    if reconciled:
        operation_methods.extend(
            (
                ("INDEX_DESCRIBE_OR_LIST", "GET", "reconcile-describe-1"),
                ("INDEX_DESCRIBE_OR_LIST", "GET", "reconcile-describe-2"),
                ("VECTOR_LIST", "GET", "reconcile-list"),
                ("VECTOR_FETCH", "GET", "reconcile-fetch-1"),
                ("VECTOR_FETCH", "GET", "reconcile-fetch-2"),
            )
        )
    authority_fingerprint = authority_fingerprint or (
        "sha256:" + sha256(f"authority-{run_id}".encode()).hexdigest()
    )
    plan_fingerprint = plan_fingerprint or (
        "sha256:" + sha256(f"plan-{run_id}".encode()).hexdigest()
    )
    target_provider_calls: list[dict[str, object]] = []
    for operation, method, identity in operation_methods:
        provider_request_id = f"pinecone-{run_id}-{identity}"
        call = cast(
            "dict[str, object]",
            json.loads(
                provider_admission._runtime_record(
                    "asklegal.hk-v1-pinecone-provider-call/v1",
                    {
                        "authority_fingerprint": authority_fingerprint,
                        "call_class": (
                            "RECONCILIATION" if identity.startswith("reconcile-") else "EVALUATION"
                        ),
                        "cost_basis": "PROVIDER_BILLING_OUT_OF_BAND_CALL_CEILING",
                        "latency_milliseconds": 3,
                        "method": method,
                        "operation": operation,
                        "plan_fingerprint": plan_fingerprint,
                        "provider_reported_cost_microunits": None,
                        "provider_request_id": provider_request_id,
                        "request_fingerprint": "sha256:"
                        + sha256(f"{operation}-{identity}".encode()).hexdigest(),
                        "request_units": 1,
                        "run_id": run_id,
                        "target_name": _TARGET,
                    },
                )
            ),
        )
        target_provider_calls.append(call)
    document: dict[str, object] = {
        "cases": sorted(cases, key=lambda item: cast("str", item["case_id"])),
        "embedding_profile_fingerprint": _EMBEDDING_PROFILE,
        "observation_cutoff": _CUTOFF,
        "proposal_fingerprint": _PROPOSAL,
        "result": "PASSED",
        "run_id": run_id,
        "schema_id": "asklegal.hk-v1-live-retrieval-evaluation/v1",
        "serving_profile_fingerprint": _SERVING_PROFILE,
        "suite_fingerprint": _SUITE_FP,
        "target_fingerprint": _TARGET_FP,
        "target_name": _TARGET,
        "target_provider_calls": target_provider_calls,
        "target_setup": setup,
    }
    document["fingerprint"] = _fingerprint(document)
    return canonicalize(checked_json_value(document))


def _evidence() -> bytes:
    return issue_provider_admission_evidence(
        semantic_run_1=_semantic("provider-run-1"),
        retrieval_run_1=_retrieval("provider-run-1"),
        semantic_run_2=_semantic("provider-run-2"),
        retrieval_run_2=_retrieval("provider-run-2"),
    )


def test_two_matching_semantic_and_retrieval_executions_are_admitted() -> None:
    receipt = parse_provider_admission_evidence(_evidence())
    assert receipt.result == "ADMITTED"
    assert receipt.run_ids == ("provider-run-1", "provider-run-2")
    assert receipt.semantic_case_count == 3
    assert receipt.retrieval_case_count == 4
    assert receipt.suite_fingerprint == _SUITE_FP


@pytest.mark.parametrize(
    ("semantic_2", "retrieval_2"),
    [
        (_semantic("provider-run-2", drift_code="REPEAL"), _retrieval("provider-run-2")),
        (_semantic("provider-run-2"), _retrieval("provider-run-2", drift_score=0.75)),
        (_semantic("provider-run-2"), _retrieval("different-run")),
        (_semantic("provider-run-1"), _retrieval("provider-run-1")),
    ],
)
def test_drift_or_reused_execution_is_rejected(semantic_2: bytes, retrieval_2: bytes) -> None:
    with pytest.raises(ProviderAdmissionError, match="PROVIDER_ADMISSION_INVALID"):
        issue_provider_admission_evidence(
            semantic_run_1=_semantic("provider-run-1"),
            retrieval_run_1=_retrieval("provider-run-1"),
            semantic_run_2=semantic_2,
            retrieval_run_2=retrieval_2,
        )


def test_cloned_run_relabelled_with_a_new_outer_id_is_rejected() -> None:
    semantic = cast("dict[str, object]", json.loads(_semantic("provider-run-1")))
    retrieval = cast("dict[str, object]", json.loads(_retrieval("provider-run-1")))
    for document in (semantic, retrieval):
        document["run_id"] = "provider-run-2"
        document.pop("fingerprint")
        document["fingerprint"] = _fingerprint(document)
    with pytest.raises(ProviderAdmissionError):
        issue_provider_admission_evidence(
            semantic_run_1=_semantic("provider-run-1"),
            retrieval_run_1=_retrieval("provider-run-1"),
            semantic_run_2=canonicalize(checked_json_value(semantic)),
            retrieval_run_2=canonicalize(checked_json_value(retrieval)),
        )


@pytest.mark.parametrize("identity_family", ["semantic", "query", "setup_embedding"])
def test_provider_attempt_identity_reuse_across_runs_is_rejected(identity_family: str) -> None:
    semantic_1 = cast("dict[str, object]", json.loads(_semantic("provider-run-1")))
    semantic_2 = cast("dict[str, object]", json.loads(_semantic("provider-run-2")))
    retrieval_1 = cast("dict[str, object]", json.loads(_retrieval("provider-run-1")))
    retrieval_2 = cast("dict[str, object]", json.loads(_retrieval("provider-run-2")))
    if identity_family == "semantic":
        first = cast(
            "dict[str, object]",
            cast("dict[str, object]", cast("list[object]", semantic_1["cases"])[0])["primary"],
        )
        second = cast(
            "dict[str, object]",
            cast("dict[str, object]", cast("list[object]", semantic_2["cases"])[0])["primary"],
        )
        second["provider_request_id"] = first["provider_request_id"]
        second["effect_receipt_id"] = semantic_effect_receipt_id(
            cast("str", second["request_id"]),
            cast("str", second["provider_request_id"]),
            cast("str", second["output_fingerprint"]),
        )
        semantic_2.pop("fingerprint")
        semantic_2["fingerprint"] = _fingerprint(semantic_2)
    else:
        if identity_family == "query":
            first = cast(
                "dict[str, object]",
                cast("dict[str, object]", cast("list[object]", retrieval_1["cases"])[0])[
                    "query_receipt"
                ],
            )
            second = cast(
                "dict[str, object]",
                cast("dict[str, object]", cast("list[object]", retrieval_2["cases"])[0])[
                    "query_receipt"
                ],
            )
            second["provider_request_id"] = first["provider_request_id"]
            second["receipt_id"] = query_readback_receipt_id(
                cast("str", second["request_id"]),
                cast("str", second["provider_request_id"]),
                cast("str", second["result_fingerprint"]),
            )
        else:
            setup_1 = cast("dict[str, object]", retrieval_1["target_setup"])
            setup_2 = cast("dict[str, object]", retrieval_2["target_setup"])
            first = cast(
                "dict[str, object]",
                cast("dict[str, object]", cast("list[object]", setup_1["records"])[0])[
                    "embedding_receipt"
                ],
            )
            second = cast(
                "dict[str, object]",
                cast("dict[str, object]", cast("list[object]", setup_2["records"])[0])[
                    "embedding_receipt"
                ],
            )
            second["provider_request_id"] = first["provider_request_id"]
            setup_2.pop("fingerprint")
            setup_2["fingerprint"] = _fingerprint(setup_2)
        retrieval_2.pop("fingerprint")
        retrieval_2["fingerprint"] = _fingerprint(retrieval_2)
    with pytest.raises(ProviderAdmissionError):
        issue_provider_admission_evidence(
            semantic_run_1=canonicalize(checked_json_value(semantic_1)),
            retrieval_run_1=canonicalize(checked_json_value(retrieval_1)),
            semantic_run_2=canonicalize(checked_json_value(semantic_2)),
            retrieval_run_2=canonicalize(checked_json_value(retrieval_2)),
        )


@pytest.mark.parametrize(
    "mutation",
    ["dropped", "duplicate", "reused", "wrong_run", "cost", "operation_count"],
)
def test_target_call_accounting_drift_or_reuse_is_rejected(mutation: str) -> None:
    semantic_1 = _semantic("provider-run-1")
    retrieval_1 = cast("dict[str, object]", json.loads(_retrieval("provider-run-1")))
    semantic_2 = _semantic("provider-run-2")
    retrieval_2 = cast("dict[str, object]", json.loads(_retrieval("provider-run-2")))
    calls_1 = cast("list[dict[str, object]]", retrieval_1["target_provider_calls"])
    calls_2 = cast("list[dict[str, object]]", retrieval_2["target_provider_calls"])
    if mutation == "dropped":
        calls_2.pop()
    else:
        changed = calls_2[1]
        if mutation == "duplicate":
            changed["provider_request_id"] = calls_2[0]["provider_request_id"]
        elif mutation == "reused":
            changed["provider_request_id"] = calls_1[1]["provider_request_id"]
        elif mutation == "wrong_run":
            changed["run_id"] = "provider-run-1"
        elif mutation == "cost":
            changed["provider_reported_cost_microunits"] = 1
        else:
            changed["operation"] = "VECTOR_FETCH"
        changed.pop("fingerprint")
        changed["fingerprint"] = _fingerprint(changed)
    retrieval_2.pop("fingerprint")
    retrieval_2["fingerprint"] = _fingerprint(retrieval_2)
    with pytest.raises(ProviderAdmissionError):
        issue_provider_admission_evidence(
            semantic_run_1=semantic_1,
            retrieval_run_1=canonicalize(checked_json_value(retrieval_1)),
            semantic_run_2=semantic_2,
            retrieval_run_2=canonicalize(checked_json_value(retrieval_2)),
        )


@pytest.mark.parametrize("operation", sorted(provider_admission._TARGET_OPERATION_COUNTS))
def test_every_planned_target_operation_receipt_is_required(operation: str) -> None:
    retrieval = cast("dict[str, object]", json.loads(_retrieval("provider-run-2")))
    calls = cast("list[dict[str, object]]", retrieval["target_provider_calls"])
    calls.remove(next(call for call in calls if call["operation"] == operation))
    retrieval.pop("fingerprint")
    retrieval["fingerprint"] = _fingerprint(retrieval)
    with pytest.raises(ProviderAdmissionError):
        issue_provider_admission_evidence(
            semantic_run_1=_semantic("provider-run-1"),
            retrieval_run_1=_retrieval("provider-run-1"),
            semantic_run_2=_semantic("provider-run-2"),
            retrieval_run_2=canonicalize(checked_json_value(retrieval)),
        )


@pytest.mark.parametrize("mutation", ["dropped", "duplicate", "wrong_run", "cost"])
def test_reconciliation_call_ledger_is_exact_and_bound(mutation: str) -> None:
    retrieval_1 = _retrieval("provider-run-1", reconciled=True)
    retrieval_2 = cast(
        "dict[str, object]", json.loads(_retrieval("provider-run-2", reconciled=True))
    )
    calls = cast("list[dict[str, object]]", retrieval_2["target_provider_calls"])
    reconciliation = [call for call in calls if call["call_class"] == "RECONCILIATION"]
    if mutation == "dropped":
        calls.remove(reconciliation[-1])
    else:
        changed = reconciliation[1]
        if mutation == "duplicate":
            changed["provider_request_id"] = reconciliation[0]["provider_request_id"]
        elif mutation == "wrong_run":
            changed["run_id"] = "provider-run-1"
        else:
            changed["provider_reported_cost_microunits"] = 1
        changed.pop("fingerprint")
        changed["fingerprint"] = _fingerprint(changed)
    retrieval_2.pop("fingerprint")
    retrieval_2["fingerprint"] = _fingerprint(retrieval_2)
    with pytest.raises(ProviderAdmissionError):
        issue_provider_admission_evidence(
            semantic_run_1=_semantic("provider-run-1"),
            retrieval_run_1=retrieval_1,
            semantic_run_2=_semantic("provider-run-2"),
            retrieval_run_2=canonicalize(checked_json_value(retrieval_2)),
        )


def test_two_reconciled_runs_remain_equivalent_and_admissible() -> None:
    evidence = issue_provider_admission_evidence(
        semantic_run_1=_semantic("provider-run-1"),
        retrieval_run_1=_retrieval("provider-run-1", reconciled=True),
        semantic_run_2=_semantic("provider-run-2"),
        retrieval_run_2=_retrieval("provider-run-2", reconciled=True),
    )
    assert parse_provider_admission_evidence(evidence).result == "ADMITTED"


def test_caller_named_case_cannot_replace_the_frozen_suite() -> None:
    document = cast("dict[str, object]", json.loads(_semantic("provider-run-1")))
    first = cast("dict[str, object]", cast("list[object]", document["cases"])[0])
    first["case_id"] = "caller-selected-case"
    document.pop("fingerprint")
    document["fingerprint"] = _fingerprint(document)
    with pytest.raises(ProviderAdmissionError):
        issue_provider_admission_evidence(
            semantic_run_1=canonicalize(checked_json_value(document)),
            retrieval_run_1=_retrieval("provider-run-1"),
            semantic_run_2=_semantic("provider-run-2"),
            retrieval_run_2=_retrieval("provider-run-2"),
        )


def test_missing_or_drifted_checked_in_suite_blocks_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(provider_admission, "_SUITE_PATH", missing)
    with pytest.raises(ProviderAdmissionError):
        _evidence()

    drifted = tmp_path / "suite.json"
    drifted.write_bytes(_SUITE_PATH.read_bytes().replace(b"Hong Kong", b"Hong K0ng", 1))
    monkeypatch.setattr(provider_admission, "_SUITE_PATH", drifted)
    with pytest.raises(ProviderAdmissionError):
        _evidence()


def _authority(
    *,
    expires_at: str = "2026-09-09T00:00:00Z",
    output_root: str = "/var/lib/asklegal/provider-run-1",
    state_root: str = "/var/lib/asklegal/provider-state",
) -> bytes:
    document: dict[str, object] = {
        "allowed_operations": provider_admission._OPERATIONS,
        "authority_id": "provider-gate-d-run-1",
        "authorized_by": "Named Local Reviewer",
        "embedding_deployment": "embedding-v1",
        "expires_at": expires_at,
        "immutable": True,
        "max_cost_microunits": 1000,
        "max_embedding_calls": 8,
        "max_input_tokens": 10000,
        "max_pinecone_create_attempts": 1,
        "max_pinecone_describe_calls": 3,
        "max_pinecone_fetch_calls": 2,
        "max_pinecone_full_readbacks": 1,
        "max_pinecone_list_calls": 1,
        "max_pinecone_queries": 4,
        "max_pinecone_reconciliation_calls": 5,
        "max_pinecone_stats_calls": 1,
        "max_pinecone_upsert_batches": 2,
        "max_semantic_calls": 6,
        "expected_pinecone_provider_calls": 14,
        "namespace": "provider-golden-v1",
        "observation_cutoff": _CUTOFF,
        "output_root": output_root,
        "pinecone_index": _TARGET,
        "pinecone_project_id": "project-1",
        "plan_fingerprint": "sha256:" + "7" * 64,
        "proposal_fingerprint": _PROPOSAL,
        "run_id": "provider-run-1",
        "schema_id": "asklegal.hk-v1-provider-execution-authority/v1",
        "schema_version": 1,
        "semantic_deployment": "semantic-v1",
        "semantic_profile_fingerprint": _SEMANTIC_PROFILE,
        "serving_profile_fingerprint": _SERVING_PROFILE,
        "state_root": state_root,
        "suite_fingerprint": _SUITE_FP,
        "tokenizer_resource_fingerprint": "sha256:" + "6" * 64,
    }
    document["fingerprint"] = _fingerprint(document)
    return canonicalize(checked_json_value(document))


def test_execution_authority_is_exact_expiring_and_self_fingerprinted() -> None:
    authority = provider_admission._execution_authority(_authority(), now="2026-09-08T00:00:00Z")
    assert authority.run_id == "provider-run-1"
    assert authority.max_semantic_calls == 6
    with pytest.raises(ProviderAdmissionError):
        provider_admission._execution_authority(
            _authority(expires_at="2026-09-07T00:00:00Z"), now="2026-09-08T00:00:00Z"
        )
    with pytest.raises(ProviderAdmissionError):
        provider_admission._execution_authority(
            _authority().replace(b'"max_embedding_calls":8', b'"max_embedding_calls":7'),
            now="2026-09-08T00:00:00Z",
        )


def test_execute_without_detached_authority_stops_before_configuration_or_effects() -> None:
    assert main(["--execute", "--now", "2026-09-08T00:00:00Z"]) == 2


def test_preflight_emits_plan_without_execution_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = provider_admission._runtime_record(
        "asklegal.hk-v1-provider-execution-plan/v1",
        {
            "max_cost_microunits": 1,
            "max_embedding_calls": 8,
            "max_input_tokens": 1,
            "max_pinecone_create_attempts": 1,
            "max_pinecone_describe_calls": 3,
            "max_pinecone_fetch_calls": 2,
            "max_pinecone_full_readbacks": 1,
            "max_pinecone_list_calls": 1,
            "max_pinecone_queries": 4,
            "max_pinecone_reconciliation_calls": 5,
            "max_pinecone_stats_calls": 1,
            "max_pinecone_upsert_batches": 2,
            "max_semantic_calls": 6,
            "expected_pinecone_provider_calls": 14,
            "run_id": "provider-run-1",
        },
    )
    monkeypatch.setattr(provider_admission, "_preflight_plan", lambda _arguments: plan)
    output = (tmp_path / "plan.json").resolve()

    assert main(["--preflight", "--plan-output", str(output)]) == 0
    assert output.read_bytes() == plan


def _serving_profile_bytes() -> bytes:
    embedding: dict[str, object] = {
        "allowed_environments": ["dev"],
        "api_contract": "2026-08-01",
        "cost_limit_microunits": 1000,
        "deployment_name": "synthetic-embedding-v1",
        "dimensions": 4,
        "encoding": "FLOAT32",
        "expires_at": "2099-01-01T00:00:00Z",
        "geography_class": "SYNTHETIC",
        "max_input_tokens": 2048,
        "metric": "cosine",
        "model_id": "synthetic-embedding-model-v1",
        "model_version": "1.0.0",
        "normalization": "UNIT_LENGTH",
        "profile_fingerprint": "",
        "profile_id": "",
        "provider": "AZURE_OPENAI",
        "resource_class": "SYNTHETIC",
        "stateful_features": False,
        "tokenizer": "o200k_base",
    }
    embedding_projection = dict(embedding)
    embedding_projection.pop("profile_fingerprint")
    embedding_projection.pop("profile_id")
    embedding_fingerprint = _fingerprint(embedding_projection)
    embedding["profile_fingerprint"] = embedding_fingerprint
    embedding["profile_id"] = "emp_" + sha256(embedding_fingerprint.encode()).hexdigest()[:48]
    document: dict[str, object] = {
        "backup_profile_ref": {
            "fingerprint": "sha256:" + "3" * 64,
            "ref_id": "cap_" + "4" * 48,
            "ref_type": "CAPABILITY_PROFILE",
        },
        "batch_size": 2,
        "dimensions": 4,
        "embedding": embedding,
        "environment": "dev",
        "expires_at": "2099-01-01T00:00:00Z",
        "fingerprint": "",
        "immutable": True,
        "index_prefix": "asklegal-dev-",
        "metric": "cosine",
        "namespace": "synthetic-v1",
        "outage_behavior": "FAIL_CLOSED",
        "pinecone_project_id": "proj1",
        "provider_timeout_seconds": 60,
        "readback_page_size": 2,
        "schema_id": "asklegal.hk-v1-serving-capability-profile",
        "schema_version": "1.0.0",
        "serving_metadata_keys": [
            "authority_note",
            "country",
            "jurisdiction",
            "source",
            "text",
            "type",
        ],
        "target_timeout_seconds": 60,
    }
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = _fingerprint(projection)
    return canonicalize(checked_json_value(document))


def _preflight_arguments(tmp_path: Path) -> Namespace:
    semantic_factory = cast(
        "Callable[[], bytes]",
        run_path(
            str(
                Path(__file__).parents[2]
                / "apps/legal-processing-worker/tests/_v1_semantic_profile_fixture.py"
            )
        )["exact_semantic_profile_bytes"],
    )
    values = {
        "semantic_profile": semantic_factory(),
        "serving_profile": _serving_profile_bytes(),
        "tokenizer_resource": (
            Path(__file__).parents[2]
            / "packages/processing/src/asklegal_processing/_resources/o200k_base.tiktoken"
        ).read_bytes(),
        "model_credential": canonicalize(
            {
                "api_key": "synthetic-model-key",
                "api_version": "2026-08-01",
                "deployment": "synthetic-semantic-v1",
                "endpoint": "https://127.0.0.1:1",
            }
        ),
        "embedding_credential": canonicalize(
            {
                "api_key": "synthetic-embedding-key",
                "api_version": "2026-08-01",
                "deployment": "synthetic-embedding-v1",
                "endpoint": "https://127.0.0.1:1",
            }
        ),
        "pinecone_credential": canonicalize(
            {
                "api_key": "synthetic-pinecone-key",
                "control_plane_host": "127.0.0.1:1",
                "index": "asklegal-dev-provider-golden-v1",
                "project_id": "proj1",
            }
        ),
    }
    paths: dict[str, Path] = {}
    for name, raw in values.items():
        path = (tmp_path / f"{name.replace('_', '-')}.json").resolve()
        path.write_bytes(raw)
        paths[name] = path
    state_root = (tmp_path / "provider-state").resolve()
    state_root.mkdir(mode=0o700)
    return Namespace(
        **paths,
        authority=None,
        now="2026-09-08T00:00:00Z",
        observation_cutoff=_CUTOFF,
        output_root=(tmp_path / "provider-run-1").resolve(),
        plan_output=(tmp_path / "provider-plan.json").resolve(),
        proposal_fingerprint=_PROPOSAL,
        proxy_host=None,
        proxy_port=None,
        run_id="provider-run-1",
        state_root=state_root,
    )


def test_real_preflight_cli_is_no_authority_and_no_transport_subprocess(tmp_path: Path) -> None:
    arguments = _preflight_arguments(tmp_path)
    command = [
        sys.executable,
        "-m",
        "tools.hk_v1_provider_admission",
        "--preflight",
        "--semantic-profile",
        str(arguments.semantic_profile),
        "--serving-profile",
        str(arguments.serving_profile),
        "--tokenizer-resource",
        str(arguments.tokenizer_resource),
        "--model-credential",
        str(arguments.model_credential),
        "--embedding-credential",
        str(arguments.embedding_credential),
        "--pinecone-credential",
        str(arguments.pinecone_credential),
        "--observation-cutoff",
        arguments.observation_cutoff,
        "--proposal-fingerprint",
        arguments.proposal_fingerprint,
        "--run-id",
        arguments.run_id,
        "--output-root",
        str(arguments.output_root),
        "--state-root",
        str(arguments.state_root),
        "--plan-output",
        str(arguments.plan_output),
    ]
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=Path(__file__).parents[2],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("PREFLIGHT_PASSED_NO_EFFECTS sha256:")
    assert "semantic_calls=6" in completed.stdout
    assert "embedding_calls=8" in completed.stdout
    assert "pinecone_create_attempts=1" in completed.stdout
    assert "pinecone_describe_calls=3" in completed.stdout
    assert "pinecone_fetch_calls=2" in completed.stdout
    assert "pinecone_upsert_batches=2" in completed.stdout
    assert "pinecone_full_readbacks=1" in completed.stdout
    assert "pinecone_list_calls=1" in completed.stdout
    assert "pinecone_queries=4" in completed.stdout
    assert "pinecone_reconciliation_calls=5" in completed.stdout
    assert "pinecone_stats_calls=1" in completed.stdout
    assert "pinecone_provider_calls=14" in completed.stdout
    assert "max_input_tokens=" in completed.stdout
    assert "max_cost_microunits=" in completed.stdout
    plan = provider_admission._document(
        arguments.plan_output.read_bytes(), maximum=provider_admission._MAX_RECEIPT_BYTES
    )
    assert plan["max_semantic_calls"] == 6
    assert plan["max_embedding_calls"] == 8
    assert plan["max_pinecone_queries"] == 4
    assert plan["max_pinecone_reconciliation_calls"] == 5
    assert plan["max_pinecone_upsert_batches"] == 2
    assert plan["max_pinecone_describe_calls"] == 3
    assert plan["max_pinecone_fetch_calls"] == 2
    assert plan["max_pinecone_list_calls"] == 1
    assert plan["max_pinecone_stats_calls"] == 1
    assert plan["expected_pinecone_provider_calls"] == 14
    assert "authority" not in completed.stdout.lower()

    helped = subprocess.run(
        [sys.executable, "-m", "tools.hk_v1_provider_admission", "--help"],
        cwd=Path(__file__).parents[2],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert helped.returncode == 0
    assert "--preflight" in helped.stdout
    assert "--execute" in helped.stdout


def _authority_for_plan(plan: dict[str, object], **overrides: object) -> bytes:
    document = {
        key: value
        for key, value in plan.items()
        if key not in {"fingerprint", "schema_id", "schema_version"}
    }
    document.update(
        {
            "authority_id": "provider-gate-d-live-run-1",
            "authorized_by": "Named Local Reviewer",
            "expires_at": "2026-09-09T00:00:00Z",
            "immutable": True,
            "schema_id": "asklegal.hk-v1-provider-execution-authority/v1",
            "schema_version": 1,
        }
    )
    document.update(overrides)
    document["fingerprint"] = _fingerprint(document)
    return canonicalize(checked_json_value(document))


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("max_cost_microunits", 0),
        ("max_semantic_calls", 5),
        ("output_root", "provider-authority-drift"),
    ],
)
def test_missing_cap_or_drifted_authority_stops_before_transport_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: str,
    value: object,
) -> None:
    arguments = _preflight_arguments(tmp_path)
    plan = cast(
        "dict[str, object]",
        json.loads(provider_admission._preflight_plan(arguments)),
    )
    authority = (tmp_path / "execution-authority.json").resolve()
    authority.write_bytes(_authority_for_plan(plan, **{override: value}))
    arguments.authority = authority
    arguments.proxy_host = "127.0.0.1"
    arguments.proxy_port = 1

    def unexpected_transport(*_args: object, **_kwargs: object) -> Never:
        message = "transport constructed before authority validation"
        raise AssertionError(message)

    monkeypatch.setattr(provider_admission, "BoundedModelTransport", unexpected_transport)
    monkeypatch.setattr(provider_admission, "ProviderTransport", unexpected_transport)
    with pytest.raises(ProviderAdmissionError):
        provider_admission._live_configuration(arguments)


def test_embedding_in_flight_without_receipt_is_not_repeated(tmp_path: Path) -> None:
    class _LostAckEmbedding:
        calls = 0

        def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> Never:
            del profile, request
            self.calls += 1
            message = "lost acknowledgement"
            raise RuntimeError(message)

    profile = EmbeddingProfile(
        "emp_test",
        _EMBEDDING_PROFILE,
        "AZURE_OPENAI",
        "HOSTED",
        "HK",
        "embedding-v1",
        "embedding-model-v1",
        "1",
        "2026-01-01",
        "o200k_base",
        4,
        "FLOAT32",
        "UNIT_LENGTH",
        "cosine",
        100,
        1000,
        "2099-01-01T00:00:00Z",
        ("dev",),
    )
    request = EmbeddingRequest(
        "rer_lost_ack",
        "record-1",
        _PROPOSAL,
        "query",
        _PROPOSAL,
        1,
        profile.profile_id,
        "batch-1",
        0,
        "cache-1",
    )
    delegate = _LostAckEmbedding()
    journal = provider_admission._JournaledEmbeddingPort(tmp_path, delegate)
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        journal.embed(profile, request)
    with pytest.raises(ProviderAdmissionError):
        journal.embed(profile, request)
    assert delegate.calls == 1


def test_semantic_in_flight_without_receipt_is_not_repeated(tmp_path: Path) -> None:
    class _LostAckSemantic:
        calls = 0

        def invoke(self, profile: object, request: object) -> Never:
            del profile, request
            self.calls += 1
            message = "lost semantic acknowledgement"
            raise RuntimeError(message)

    request = provider_admission.SemanticTaskRequest(
        "ser_lost_ack",
        "HK_CASE_PROPOSITION_ANALYSIS",
        "DECISION",
        "semantic-profile-1",
        _PROPOSAL,
        "subject-1",
        ("evidence-1",),
        b"exact evidence",
        "sha256:" + sha256(b"exact evidence").hexdigest(),
    )
    profile = SimpleNamespace(profile_id="semantic-profile-1")
    delegate = _LostAckSemantic()
    journal = provider_admission._JournaledSemanticRunner(tmp_path, delegate)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="lost semantic acknowledgement"):
        journal.invoke(profile, request)  # type: ignore[arg-type]
    with pytest.raises(ProviderAdmissionError):
        journal.invoke(profile, request)  # type: ignore[arg-type]
    assert delegate.calls == 1


def test_target_write_in_flight_without_receipt_is_not_repeated(tmp_path: Path) -> None:
    gate = provider_admission._AuthorityGate(1)
    gate.bind(tmp_path)
    operation = "upserting into exact-target batch 1"
    gate.select(operation)
    gate.require_write("upserting into exact-target")
    gate.select(operation)
    with pytest.raises(ProviderAdmissionError):
        gate.require_write("upserting into exact-target")


def test_lost_create_ack_is_adopted_by_exact_describe_without_repeating_write(  # noqa: C901
    tmp_path: Path,
) -> None:
    suite = provider_admission._load_suite()
    profile = EmbeddingProfile(
        "emp_test",
        _EMBEDDING_PROFILE,
        "AZURE_OPENAI",
        "HOSTED",
        "HK",
        "embedding-v1",
        "embedding-model-v1",
        "1",
        "2026-01-01",
        "o200k_base",
        4,
        "FLOAT32",
        "UNIT_LENGTH",
        "cosine",
        100,
        1000,
        "2099-01-01T00:00:00Z",
        ("dev",),
    )
    authority = provider_admission._execution_authority(_authority(), now="2026-09-08T00:00:00Z")
    gate = provider_admission._AuthorityGate(3, authority)
    gate.bind(tmp_path)

    class _Embedding:
        def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
            assert profile.profile_id == "emp_test"
            values = (float(request.batch_position + 1), 0.0, 0.0, 0.0)
            vector_fingerprint = provider_admission.live_vector_fingerprint(values)
            return EmbeddedVector(
                values,
                EmbeddingReceipt(
                    "emc_" + sha256(request.request_id.encode()).hexdigest()[:48],
                    request.request_id,
                    "provider-" + request.request_id,
                    4,
                    vector_fingerprint,
                    request.token_count,
                    1,
                    "SUCCEEDED",
                ),
            )

    class _Counter:
        tokenizer_id = "o200k_base"

        def count(self, text: str) -> int:
            return len(text.encode())

    class _LostAckTarget:
        target_name = _TARGET
        create_calls = 0
        describe_calls = 0

        def __init__(self) -> None:
            self.definition: TargetDefinition | None = None
            self.records: dict[str, TargetRecord] = {}
            self.upserts = 0

        @staticmethod
        def _record(operation: str, method: str, identity: str) -> None:
            gate.record_provider_call(
                provider_admission.PineconeProviderCallReceipt(
                    operation,
                    method,
                    "sha256:" + sha256(f"{operation}-{identity}".encode()).hexdigest(),
                    f"pinecone-provider-run-1-{identity}",
                    1,
                )
            )

        def create(self, definition: TargetDefinition) -> None:
            self._record("INDEX_DESCRIBE_OR_LIST", "GET", "describe-1")
            gate.require_write(f"creating index {definition.name}")
            self.create_calls += 1
            self.definition = definition
            self._record("INDEX_CREATE", "POST", "create")
            message = "lost create acknowledgement"
            raise provider_admission.OutcomeUnknown(message)

        def describe(self, target_name: str) -> TargetDefinition:
            self.describe_calls += 1
            assert target_name == self.target_name
            assert self.definition is not None
            self._record("INDEX_DESCRIBE_OR_LIST", "GET", "describe-2")
            return self.definition

        def upsert_batch(self, target_name: str, records: tuple[TargetRecord, ...]) -> None:
            gate.require_write(f"upserting into {target_name}")
            self.upserts += 1
            if self.upserts == 1:
                self._record("INDEX_DESCRIBE_OR_LIST", "GET", "describe-3")
            self._record("VECTOR_UPSERT", "POST", f"upsert-{self.upserts}")
            self.records.update({record.record_id: record for record in records})

        def describe_stats(self, target_name: str) -> dict[str, object]:
            assert target_name == self.target_name
            self._record("INDEX_STATS", "POST", "stats")
            return {"totalVectorCount": len(self.records)}

        def enumerate(self, target_name: str) -> tuple[TargetRecord, ...]:
            assert target_name == self.target_name
            self._record("VECTOR_LIST", "GET", "list")
            self._record("VECTOR_FETCH", "GET", "fetch-1")
            self._record("VECTOR_FETCH", "GET", "fetch-2")
            return tuple(sorted(self.records.values(), key=lambda record: record.record_id))

    target = _LostAckTarget()
    configuration = provider_admission._LiveConfiguration(
        authority,
        cast("object", None),  # type: ignore[arg-type]
        SimpleNamespace(
            batch_size=2,
            dimensions=4,
            embedding=profile,
            metric="cosine",
            namespace="provider-golden-v1",
        ),  # type: ignore[arg-type]
        cast("object", None),  # type: ignore[arg-type]
        _Embedding(),
        target,  # type: ignore[arg-type]
        _Counter(),  # type: ignore[arg-type]
        gate,
    )
    with pytest.raises(provider_admission.OutcomeUnknown):
        provider_admission._prepare_target(configuration, suite, "provider-run-1")
    setup, definition = provider_admission._prepare_target(configuration, suite, "provider-run-1")
    assert target.create_calls == 1
    assert target.describe_calls == 1
    assert setup["record_count"] == 4
    assert definition == target.definition


def _install_execute_fakes(  # noqa: C901, PLR0915 - complete injected phase harness.
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    crash_after: str | None = None,
) -> tuple[Namespace, dict[str, int]]:
    output_root = (tmp_path / "provider-run-1").resolve()
    output_root.mkdir()
    state_root = (tmp_path / "provider-state").resolve()
    state_root.mkdir(mode=0o700)
    authority_root = (tmp_path / "read-only-authority").resolve()
    authority_root.mkdir()
    authority_path = (authority_root / "execution-authority.json").resolve()
    authority_path.write_bytes(_authority(output_root=str(output_root), state_root=str(state_root)))
    authority_root.chmod(0o500)
    authority = provider_admission._execution_authority(
        authority_path.read_bytes(), now="2026-09-08T00:00:00Z"
    )
    retrieval_document = cast("dict[str, object]", json.loads(_retrieval(authority.run_id)))
    setup = cast("dict[str, object]", retrieval_document["target_setup"])
    definition = TargetDefinition(
        _TARGET,
        _TARGET_FP,
        4,
        "cosine",
        "provider-golden-v1",
    )
    setup_records = {
        cast("str", item["record_id"]): cast("dict[str, object]", item)
        for item in cast("list[dict[str, object]]", setup["records"])
    }
    records: list[TargetRecord] = []
    vector_fingerprints: dict[tuple[float, ...], str] = {}
    for index, raw_case in enumerate(cast("list[object]", _SUITE["retrieval_cases"])):
        golden = cast("dict[str, object]", raw_case)
        expected = cast("dict[str, object]", cast("list[object]", golden["expected_records"])[0])
        record_id = cast("str", expected["record_id"])
        vector = (float(index + 1), 0.0, 0.0, 0.0)
        retained = setup_records[record_id]
        receipt = cast("dict[str, object]", retained["embedding_receipt"])
        vector_fingerprints[vector] = cast("str", receipt["vector_fingerprint"])
        records.append(
            TargetRecord(
                record_id,
                cast("str", expected["payload_fingerprint"]),
                vector,
                cast("str", expected["text"]),
                cast("str", expected["country"]),
                cast("str", expected["jurisdiction"]),
                cast("str", expected["material_type"]),
                cast("str", expected["source"]),
                cast("str", expected["authority_note"]),
            )
        )

    gate = provider_admission._AuthorityGate(3, authority)
    counts = {"describe": 0, "enumerate": 0, "prepare": 0, "retrieval": 0, "semantic": 0}

    class _RetainedTarget:
        target_name = _TARGET
        describe_calls = 0
        enumerate_calls = 0

        def describe(self, target_name: str) -> TargetDefinition:
            assert target_name == self.target_name
            self.describe_calls += 1
            counts["describe"] += 1
            gate.record_provider_call(
                provider_admission.PineconeProviderCallReceipt(
                    "INDEX_DESCRIBE_OR_LIST",
                    "GET",
                    "sha256:"
                    + sha256(f"reconcile-describe-{self.describe_calls}".encode()).hexdigest(),
                    f"pinecone-provider-reconcile-describe-{self.describe_calls}",
                    1,
                )
            )
            return definition

        def enumerate(self, target_name: str) -> tuple[TargetRecord, ...]:
            assert target_name == self.target_name
            self.enumerate_calls += 1
            counts["enumerate"] += 1
            for operation, method, identity in (
                ("INDEX_DESCRIBE_OR_LIST", "GET", "enumerate-describe"),
                ("VECTOR_LIST", "GET", "enumerate-list"),
                ("VECTOR_FETCH", "GET", "enumerate-fetch-1"),
                ("VECTOR_FETCH", "GET", "enumerate-fetch-2"),
            ):
                gate.record_provider_call(
                    provider_admission.PineconeProviderCallReceipt(
                        operation,
                        method,
                        "sha256:" + sha256(f"reconcile-{identity}".encode()).hexdigest(),
                        f"pinecone-provider-reconcile-{identity}",
                        1,
                    )
                )
            return tuple(sorted(records, key=lambda item: item.record_id))

    target = _RetainedTarget()
    configuration = provider_admission._LiveConfiguration(
        authority,
        SimpleNamespace(environment="LOCAL_SYNTHETIC"),  # type: ignore[arg-type]
        SimpleNamespace(
            dimensions=4,
            embedding=cast("object", None),
            fingerprint=_SERVING_PROFILE,
            metric="cosine",
            namespace="provider-golden-v1",
        ),  # type: ignore[arg-type]
        cast("object", None),  # type: ignore[arg-type]
        cast("object", None),  # type: ignore[arg-type]
        target,  # type: ignore[arg-type]
        cast("object", None),  # type: ignore[arg-type]
        gate,
    )

    def prepare_target(
        _configuration: object, _suite: object, _run_id: str
    ) -> tuple[dict[str, object], TargetDefinition]:
        counts["prepare"] += 1
        return setup, definition

    def semantic_evaluation(**_kwargs: object) -> bytes:
        counts["semantic"] += 1
        return _semantic(authority.run_id)

    def retrieval_evaluation(**_kwargs: object) -> bytes:
        counts["retrieval"] += 1
        return _retrieval(
            authority.run_id,
            authority_fingerprint=authority.fingerprint,
            plan_fingerprint=authority.plan_fingerprint,
        )

    monkeypatch.setattr(provider_admission, "_live_configuration", lambda _args: configuration)
    monkeypatch.setattr(provider_admission, "_prepare_target", prepare_target)
    monkeypatch.setattr(provider_admission, "_semantic_cases", lambda *_args: ())
    monkeypatch.setattr(provider_admission, "_retrieval_cases", lambda *_args: ())
    monkeypatch.setattr(provider_admission, "run_live_semantic_evaluation", semantic_evaluation)
    monkeypatch.setattr(provider_admission, "run_live_retrieval_evaluation", retrieval_evaluation)
    monkeypatch.setattr(
        provider_admission,
        "live_vector_fingerprint",
        lambda vector: vector_fingerprints[tuple(vector)],
    )
    if crash_after is not None:
        original_write = provider_admission._write_exact
        crashed = False

        def crash_after_write(path: Path, raw: bytes) -> None:
            nonlocal crashed
            original_write(path, raw)
            if not crashed and path.name == crash_after:
                crashed = True
                message = f"injected crash after {crash_after}"
                raise RuntimeError(message)

        monkeypatch.setattr(provider_admission, "_write_exact", crash_after_write)
    arguments = Namespace(
        authority=authority_path,
        now="2026-09-08T00:00:00Z",
        observation_cutoff=_CUTOFF,
        output_root=output_root,
        proposal_fingerprint=_PROPOSAL,
        run_id=authority.run_id,
        state_root=state_root,
    )
    return arguments, counts


@pytest.mark.parametrize(
    "crash_after",
    ["target-setup.json", "semantic-evaluation.json", "retrieval-evaluation.json"],
)
def test_single_run_resumes_each_retained_phase_without_repeating_completed_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_after: str,
) -> None:
    arguments, counts = _install_execute_fakes(tmp_path, monkeypatch, crash_after=crash_after)
    assert arguments.authority.parent.stat().st_mode & 0o777 == 0o500
    with pytest.raises(RuntimeError, match="injected crash"):
        provider_admission._execute(arguments)
    semantic, retrieval = provider_admission._execute(arguments)
    assert semantic == _semantic("provider-run-1")
    assert retrieval == _retrieval(
        "provider-run-1",
        authority_fingerprint=provider_admission._execution_authority(
            arguments.authority.read_bytes(), now=arguments.now
        ).fingerprint,
        plan_fingerprint="sha256:" + "7" * 64,
    )
    reconciliation_count = 0 if crash_after == "retrieval-evaluation.json" else 1
    expected_counts = {
        "describe": reconciliation_count,
        "enumerate": reconciliation_count,
        "prepare": 1,
        "retrieval": 1,
        "semantic": 1,
    }
    assert counts == expected_counts

    assert provider_admission._execute(arguments) == (semantic, retrieval)
    assert counts == expected_counts
    arguments.authority.parent.chmod(0o700)


def test_completed_authority_cannot_move_roots_or_recreate_deleted_run_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, counts = _install_execute_fakes(tmp_path, monkeypatch)
    assert arguments.authority.parent.stat().st_mode & 0o777 == 0o500
    provider_admission._execute(arguments)
    assert counts == {
        "describe": 0,
        "enumerate": 0,
        "prepare": 1,
        "retrieval": 1,
        "semantic": 1,
    }

    original_root = arguments.output_root
    different_root = (tmp_path / "different-root").resolve()
    different_root.mkdir()
    arguments.output_root = different_root
    with pytest.raises(ProviderAdmissionError):
        provider_admission._execute(arguments)
    assert counts == {
        "describe": 0,
        "enumerate": 0,
        "prepare": 1,
        "retrieval": 1,
        "semantic": 1,
    }
    arguments.authority.parent.chmod(0o700)

    arguments.output_root = original_root
    (original_root / "execution-state.json").unlink()
    with pytest.raises(ProviderAdmissionError):
        provider_admission._execute(arguments)
    assert counts == {
        "describe": 0,
        "enumerate": 0,
        "prepare": 1,
        "retrieval": 1,
        "semantic": 1,
    }


def test_concurrent_process_cannot_share_one_authority_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, counts = _install_execute_fakes(tmp_path, monkeypatch)
    authority = provider_admission._execution_authority(
        arguments.authority.read_bytes(), now=arguments.now
    )
    lock_path = arguments.state_root / f"{authority.fingerprint}.lock"
    with lock_path.open("a+b") as held:
        provider_admission.fcntl.flock(
            held.fileno(), provider_admission.fcntl.LOCK_EX | provider_admission.fcntl.LOCK_NB
        )
        with pytest.raises(ProviderAdmissionError):
            provider_admission._execute(arguments)
    assert counts == {
        "describe": 0,
        "enumerate": 0,
        "prepare": 0,
        "retrieval": 0,
        "semantic": 0,
    }
    arguments.authority.parent.chmod(0o700)


def test_cli_issues_canonical_report_and_exact_replay(tmp_path: Path) -> None:
    inputs = {
        "semantic-run-1": _semantic("provider-run-1"),
        "retrieval-run-1": _retrieval("provider-run-1"),
        "semantic-run-2": _semantic("provider-run-2"),
        "retrieval-run-2": _retrieval("provider-run-2"),
    }
    args: list[str] = []
    for name, raw in inputs.items():
        path = (tmp_path / f"{name}.json").resolve()
        path.write_bytes(raw)
        args.extend((f"--{name}", str(path)))
    output = (tmp_path / "provider-admission.json").resolve()
    args.extend(("--output", str(output)))
    assert main(args) == 0
    first = output.read_bytes()
    assert main(args) == 0
    assert output.read_bytes() == first == _evidence()
