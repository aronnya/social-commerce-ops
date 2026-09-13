from fastapi.testclient import TestClient


def _catalogue(db_client: TestClient) -> tuple[int, int]:
    supplier = db_client.post("/api/v1/suppliers", json={"name": "Demo Preorder API Supplier"})
    assert supplier.status_code == 201
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": "Demo Preorder API Dress",
            "selling_price": "85.00",
        },
    )
    assert product.status_code == 201
    customer = db_client.post("/api/v1/customers", json={"name": "Demo Preorder API Customer"})
    assert customer.status_code == 201
    return customer.json()["id"], product.json()["id"]


def test_create_walk_in_preorder_returns_201(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    response = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "CONFIRMED"
    assert body["enquiry_id"] is None
    assert float(body["agreed_price"]) == 85.0


def test_create_preorder_from_enquiry(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    enquiry = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id, "quantity": 2},
    )
    created = db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquiry_id": enquiry.json()["id"],
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "CONFIRMED"
    assert created.json()["quantity"] == 2
    listed = db_client.get(f"/api/v1/enquiries/{enquiry.json()['id']}")
    assert listed.json()["outcome"] == "PREORDERED"


def test_create_preorder_missing_ids_return_404(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    assert (
        db_client.post(
            "/api/v1/preorders",
            json={"customer_id": 999999, "product_id": product_id},
        ).status_code
        == 404
    )
    assert (
        db_client.post(
            "/api/v1/preorders",
            json={"customer_id": customer_id, "product_id": 999999},
        ).status_code
        == 404
    )
    assert (
        db_client.post(
            "/api/v1/preorders",
            json={
                "customer_id": customer_id,
                "product_id": product_id,
                "enquiry_id": 999999,
            },
        ).status_code
        == 404
    )


def test_create_preorder_enquiry_mismatch_and_duplicate(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    other = db_client.post("/api/v1/customers", json={"name": "Demo Other Preorder API Customer"})
    enquiry = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    mismatch = db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": other.json()["id"],
            "product_id": product_id,
            "enquiry_id": enquiry.json()["id"],
        },
    )
    assert mismatch.status_code == 409
    first = db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquiry_id": enquiry.json()["id"],
        },
    )
    assert first.status_code == 201
    duplicate = db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquiry_id": enquiry.json()["id"],
        },
    )
    assert duplicate.status_code == 409


def test_create_preorder_validation(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    assert (
        db_client.post(
            "/api/v1/preorders",
            json={
                "customer_id": customer_id,
                "product_id": product_id,
                "status": "CONFIRMED",
            },
        ).status_code
        == 422
    )
    assert (
        db_client.post(
            "/api/v1/preorders",
            json={"customer_id": customer_id, "product_id": product_id, "quantity": 0},
        ).status_code
        == 422
    )
    assert (
        db_client.post(
            "/api/v1/preorders",
            json={
                "customer_id": customer_id,
                "product_id": product_id,
                "agreed_price": "-1.00",
            },
        ).status_code
        == 422
    )


def test_get_and_list_preorders(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    other = db_client.post("/api/v1/customers", json={"name": "Demo List Preorder Customer"})
    enquiry = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    linked = db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquiry_id": enquiry.json()["id"],
        },
    )
    walk_in = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": other.json()["id"], "product_id": product_id},
    )
    fetched = db_client.get(f"/api/v1/preorders/{linked.json()['id']}")
    assert fetched.status_code == 200
    assert db_client.get("/api/v1/preorders/999999").status_code == 404

    by_customer = db_client.get(f"/api/v1/preorders?customer_id={customer_id}")
    assert [item["id"] for item in by_customer.json()] == [linked.json()["id"]]
    by_product = db_client.get(f"/api/v1/preorders?product_id={product_id}")
    assert len(by_product.json()) == 2
    by_status = db_client.get("/api/v1/preorders?status=CONFIRMED")
    assert {item["id"] for item in by_status.json()} == {
        linked.json()["id"],
        walk_in.json()["id"],
    }
    by_enquiry = db_client.get(f"/api/v1/preorders?enquiry_id={enquiry.json()['id']}")
    assert [item["id"] for item in by_enquiry.json()] == [linked.json()["id"]]
    assert db_client.get("/api/v1/preorders?status=PAID").status_code == 422


def test_patch_preorder(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    preorder_id = created.json()["id"]
    notes = db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"notes": "hold size"})
    assert notes.status_code == 200
    assert notes.json()["notes"] == "hold size"
    quantity = db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"quantity": 2})
    assert quantity.status_code == 200
    assert quantity.json()["quantity"] == 2
    price = db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"agreed_price": "90.00"})
    assert price.status_code == 200
    assert float(price.json()["agreed_price"]) == 90.0

    assert (
        db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"customer_id": 1}).status_code
        == 422
    )
    assert (
        db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"product_id": 1}).status_code
        == 422
    )
    assert (
        db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"enquiry_id": 1}).status_code
        == 422
    )
    assert (
        db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"status": "ARRIVED"}).status_code
        == 422
    )

    db_client.post(f"/api/v1/preorders/{preorder_id}/transitions", json={"status": "CANCELLED"})
    blocked = db_client.patch(f"/api/v1/preorders/{preorder_id}", json={"quantity": 5})
    assert blocked.status_code == 409
    blocked_price = db_client.patch(
        f"/api/v1/preorders/{preorder_id}", json={"agreed_price": "1.00"}
    )
    assert blocked_price.status_code == 409


def test_preorder_transitions(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    preorder_id = created.json()["id"]
    blocked = db_client.post(
        f"/api/v1/preorders/{preorder_id}/transitions",
        json={"status": "ORDERED_FROM_SUPPLIER"},
    )
    assert blocked.status_code == 409

    supplier_id = db_client.get(f"/api/v1/products/{product_id}").json()["supplier_id"]
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder_id]},
    )
    assert draft.status_code == 201
    placed = db_client.post(f"/api/v1/supplier-orders/{draft.json()['id']}/place")
    assert placed.status_code == 200
    assert (
        db_client.get(f"/api/v1/preorders/{preorder_id}").json()["status"]
        == "ORDERED_FROM_SUPPLIER"
    )
    for status in (
        "ARRIVED",
        "READY_FOR_CUSTOMER",
        "FULFILLED",
    ):
        response = db_client.post(
            f"/api/v1/preorders/{preorder_id}/transitions",
            json={"status": status},
        )
        assert response.status_code == 200
        assert response.json()["status"] == status

    cancelled = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    cancel = db_client.post(
        f"/api/v1/preorders/{cancelled.json()['id']}/transitions",
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    skip = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    illegal = db_client.post(
        f"/api/v1/preorders/{skip.json()['id']}/transitions",
        json={"status": "ARRIVED"},
    )
    assert illegal.status_code == 409
    same = db_client.post(
        f"/api/v1/preorders/{skip.json()['id']}/transitions",
        json={"status": "CONFIRMED"},
    )
    assert same.status_code == 409
    assert (
        db_client.post(
            "/api/v1/preorders/999999/transitions",
            json={"status": "CANCELLED"},
        ).status_code
        == 404
    )


def test_cannot_delete_customer_or_product_with_preorder(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client)
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    assert created.status_code == 201
    assert db_client.delete(f"/api/v1/customers/{customer_id}").status_code == 409
    assert db_client.get(f"/api/v1/customers/{customer_id}").status_code == 200
    assert db_client.delete(f"/api/v1/products/{product_id}").status_code == 409
    assert db_client.get(f"/api/v1/products/{product_id}").status_code == 200
