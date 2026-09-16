from fastapi.testclient import TestClient


def _catalogue(
    db_client: TestClient,
    *,
    supplier_name: str = "Demo Recon API Supplier",
    product_name: str = "Demo Recon API Dress",
) -> tuple[int, int, int]:
    supplier = db_client.post("/api/v1/suppliers", json={"name": supplier_name})
    assert supplier.status_code == 201
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": product_name,
            "supplier_cost": "40.00",
            "selling_price": "85.00",
        },
    )
    assert product.status_code == 201
    customer = db_client.post(
        "/api/v1/customers", json={"name": f"Demo Recon API Customer {supplier_name}"}
    )
    assert customer.status_code == 201
    return supplier.json()["id"], product.json()["id"], customer.json()["id"]


def _preorder(db_client: TestClient, customer_id: int, product_id: int, quantity: int) -> dict:
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id, "quantity": quantity},
    )
    assert created.status_code == 201
    return created.json()


def _arrived_order(db_client: TestClient, supplier_id: int, preorder_ids: list[int]) -> dict:
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": preorder_ids},
    )
    assert draft.status_code == 201
    order_id = draft.json()["id"]
    assert db_client.post(f"/api/v1/supplier-orders/{order_id}/place").status_code == 200
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        response = db_client.post(
            f"/api/v1/supplier-orders/{order_id}/transitions",
            json={"status": status},
        )
        assert response.status_code == 200
    return db_client.get(f"/api/v1/supplier-orders/{order_id}").json()


def test_reconcile_exact_exposes_received_and_reconciled_fields(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="Exact")
    preorder = _preorder(db_client, customer_id, product_id, 2)
    order = _arrived_order(db_client, supplier_id, [preorder["id"]])
    line = order["lines"][0]
    assert line["received_quantity"] is None
    assert order["reconciled_at"] is None
    response = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [{"line_id": line["id"], "received_quantity": 2}],
            "reconciliation_notes": "  all arrived  ",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RECONCILED"
    assert body["reconciled_at"] is not None
    assert body["reconciliation_notes"] == "all arrived"
    assert body["lines"][0]["quantity"] == 2
    assert body["lines"][0]["received_quantity"] == 2
    assert db_client.get(f"/api/v1/preorders/{preorder['id']}").json()["status"] == "ARRIVED"
    assert db_client.get("/api/v1/inventory").json() == []


def test_reconcile_shortage(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="Shortage")
    first = _preorder(db_client, customer_id, product_id, 2)
    second = _preorder(db_client, customer_id, product_id, 2)
    third = _preorder(db_client, customer_id, product_id, 1)
    order = _arrived_order(db_client, supplier_id, [first["id"], second["id"], third["id"]])
    line = order["lines"][0]
    response = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={"lines": [{"line_id": line["id"], "received_quantity": 4}]},
    )
    assert response.status_code == 200
    assert db_client.get(f"/api/v1/preorders/{first['id']}").json()["status"] == "ARRIVED"
    assert db_client.get(f"/api/v1/preorders/{second['id']}").json()["status"] == "ARRIVED"
    assert (
        db_client.get(f"/api/v1/preorders/{third['id']}").json()["status"]
        == "ORDERED_FROM_SUPPLIER"
    )
    assert db_client.get("/api/v1/inventory").json() == []


def test_reconcile_excess_creates_inventory(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="Excess")
    first = _preorder(db_client, customer_id, product_id, 2)
    second = _preorder(db_client, customer_id, product_id, 2)
    order = _arrived_order(db_client, supplier_id, [first["id"], second["id"]])
    line = order["lines"][0]
    response = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={"lines": [{"line_id": line["id"], "received_quantity": 5}]},
    )
    assert response.status_code == 200
    lots = db_client.get("/api/v1/inventory").json()
    assert len(lots) == 1
    assert lots[0]["quantity_on_hand"] == 1
    assert lots[0]["product_id"] == product_id
    assert lots[0]["supplier_order_line_id"] == line["id"]


