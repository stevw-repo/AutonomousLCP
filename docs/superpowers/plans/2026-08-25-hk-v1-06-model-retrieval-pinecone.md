# Compact Model, Retrieval, and Pinecone Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit exact generative, tokenizer, embedding, cost/quota, retrieval, and Pinecone profiles using a compact repeatable evaluation.

**Architecture:** Replace hard-coded proof profiles with strict immutable profile documents read through application-owned configuration/evidence ports. Run a small fixed golden suite through existing strict model and promotion adapters, then build a disposable complete evaluation index and require expected-record-in-top-results retrieval. Only exact read-back evidence issues current capability profiles; production composition remains disabled until Plan 7 consumes those profiles.

**Tech Stack:** Python 3.14.7, Azure OpenAI through Microsoft Foundry, existing `AzureSemanticTaskRunner` and `AzureOpenAIEmbeddingAdapter`, exact tokenizer package pinned in locks, Pinecone REST adapter, strict JSON, Pytest.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- Model use is limited to accepted Gazette, reconstruction, Cases proposition/treatment, and change-gated HKEX tasks.
- Every call binds exact provider, deployment, model version, prompt, schema, tokenizer, evidence budget, retry/timeout, quota, cost, data-handling, environment, and expiry.
- Extra, missing, unknown, malformed, unsupported, or unsupplied-citation model output is rejected, never repaired.
- Evaluation is compact: one representative golden set, English/Traditional Chinese/bilingual/cross-language slices, expected-record-in-top-results checks, one short report, and one clean repeat.
- Invented evidence, wrong attribution, broadened meaning, cross-case leakage, and incomplete bilingual legislation are zero-tolerance failures.
- Embedding input is exactly `metadata.text`; the Pinecone payload has exactly six fields.
- Provider/model/embedding/Pinecone calls require exact separate authorization at Task 6. Pinecone deletion requires its own explicit destructive authority.

## Dependency and exit contract

Depends on Plans 3–5 authentic record shapes, request builders, and compact golden slices. Produces:

```python
def load_semantic_profile_set(reader: ProfileReader) -> SemanticProfileSet: ...


def run_semantic_golden_suite(
    suite: HKV1GoldenSuite, semantic: SemanticTaskRunner
) -> HKV1SemanticEvaluationResult: ...


def run_retrieval_evaluation(
    cases: tuple[RetrievalGoldenCase, ...],
    embeddings: EmbeddingPort,
    target: RetrievalTargetPort,
) -> HKV1RetrievalEvaluationResult: ...
```

Plan 7 consumes exact current capability-evidence references for semantic, embedding, Pinecone-write, backup, and read-back operations. Plan 9 reuses the same frozen profiles without drift.

## File structure

- Create `packages/processing/src/asklegal_processing/profiles.py` — strict semantic profile document loader and fingerprint verification.
- Create `packages/processing/src/asklegal_processing/tokenization.py` — exact tokenizer boundary and counts.
- Create `packages/processing/src/asklegal_processing/evaluation.py` — compact semantic golden-suite runner and report.
- Create `packages/promotion/src/asklegal_promotion/profiles.py` — embedding/Pinecone target/capability profile loader.
- Create `packages/promotion/src/asklegal_promotion/retrieval.py` — exact expected-record top-results evaluator.
- Modify `packages/promotion` model/ports/local/remote modules — bounded query result and adapter contract.
- Create `tools/hk_v1_provider_admission.py` — disabled-by-default admission CLI using ignored evidence/config paths.
- Modify legal-processing and promotion infrastructure loaders to consume admitted profiles rather than placeholder builders.
- Add profile schemas to `contracts/schemas/` and focused tests in processing, promotion, tools, and application packages.

---

### Task 1: Add strict immutable provider-profile contracts

**Files:**
- Create: `packages/processing/src/asklegal_processing/profiles.py`
- Create: `packages/promotion/src/asklegal_promotion/profiles.py`
- Create: `contracts/schemas/hk-v1-semantic-profile.schema.json`
- Create: `contracts/schemas/hk-v1-serving-capability-profile.schema.json`
- Create: `packages/processing/tests/test_profiles.py`
- Create: `packages/promotion/tests/test_profiles.py`
- Modify: `packages/processing/src/asklegal_processing/__init__.py`
- Modify: `packages/promotion/src/asklegal_promotion/__init__.py`

**Interfaces:**
- Consumes: exact canonical profile bytes from an immutable profile reader.
- Produces: `load_semantic_profile_set()` and `load_serving_capability_profile()`.

- [ ] **Step 1: Write failing placeholder and drift tests**

