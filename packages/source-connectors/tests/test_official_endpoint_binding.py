"""Exact official endpoint locator binding tests."""

import pytest
from asklegal_source_connectors import (
    OfficialEndpointContract,
    bind_official_endpoint_locator,
    load_hk_legislation_source_register,
)


def _template(suffix: str) -> OfficialEndpointContract:
    register = load_hk_legislation_source_register()
    return next(endpoint for endpoint in register.endpoints if endpoint.url.endswith(suffix))


def test_hkel_pdf_locator_binds_without_authority_or_contract_drift() -> None:
    endpoint = _template("/{verified_copy_locator}.pdf")

    bound = bind_official_endpoint_locator(
        endpoint,
        placeholder="verified_copy_locator",
        locator="cap_1/2026-07-01/en",
    )

    assert bound.endpoint_id == endpoint.endpoint_id
    assert bound.endpoint_version == endpoint.version
    assert bound.url == "https://www.elegislation.gov.hk/hk/cap_1/2026-07-01/en.pdf"


def test_unicode_locator_is_canonically_percent_encoded() -> None:
    endpoint = _template("/{official_material_locator}")

    bound = bind_official_endpoint_locator(
        endpoint,
        placeholder="official_material_locator",
        locator="法令/决定.html",
    )

    assert bound.url == ("https://www.npc.gov.cn/%E6%B3%95%E4%BB%A4/%E5%86%B3%E5%AE%9A.html")


@pytest.mark.parametrize(
    "locator",
    [
        "../admin",
        "a/../admin",
        "/absolute",
        "trailing/",
        "double//segment",
        "https://evil.invalid/path",
        "item?secret=value",
        "item#fragment",
        "item\\child",
        "{other}",
    ],
)
def test_locator_cannot_escape_or_reinterpret_the_declared_path(locator: str) -> None:
    endpoint = _template("/{issued_artifact_locator}")

    with pytest.raises(ValueError, match="locator"):
        bind_official_endpoint_locator(
            endpoint,
            placeholder="issued_artifact_locator",
            locator=locator,
        )


def test_wrong_or_missing_template_fails_closed() -> None:
    register = load_hk_legislation_source_register()
    fixed = next(endpoint for endpoint in register.endpoints if "{" not in endpoint.url)
    template = _template("/{legal_item_locator}")

    with pytest.raises(ValueError, match="exactly the requested"):
        bind_official_endpoint_locator(
            template,
            placeholder="wrong_locator",
            locator="cap_1",
        )
    with pytest.raises(ValueError, match="exactly the requested"):
        bind_official_endpoint_locator(
            fixed,
            placeholder="legal_item_locator",
            locator="cap_1",
        )
