"""Delete (D): delete rows matching a filter, then drop the table and
namespace entirely.

Run via: uv run scripts/04_delete.py
Note: dropping a table removes its catalog entry; RustFS does not purge the
underlying objects on drop (no purge-on-drop support), so this only tears
down the catalog side, not the raw bytes in the bucket.
"""

from catalog import IDENTIFIER, NAMESPACE, get_catalog


def main() -> None:
    catalog = get_catalog()
    table = catalog.load_table(IDENTIFIER)

    print("Rows before delete:")
    for row in table.scan().to_arrow().to_pylist():
        print(" ", row)

    table.delete(delete_filter="customer == 'globex'")
    print("\nDeleted rows where customer == 'globex'")

    table = catalog.load_table(IDENTIFIER)
    print("\nRows after delete:")
    for row in table.scan().to_arrow().to_pylist():
        print(" ", row)

    catalog.drop_table(IDENTIFIER)
    print(f"\nDropped table: {IDENTIFIER} (exists now: {catalog.table_exists(IDENTIFIER)})")

    catalog.drop_namespace(NAMESPACE)
    print(f"Dropped namespace: {NAMESPACE} (namespaces now: {catalog.list_namespaces()})")


if __name__ == "__main__":
    main()