def test_reconcile_explicit_arrived_preorder_ids(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="Explicit")
    first = _preorder(db_client, customer_id, product_id, 2)
    second = _preorder(db_client, customer_id, product_id, 2)
    third = _preorder(db_client, customer_id, product_id, 1)
    order = _arrived_order(db_client, supplier_id, [first["id"], second["id"], third["id"]])
    line = order["lines"][0]
    response = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {
                    "line_id": line["id"],
                    "received_quantity": 3,
                    "arrived_preorder_ids": [third["id"]],
                }
            ]
        },
    )
    assert response.status_code == 200
    assert (
        db_client.get(f"/api/v1/preorders/{first['id']}").json()["status"]
        == "ORDERED_FROM_SUPPLIER"
    )
    assert db_client.get(f"/api/v1/preorders/{third['id']}").json()["status"] == "ARRIVED"
    lots = db_client.get("/api/v1/inventory").json()
    assert len(lots) == 1
    assert lots[0]["quantity_on_hand"] == 2


def test_reconcile_empty_arrived_preorder_ids(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="EmptyIds")
    first = _preorder(db_client, customer_id, product_id, 2)
    second = _preorder(db_client, customer_id, product_id, 1)
    order = _arrived_order(db_client, supplier_id, [first["id"], second["id"]])
    line = order["lines"][0]
    response = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {
                    "line_id": line["id"],
                    "received_quantity": 3,
                    "arrived_preorder_ids": [],
                }
            ]
        },
    )
    assert response.status_code == 200
    assert (
        db_client.get(f"/api/v1/preorders/{first['id']}").json()["status"]
        == "ORDERED_FROM_SUPPLIER"
    )
    assert (
        db_client.get(f"/api/v1/preorders/{second['id']}").json()["status"]
        == "ORDERED_FROM_SUPPLIER"
    )
    lots = db_client.get("/api/v1/inventory").json()
    assert len(lots) == 1
    assert lots[0]["quantity_on_hand"] == 3


def test_reconcile_wrong_state_and_second_call_rejected(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="State")
    preorder = _preorder(db_client, customer_id, product_id, 1)
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    order_id = draft.json()["id"]
    placed = db_client.post(f"/api/v1/supplier-orders/{order_id}/place")
    line_id = placed.json()["lines"][0]["id"]
    assert (
        db_client.post(
            f"/api/v1/supplier-orders/{order_id}/reconcile",
            json={"lines": [{"line_id": line_id, "received_quantity": 1}]},
        ).status_code
        == 409
    )
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        assert (
            db_client.post(
                f"/api/v1/supplier-orders/{order_id}/transitions",
                json={"status": status},
            ).status_code
            == 200
        )
    first = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/reconcile",
        json={"lines": [{"line_id": line_id, "received_quantity": 1}]},
    )
    assert first.status_code == 200
    second = db_client.post(
        f"/api/v1/supplier-orders/{order_id}/reconcile",
        json={"lines": [{"line_id": line_id, "received_quantity": 1}]},
    )
    assert second.status_code == 409


def test_reconcile_missing_line_rejected(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="MissingLine")
    other_product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier_id,
            "name": "Demo Recon API Other",
            "supplier_cost": "10.00",
            "selling_price": "20.00",
        },
    )
    a = _preorder(db_client, customer_id, product_id, 1)
    b = _preorder(db_client, customer_id, other_product.json()["id"], 1)
    order = _arrived_order(db_client, supplier_id, [a["id"], b["id"]])
    missing = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={"lines": [{"line_id": order["lines"][0]["id"], "received_quantity": 1}]},
    )
    assert missing.status_code == 409
    unknown = db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={"lines": [{"line_id": 999999, "received_quantity": 1}]},
    )
    assert unknown.status_code == 404


def test_generic_transitions_cannot_reconcile_or_arrive_preorder(
    db_client: TestClient,
) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, supplier_name="Generic")
    preorder = _preorder(db_client, customer_id, product_id, 1)
    order = _arrived_order(db_client, supplier_id, [preorder["id"]])
    assert (
        db_client.post(
            f"/api/v1/supplier-orders/{order['id']}/transitions",
            json={"status": "RECONCILED"},
        ).status_code
        == 422
    )
    assert (
        db_client.post(
            f"/api/v1/preorders/{preorder['id']}/transitions",
            json={"status": "ARRIVED"},
        ).status_code
        == 409
    )


def test_reconcile_missing_order_returns_404(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/supplier-orders/999999/reconcile",
        json={"lines": [{"line_id": 1, "received_quantity": 0}]},
    )
    assert response.status_code == 404
