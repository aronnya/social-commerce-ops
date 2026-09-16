from fastapi.testclient import TestClient


ZERO_COUNTS = {
    "preorder_overpaid": 0,
    "supplier_order_needs_reconciliation": 0,
    "preorder_needs_customer_ready": 0,
    "preorder_needs_fulfilment": 0,
    "supplier_order_draft_needs_placement": 0,
    "preorder_needs_supplier_order": 0,
}


def _catalogue(db_client: TestClient, *, suffix: str) -> tuple[int, int, int]:
    supplier = db_client.post(
        "/api/v1/suppliers", json={"name": f"Demo Attention API Supplier {suffix}"}
    )
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": f"Demo Attention API Dress {suffix}",
            "supplier_cost": "40.00",
            "selling_price": "85.00",
        },
    )
    customer = db_client.post(
        "/api/v1/customers",
        json={"name": f"Demo Attention API Customer {suffix}"},
    )
    return supplier.json()["id"], product.json()["id"], customer.json()["id"]


def _preorder(
    db_client: TestClient,
    customer_id: int,
    product_id: int,
    quantity: int = 1,
    **extra,
) -> dict:
    payload = {
        "customer_id": customer_id,
        "product_id": product_id,
        "quantity": quantity,
        **extra,
    }
    created = db_client.post("/api/v1/preorders", json=payload)
    assert created.status_code == 201
    return created.json()


def _arrive_order(db_client: TestClient, order_id: int) -> None:
    assert db_client.post(f"/api/v1/supplier-orders/{order_id}/place").status_code == 200
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        response = db_client.post(
            f"/api/v1/supplier-orders/{order_id}/transitions",
            json={"status": status},
        )
        assert response.status_code == 200


def _attention(db_client: TestClient) -> dict:
    response = db_client.get("/api/v1/attention")
    assert response.status_code == 200
    return response.json()


def _types(body: dict) -> list[str]:
    return [item["type"] for item in body["items"]]


def _counts_match_items(body: dict) -> None:
    counts = dict(ZERO_COUNTS)
    for item in body["items"]:
        counts[item["type"]] += 1
    assert body["counts"] == counts


def test_get_attention_empty_queue(db_client: TestClient) -> None:
    body = _attention(db_client)
    assert body["items"] == []
    assert body["counts"] == ZERO_COUNTS


def test_attention_exposes_six_types_counts_and_order(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, suffix="Six")
    unallocated = _preorder(db_client, customer_id, product_id)
    draft_preorder = _preorder(db_client, customer_id, product_id)
    recon_preorder = _preorder(db_client, customer_id, product_id)
    arrived_preorder = _preorder(db_client, customer_id, product_id)
    ready_preorder = _preorder(db_client, customer_id, product_id)
    over = _preorder(
        db_client, customer_id, product_id, agreed_price="10.00"
    )
    db_client.post(
        f"/api/v1/preorders/{over['id']}/payments",
        json={"amount": "25.00", "method": "REVOLUT"},
    )
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [draft_preorder["id"]]},
    )
    recon_draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [recon_preorder["id"]]},
    )
    ready_draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [ready_preorder["id"]]},
    )
    arrived_draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [arrived_preorder["id"]]},
    )
    _arrive_order(db_client, recon_draft.json()["id"])
    _arrive_order(db_client, ready_draft.json()["id"])
    _arrive_order(db_client, arrived_draft.json()["id"])
    for order_id, preorder, make_ready in (
        (ready_draft.json()["id"], ready_preorder, True),
        (arrived_draft.json()["id"], arrived_preorder, False),
    ):
        order = db_client.get(f"/api/v1/supplier-orders/{order_id}").json()
        db_client.post(
            f"/api/v1/supplier-orders/{order['id']}/reconcile",
            json={
                "lines": [
                    {
                        "line_id": order["lines"][0]["id"],
                        "received_quantity": 1,
                    }
                ]
            },
        )
        if make_ready:
            db_client.post(
                f"/api/v1/preorders/{preorder['id']}/transitions",
                json={"status": "READY_FOR_CUSTOMER"},
            )
    body = _attention(db_client)
    _counts_match_items(body)
    types = set(_types(body))
    assert types == {
        "preorder_overpaid",
        "supplier_order_needs_reconciliation",
        "preorder_needs_customer_ready",
        "preorder_needs_fulfilment",
        "supplier_order_draft_needs_placement",
        "preorder_needs_supplier_order",
    }
    assert _types(body) == sorted(
        _types(body),
        key=lambda name: [
            "preorder_overpaid",
            "supplier_order_needs_reconciliation",
            "preorder_needs_customer_ready",
            "preorder_needs_fulfilment",
            "supplier_order_draft_needs_placement",
            "preorder_needs_supplier_order",
        ].index(name),
    )
    keys = [(item["type"], item["entity_type"], item["entity_id"]) for item in body["items"]]
    assert len(keys) == len(set(keys))
    assert any(item["entity_id"] == unallocated["id"] for item in body["items"])
    assert any(item["entity_id"] == draft.json()["id"] for item in body["items"])


