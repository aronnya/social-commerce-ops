from fastapi.testclient import TestClient

from app.schemas import CustomerCreate, CustomerUpdate


def test_create_customer_rejects_empty_name(client: TestClient) -> None:
    response = client.post("/api/v1/customers", json={"name": ""})
    assert response.status_code == 422


def test_create_customer_rejects_whitespace_only_name(client: TestClient) -> None:
    response = client.post("/api/v1/customers", json={"name": "   "})
    assert response.status_code == 422


def test_customer_name_whitespace_is_trimmed() -> None:
    created = CustomerCreate(name="   Amina   ")
    assert created.name == "Amina"

    updated = CustomerUpdate(name="   Amina   ")
    assert updated.name == "Amina"


def test_create_update_and_delete_customer(db_client: TestClient) -> None:
    created = db_client.post(
        "/api/v1/customers",
        json={
            "name": "Demo Customer Amina",
            "facebook_name": "amina.demo.not.real",
            "phone": "+353000000000",
        },
    )
    assert created.status_code == 201
    customer_id = created.json()["id"]
    assert created.json()["name"] == "Demo Customer Amina"

    updated = db_client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"notes": "Synthetic fixture; not a real person"},
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Synthetic fixture; not a real person"

    listed = db_client.get("/api/v1/customers")
    assert any(item["id"] == customer_id for item in listed.json())

    deleted = db_client.delete(f"/api/v1/customers/{customer_id}")
    assert deleted.status_code == 204

    missing = db_client.get(f"/api/v1/customers/{customer_id}")
    assert missing.status_code == 404


def test_get_missing_customer_returns_404(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/customers/999999")
    assert response.status_code == 404


def test_reject_blank_customer_name(db_client: TestClient) -> None:
    response = db_client.post("/api/v1/customers", json={"name": ""})
    assert response.status_code == 422
