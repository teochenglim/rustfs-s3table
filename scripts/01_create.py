"""Create (C): namespace + table, seeded with an initial batch of rows.

Run via: uv run scripts/01_create.py
"""

import pyarrow as pa

from catalog import IDENTIFIER, NAMESPACE, ORDERS_SCHEMA, get_catalog

INITIAL_ROWS = [
    {"order_id": 1, "customer": "acme", "amount": 42.50},
    {"order_id": 2, "customer": "globex", "amount": 17.25},
    {"order_id": 3, "customer": "acme", "amount": 8.75},
]


def main() -> None:
    catalog = get_catalog()
    print(f"Connected to RustFS Iceberg REST catalog at {catalog.properties['uri']}")

    if (NAMESPACE,) not in catalog.list_namespaces():
        catalog.create_namespace(NAMESPACE)
        print(f"Created namespace: {NAMESPACE}")
    else:
        print(f"Namespace already exists: {NAMESPACE}")

    if catalog.table_exists(IDENTIFIER):
        print(f"Table already exists: {IDENTIFIER} (dropping for a clean run)")
        catalog.drop_table(IDENTIFIER)

    table = catalog.create_table(IDENTIFIER, schema=ORDERS_SCHEMA)
    print(f"Created table: {IDENTIFIER}")

    rows = pa.Table.from_pylist(INITIAL_ROWS, schema=ORDERS_SCHEMA)
    table.append(rows)
    print(f"Appended {rows.num_rows} initial rows")


if __name__ == "__main__":
    main()
