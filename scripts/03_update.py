"""Update (U): append new rows, "update" existing rows via a filtered
overwrite (Iceberg has no in-place UPDATE), and evolve the schema.

Run via: uv run scripts/03_update.py
"""

import pyarrow as pa
from pyiceberg.types import StringType

from catalog import IDENTIFIER, ORDERS_SCHEMA, get_catalog


def main() -> None:
    catalog = get_catalog()
    table = catalog.load_table(IDENTIFIER)

    # --- append: add a brand new row ---
    new_rows = pa.Table.from_pylist(
        [{"order_id": 4, "customer": "initech", "amount": 99.99}],
        schema=ORDERS_SCHEMA,
    )
    table.append(new_rows)
    print(f"Appended {new_rows.num_rows} row(s)")

    # --- update: Iceberg has no row-level UPDATE statement. "Updating" a
    # row means overwriting the rows matched by a filter with new values. ---
    updated_row = pa.Table.from_pylist(
        [{"order_id": 1, "customer": "acme", "amount": 50.00}],
        schema=ORDERS_SCHEMA,
    )
    table.overwrite(updated_row, overwrite_filter="order_id == 1")
    print("Updated order_id == 1 (overwrote its amount to 50.00)")

    # --- schema evolution: add a nullable column ---
    table = catalog.load_table(IDENTIFIER)
    if "status" not in table.schema().column_names:
        with table.update_schema() as update:
            update.add_column("status", StringType())
        print("Added column: status")
    else:
        print("Column already present: status")

    table = catalog.load_table(IDENTIFIER)
    print("\nCurrent rows:")
    for row in table.scan().to_arrow().to_pylist():
        print(" ", row)


if __name__ == "__main__":
    main()
