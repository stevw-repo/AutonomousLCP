"""Deterministic no-network Watcher and Scraper reference connector."""

from __future__ import annotations

from .admission import ResponseAdmissionPolicy, admit_response
from .model import (
    AcquisitionArtifact,
    ConnectorRequest,
    EndpointContract,
    RegisteredSource,
    ScraperResult,
    ScraperResultCode,
    SourcePolicyState,
    SourceRegistry,
    SyntheticPage,
    SyntheticResponse,
    WatcherResult,
    WatcherResultCode,
)


class SyntheticConnector:
    """A scripted local connector that cannot access a network or model."""

    def __init__(
        self,
        registry: SourceRegistry,
        *,
        admission_policy: ResponseAdmissionPolicy | None = None,
    ) -> None:
        """Bind connector behavior to one exact synthetic source registry."""
        if type(registry) is not SourceRegistry:
            raise TypeError("registry must be an exact SourceRegistry")
        self.registry = registry
        self.admission_policy = admission_policy or ResponseAdmissionPolicy()

    def watch(
        self,
        request: ConnectorRequest,
        responses: tuple[SyntheticResponse, ...],
    ) -> WatcherResult:
        """Evaluate bounded scripted responses into exactly one Watcher result."""
        _source, endpoint = self._admit_request(request)
        if not responses:
            raise ValueError("synthetic Watcher requires at least one response")
        artifacts: list[AcquisitionArtifact] = []
        attempts = 0
        for response in responses[: request.retry_profile.attempt_ceiling]:
            attempts += 1
            classification = admit_response(response, endpoint, self.admission_policy)
            artifacts.append(AcquisitionArtifact("WATCHER_ATTEMPT", response, classification))
            if self._contract_drift(response, endpoint):
                return WatcherResult(
                    WatcherResultCode.SOURCE_CONTRACT_CHANGED,
                    tuple(artifacts),
                    endpoint.allowed_path_prefix,
                    attempts,
                )
            if not classification.admitted:
                return WatcherResult(
                    WatcherResultCode.UNSAFE_RESPONSE,
                    tuple(artifacts),
                    endpoint.allowed_path_prefix,
                    attempts,
                )
            if response.authentication_failed:
                return WatcherResult(
                    WatcherResultCode.SOURCE_CONTRACT_CHANGED,
                    tuple(artifacts),
                    endpoint.allowed_path_prefix,
                    attempts,
                )
            if response.transient:
                continue
            if response.status_code == 304:
                code = (
                    WatcherResultCode.SUPPORTED_NO_CHANGE
                    if endpoint.http_304_proves_no_change
                    else WatcherResultCode.INCOMPLETE_OBSERVATION
                )
            elif response.status_code != 200:
                code = WatcherResultCode.SOURCE_CONTRACT_CHANGED
            elif response.signal == request.prior_signal:
                code = (
                    WatcherResultCode.SUPPORTED_NO_CHANGE
                    if endpoint.equal_signal_proves_no_change
                    else WatcherResultCode.INCOMPLETE_OBSERVATION
                )
            else:
                code = WatcherResultCode.POSSIBLE_CHANGE
            return WatcherResult(code, tuple(artifacts), endpoint.allowed_path_prefix, attempts)
        return WatcherResult(
            WatcherResultCode.SOURCE_UNAVAILABLE,
            tuple(artifacts),
            endpoint.allowed_path_prefix,
            attempts,
        )

    def scrape(
        self,
        request: ConnectorRequest,
        attempts: tuple[tuple[SyntheticPage, ...], ...],
    ) -> ScraperResult:
        """Prove one stable, complete inventory or fail closed after one restart."""
        _source, endpoint = self._admit_request(request)
        if not attempts:
            raise ValueError("synthetic Scraper requires at least one attempt")
        all_artifacts: list[AcquisitionArtifact] = []
        attempt_count = 0
        restart_count = 0
        last_members: tuple[str, ...] = ()
        last_cursors: tuple[str, ...] = ()
        last_total = 0
        for pages in attempts[: request.retry_profile.attempt_ceiling]:
            attempt_count += 1
            if not pages:
                continue
            generations: set[str] = set()
            members: list[str] = []
            cursors: list[str] = []
            unsafe = False
            contract_changed = False
            for index, page in enumerate(pages):
                classification = admit_response(page.response, endpoint, self.admission_policy)
                all_artifacts.append(
                    AcquisitionArtifact(f"SCRAPER_PAGE_{index + 1}", page.response, classification)
                )
                if self._contract_drift(page.response, endpoint):
                    contract_changed = True
                elif not classification.admitted:
                    unsafe = True
                if page.response.authentication_failed or page.response.status_code != 200:
                    contract_changed = contract_changed or not page.response.transient
                generations.add(page.inventory_generation)
                cursors.append(page.cursor)
                members.extend(page.member_ids)
                last_total = page.declared_total
            last_members = tuple(members)
            last_cursors = tuple(cursors)
            if unsafe:
                return ScraperResult(
                    ScraperResultCode.UNSAFE_RESPONSE,
                    tuple(all_artifacts),
                    last_members,
                    last_cursors,
                    last_total,
                    restart_count,
                    attempt_count,
                )
            if contract_changed:
                return ScraperResult(
                    ScraperResultCode.SOURCE_CONTRACT_CHANGED,
                    tuple(all_artifacts),
                    last_members,
                    last_cursors,
                    last_total,
                    restart_count,
                    attempt_count,
                )
            if any(page.response.transient for page in pages):
                continue
            if len(generations) != 1:
                restart_count += 1
                if restart_count < len(attempts):
                    continue
                return ScraperResult(
                    ScraperResultCode.PARTIAL_CAPTURE,
                    tuple(all_artifacts),
                    last_members,
                    last_cursors,
                    last_total,
                    restart_count,
                    attempt_count,
                )
            complete = self._inventory_complete(pages, endpoint, members)
            if not complete:
                code = ScraperResultCode.PARTIAL_CAPTURE
            elif all(page.response.signal == request.prior_signal for page in pages):
                code = ScraperResultCode.SUPPORTED_NO_CHANGE_AFTER_CAPTURE
            else:
                code = ScraperResultCode.SNAPSHOT_PRESERVED
            return ScraperResult(
                code,
                tuple(all_artifacts),
                last_members,
                last_cursors,
                last_total,
                restart_count,
                attempt_count,
            )
        return ScraperResult(
            ScraperResultCode.SOURCE_UNAVAILABLE,
            tuple(all_artifacts),
            last_members,
            last_cursors,
            last_total,
            restart_count,
            attempt_count,
        )

    def _admit_request(
        self,
        request: ConnectorRequest,
    ) -> tuple[RegisteredSource, EndpointContract]:
        if type(request) is not ConnectorRequest:
            raise TypeError("request must be an exact ConnectorRequest")
        source, endpoint = self.registry.resolve(
            request.source_id,
            request.source_version,
            request.endpoint_id,
            request.endpoint_version,
        )
        if source.policy_state is not SourcePolicyState.CONFIGURED:
            raise PermissionError("source authorization is not configured")
        if source.authorization_expires_at < request.observation_cutoff:
            raise PermissionError("source authorization is expired")
        if (
            request.rulebook_id != endpoint.rulebook_id
            or request.rulebook_version != endpoint.rulebook_version
        ):
            raise LookupError("request rulebook does not match endpoint contract")
        if request.method not in endpoint.methods:
            raise PermissionError("request method is outside the source contract")
        return source, endpoint

    @staticmethod
    def _contract_drift(response: SyntheticResponse, endpoint: EndpointContract) -> bool:
        return (
            response.host != endpoint.allowed_host
            or not response.path.startswith(endpoint.allowed_path_prefix)
            or response.redirect_host not in endpoint.redirect_hosts
            or response.media_type not in endpoint.media_types
        )

    @staticmethod
    def _inventory_complete(
        pages: tuple[SyntheticPage, ...],
        endpoint: EndpointContract,
        members: list[str],
    ) -> bool:
        if len(pages) > endpoint.max_pages or len(members) > endpoint.max_items:
            return False
        if len(set(members)) != len(members):
            return False
        declared_totals = {page.declared_total for page in pages}
        if len(declared_totals) != 1 or next(iter(declared_totals)) != len(members):
            return False
        for index, page in enumerate(pages):
            expected_next = "END" if index == len(pages) - 1 else pages[index + 1].cursor
            if page.next_cursor != expected_next:
                return False
        return not endpoint.complete_inventory_required or bool(pages)
