from fastapi.testclient import TestClient


def _catalogue(db_client: TestClient, *, suffix: str) -> tuple[int, int, int]:
    supplier = db_client.post(
        "/api/v1/suppliers", json={"name": f"Demo Inventory API Supplier {suffix}"}
    )
    assert supplier.status_code == 201
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": f"Demo Inventory API Dress {suffix}",
            "supplier_cost": "40.00",
            "selling_price": "85.00",
        },
    )
    assert product.status_code == 201
    customer = db_client.post(
        "/api/v1/customers", json={"name": f"Demo Inventory API Customer {suffix}"}
    )
    assert customer.status_code == 201
    return supplier.json()["id"], product.json()["id"], customer.json()["id"]


def _arrived_order(db_client: TestClient, supplier_id: int, preorder_ids: list[int]) -> dict:
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": preorder_ids},
    )
    order_id = draft.json()["id"]
    db_client.post(f"/api/v1/supplier-orders/{order_id}/place")
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        db_client.post(
            f"/api/v1/supplier-orders/{order_id}/transitions",
            json={"status": status},
        )
    return db_client.get(f"/api/v1/supplier-orders/{order_id}").json()


def _lot_from_over_receipt(db_client: TestClient, suffix: str, quantity: int = 1) -> tuple[dict, int]:
    supplier_id, product_id, customer_id = _catalogue(db_client, suffix=suffix)
    preorder = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id, "quantity": quantity},
    )
    order = _arrived_order(db_client, supplier_id, [preorder.json()["id"]])
    line = order["lines"][0]
    db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={"lines": [{"line_id": line["id"], "received_quantity": quantity + 1}]},
    )
    lots = db_client.get("/api/v1/inventory").json()
    assert len(lots) == 1
    return lots[0], product_id


def test_list_and_filter_inventory_lots(db_client: TestClient) -> None:
    supplier_id, product_a, customer_id = _catalogue(db_client, suffix="ListA")
    product_b = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier_id,
            "name": "Demo Inventory API Dress ListB",
            "supplier_cost": "10.00",
            "selling_price": "20.00",
        },
    )
    a = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_a, "quantity": 1},
    )
    b = db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": customer_id,
            "product_id": product_b.json()["id"],
            "quantity": 1,
        },
    )
    order = _arrived_order(db_client, supplier_id, [a.json()["id"], b.json()["id"]])
    by_product = {line["product_id"]: line for line in order["lines"]}
    db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {"line_id": by_product[product_a]["id"], "received_quantity": 2},
                {
                    "line_id": by_product[product_b.json()["id"]]["id"],
                    "received_quantity": 3,
                },
            ]
        },
    )
    lots = db_client.get("/api/v1/inventory").json()
    assert len(lots) == 2
    filtered = db_client.get("/api/v1/inventory", params={"product_id": product_a})
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["product_id"] == product_a
    assert filtered.json()[0]["quantity_on_hand"] == 1


def test_get_inventory_lot_and_missing(db_client: TestClient) -> None:
    lot, product_id = _lot_from_over_receipt(db_client, suffix="Get")
    response = db_client.get(f"/api/v1/inventory/{lot['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == lot["id"]
    assert body["product_id"] == product_id
    assert body["quantity_on_hand"] == 1
    assert body["created_at"] is not None
    assert body["updated_at"] is not None
    assert db_client.get("/api/v1/inventory/999999").status_code == 404


def test_inventory_has_no_mutation_routes(db_client: TestClient) -> None:
    assert db_client.post("/api/v1/inventory", json={}).status_code == 405
    assert db_client.patch("/api/v1/inventory/1", json={}).status_code == 405
    assert db_client.delete("/api/v1/inventory/1").status_code == 405
