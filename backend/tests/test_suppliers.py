from fastapi.testclient import TestClient


def test_create_supplier_rejects_empty_name(client: TestClient) -> None:
    response = client.post("/api/v1/suppliers", json={"name": ""})
    assert response.status_code == 422


def test_create_supplier_rejects_whitespace_only_name(client: TestClient) -> None:
    response = client.post("/api/v1/suppliers", json={"name": "   "})
    assert response.status_code == 422


def test_create_and_list_supplier(db_client: TestClient) -> None:
    created = db_client.post(
        "/api/v1/suppliers",
        json={"name": "Demo Karachi Supplier", "whatsapp": "+92000000000"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Demo Karachi Supplier"
    assert body["id"] >= 1

    listed = db_client.get("/api/v1/suppliers")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())


def test_get_missing_supplier_returns_404(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/suppliers/999999")
    assert response.status_code == 404


def test_update_supplier(db_client: TestClient) -> None:
    created = db_client.post("/api/v1/suppliers", json={"name": "Demo Lahore Supplier"})
    supplier_id = created.json()["id"]

    updated = db_client.patch(
        f"/api/v1/suppliers/{supplier_id}",
        json={"notes": "Synthetic test supplier only"},
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Synthetic test supplier only"


def test_cannot_delete_supplier_with_products(db_client: TestClient) -> None:
    supplier = db_client.post(
        "/api/v1/suppliers", json={"name": "Demo Supplier With Catalogue Item"}
    )
    supplier_id = supplier.json()["id"]
    product = db_client.post(
        "/api/v1/products",
        json={"supplier_id": supplier_id, "name": "Demo Lawn Suit"},
    )
    product_id = product.json()["id"]

    blocked = db_client.delete(f"/api/v1/suppliers/{supplier_id}")
    assert blocked.status_code == 409

    removed_product = db_client.delete(f"/api/v1/products/{product_id}")
    assert removed_product.status_code == 204

    allowed = db_client.delete(f"/api/v1/suppliers/{supplier_id}")
    assert allowed.status_code == 204
