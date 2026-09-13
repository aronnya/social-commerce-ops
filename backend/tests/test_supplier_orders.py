from fastapi.testclient import TestClient


def _catalogue(
    db_client: TestClient,
    *,
    supplier_name: str = "Demo SO API Supplier",
    product_name: str = "Demo SO API Dress",
    supplier_cost: str = "40.00",
) -> tuple[int, int, int]:
    supplier = db_client.post("/api/v1/suppliers", json={"name": supplier_name})
    assert supplier.status_code == 201
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": product_name,
            "supplier_cost": supplier_cost,
            "selling_price": "85.00",
        },
    )
    assert product.status_code == 201
    customer = db_client.post(
        "/api/v1/customers", json={"name": f"Demo SO API Customer {supplier_name}"}
    )
    assert customer.status_code == 201
    return supplier.json()["id"], product.json()["id"], customer.json()["id"]


def _preorder(db_client: TestClient, customer_id: int, product_id: int, quantity: int = 1) -> dict:
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id, "quantity": quantity},
    )
    assert created.status_code == 201
    return created.json()


def test_generate_draft_one_preorder(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    preorder = _preorder(db_client, customer_id, product_id, quantity=2)
    response = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["supplier_id"] == supplier_id
    assert len(body["lines"]) == 1
    assert body["lines"][0]["product_id"] == product_id
    assert body["lines"][0]["quantity"] == 2
    assert float(body["lines"][0]["unit_cost"]) == 40.0
    assert len(body["lines"][0]["allocations"]) == 1
    assert body["lines"][0]["allocations"][0]["preorder_id"] == preorder["id"]
    assert body["lines"][0]["allocations"][0]["quantity"] == 2
    assert db_client.get(f"/api/v1/preorders/{preorder['id']}").json()["status"] == "CONFIRMED"


def test_generate_draft_consolidates_and_splits_products(db_client: TestClient) -> None:
    supplier_id, product_x, customer_id = _catalogue(db_client)
    product_y = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier_id,
            "name": "Demo SO API Dress Y",
            "supplier_cost": "15.00",
            "selling_price": "50.00",
        },
    )
    a = _preorder(db_client, customer_id, product_x, quantity=2)
    b = _preorder(db_client, customer_id, product_x, quantity=1)
    c = _preorder(db_client, customer_id, product_y.json()["id"], quantity=1)
    response = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [a["id"], b["id"], c["id"]]},
    )
    assert response.status_code == 201
    lines = {line["product_id"]: line for line in response.json()["lines"]}
    assert lines[product_x]["quantity"] == 3
    assert {item["preorder_id"] for item in lines[product_x]["allocations"]} == {a["id"], b["id"]}
    assert lines[product_y.json()["id"]]["quantity"] == 1


def test_generate_draft_error_cases(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    other_supplier, other_product, other_customer = _catalogue(
        db_client, supplier_name="Demo SO API Other"
    )
    preorder = _preorder(db_client, customer_id, product_id)
    other = _preorder(db_client, other_customer, other_product)
    assert (
        db_client.post(
            "/api/v1/supplier-orders/generate-draft",
            json={"supplier_id": 999999, "preorder_ids": [preorder["id"]]},
        ).status_code
        == 404
    )
    assert (
        db_client.post(
            "/api/v1/supplier-orders/generate-draft",
            json={"supplier_id": supplier_id, "preorder_ids": [999999]},
        ).status_code
        == 404
    )
    assert (
        db_client.post(
            "/api/v1/supplier-orders/generate-draft",
            json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"], other["id"]]},
        ).status_code
        == 409
    )
    cancelled = _preorder(db_client, customer_id, product_id)
    db_client.post(
        f"/api/v1/preorders/{cancelled['id']}/transitions", json={"status": "CANCELLED"}
    )
    assert (
        db_client.post(
            "/api/v1/supplier-orders/generate-draft",
            json={"supplier_id": supplier_id, "preorder_ids": [cancelled["id"]]},
        ).status_code
        == 409
    )
    first = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    assert first.status_code == 201
    assert (
        db_client.post(
            "/api/v1/supplier-orders/generate-draft",
            json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
        ).status_code
        == 409
    )


def test_generate_draft_omitted_ids(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    other_supplier, other_product, other_customer = _catalogue(
        db_client, supplier_name="Demo SO API Skip"
    )
    mine = _preorder(db_client, customer_id, product_id)
    _preorder(db_client, other_customer, other_product)
    response = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id},
    )
    assert response.status_code == 201
    alloc_ids = {
        item["preorder_id"]
        for line in response.json()["lines"]
        for item in line["allocations"]
    }
    assert alloc_ids == {mine["id"]}
    empty_supplier = db_client.post("/api/v1/suppliers", json={"name": "Demo SO API Empty"})
    empty_product = db_client.post(
        "/api/v1/products",
        json={"supplier_id": empty_supplier.json()["id"], "name": "Demo Unused Dress"},
    )
    assert empty_product.status_code == 201
    empty = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": empty_supplier.json()["id"]},
    )
    assert empty.status_code == 409


