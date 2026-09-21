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
