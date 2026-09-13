from fastapi.testclient import TestClient


def _catalogue(db_client: TestClient, *, selling_price: str | None = "85.00") -> tuple[int, int]:
    supplier = db_client.post("/api/v1/suppliers", json={"name": "Demo Payment API Supplier"})
    assert supplier.status_code == 201
    product_body: dict = {
        "supplier_id": supplier.json()["id"],
        "name": "Demo Payment API Dress",
    }
    if selling_price is not None:
        product_body["selling_price"] = selling_price
    product = db_client.post("/api/v1/products", json=product_body)
    assert product.status_code == 201
    customer = db_client.post("/api/v1/customers", json={"name": "Demo Payment API Customer"})
    assert customer.status_code == 201
    return customer.json()["id"], product.json()["id"]


def _preorder(db_client: TestClient, **extra) -> dict:
    customer_id, product_id = _catalogue(db_client)
    payload = {"customer_id": customer_id, "product_id": product_id, **extra}
    created = db_client.post("/api/v1/preorders", json=payload)
    assert created.status_code == 201
    return created.json()


def test_create_payment_returns_201(db_client: TestClient) -> None:
    preorder = _preorder(db_client)
    response = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "40.00", "method": "REVOLUT"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["preorder_id"] == preorder["id"]
    assert float(body["amount"]) == 40.0
    assert body["method"] == "REVOLUT"
    fetched = db_client.get(f"/api/v1/preorders/{preorder['id']}")
    assert fetched.json()["status"] == "CONFIRMED"


def test_create_payment_missing_preorder_returns_404(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/preorders/999999/payments",
        json={"amount": "10.00", "method": "BANK_TRANSFER"},
    )
    assert response.status_code == 404


def test_create_payment_null_agreed_price_returns_409(db_client: TestClient) -> None:
    customer_id, product_id = _catalogue(db_client, selling_price=None)
    created = db_client.post(
        "/api/v1/preorders",
        json={"customer_id": customer_id, "product_id": product_id, "agreed_price": None},
    )
    assert created.status_code == 201
    response = db_client.post(
        f"/api/v1/preorders/{created.json()['id']}/payments",
        json={"amount": "10.00", "method": "REVOLUT"},
    )
    assert response.status_code == 409


def test_list_and_get_payments(db_client: TestClient) -> None:
    first = _preorder(db_client)
    second = _preorder(db_client)
    created = db_client.post(
        f"/api/v1/preorders/{first['id']}/payments",
        json={"amount": "10.00", "method": "REVOLUT"},
    )
    assert created.status_code == 201
    payment_id = created.json()["id"]
    db_client.post(
        f"/api/v1/preorders/{second['id']}/payments",
        json={"amount": "5.00", "method": "BANK_TRANSFER"},
    )
    listed = db_client.get(f"/api/v1/preorders/{first['id']}/payments")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [payment_id]
    fetched = db_client.get(f"/api/v1/preorders/{first['id']}/payments/{payment_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payment_id
    mismatched = db_client.get(f"/api/v1/preorders/{second['id']}/payments/{payment_id}")
    assert mismatched.status_code == 404


def test_patch_payment_reference_and_notes(db_client: TestClient) -> None:
    preorder = _preorder(db_client)
    created = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "10.00", "method": "REVOLUT"},
    )
    payment_id = created.json()["id"]
    patched = db_client.patch(
        f"/api/v1/preorders/{preorder['id']}/payments/{payment_id}",
        json={"reference": "REV-1", "notes": "deposit"},
    )
    assert patched.status_code == 200
    assert patched.json()["reference"] == "REV-1"
    assert patched.json()["notes"] == "deposit"
    assert float(patched.json()["amount"]) == 10.0
    assert patched.json()["method"] == "REVOLUT"


def test_patch_payment_rejects_amount_and_method(db_client: TestClient) -> None:
    preorder = _preorder(db_client)
    created = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "10.00", "method": "REVOLUT"},
    )
    payment_id = created.json()["id"]
    amount = db_client.patch(
        f"/api/v1/preorders/{preorder['id']}/payments/{payment_id}",
        json={"amount": "99.00"},
    )
    assert amount.status_code == 422
    method = db_client.patch(
        f"/api/v1/preorders/{preorder['id']}/payments/{payment_id}",
        json={"method": "BANK_TRANSFER"},
    )
    assert method.status_code == 422


def test_delete_payment_is_not_allowed(db_client: TestClient) -> None:
    preorder = _preorder(db_client)
    created = db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "10.00", "method": "REVOLUT"},
    )
    deleted = db_client.delete(
        f"/api/v1/preorders/{preorder['id']}/payments/{created.json()['id']}"
    )
    assert deleted.status_code in {404, 405}


def test_preorder_payment_summary_on_get(db_client: TestClient) -> None:
    preorder = _preorder(db_client)
    unpaid = db_client.get(f"/api/v1/preorders/{preorder['id']}")
    assert unpaid.status_code == 200
    summary = unpaid.json()["payment_summary"]
    assert summary["status"] == "UNPAID"
    assert float(summary["total_amount"]) == 85.0
    assert float(summary["amount_paid"]) == 0.0
    assert float(summary["outstanding_balance"]) == 85.0
    assert unpaid.json()["status"] == "CONFIRMED"

    db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "40.00", "method": "REVOLUT"},
    )
    partial = db_client.get(f"/api/v1/preorders/{preorder['id']}").json()
    assert partial["status"] == "CONFIRMED"
    assert partial["payment_summary"]["status"] == "PARTIALLY_PAID"
    assert float(partial["payment_summary"]["amount_paid"]) == 40.0

    db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "45.00", "method": "BANK_TRANSFER"},
    )
    paid = db_client.get(f"/api/v1/preorders/{preorder['id']}").json()
    assert paid["payment_summary"]["status"] == "PAID"
    assert float(paid["payment_summary"]["amount_paid"]) == 85.0

    db_client.post(
        f"/api/v1/preorders/{preorder['id']}/payments",
        json={"amount": "1.00", "method": "REVOLUT"},
    )
    overpaid = db_client.get(f"/api/v1/preorders/{preorder['id']}").json()
    assert overpaid["payment_summary"]["status"] == "OVERPAID"
    assert overpaid["status"] == "CONFIRMED"