def test_list_and_get_supplier_orders(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    other_supplier, other_product, other_customer = _catalogue(
        db_client, supplier_name="Demo SO API List"
    )
    mine = _preorder(db_client, customer_id, product_id)
    other = _preorder(db_client, other_customer, other_product)
    first = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [mine["id"]]},
    )
    second = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": other_supplier, "preorder_ids": [other["id"]]},
    )
    listed = db_client.get("/api/v1/supplier-orders")
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} >= {first.json()["id"], second.json()["id"]}
    filtered = db_client.get(f"/api/v1/supplier-orders?supplier_id={supplier_id}")
    assert [item["id"] for item in filtered.json()] == [first.json()["id"]]
    by_status = db_client.get("/api/v1/supplier-orders?status=DRAFT")
    assert {item["id"] for item in by_status.json()} >= {first.json()["id"], second.json()["id"]}
    fetched = db_client.get(f"/api/v1/supplier-orders/{first.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == first.json()["id"]
    assert db_client.get("/api/v1/supplier-orders/999999").status_code == 404


def test_patch_supplier_order_notes(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    preorder = _preorder(db_client, customer_id, product_id)
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    order_id = draft.json()["id"]
    patched = db_client.patch(
        f"/api/v1/supplier-orders/{order_id}", json={"notes": "check sizes"}
    )
    assert patched.status_code == 200
    assert patched.json()["notes"] == "check sizes"
    assert (
        db_client.patch(
            f"/api/v1/supplier-orders/{order_id}", json={"status": "PLACED"}
        ).status_code
        == 422
    )
    assert (
        db_client.patch(
            f"/api/v1/supplier-orders/{order_id}", json={"supplier_id": supplier_id}
        ).status_code
        == 422
    )


def test_delete_draft_and_regenerate(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    preorder = _preorder(db_client, customer_id, product_id)
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    deleted = db_client.delete(f"/api/v1/supplier-orders/{draft.json()['id']}")
    assert deleted.status_code == 204
    assert db_client.get(f"/api/v1/preorders/{preorder['id']}").json()["status"] == "CONFIRMED"
    again = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    assert again.status_code == 201
    placed = db_client.post(f"/api/v1/supplier-orders/{again.json()['id']}/place")
    assert placed.status_code == 200
    assert db_client.delete(f"/api/v1/supplier-orders/{placed.json()['id']}").status_code == 409


def test_place_supplier_order(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    preorder = _preorder(db_client, customer_id, product_id)
    payment = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "10.00", "method": "REVOLUT"},
    )
    assert payment.status_code == 201
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    placed = db_client.post(f"/api/v1/supplier-orders/{draft.json()['id']}/place")
    assert placed.status_code == 200
    assert placed.json()["status"] == "PLACED"
    assert placed.json()["placed_at"] is not None
    fetched = db_client.get(f"/api/v1/preorders/{preorder['id']}")
    assert fetched.json()["status"] == "ORDERED_FROM_SUPPLIER"
    assert fetched.json()["payment_summary"]["status"] == "PARTIALLY_PAID"
    payments = db_client.get(f"/api/v1/preorders/{preorder['id']}/payments")
    assert [item["id"] for item in payments.json()] == [payment.json()["id"]]
    assert (
        db_client.post(f"/api/v1/supplier-orders/{placed.json()['id']}/place").status_code
        == 409
    )


def test_supplier_order_transitions(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client)
    preorder = _preorder(db_client, customer_id, product_id)
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    order_id = draft.json()["id"]
    assert (
        db_client.post(
            f"/api/v1/supplier-orders/{order_id}/transitions",
            json={"status": "PLACED"},
        ).status_code
        == 422
    )
    placed = db_client.post(f"/api/v1/supplier-orders/{order_id}/place")
    assert placed.status_code == 200
    skip = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "DISPATCHED"},
    )
    assert skip.status_code == 409
    confirmed = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"
    same = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "CONFIRMED"},
    )
    assert same.status_code == 409
    dispatched = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "DISPATCHED"},
    )
    assert dispatched.json()["status"] == "DISPATCHED"
    arrived = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "ARRIVED"},
    )
    assert arrived.json()["status"] == "ARRIVED"
    reverse = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "DISPATCHED"},
    )
    assert reverse.status_code == 409
    reconciled = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/transitions",
        json={"status": "RECONCILED"},
    )
    assert reconciled.json()["status"] == "RECONCILED"
    assert (
        db_client.get(f"/api/v1/preorders/{preorder['id']}").json()["status"]
        == "ORDERED_FROM_SUPPLIER"
    )
    assert db_client.get("/api/v1/supplier-orders/999999").status_code == 404
    assert (
        db_client.post(
            "/api/v1/supplier-orders/999999/transitions",
            json={"status": "CONFIRMED"},
        ).status_code
        == 404
    )
