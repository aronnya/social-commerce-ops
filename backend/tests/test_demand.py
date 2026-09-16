from fastapi.testclient import TestClient

from app.schemas import LOST_DEMAND_REASONS


LOST_ORDER = list(LOST_DEMAND_REASONS)


def _catalogue(db_client: TestClient, *, suffix: str) -> tuple[int, int, int]:
    supplier = db_client.post(
        "/api/v1/suppliers", json={"name": f"Demo Demand API Supplier {suffix}"}
    )
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": f"Demo Demand API Dress {suffix}",
            "supplier_cost": "40.00",
            "selling_price": "85.00",
        },
    )
    customer = db_client.post(
        "/api/v1/customers",
        json={"name": f"Demo Demand API Customer {suffix}"},
    )
    return supplier.json()["id"], product.json()["id"], customer.json()["id"]


def _demand(db_client: TestClient, **params):
    response = db_client.get("/api/v1/analytics/demand", params=params or None)
    return response


def test_get_demand_empty(db_client: TestClient) -> None:
    response = _demand(db_client)
    assert response.status_code == 200
    body = response.json()
    overview = body["overview"]
    assert overview["total_enquiries"] == 0
    assert overview["open_enquiries"] == 0
    assert overview["resolved_enquiries"] == 0
    assert overview["converted_enquiries"] == 0
    assert overview["lost_enquiries"] == 0
    assert overview["requested_quantity"] == 0
    assert overview["conversion_rate"] is None
    assert overview["unlinked_preordered_outcomes"] == 0
    assert overview["linked_preorder_outcome_mismatch"] == 0
    assert body["products"] == []
    assert body["suppliers"] == []
    assert [bucket["reason"] for bucket in body["lost_demand"]] == LOST_ORDER
    assert all(bucket["count"] == 0 for bucket in body["lost_demand"])
    assert body["fulfilment"]["date_basis"] == "all_time"
    assert body["fulfilment"]["reconciled_order_count"] == 0
    assert body["fulfilment"]["ordered_quantity"] == 0
    assert body["fulfilment"]["received_quantity"] == 0
    assert body["fulfilment"]["shortage_units"] == 0
    assert body["fulfilment"]["excess_units"] == 0
    assert "from" in body
    assert "from_" not in body
    assert body["from"] is None
    assert body["to"] is None


def test_demand_mixed_conversion_integrity_and_ordering(db_client: TestClient) -> None:
    supplier_id, product_a, customer_id = _catalogue(db_client, suffix="MixA")
    product_b = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier_id,
            "name": "Demo Demand API Dress MixB",
            "selling_price": "85.00",
        },
    ).json()
    linked = db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_a, "quantity": 2},
    ).json()
    db_client.post(
        "/api/v1/preorders",
        json={
            "customer_id": customer_id,
            "product_id": product_a,
            "enquiry_id": linked["id"],
        },
    )
    db_client.patch(
        f"/api/v1/enquiries/{linked['id']}", json={"outcome": "NOT_INTERESTED"}
    )
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_a,
            "outcome": "PREORDERED",
        },
    )
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_b["id"],
            "quantity": 1,
            "outcome": "TOO_EXPENSIVE",
        },
    )
    db_client.post(
        "/api/v1/enquiries",
        json={"customer_id": customer_id, "product_id": product_a},
    )
    walk_in = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_a},
    ).json()
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [walk_in["id"]]},
    ).json()
    db_client.post(f"/api/v1/supplier-orders/{draft['id']}/place")
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        db_client.post(
            f"/api/v1/supplier-orders/{draft['id']}/transitions",
            json={"status": status},
        )
    order = db_client.get(f"/api/v1/supplier-orders/{draft['id']}").json()
    db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {"line_id": order["lines"][0]["id"], "received_quantity": 1}
            ]
        },
    )

    body = _demand(db_client).json()
    overview = body["overview"]
    assert overview["total_enquiries"] == 4
    assert overview["converted_enquiries"] == 1
    assert overview["lost_enquiries"] == 1
    assert overview["open_enquiries"] == 1
    assert overview["unlinked_preordered_outcomes"] == 1
    assert overview["linked_preorder_outcome_mismatch"] == 1
    assert overview["resolved_enquiries"] == 2
    assert overview["requested_quantity"] == 5
    assert overview["conversion_rate"] is not None
    lost = {bucket["reason"]: bucket["count"] for bucket in body["lost_demand"]}
    assert [bucket["reason"] for bucket in body["lost_demand"]] == LOST_ORDER
    assert lost["TOO_EXPENSIVE"] == 1
    assert lost["NOT_INTERESTED"] == 0
    assert [row["product_id"] for row in body["products"]] == [product_a, product_b["id"]]
    assert body["products"][0]["enquiry_count"] == 3
    assert body["products"][0]["requested_quantity"] == 4
    assert body["suppliers"][0]["supplier_id"] == supplier_id
    assert body["fulfilment"]["date_basis"] == "all_time"
    assert body["fulfilment"]["reconciled_order_count"] == 1
    assert body["fulfilment"]["ordered_quantity"] == 1
    assert body["fulfilment"]["received_quantity"] == 1


