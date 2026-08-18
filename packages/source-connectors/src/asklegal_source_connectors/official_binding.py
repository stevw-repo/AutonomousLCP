"""Safe item-specific binding for declared official endpoint templates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from .model import exact_text
from .official import OfficialEndpointContract

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_PATH_SEGMENT_SAFE = "-._~!$&'()*+,;=:@"


@dataclass(frozen=True, slots=True)
class BoundOfficialEndpoint:
    """One exact concrete locator bound to one versioned endpoint template."""

    endpoint_id: str
    endpoint_version: str
    placeholder: str
    locator: str
    url: str

    def __post_init__(self) -> None:
        for field in (
            "endpoint_id",
            "endpoint_version",
            "placeholder",
            "locator",
            "url",
        ):
            exact_text(getattr(self, field), field)
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("bound endpoint must remain one HTTPS URL")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("bound endpoint cannot contain credentials or a fragment")


def bind_official_endpoint_locator(
    endpoint: OfficialEndpointContract,
    *,
    placeholder: str,
    locator: str,
) -> BoundOfficialEndpoint:
    """Bind one declared path placeholder without permitting URL authority drift."""
    if type(endpoint) is not OfficialEndpointContract:
        raise TypeError("endpoint must be an exact OfficialEndpointContract")
    exact_placeholder = exact_text(placeholder, "placeholder")
    exact_locator = exact_text(locator, "locator")
    placeholders = tuple(_PLACEHOLDER.findall(endpoint.url))
    if placeholders != (exact_placeholder,):
        raise ValueError("endpoint must declare exactly the requested placeholder")
    if any(character in exact_locator for character in ("?", "#", "\\", "{", "}")):
        raise ValueError("locator contains a forbidden URL control character")
    if exact_locator.startswith("/") or exact_locator.endswith("/"):
        raise ValueError("locator must be one relative non-empty path")
    segments = exact_locator.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise ValueError("locator contains an empty or traversal segment")
    encoded_locator = "/".join(quote(segment, safe=_PATH_SEGMENT_SAFE) for segment in segments)
    resolved = endpoint.url.replace(f"{{{exact_placeholder}}}", encoded_locator)
    template_url = urlsplit(endpoint.url)
    resolved_url = urlsplit(resolved)
    if (
        resolved_url.scheme != template_url.scheme
        or resolved_url.hostname != template_url.hostname
        or resolved_url.port != template_url.port
        or resolved_url.username
        or resolved_url.password
        or resolved_url.fragment
    ):
        raise ValueError("locator binding changed the endpoint authority")
    return BoundOfficialEndpoint(
        endpoint.endpoint_id,
        endpoint.version,
        exact_placeholder,
        exact_locator,
        resolved,
    )
