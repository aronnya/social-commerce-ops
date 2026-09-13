from fastapi.testclient import TestClient

from app.schemas import ProductCreate, ProductUpdate


def _demo_supplier(db_client: TestClient) -> int:
    response = db_client.post("/api/v1/suppliers", json={"name": "Demo Islamabad Supplier"})
    assert response.status_code == 201
    return response.json()["id"]


def test_create_product_rejects_empty_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/products",
        json={"supplier_id": 1, "name": ""},
    )
    assert response.status_code == 422


def test_create_product_rejects_whitespace_only_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/products",
        json={"supplier_id": 1, "name": "   "},
    )
    assert response.status_code == 422


def test_product_name_whitespace_is_trimmed() -> None:
    created = ProductCreate(supplier_id=1, name="   Blue Dress   ")
    assert created.name == "Blue Dress"

    updated = ProductUpdate(name="   Blue Dress   ")
    assert updated.name == "Blue Dress"


def test_create_product_rejects_negative_supplier_cost(client: TestClient) -> None:
    response = client.post(
        "/api/v1/products",
        json={"supplier_id": 1, "name": "Demo Shirt", "supplier_cost": "-1.00"},
    )
    assert response.status_code == 422


def test_create_product_rejects_negative_selling_price(client: TestClient) -> None:
    response = client.post(
        "/api/v1/products",
        json={"supplier_id": 1, "name": "Demo Shirt", "selling_price": "-1.00"},
    )
    assert response.status_code == 422


def test_product_requires_existing_supplier(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/products",
        json={"supplier_id": 999999, "name": "Demo Embroidered Shirt"},
    )
    assert response.status_code == 404


def test_create_list_filter_and_update_product(db_client: TestClient) -> None:
    supplier_id = _demo_supplier(db_client)
    other_supplier_id = _demo_supplier(db_client)

    created = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier_id,
            "name": "Demo Green Lawn Suit",
            "colour": "green",
            "size": "M",
            "style": "lawn-suit",
            "selling_price": "85.00",
        },
    )
    assert created.status_code == 201
    product = created.json()
    assert product["supplier_id"] == supplier_id
    assert float(product["selling_price"]) == 85.0

    db_client.post(
        "/api/v1/products",
        json={"supplier_id": other_supplier_id, "name": "Demo Other Catalogue Dress"},
    )

    filtered = db_client.get(f"/api/v1/products?supplier_id={supplier_id}")
    assert filtered.status_code == 200
    names = [item["name"] for item in filtered.json()]
    assert names == ["Demo Green Lawn Suit"]

    updated = db_client.patch(
        f"/api/v1/products/{product['id']}",
        json={"size": "L"},
    )
    assert updated.status_code == 200
    assert updated.json()["size"] == "L"


def test_get_missing_product_returns_404(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/products/999999")
    assert response.status_code == 404


def test_cannot_delete_product_with_enquiries(db_client: TestClient) -> None:
    supplier = db_client.post("/api/v1/suppliers", json={"name": "Demo Product Delete Supplier"})
    product = db_client.post(
        "/api/v1/products",
        json={"supplier_id": supplier.json()["id"], "name": "Demo Product Delete Dress"},
    )
    customer = db_client.post("/api/v1/customers", json={"name": "Demo Product Delete Customer"})
    product_id = product.json()["id"]
    enquiry = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer.json()["id"], "product_id": product_id},
    )
    assert enquiry.status_code == 201

    blocked = db_client.delete(f"/api/v1/products/{product_id}")
    assert blocked.status_code == 409
    still_there = db_client.get(f"/api/v1/products/{product_id}")
    assert still_there.status_code == 200
