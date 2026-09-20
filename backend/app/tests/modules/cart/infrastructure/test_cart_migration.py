"""Migration metadata tests for the persisted cart (U2).

Pins the Alembic chain (single head, chained after the catalog
migration), the registered ORM tables, and the key constraints so the
durable contract cannot silently drift from the models.
"""

import importlib.util
from pathlib import Path

from app.shared.db.base import Base

VERSIONS = Path(__file__).resolve().parents[5] / "alembic" / "versions"
MIGRATION_FILE = VERSIONS / "e3f4a5b6c7d8_add_cart.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("cart_migration", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCartMigrationChain:
    def test_migration_file_exists(self) -> None:
        assert MIGRATION_FILE.is_file()

    def test_revision_chained_after_catalog(self) -> None:
        module = _load_migration()

        assert module.revision == "e3f4a5b6c7d8"
        assert module.down_revision == "d2e3f4a5b6c7"

    def test_single_head(self) -> None:
        revisions: dict[str, str | None] = {}
        for path in VERSIONS.glob("*.py"):
            if path.name == "__init__.py":
                continue
            spec = importlib.util.spec_from_file_location(path.stem, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            revisions[str(module.revision)] = (
                str(module.down_revision)
                if isinstance(module.down_revision, str)
                else None
            )

        downstreams = set(revisions.values())
        heads = [rev for rev in revisions if rev not in downstreams]
        assert heads == ["e3f4a5b6c7d8"]


class TestCartTablesRegistered:
    def test_tables_and_constraints(self) -> None:
        assert "carts" in Base.metadata.tables
        assert "cart_items" in Base.metadata.tables

        carts = Base.metadata.tables["carts"]
        assert {c.name for c in carts.primary_key.columns} == {"id"}
        unique_names = {
            c.name
            for c in carts.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        }
        assert "uq_carts_customer_id" in unique_names
        fk_targets = {
            fk.target_fullname for c in carts.columns.values() for fk in c.foreign_keys
        }
        assert "users.id" in fk_targets

        items = Base.metadata.tables["cart_items"]
        assert {c.name for c in items.primary_key.columns} == {
            "cart_id",
            "product_id",
        }
        check_names = {
            c.name
            for c in items.constraints
            if c.__class__.__name__ == "CheckConstraint"
        }
        assert "ck_cart_items_quantity_range" in check_names
        item_fk_targets = {
            fk.target_fullname for c in items.columns.values() for fk in c.foreign_keys
        }
        assert "carts.id" in item_fk_targets
        assert "catalog_products.id" in item_fk_targets

    def test_models_imported_by_alembic_env(self) -> None:
        env_source = (VERSIONS.parent / "env.py").read_text()
        assert "CartModel" in env_source
        assert "CartItemModel" in env_source
