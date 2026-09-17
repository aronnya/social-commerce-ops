from fastapi.testclient import TestClient


POST_ADDRESS = "Test Recipient\n1 Test Street\nTest Town"


def _catalogue(db_client: TestClient, *, suffix: str) -> tuple[int, int, int]:
    supplier = db_client.post(
        "/api/v1/suppliers", json={"name": f"Demo Fulfil API Supplier {suffix}"}
    )
    assert supplier.status_code == 201
    product = db_client.post(
        "/api/v1/products",
        json={
            "supplier_id": supplier.json()["id"],
            "name": f"Demo Fulfil API Dress {suffix}",
            "supplier_cost": "40.00",
            "selling_price": "85.00",
        },
    )
    assert product.status_code == 201
    customer = db_client.post(
        "/api/v1/customers", json={"name": f"Demo Fulfil API Customer {suffix}"}
    )
    assert customer.status_code == 201
    return supplier.json()["id"], product.json()["id"], customer.json()["id"]


def _ready_preorder(db_client: TestClient, *, suffix: str) -> dict:
    supplier_id, product_id, customer_id = _catalogue(db_client, suffix=suffix)
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    )
    assert created.status_code == 201
    preorder_id = created.json()["id"]
    draft = db_client.post(
        "/api/v1/supplier-orders/generate-draft",
        json={"supplier_id": supplier_id, "preorder_ids": [preorder_id]},
    )
    assert draft.status_code == 201
    order_id = draft.json()["id"]
    assert db_client.post(f"/api/v1/supplier-orders/{order_id}/place").status_code == 200
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        assert (
            db_client.post(
                f"/api/v1/supplier-orders/{order_id}/transitions",
                json={"status": status},
            ).status_code
            == 200
        )
    order = db_client.get(f"/api/v1/supplier-orders/{order_id}").json()
    assert (
        db_client.post(
            f"/api/v1/supplier-orders/{order_id}/reconcile",
            json={
                "lines": [
                    {
                        "line_id": order["lines"][0]["id"],
                        "received_quantity": 1,
                    }
                ]
            },
        ).status_code
        == 200
    )
    assert (
        db_client.post(
            f"/api/v1/preorders/{preorder_id}/transitions",
            json={"status": "READY_FOR_CUSTOMER"},
        ).status_code
        == 200
    )
    return db_client.get(f"/api/v1/preorders/{preorder_id}").json()


def test_home_collection_fulfil_returns_200(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="Home")
    assert preorder["fulfilment"] is None
    response = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/fulfil",
        json={"method": "HOME_COLLECTION"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FULFILLED"
    fulfilment = body["fulfilment"]
    assert fulfilment["method"] == "HOME_COLLECTION"
    assert fulfilment["postage_type"] is None
    assert fulfilment["delivery_address"] is None
    assert fulfilment["postage_cost"] is None
    assert fulfilment["tracking_reference"] is None
    fetched = db_client.get(f"/api/v1/preorders/{preorder['id']}").json()
    assert fetched["fulfilment"]["method"] == "HOME_COLLECTION"


def test_post_regular_with_and_without_postage_cost(db_client: TestClient) -> None:
    with_cost = _ready_preorder(db_client, suffix="RegCost")
    response = db_client.post(
        f"/api/v1/preorders/{with_cost['id']}/fulfil",
        json={
            "method": "POST",
            "postage_type": "REGULAR",
            "delivery_address": POST_ADDRESS,
            "postage_cost": "4.50",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fulfilment"]["postage_type"] == "REGULAR"
    assert body["fulfilment"]["delivery_address"] == POST_ADDRESS
    assert float(body["fulfilment"]["postage_cost"]) == 4.5
    assert body["fulfilment"]["tracking_reference"] is None

    without_cost = _ready_preorder(db_client, suffix="RegNone")
    none_cost = db_client.post(
        f"/api/v1/preorders/{without_cost['id']}/fulfil",
        json={
            "method": "POST",
            "postage_type": "REGULAR",
            "delivery_address": POST_ADDRESS,
        },
    )
    assert none_cost.status_code == 200
    assert none_cost.json()["fulfilment"]["postage_cost"] is None
    assert none_cost.json()["fulfilment"]["tracking_reference"] is None


def test_post_registered_returns_tracking(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="Regd")
    response = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/fulfil",
        json={
            "method": "POST",
            "postage_type": "REGISTERED",
            "delivery_address": POST_ADDRESS,
            "tracking_reference": "TEST-REG-12345",
        },
    )
    assert response.status_code == 200
    fulfilment = response.json()["fulfilment"]
    assert fulfilment["postage_type"] == "REGISTERED"
    assert fulfilment["delivery_address"] == POST_ADDRESS
    assert fulfilment["tracking_reference"] == "TEST-REG-12345"
    assert fulfilment["postage_cost"] is None


def test_invalid_payload_returns_422(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="Invalid")
    missing_address = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/fulfil",
        json={"method": "POST", "postage_type": "REGULAR"},
    )
    assert missing_address.status_code == 422
    home_with_post = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/fulfil",
        json={"method": "HOME_COLLECTION", "postage_type": "REGULAR"},
    )
    assert home_with_post.status_code == 422
    still_ready = db_client.get(f"/api/v1/preorders/{preorder['id']}").json()
    assert still_ready["status"] == "READY_FOR_CUSTOMER"
    assert still_ready["fulfilment"] is None


