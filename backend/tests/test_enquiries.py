from fastapi.testclient import TestClient


def _catalogue(db_client: TestClient) -> tuple[int, int]:
    supplier = db_client.post("/api/v1/suppliers", json={"name": "Demo Enquiry API Supplier"})
    assert supplier.status_code == 201
    product = db_client.post(
        "/api/v1/products",
        json={"supplier_id": supplier.json()["id"], "name": "Demo Enquiry API Dress"},
    )
    assert product.status_code == 201
    customer = db_client.post("/api/v1/customers", json={"name": "Demo Enquiry API Customer"})
    assert customer.status_code == 201
    return customer.json()["id"], product.json()["id"]


def test_create_enquiry_returns_201(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    response = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] == customer_id
    assert body["product_id"] == product_id
    assert body["quantity"] == 1
    assert body["outcome"] is None


def test_create_enquiry_missing_customer_returns_404(db_client: TestClient) -> None:
    _, product_id = _catalogue(db_client)
    response = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": 999999, "product_id": product_id},
    )
    assert response.status_code == 404


def test_create_enquiry_missing_product_returns_404(db_client: TestClient) -> None:
    customer_id, _ = _catalogue(db_client)
    response = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": 999999},
    )
    assert response.status_code == 404


def test_get_enquiry_returns_200(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    response = db_client.get(f"/api/v1/enquiries/{created.json()['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]


def test_get_missing_enquiry_returns_404(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/enquiries/999999")
    assert response.status_code == 404


def test_patch_enquiry_outcome_returns_200(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    response = db_client.patch(
        f"/api/v1/enquiries/{created.json()['id']}",
        json={"outcome": "TOO_EXPENSIVE"},
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "TOO_EXPENSIVE"


def test_patch_enquiry_outcome_back_to_null_returns_200(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "outcome": "NOT_INTERESTED",
        },
    )
    response = db_client.patch(
        f"/api/v1/enquiries/{created.json()['id']}",
        json={"outcome": None},
    )
    assert response.status_code == 200
    assert response.json()["outcome"] is None


def test_patch_enquiry_rejects_customer_and_product_id(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    enquiry_id = created.json()["id"]
    customer = db_client.patch(f"/api/v1/enquiries/{enquiry_id}", json={"customer_id": 1})
    product = db_client.patch(f"/api/v1/enquiries/{enquiry_id}", json={"product_id": 1})
    assert customer.status_code == 422
    assert product.status_code == 422


def test_delete_enquiry_returns_204(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    deleted = db_client.delete(f"/api/v1/enquiries/{created.json()['id']}")
    assert deleted.status_code == 204
    missing = db_client.get(f"/api/v1/enquiries/{created.json()['id']}")
    assert missing.status_code == 404


def test_list_enquiries_filter_by_product_id(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    other_product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": db_client.get(f"/api/v1/products/{product_id}").json()["supplier_id"],
            "name": "Demo Other Enquiry Dress",
        },
    )
    db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": other_product.json()["id"]},
    )
    listed = db_client.get(f"/api/v1/enquiries?product_id={product_id}")
    assert listed.status_code == 200
    assert [item["product_id"] for item in listed.json()] == [product_id]


def test_list_enquiries_filter_by_customer_id(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    other_customer = db_client.post("/api/v1/customers", json={"name": "Demo Other Enquiry Customer"})
    db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": other_customer.json()["id"], "product_id": product_id},
    )
    listed = db_client.get(f"/api/v1/enquiries?customer_id={customer_id}")
    assert listed.status_code == 200
    assert [item["customer_id"] for item in listed.json()] == [customer_id]


def test_list_enquiries_filter_by_outcome(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "outcome": "TOO_EXPENSIVE",
        },
    )
    db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id, "outcome": "WRONG_SIZE"},
    )
    listed = db_client.get("/api/v1/enquiries?outcome=TOO_EXPENSIVE")
    assert listed.status_code == 200
    assert [item["outcome"] for item in listed.json()] == ["TOO_EXPENSIVE"]


def test_list_enquiries_open_only(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    open_one = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "outcome": "NOT_INTERESTED",
        },
    )
    listed = db_client.get("/api/v1/enquiries?open_only=true")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [open_one.json()["id"]]
    assert all(item["outcome"] is None for item in listed.json())


def test_list_enquiries_rejects_outcome_with_open_only(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/enquiries?outcome=TOO_EXPENSIVE&open_only=true")
    assert response.status_code == 422


def test_list_enquiries_rejects_invalid_outcome(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/enquiries?outcome=LOST")
    assert response.status_code == 422