```python
def test_semantic_profile_rejects_placeholder_model_version() -> None:
    with pytest.raises(ProfileError, match="MODEL_VERSION_NOT_EXACT"):
        load_semantic_profile_set(reader(profile_document(model_version="latest")))


def test_serving_profile_rejects_fingerprint_drift() -> None:
    raw = serving_profile_bytes()
    with pytest.raises(ProfileError, match="PROFILE_FINGERPRINT_MISMATCH"):
        load_serving_capability_profile(reader(raw + b" "))
```

- [ ] **Step 2: Run and verify profile modules are absent**

Run: `python3 -m pytest packages/processing/tests/test_profiles.py packages/promotion/tests/test_profiles.py -q`

Expected: collection fails for the missing modules.

- [ ] **Step 3: Implement exact profile types and closed decoding**

```python
@dataclass(frozen=True, slots=True)
class ProviderRetryProfile:
    attempt_ceiling: int
    timeout_seconds: int
    backoff_seconds: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SemanticProfileSet:
    revision: str
    profiles: tuple[SemanticTaskProfile, ...]
    retry_profile: ProviderRetryProfile
    quota_limit_tokens: int
    cost_limit_microunits: int
    fingerprint: str


class ProfileReader(Protocol):
    def read_exact(self, reference: ImmutableReference) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ServingCapabilityProfile:
    embedding: EmbeddingProfile
    pinecone_project_id: str
    index_prefix: str
    dimensions: int
    metric: str
    namespace: str
    batch_size: int
    readback_page_size: int
    backup_profile_ref: ImmutableReference
    expires_at: str
    fingerprint: str
```

Reject placeholder terms (`latest`, `default`, `current`, `auto`), unknown keys, non-exact model versions, mismatched dimensions/metric, expired profiles, stateful features, environment mismatch, and fingerprint drift. Secrets are references, never profile fields.

- [ ] **Step 4: Run schema, profile, and contract tests**

Run: `python3 -m pytest packages/processing/tests/test_profiles.py packages/promotion/tests/test_profiles.py packages/contracts/tests/test_schema_and_binding.py -q`

Expected: all tests pass with only synthetic exact profiles.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/processing packages/promotion contracts/schemas`

Expected: strict profile contracts and tests; no real credentials or coordinates. Commit only with exact user authorization.

### Task 2: Pin tokenizer behavior and preflight cost/quota

**Files:**
- Create: `packages/processing/src/asklegal_processing/tokenization.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock` through the repository lock command.
- Create: `packages/processing/tests/test_tokenization.py`
- Modify: `packages/promotion/tests/test_profiles.py`

**Interfaces:**
- Consumes: exact tokenizer ID and text.
- Produces: `TokenCounter.count(text) -> int` and `preflight_provider_budget()`.

- [ ] **Step 1: Write failing exact-count and overflow tests**

```python
def test_token_counter_matches_frozen_multilingual_vectors() -> None:
    counter = ExactTokenCounter("o200k_base")
    assert counter.count("hello") == 1
    assert counter.count("香港法例 Hong Kong legislation") > 1


def test_preflight_rejects_cost_above_profile_limit() -> None:
    with pytest.raises(ProfileError, match="COST_LIMIT_EXCEEDED"):
        preflight_provider_budget(expensive_requests(), low_cost_profile())
```

- [ ] **Step 2: Run and observe the missing tokenization boundary**

Run: `python3 -m pytest packages/processing/tests/test_tokenization.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement exact tokenizer selection and budget preflight**

```python
class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class ProviderBudgetRequest:
    input_tokens: int
    worst_case_output_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderBudgetProfile:
    quota_limit_tokens: int
    cost_limit_microunits: int
    input_cost_microunits_per_million: int
    output_cost_microunits_per_million: int


@dataclass(frozen=True, slots=True)
class ProviderBudgetDecision:
    total_input_tokens: int
    total_worst_case_output_tokens: int
    worst_case_cost_microunits: int


def preflight_provider_budget(
    requests: tuple[ProviderBudgetRequest, ...],
    profile: ProviderBudgetProfile,
) -> ProviderBudgetDecision: ...
```

Pin the tokenizer library/version/hash in the locks and wheelhouse. Reject an unknown tokenizer, per-input overflow, total quota overflow, and worst-case cost overflow before any provider call.

- [ ] **Step 4: Rebuild locks/wheelhouse inputs and run token tests**

Run the repository's existing locked dependency refresh command for Python 3.14.7, then run:

`python3 -m pytest packages/processing/tests/test_tokenization.py packages/promotion/tests/test_profiles.py tools/tests/test_v1_poc_wheelhouse.py -q`