def test_attention_item_disappears_after_workflow(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, suffix="Gone")
    preorder = _preorder(db_client, customer_id, product_id)
    assert _types(_attention(db_client)) == ["preorder_needs_supplier_order"]
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder["id"]]},
    )
    assert _types(_attention(db_client)) == ["supplier_order_draft_needs_placement"]
    _arrive_order(db_client, draft.json()["id"])
    assert "supplier_order_needs_reconciliation" in _types(_attention(db_client))
    order = db_client.get(f"/api/v1/supplier-orders/{draft.json()['id']}").json()
    db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {"line_id": order["lines"][0]["id"], "received_quantity": 1}
            ]
        },
    )
    assert _types(_attention(db_client)) == ["preorder_needs_customer_ready"]
    db_client.post(
        f"/api/v1/preorders/{preorder['id']}/transitions",
        json={"status": "READY_FOR_CUSTOMER"},
    )
    assert _types(_attention(db_client)) == ["preorder_needs_fulfilment"]
    db_client.post(
        f"/api/v1/preorders/{preorder['id']}/transitions",
        json={"status": "FULFILLED"},
    )
    assert _attention(db_client)["items"] == []


def test_attention_two_types_same_preorder_and_exclusions(
    db_client: TestClient,
) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, suffix="Two")
    over = _preorder(
        db_client, customer_id, product_id, agreed_price="50.00"
    )
    db_client.post(
        f"/api/v1/preorders/{over['id']}/payments",
        json={"amount": "80.00", "method": "REVOLUT"},
    )
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [over["id"]]},
    )
    _arrive_order(db_client, draft.json()["id"])
    order = db_client.get(f"/api/v1/supplier-orders/{draft.json()['id']}").json()
    db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {"line_id": order["lines"][0]["id"], "received_quantity": 1}
            ]
        },
    )
    db_client.post(
        f"/api/v1/preorders/{over['id']}/transitions",
        json={"status": "READY_FOR_CUSTOMER"},
    )
    placed = _preorder(db_client, customer_id, product_id)
    placed_draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [placed["id"]]},
    )
    db_client.post(f"/api/v1/supplier-orders/{placed_draft.json()['id']}/place")
    cancelled = _preorder(db_client, customer_id, product_id)
    db_client.post(
        f"/api/v1/preorders/{cancelled['id']}/transitions",
        json={"status": "CANCELLED"},
    )
    enquiry = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    assert enquiry.status_code == 201
    body = _attention(db_client)
    types_for_over = {
        item["type"] for item in body["items"] if item["entity_id"] == over["id"]
    }
    assert types_for_over == {"preorder_overpaid", "preorder_needs_fulfilment"}
    assert "supplier_order_draft_needs_placement" not in _types(body)
    assert all(item["entity_id"] != placed_draft.json()["id"] for item in body["items"])
    assert all(item["entity_id"] != cancelled["id"] for item in body["items"])
    assert all(item["entity_type"] != "enquiry" for item in body["items"])
    _counts_match_items(body)


def test_attention_post_not_supported(db_client: TestClient) -> None:
    assert db_client.post("/api/v1/attention", json={}).status_code == 405
