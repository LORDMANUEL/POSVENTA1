import pytest


@pytest.mark.parametrize("module_key", ["payments", "fiscal", "music", "visual"])
def test_external_modules_cannot_be_enabled_without_certification(
    client,
    owner_headers,
    module_key: str,
) -> None:
    before = client.get("/admin/modules", headers=owner_headers)
    assert before.status_code == 200
    row = next(item for item in before.json() if item["key"] == module_key)
    assert row["enabled"] is False
    assert row["external_gate"]

    enabled = client.put(
        f"/admin/modules/{module_key}",
        params={"enabled": "true"},
        headers=owner_headers,
    )
    assert enabled.status_code == 409, enabled.text
    assert "certific" in str(enabled.json()["detail"]).lower()

    after = client.get("/admin/modules", headers=owner_headers)
    assert after.status_code == 200
    row = next(item for item in after.json() if item["key"] == module_key)
    assert row["enabled"] is False