Expected: frozen multilingual counts pass and locked offline installation inputs reproduce.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- pyproject.toml uv.lock packages/processing tools`

Expected: one pinned tokenizer dependency and deterministic count tests. A dependency/lock change is implementation work; commit only with exact user authorization.

### Task 3: Build the compact semantic golden-suite runner

**Files:**
- Create: `packages/processing/src/asklegal_processing/evaluation.py`
- Create: `packages/processing/tests/fixtures/hk_v1_golden_suite.json`
- Create: `packages/processing/tests/test_compact_evaluation.py`

**Interfaces:**
- Consumes: fixed evidence refs/bytes, expected strict outcomes, exact profiles, and `SemanticTaskRunner`.
- Produces: `HKV1SemanticEvaluationResult` with per-case pass/fail and no aggregate score that can hide a zero-tolerance failure.

- [ ] **Step 1: Write failing golden-suite behavior tests**

```python
def test_golden_suite_covers_required_material_and_language_slices() -> None:
    suite = load_hk_v1_golden_suite()
    assert {case.material for case in suite.cases} == {"GAZETTE", "LEGISLATION", "CASES", "HKEX"}
    assert {case.language_slice for case in suite.cases} >= {
        "EN",
        "ZH_HANT",
        "BILINGUAL",
        "CROSS_LANGUAGE",
    }


def test_one_invented_citation_fails_the_whole_semantic_gate() -> None:
    result = run_semantic_golden_suite(suite_one_bad_citation(), scripted_runner())
    assert result.passed is False
    assert result.failure_codes == ("UNSUPPLIED_EVIDENCE_CITATION",)
