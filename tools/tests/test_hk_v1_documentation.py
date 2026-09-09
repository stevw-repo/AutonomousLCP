"""Regression tests for current Hong Kong V1 continuity sections."""

from pathlib import Path

CURRENT_SECTION_BY_PATH = {
    Path(".agent/CONTEXT.md"): "## Current V1 position",
    Path(".agent/HANDOFF.md"): "## Current V1 position",
    Path(".agent/WORKING_STATE.md"): "## Current goal",
}


def load_current_v1_sections() -> str:
    """Return only sections whose headings declare the current V1 position."""
    sections: list[str] = []
    for path, marker in CURRENT_SECTION_BY_PATH.items():
        text = path.read_text(encoding="utf-8")
        assert text.count(marker) == 1, (
            f"{path}: expected exactly one current-section heading {marker!r}"
        )
        section = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
        assert section, f"{path}: current section {marker!r} must not be empty"
        sections.append(section)
    return "\n".join(sections)


def test_current_v1_sections_are_fail_closed_and_track_plan_2_external_gate() -> None:
    """Current sections must reject superseded scope and stale plan position."""
    current_sections = " ".join(load_current_v1_sections().split())
    forbidden = (
        "Principles still needs publisher/title/licence selection",
        "Turnstile acceptance path is still a technical admission blocker and must not be bypassed",
        "bounded manual acquisition procedure",
        "Ask.Legal route is the V1 activation boundary",
        "No implementation resumes until the user selects how to execute the completed plan set.",
        "Complete the Plan 1 exit fix and independent review",
        "After an independent Ready verdict, then begin Plan 2 source-neutral local work",
        "Begin Plan 2 source-neutral local work",
    )
    assert not any(text in current_sections for text in forbidden)

    path = Path(".agent/HANDOFF.md")
    engineering = _load_exact_section(path, "## Verified engineering state")
    next_work = _load_exact_section(path, "## Exact next work")
    for required in (
        "Ruff format: all 468 formatter-checked files formatted",
        "Python boundary: 257 files, the same 12 exact reviewed exceptions",
        "ordinary suite: 1725 passed, 4 skipped in 185.52 seconds",
    ):
        assert required in engineering
    assert "Plan 1 exit re-review is complete: **Ready for Plan 2**" in next_work
    assert "Proceed only with Plan 2 Task 7 authentic source admission" in next_work
    assert "Asia/Hong_Kong observation window" in next_work
    assert "Obtain the user's execution-mode choice, then begin Plan 1, Task 1" not in next_work


def _load_exact_section(path: Path, marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(marker) == 1, f"{path}: expected exactly one section {marker!r}"
    section = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    assert section, f"{path}: section {marker!r} must not be empty"
    return " ".join(section.split())


def test_operator_progress_reads_the_configured_due_cycle_state_root() -> None:
    """The documented read-only projection must inspect the worker's real journal root."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    assert "--state-root /var/lib/asklegal/acquisition/due-cycle" in runbook
    assert "--state-root /var/lib/asklegal/acquisition \\" not in runbook


def test_operator_admission_exit_codes_distinguish_manifest_and_evidence_failures() -> None:
    """Operators must not confuse a blocked read-back with malformed CLI input."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    assert "exit `1` is a valid but blocked" in runbook
    assert "including retained-evidence read-back blockers" in runbook
    assert "Exit `2`\nmeans the manifest or invocation input itself" in runbook


def test_operator_runbook_exposes_current_review_promotion_and_no_change_boundaries() -> None:
    """The runbook must not require a restart, manual trigger, or invented no-change CLI."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    for required in (
        "asklegal.local-review-authority/v1",
        "/var/lib/asklegal/review/review-authority.json",
        "/var/lib/asklegal/review/approved-packages/<exact-approval-id>/",
        "/var/lib/asklegal/review/promotion-triggers/<exact-approval-id>.json",
        "promote_approved_hk_v1",
        "discovers a newly retained valid package without restart",
        "There is presently no separate manual all-family no-change acceptance CLI.",
        "continue_hk_v1_due_acceptance",
        "before Legal Processing, proposal, Review, or Promotion effects",
        "Do not create, copy, edit, or delete a promotion trigger manually.",
        "asklegal.hk-v1-serving-state-transition-authority/v1",
        "rollback-readback.json",
        "restoration-readback.json",
        "sudo /usr/bin/install --owner=3007 --group=3007 --mode=0600",
        "sudo /usr/bin/systemctl start asklegal-promotion-worker.service",
    ):
        assert required in runbook
    assert "ASKLEGAL_PROMOTION_TRIGGER=/" not in runbook


def test_operator_runbook_lists_exact_current_no_effect_and_gated_entrypoints() -> None:
    """Every available local operator phase names its current module and effect switch."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    for module in (
        "tools.v1_poc_collect_host_facts",
        "tools.hk_v1_host_reconcile",
        "tools.hk_v1_host_apply",
        "tools.hk_v1_gld_operator",
        "tools.hk_v1_prepare_acquisition_config",
        "tools.hk_v1_select_acceptance_cutoffs",
        "tools.hk_v1_live_cycle",
        "tools.hk_v1_stage_vault_credential_rotation",
        "tools.hk_v1_vault_primary_root_rotation",
        "tools.hk_v1_vault_application_rotation",
        "tools.hk_v1_recovery_proof",
        "tools.hk_v1_serving_state_transition",
        "tools.hk_v1_archive_cleanup",
        "tools.hk_v1_operational_evidence",
        "tools.hk_v1_live_admission",
    ):
        assert module in runbook
    assert "--mode preflight" in runbook
    assert "--mode enqueue" in runbook
    assert "--mode result" in runbook
    assert "--execute" in runbook
    assert "--authorize-local-execution" in runbook


