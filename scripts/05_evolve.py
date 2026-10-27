"""Evolve: everything RustFS's S3 Tables supports beyond plain CRUD —
schema evolution (rename/alter-type/reorder/drop columns), table properties,
partition evolution, table rename, and time travel.

Run via: uv run scripts/05_evolve.py
Uses its own scratch namespace/table so it doesn't touch demo.orders.
"""

import pyarrow as pa
from pyiceberg.exceptions import NamespaceNotEmptyError
from pyiceberg.types import LongType

from catalog import get_catalog

NAMESPACE = "evolve_demo"
TABLE = "events"
IDENTIFIER = f"{NAMESPACE}.{TABLE}"

SCHEMA = pa.schema(
    [
        pa.field("id", pa.int32(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("score", pa.float32(), nullable=False),
    ]
)


def main() -> None:
    catalog = get_catalog()

    if (NAMESPACE,) not in catalog.list_namespaces():
        catalog.create_namespace(NAMESPACE)
    if catalog.table_exists(IDENTIFIER):
        catalog.drop_table(IDENTIFIER)

    table = catalog.create_table(IDENTIFIER, schema=SCHEMA)
    table.append(pa.Table.from_pylist([{"id": 1, "name": "a", "score": 1.5}], schema=SCHEMA))
    print(f"Created {IDENTIFIER}\n{table.schema()}")

    # --- schema evolution: rename a column ---
    with table.update_schema() as update:
        update.rename_column("name", "full_name")
    table = catalog.load_table(IDENTIFIER)
    print(f"\nRenamed column name -> full_name\n{table.schema()}")

    # --- schema evolution: widen a column's type (int -> long) ---
    with table.update_schema() as update:
        update.update_column("id", field_type=LongType())
    table = catalog.load_table(IDENTIFIER)
    print(f"\nWidened id: int -> long\n{table.schema()}")

    # --- schema evolution: relax a column to optional ---
    with table.update_schema() as update:
        update.update_column("full_name", required=False)
    table = catalog.load_table(IDENTIFIER)
    print(f"\nMade full_name optional\n{table.schema()}")

    # --- schema evolution: reorder columns ---
    with table.update_schema() as update:
        update.move_after("score", "id")
    table = catalog.load_table(IDENTIFIER)
    print(f"\nReordered: score moved after id\n{table.schema()}")

    # --- schema evolution: drop a column ---
    with table.update_schema() as update:
        update.delete_column("score")
    table = catalog.load_table(IDENTIFIER)
    print(f"\nDropped column score\n{table.schema()}")

    # --- table properties ---
    with table.transaction() as txn:
        txn.set_properties(owner="demo", **{"retention.days": "7"})
    table = catalog.load_table(IDENTIFIER)
    print(f"\nSet table properties: {table.properties}")

    # --- partition evolution: add a partition field without rewriting data ---
    with table.update_spec() as update:
        update.add_identity("id")
    table = catalog.load_table(IDENTIFIER)
    print(f"\nAdded partition field on id: {table.spec()}")

    # --- rename table ---
    renamed = f"{NAMESPACE}.events_v2"
    catalog.rename_table(IDENTIFIER, renamed)
    print(f"\nRenamed table {IDENTIFIER} -> {renamed}")
    table = catalog.load_table(renamed)

    # --- time travel: scan as of the very first snapshot ---
    history = table.history()
    print(f"\nSnapshot history ({len(history)} snapshot(s)):")
    for entry in history:
        print(" ", entry)
    first_snapshot_id = history[0].snapshot_id
    rows_at_first_snapshot = table.scan(snapshot_id=first_snapshot_id).to_arrow().to_pylist()
    print(f"\nScan as of first snapshot ({first_snapshot_id}):")
    for row in rows_at_first_snapshot:
        print(" ", row)

    # --- cleanup ---
    catalog.drop_table(renamed)
    try:
        catalog.drop_namespace(NAMESPACE)
        print(f"\nCleaned up: dropped table and namespace {NAMESPACE}")
    except NamespaceNotEmptyError:
        # RustFS has no purge-on-drop: dropping a table removes its catalog
        # entry but can leave catalog-side bookkeeping behind after enough
        # schema/partition/rename churn, which blocks namespace deletion.
        # `make down && make up` gives a fully clean slate (fresh PVC).
        print(
            f"\nDropped table, but namespace {NAMESPACE} still reports "
            "non-empty (expected after rename + partition evolution — "
            "RustFS has no purge-on-drop). Run `make down && make up` for "
            "a clean slate if needed."
        )


if __name__ == "__main__":
    main()
