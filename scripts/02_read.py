"""Read (R): list namespaces/tables, inspect schema and snapshot history, and
scan the table with and without a filter.

Run via: uv run scripts/02_read.py
"""

from catalog import IDENTIFIER, NAMESPACE, get_catalog


def main() -> None:
    catalog = get_catalog()

    print("Namespaces:", catalog.list_namespaces())
    print(f"Tables in {NAMESPACE}:", catalog.list_tables(NAMESPACE))

    table = catalog.load_table(IDENTIFIER)

    print("\nSchema:")
    print(table.schema())

    print("\nSnapshot history:")
    for snapshot in table.history():
        print(" ", snapshot)

    print("\nFull scan:")
    rows = table.scan().to_arrow().to_pylist()
    for row in rows:
        print(" ", row)

    print("\nFiltered scan (customer == 'acme'):")
    for row in table.scan(row_filter="customer == 'acme'").to_arrow().to_pylist():
        print(" ", row)

    total = sum(row["amount"] for row in rows)
    print(f"\nTotal amount across all rows: {total:.2f}")


if __name__ == "__main__":
    main()