def test_unknown_preorder_returns_404(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/preorders/999999/fulfil",
        json={"method": "HOME_COLLECTION"},
    )
    assert response.status_code == 404


def test_wrong_state_and_duplicate_return_409(db_client: TestClient) -> None:
    supplier_id, product_id, customer_id = _catalogue(db_client, suffix="Conflict")
    confirmed = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id},
    ).json()
    wrong = db_client.post(
        f"/api/v1/preorders/{confirmed['id']}/fulfil",
        json={"method": "HOME_COLLECTION"},
    )
    assert wrong.status_code == 409
    ready = _ready_preorder(db_client, suffix="Dup")
    first = db_client.post(
        f"/api/v1/preorders/{ready['id']}/fulfil",
        json={"method": "HOME_COLLECTION"},
    )
    assert first.status_code == 200
    duplicate = db_client.post(
        f"/api/v1/preorders/{ready['id']}/fulfil",
        json={"method": "HOME_COLLECTION"},
    )
    assert duplicate.status_code == 409


def test_generic_transition_cannot_fulfil(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="Generic")
    blocked = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/transitions",
        json={"status": "FULFILLED"},
    )
    assert blocked.status_code == 422
    assert db_client.get(f"/api/v1/preorders/{preorder['id']}").json()["status"] == (
        "READY_FOR_CUSTOMER"
    )


def test_payment_summary_unchanged_by_fulfilment(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="Pay")
    payment = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "20.00", "method": "REVOLUT"},
    )
    assert payment.status_code == 201
    before = db_client.get(f"/api/v1/preorders/{preorder['id']}").json()["payment_summary"]
    fulfilled = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/fulfil",
        json={"method": "HOME_COLLECTION"},
    )
    assert fulfilled.status_code == 200
    after = fulfilled.json()["payment_summary"]
    assert after == before
    assert after["status"] == "PARTIALLY_PAID"


def test_attention_item_disappears_after_http_fulfil(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="Attn")
    queue = db_client.get("/api/v1/attention").json()
    types = [item["type"] for item in queue["items"]]
    assert types == ["preorder_needs_fulfilment"]
    assert (
        db_client.post(
            f"/api/v1/preorders/{preorder['id']}/fulfil",
            json={"method": "HOME_COLLECTION"},
        ).status_code
        == 200
    )
    assert db_client.get("/api/v1/attention").json()["items"] == []


def test_no_fulfilment_mutation_routes(db_client: TestClient) -> None:
    preorder = _ready_preorder(db_client, suffix="NoMut")
    path = f"/api/v1/preorders/{preorder['id']}/fulfil"
    assert db_client.patch(path, json={"notes": "x"}).status_code == 405
    assert db_client.delete(path).status_code == 405
    assert db_client.get(f"/api/v1/preorders/{preorder['id']}/fulfilment").status_code == 404
    assert db_client.get("/api/v1/fulfilments").status_code == 404
