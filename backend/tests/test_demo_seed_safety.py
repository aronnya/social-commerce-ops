from pathlib import Path

from scripts.demo_safety import (
    UnsafeDemoTargetError,
    assert_demo_seed_allowed,
    is_safe_demo_database_url,
)
import pytest


def test_loopback_demo_name_is_safe() -> None:
    assert is_safe_demo_database_url(
        "postgresql://user:secret@127.0.0.1:5432/sco_demo"
    )
    assert is_safe_demo_database_url(
        "postgresql+psycopg://user:secret@localhost:5432/ops_test"
    )


def test_hosted_or_unmarked_local_names_are_unsafe() -> None:
    assert not is_safe_demo_database_url(
        "postgresql://user:secret@db.example.com:5432/sco_demo"
    )
    assert not is_safe_demo_database_url(
        "postgresql://user:secret@127.0.0.1:5432/postgres"
    )
    assert not is_safe_demo_database_url("")
    assert not is_safe_demo_database_url(None)


def test_guard_requires_allow_flag_and_safe_url() -> None:
    with pytest.raises(UnsafeDemoTargetError):
        assert_demo_seed_allowed(
            allow_flag=None,
            database_url="postgresql://u:p@127.0.0.1:5432/sco_demo",
        )
    with pytest.raises(UnsafeDemoTargetError):
        assert_demo_seed_allowed(allow_flag="1", database_url=None)
    with pytest.raises(UnsafeDemoTargetError):
        assert_demo_seed_allowed(
            allow_flag="1",
            database_url="postgresql://u:p@db.example.com:5432/sco_demo",
        )
    assert_demo_seed_allowed(
        allow_flag="1",
        database_url="postgresql://u:p@127.0.0.1:5432/sco_demo",
    )


def _seed_source() -> str:
    return Path(__file__).resolve().parents[1].joinpath("scripts", "seed_demo.py").read_text(
        encoding="utf-8"
    )


def test_demo_records_use_named_fictional_identities() -> None:
    text = _seed_source()
    assert "Aisha Rahman" in text
    assert "Sara Malik" in text
    assert "Crescent Textiles" in text
    assert "Emerald Lawn Kurti" in text
    assert "Demo FB" not in text
    assert "Aisha Demo" not in text


def test_demo_seed_script_does_not_create_overpayment() -> None:
    text = _seed_source()
    assert "DEMO-OVERPAY" not in text
    assert 'po_registered.id, "90.00"' not in text
    assert 'po_registered.id, "70.00"' in text


def test_demo_reset_truncates_and_restarts_identity() -> None:
    text = _seed_source()
    assert "TRUNCATE TABLE" in text
    assert "RESTART IDENTITY" in text
    table_block = text.split("APPLICATION_TABLES = (")[1].split(")")[0]
    for table in (
        "fulfilments",
        "inventory_lots",
        "supplier_order_allocations",
        "supplier_order_lines",
        "supplier_orders",
        "payments",
        "preorders",
        "enquiries",
        "products",
        "customers",
        "suppliers",
    ):
        assert f'"{table}"' in table_block
    assert "alembic_version" not in table_block
