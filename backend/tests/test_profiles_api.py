from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import CRITERIA


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "name": "Mon profil",
        "threshold": 70,
        "weights": dict.fromkeys(CRITERIA, 1.0),
    } | overrides


def test_default_profiles_are_seeded(client: TestClient) -> None:
    profiles = client.get("/api/profiles").json()
    names = [p["name"] for p in profiles]
    assert set(names) == {
        "GTA 6 — Viral",
        "GTA 6 — Humour",
        "GTA 6 — Action",
        "Gaming — Immersion",
        "Gaming — Histoire",
    }
    assert sum(p["is_default"] for p in profiles) == 1
    assert profiles[0]["is_default"] and profiles[0]["name"] == "GTA 6 — Viral"
    assert all(set(p["weights"]) == set(CRITERIA) for p in profiles)
    assert all(p["min_duration"] == 61 and p["max_duration"] == 180 for p in profiles)
    assert client.get("/api/criteria").json()[0] == {"key": "hook", "label": "Force de l'accroche"}


def test_profile_crud_and_duplicate(client: TestClient) -> None:
    r = client.post("/api/profiles", json=_payload(weights={"hook": 2.0}))
    assert r.status_code == 201
    created = r.json()
    assert created["weights"]["hook"] == 2.0 and created["weights"]["retention"] == 1.0

    r = client.put(f"/api/profiles/{created['id']}", json=_payload(name="Renommé", threshold=50))
    assert r.json()["name"] == "Renommé" and r.json()["threshold"] == 50

    dup = client.post(f"/api/profiles/{created['id']}/duplicate").json()
    assert dup["name"] == "Renommé (copie)" and not dup["is_default"]
    dup2 = client.post(f"/api/profiles/{created['id']}/duplicate").json()
    assert dup2["name"] == "Renommé (copie) 2"

    assert client.post("/api/profiles", json=_payload(name="Renommé")).status_code == 409
    assert client.delete(f"/api/profiles/{dup['id']}").status_code == 204
    assert client.get(f"/api/profiles/{dup['id']}").status_code == 404


def test_default_profile_switch_and_protection(client: TestClient) -> None:
    created = client.post("/api/profiles", json=_payload(is_default=True)).json()
    profiles = client.get("/api/profiles").json()
    assert [p["id"] for p in profiles if p["is_default"]] == [created["id"]]
    assert client.delete(f"/api/profiles/{created['id']}").status_code == 409


def test_profile_validation(client: TestClient) -> None:
    assert client.post("/api/profiles", json=_payload(weights={"inconnu": 1})).status_code == 422
    assert client.post("/api/profiles", json=_payload(weights={"hook": -1})).status_code == 422
    zero = dict.fromkeys(CRITERIA, 0.0)
    assert client.post("/api/profiles", json=_payload(weights=zero)).status_code == 422
    assert client.post("/api/profiles", json=_payload(min_duration=60)).status_code == 422
    assert client.post("/api/profiles", json=_payload(max_duration=181)).status_code == 422
    r = client.post("/api/profiles", json=_payload(min_duration=150, max_duration=100))
    assert r.status_code == 422
    assert client.post("/api/profiles", json=_payload(threshold=101)).status_code == 422