```

- [ ] **Step 2: Run and verify evaluator is absent**

Run: `python3 -m pytest packages/processing/tests/test_compact_evaluation.py -q`

Expected: collection fails for the missing evaluator.

- [ ] **Step 3: Implement strict per-case evaluation**

```python
@dataclass(frozen=True, slots=True)
class HKV1GoldenCase:
    case_id: str
    material: Literal["GAZETTE", "LEGISLATION", "CASES", "HKEX"]
    language_slice: Literal["EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"]
    decision_request: SemanticTaskRequest
    challenge_request: SemanticTaskRequest
    expected_decision_code: str
    expected_evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKV1GoldenSuite:
    revision: str
    cases: tuple[HKV1GoldenCase, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKV1SemanticEvaluationResult:
    run_id: str
    profile_fingerprint: str
    case_results: tuple[GoldenCaseResult, ...]
    failure_codes: tuple[str, ...]
    passed: bool
    fingerprint: str
```

Compare schema, allowed decision codes, evidence refs, citation locators, court/opinion/authority attribution, qualifications, exceptions, bilingual alignment, and forbidden broadening. Keep samples short and store full evidence by immutable reference.

- [ ] **Step 4: Run compact and existing strict semantic suites**

Run: `python3 -m pytest packages/processing/tests/test_compact_evaluation.py packages/processing/tests/test_semantic_boundary.py packages/processing/tests/test_remote_semantic_runner.py -q`

Expected: all deterministic evaluation tests pass; no remote call occurs.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/processing`

Expected: one small fixed golden suite and strict evaluator. Commit only with exact user authorization.

### Task 4: Add simple top-results retrieval evaluation

**Files:**
- Create: `packages/promotion/src/asklegal_promotion/retrieval.py`
- Modify: `packages/promotion/src/asklegal_promotion/model.py`
- Modify: `packages/promotion/src/asklegal_promotion/ports.py`
- Modify: `packages/promotion/src/asklegal_promotion/local.py`
- Modify: `packages/promotion/src/asklegal_promotion/remote.py`
- Create: `packages/promotion/tests/fixtures/hk_v1_retrieval_golden.json`
- Create: `packages/promotion/tests/test_retrieval_evaluation.py`

**Interfaces:**
- Consumes: golden query text, expected record IDs, exact embedding profile, `EmbeddingPort`, and `RetrievalTargetPort.query()`.
- Produces: `HKV1RetrievalEvaluationResult`.

- [ ] **Step 1: Write failing expected-record tests**

```python
def test_each_query_passes_when_an_expected_record_is_in_top_results() -> None:
    result = run_retrieval_evaluation(golden_queries(), embeddings(), target_with_expected_hits())
    assert result.passed is True


def test_missing_expected_record_fails_without_statistical_substitute() -> None:
    result = run_retrieval_evaluation(
        golden_queries(), embeddings(), target_without_expected_hits()
    )
    assert result.passed is False
    assert result.case_results[0].failure_code == "EXPECTED_RECORD_NOT_IN_TOP_RESULTS"
```

- [ ] **Step 2: Run and observe missing retrieval module**

Run: `python3 -m pytest packages/promotion/tests/test_retrieval_evaluation.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement the simple retrieval gate**

```python
@dataclass(frozen=True, slots=True)
class RetrievalGoldenCase:
    case_id: str
    language_slice: Literal["EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"]
    query_text: str
    expected_record_ids: tuple[str, ...]
    top_k: int


@dataclass(frozen=True, slots=True)
class RetrievedTargetRecord:
    record_id: str
    score: float
    serving_payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class RetrievalGoldenCaseResult:
    case_id: str
    returned_record_ids: tuple[str, ...]
    failure_code: str


@dataclass(frozen=True, slots=True)
class HKV1RetrievalEvaluationResult:
    run_id: str
    case_results: tuple[RetrievalGoldenCaseResult, ...]
    passed: bool
    fingerprint: str


class RetrievalTargetPort(Protocol):
    def query(
        self, name: str, vector: tuple[float, ...], top_k: int
    ) -> tuple[RetrievedTargetRecord, ...]: ...


def run_retrieval_evaluation(
    cases: tuple[RetrievalGoldenCase, ...],
    embeddings: EmbeddingPort,
    target: RetrievalTargetPort,
) -> HKV1RetrievalEvaluationResult: ...
```

Add the same bounded `query()` contract to local and Pinecone target adapters;
Pinecone requests include values and six-field metadata and the decoder rejects
unknown/missing payload fields. Require each case to return at least one expected
record within its declared `top_k`; verify returned IDs and six-field payload
fingerprints. Do not introduce weighted scores, confidence thresholds, or a
large benchmark.

- [ ] **Step 4: Run retrieval and remote-adapter suites**

Run: `python3 -m pytest packages/promotion/tests/test_retrieval_evaluation.py packages/promotion/tests/test_remote_adapters.py -q`

Expected: all local fake and transport-boundary tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/promotion`

Expected: exact per-query pass/fail retrieval only. Commit only with exact user authorization.

### Task 5: Replace placeholder application composition with admitted-profile readers

**Files:**
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_infrastructure.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py`
- Create: `apps/legal-processing-worker/tests/test_v1_model_profiles.py`
- Create: `apps/promotion-worker/tests/test_v1_serving_profiles.py`

**Interfaces:**
- Consumes: exact immutable profile refs and application-owned secret materials.
- Produces: fail-closed `AzureSemanticTaskRunner`, `AzureOpenAIEmbeddingAdapter`, and `PineconeServingTargetStore` composition only when profile and credential coordinates match.

- [ ] **Step 1: Write failing no-side-override tests**

```python
def test_environment_enable_flag_cannot_replace_profile_evidence() -> None:
    environment = {"ASKLEGAL_ENABLE_REAL_MODEL": "1"}
    with pytest.raises(ConfigurationError, match="SEMANTIC_PROFILE_EVIDENCE_MISSING"):
        load_v1_infrastructure(environment, empty_profile_reader())


def test_profile_credential_deployment_mismatch_fails_closed() -> None:
    with pytest.raises(ConfigurationError, match="SEMANTIC_DEPLOYMENT_MISMATCH"):
        load_v1_infrastructure({}, profile_reader(), credentials_for_other_deployment())
```

- [ ] **Step 2: Run and observe current hard-coded proof profile behavior**

Run: `python3 -m pytest apps/legal-processing-worker/tests/test_v1_model_profiles.py apps/promotion-worker/tests/test_v1_serving_profiles.py -q`

Expected: new tests fail until `_profile()` and proof target assumptions are removed from real composition.

- [ ] **Step 3: Compose only through exact readers**

Delete real-path use of the hard-coded `stp_v1_poc` profile. Preserve deterministic local fakes only under the exact `LOCAL_SYNTHETIC` environment. Profile readers return canonical bytes by immutable ref; credential readers return secrets separately; the loader verifies all public coordinates before constructing adapters.

- [ ] **Step 4: Run application profile and architecture tests**

Run: `python3 -m pytest apps/legal-processing-worker/tests/test_v1_model_profiles.py apps/promotion-worker/tests/test_v1_serving_profiles.py tools/tests/test_v1_poc_application_composition.py tools/tests/test_architecture_spike.py -q`

Expected: all tests pass; missing evidence leaves provider effects disabled.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/legal-processing-worker apps/promotion-worker`

Expected: exact evidence-driven composition and no global real-provider enable flag. Commit only with exact user authorization.

### Task 6: Execute the authorized compact provider and target admission

**Files:**
- Create: `tools/hk_v1_provider_admission.py`
- Create: `tools/tests/test_hk_v1_provider_admission.py`
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: ignored canonical profile files, sealed credentials, fixed golden suites, and exact provider/Pinecone action authority.
- Produces: two byte-stable evaluation reports and immutable current capability-evidence artifacts.

- [ ] **Step 1: Write the disabled-by-default CLI test**

```python
def test_provider_admission_refuses_without_explicit_capability_refs() -> None:
    result = run_provider_admission(AdmissionArguments.empty(), fake_environment())
    assert result.exit_code == 2
    assert result.error_code == "PROVIDER_ADMISSION_NOT_AUTHORIZED"
```

- [ ] **Step 2: Implement exact CLI arguments and dry-run preflight**

```text
python3 -m tools.hk_v1_provider_admission \
  --semantic-profile-ref var/hk-v1/admission-input/semantic-profile.ref.json \
  --serving-profile-ref var/hk-v1/admission-input/serving-profile.ref.json \
  --golden-suite packages/processing/tests/fixtures/hk_v1_golden_suite.json \
  --retrieval-suite packages/promotion/tests/fixtures/hk_v1_retrieval_golden.json \
  --mode preflight
```

Preflight reads profiles/evidence, checks expiry/quota/cost/credentials/target naming, prints exact intended calls and maximum cost, and performs no provider request.

- [ ] **Step 3: Stop and obtain exact external authority**

Require explicit authority for the named Azure deployments, embedding deployment, Pinecone project, disposable evaluation index name, maximum call/token/cost limits, and write operations. Do not infer deletion authority.

- [ ] **Step 4: Run two clean admission executions**

Run the same command as Step 2 with `--mode execute --output-root var/hk-v1/provider-admission/run-1`, then with `run-2` after recreating only those exact empty output directories.

Expected: semantic golden suite passes, complete evaluation index is written and fully read back, every retrieval case passes, reports have the same semantic/profile/case fingerprints, and no zero-tolerance failure exists.

- [ ] **Step 5: Preserve evidence and handle the disposable index safely**

Retain the evaluation index until the user explicitly authorizes its exact deletion, or promote it to a named retained admission artifact if that is operationally cheaper. Record all external calls, request IDs, cost, index name, read-back counts, and evidence refs in `.agent/WORKING_STATE.md` without secrets.

### Task 7: Issue capability evidence and mark legal packages technically ready

**Files:**
- Modify: `tools/hk_v1_provider_admission.py`
- Modify: `tools/build_hk_legislation_rulebook.py`
- Modify: `tools/build_hk_cases_rulebook.py`
- Modify: `tools/build_hk_regulatory_rulebook.py`
- Modify generated package readiness members through those generators.
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: two passing provider-admission reports and exact read-back evidence.
- Produces: current capability profile refs and `READY` package status for Legislation, Cases, Main Board, and GEM.

- [ ] **Step 1: Add failing repeat-evidence tests**

```python
def test_capability_evidence_requires_two_matching_clean_runs() -> None:
    with pytest.raises(AdmissionError, match="REPEAT_RUN_MISMATCH"):
        issue_capability_evidence(run_one(), drifted_run_two())
```

- [ ] **Step 2: Implement evidence issuance**

Issue one immutable artifact per capability containing profile ref/fingerprint, allowed application/effect, environment, provider coordinates without secrets, evaluation refs, cost/quota, valid-from/until, and admission result. A mismatched repeat run, expired profile, incomplete read-back, or retained failure emits no current evidence.

- [ ] **Step 3: Regenerate package readiness from exact capability refs**

Legislation, Cases, Main, and GEM become `READY` only when their authentic source readiness and required semantic profile/evaluation refs both validate. A package not requiring a semantic call still binds the approved deterministic/model-allocation profile proving why no call is needed.

- [ ] **Step 4: Run focused and complete gates**

Run: `python3 -m pytest packages/processing/tests packages/promotion/tests packages/legal-desks/tests tools/tests/test_hk_v1_provider_admission.py -q`

Expected: all provider, evaluation, package-readiness, and strict-output tests pass.

Run: `python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: complete shipping gate passes.

- [ ] **Step 5: Stop at the checkpoint gate**

Record exact profile/evaluation/capability fingerprints and external effects in `.agent/WORKING_STATE.md`. Request explicit commit authorization before creating the Plan 6 checkpoint. Plan 7 may consume only these exact current capability refs.