def test_demand_date_filter_uses_from_query_param(db_client: TestClient) -> None:
    _, product_id, customer_id = _catalogue(db_client, suffix="Dates")
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquired_at": "2026-01-01T10:00:00Z",
        },
    )
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquired_at": "2026-01-02T10:00:00Z",
        },
    )
    db_client.post(
        "/api/v1/enquiries",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "enquired_at": "2026-01-03T10:00:00Z",
        },
    )
    walk_in = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    ).json()
    supplier_id = db_client.get(f"/api/v1/products/{product_id}").json()["supplier_id"]
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [walk_in["id"]]},
    ).json()
    db_client.post(f"/api/v1/supplier-orders/{draft['id']}/place")
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        db_client.post(
            f"/api/v1/supplier-orders/{draft['id']}/transitions",
            json={"status": status},
        )
    order = db_client.get(f"/api/v1/supplier-orders/{draft['id']}").json()
    db_client.post(
        f"/api/v1/supplier-orders/{order['id']}/reconcile",
        json={
            "lines": [
                {"line_id": order["lines"][0]["id"], "received_quantity": 2}
            ]
        },
    )
    all_time = _demand(db_client).json()
    filtered = _demand(
        db_client,
        **{"from": "2026-01-02T10:00:00Z", "to": "2026-01-03T10:00:00Z"},
    )
    assert filtered.status_code == 200
    assert "from=" in str(filtered.request.url)
    assert "from_=" not in str(filtered.request.url)
    body = filtered.json()
    assert body["overview"]["total_enquiries"] == 1
    assert "from" in body
    assert body["fulfilment"]["reconciled_order_count"] == all_time["fulfilment"][
        "reconciled_order_count"
    ]
    assert body["fulfilment"]["received_quantity"] == all_time["fulfilment"][
        "received_quantity"
    ]
    assert body["fulfilment"]["received_quantity"] == 2


def test_demand_from_to_validation(db_client: TestClient) -> None:
    aware = "2026-01-02T10:00:00Z"
    naive = "2026-01-02T10:00:00"
    later = "2026-01-03T10:00:00Z"
    inverted = _demand(db_client, **{"from": later, "to": aware})
    equal = _demand(db_client, **{"from": aware, "to": aware})
    naive_from = _demand(db_client, **{"from": naive, "to": later})
    naive_to = _demand(db_client, **{"from": aware, "to": naive})
    assert inverted.status_code == 422
    assert equal.status_code == 422
    assert naive_from.status_code == 422
    assert naive_to.status_code == 422


def test_demand_post_not_supported(db_client: TestClient) -> None:
    assert db_client.post("/api/v1/analytics/demand", json={}).status_code == 405