def test_operator_runbook_exposes_both_authorized_host_apply_phases() -> None:
    """Host instructions must stop for a new plan between image build and deployment."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    for required in (
        "asklegal.hk-v1-host-apply-authority/v1",
        "PHASE_COMPLETE_REPLAN_REQUIRED",
        "var/hk-v1/host/application-build-results.json",
        "asklegal/<service>:hk-v1-candidate",
        "--application-build-results",
        "/etc/asklegal/deployment-images",
        "root-owned, regular `0400` persistent restart input",
        "Every action image ID must equal the corresponding retained build-result row.",
        "all five timers active",
        "no unexpected container",
        "Terminal replay revalidates these current facts",
        "retained runtime state",
        "--plan /absolute/path/to/hk-v1/host/reconcile-plan.json",
        "--plan /absolute/path/to/hk-v1/host/deployment-plan.json",
        "Reboot remains a later",
    ):
        assert required in normalized
    assert "there is currently no command in this runbook that applies" not in runbook


def test_operator_runbook_preserves_recovery_limit_and_current_credential_boundary() -> None:
    """Local bootstrap must not imply recovery admission or document the legacy rotation CLI."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    for required in (
        "I_HAVE_CONSOLE_ACCESS=1",
        'admission_limitations=["RECOVERY_PREFLIGHT_NOT_READY"]',
        "v1_admitted=false",
        "/usr/local/libexec/asklegal-vault-application-rotation-network",
        "/usr/local/libexec/asklegal-vault-primary-root-rotation-network",
        "root-owned executables with mode `0755`",
        "Host rollback snapshots and restores each predecessor or exact absence.",
        "tools.hk_v1_vault_application_rotation",
        "tools.hk_v1_vault_primary_root_rotation",
        "-m tools.hk_v1_vault_primary_root_rotation preflight",
        "-m tools.hk_v1_vault_primary_root_rotation execute",
        "-m tools.hk_v1_vault_application_rotation preflight",
        "-m tools.hk_v1_vault_application_rotation execute",
        "--staging-receipt",
        "--primary-root-rotation-plan",
        "--primary-root-rotation-report",
        "--sealed-root",
        "--application-build-results",
        "--application-image-inputs",
        "--authorized-plan-fingerprint",
        "--vault-application-rotation-plan",
        "--vault-application-rotation-report",
        "strictly parsed terminal `SUCCEEDED` report",
        "new-root acceptance",
        "old-root rejection",
        "the seven application vault credentials plus both Primary vault root components",
        "Run preflight as root",
        "Execution is root-only and effectful",
        "terminal successful batch result",
    ):
        assert required in normalized
    assert "--credential-name pinecone-poc" not in runbook
    assert "--credential-rotation-plan" not in runbook


def test_operator_runbook_exposes_retained_live_recovery_boundary() -> None:
    """Recovery documentation must match the restart-safe CLI and helper boundary."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    for required in (
        "--mode PLAN_LIVE",
        "--live-request",
        "--live-credential-manifest",
        "--sql-backup-path-manifest",
        "LIVE_RECOVERY_PLAN_READY",
        "--mode EXECUTE_LIVE",
        "--live-authority",
        "--live-clean-room-root",
        "--live-state-root",
        "/usr/local/libexec/asklegal-sql-recovery-admin",
        "/usr/local/libexec/asklegal-scheduler-recovery-admin",
        "PRIMARY_VAULT_RECOVERY_READER",
        "RECOVERY_VAULT_RECOVERY_READER",
        "SQL_SERVER_RECOVERY_ADMIN",
        "SCHEDULER_GENERAL_RECOVERY_ADMIN",
        "SCHEDULER_PROMOTION_RECOVERY_ADMIN",
    ):
        assert required in runbook
    assert "Preflight only from the CLI; real adapters unavailable" not in runbook
    assert "There is still no standalone CLI that restores a real SQL database" not in runbook


def test_operator_runbook_exposes_exact_gld_authority_sequence() -> None:
    """GLD must remain disabled until browser input and two exact authorities exist."""
    runbook = Path("docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md").read_text(encoding="utf-8")
    for required in (
        "tools.v1_poc_patchright_runtime --check",
        "blocker=NONE",
        "separate OCI build/proof blocker",
        "var/application-inputs/ms-playwright",
        "var/patchright-debs",
        "tools.hk_v1_gld_operator preflight",
        "ASKLEGAL_HK_V1_GLD_OPERATOR_MODE=DISABLED",
        "DISCOVER_GLD_CHALLENGE_CONTRACT",
        "DISCOVER_CONTRACT",
        "OBSERVE_GLD_CURRENT_WINDOW",
        "OBSERVE_WINDOW",
        "does not click, accept terms",
        "obtain explicit user permission",
        "GLD itself needs no API key",
    ):
        assert required in runbook
