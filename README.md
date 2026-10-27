# rustfs-s3table

A local demo of [RustFS](https://rustfs.com)'s **S3 Tables** feature — RustFS
embeds an Apache Iceberg REST catalog directly in the storage server, so an
S3 bucket can double as an Iceberg warehouse with no separate catalog
service. Runs as a single pod on a local colima Kubernetes cluster.

## Do I need an external catalog?

**No.** RustFS's S3 Tables is self-contained: enabling a bucket as a "table
bucket" turns RustFS itself into the Iceberg REST catalog for that bucket —
table data, manifests, and metadata are all just objects in the same bucket,
and the catalog API (`/iceberg/v1/...`) is served from the same process and
port as the S3 API. Any Iceberg REST client (PyIceberg, Spark, DuckDB,
read-only Trino) points straight at RustFS; there's no Hive Metastore,
Nessie, or AWS Glue to stand up.

An external REST catalog is only relevant if you *already* run one and want
RustFS purely as the object store underneath it — a different deployment
pattern that this repo doesn't use.

Known limits of the built-in catalog (preview feature):
- No SQL engine and no multi-table atomic transactions.
- Dropping a table removes the catalog entry but does **not** purge the
  underlying objects (no purge-on-drop).
- No staged table creation, no Iceberg format v3.
- No built-in periodic maintenance scheduler (background maintenance is
  opt-in/explicit).

## Prerequisites

- [colima](https://github.com/abiquo/colima) running with Kubernetes enabled,
  `kubectl` pointed at the `colima` context:

  ```bash
  colima start --cpu 8 --memory 24 --kubernetes
  ```

- `docker`, `aws` CLI, `curl` 7.76+ (needs `--aws-sigv4`).
- [`pyenv`](https://github.com/pyenv/pyenv) to provide the Python interpreter
  and [`uv`](https://docs.astral.sh/uv/) to manage the project's venv and
  dependencies. Install both via Homebrew:

  ```bash
  brew install pyenv uv
  ```

Verify your cluster first:

```bash
colima status
kubectl config current-context   # should print: colima
```

### Python environment

This project pins Python via `.python-version` (currently `3.13`) and is
configured (`[tool.uv] python-preference = "only-system"` in
`pyproject.toml`) to use whatever interpreter `pyenv` resolves on `PATH`
rather than letting `uv` download its own. Install the matching version with
`pyenv`, then let `uv` create the venv and install dependencies:

```bash
pyenv install --skip-existing $(cat .python-version)
uv sync
```

`uv sync` reads `pyproject.toml` / `uv.lock` and creates `.venv` with
`pyiceberg[pyarrow]`, `boto3`, and `s3fs`. Every `uv run scripts/...` call
(including the Makefile's `demo-*` targets) uses that venv automatically —
no `source .venv/bin/activate` needed, and no extra steps if you've already
run `uv sync` once.

## Layout

```
k8s/
  deployment.yaml   RustFS pod (PVC-backed /data, health probes)
  pvc.yaml          2Gi via the local-path StorageClass
  secret.yaml       demo access/secret key (local-only, not for real use)
  service.yaml      NodePort: 9000->30900 (S3 API), 9001->30901 (console)
scripts/
  catalog.py        shared PyIceberg catalog connection (imported, not run)
  01_create.py      Create: namespace + table, seeded with rows
  02_read.py        Read:   list namespaces/tables, scan, filtered scan
  03_update.py      Update: append, filtered overwrite ("UPDATE"), add column
  04_delete.py      Delete: row delete, drop table, drop namespace
  05_evolve.py      Evolve: schema evolution beyond add-column, table
                     properties, partition evolution, table rename, time travel
Makefile            drives the whole lifecycle
```

Everything deploys to the `default` namespace — this is a throwaway local
demo, not meant to model a real cluster layout.

## Usage

Full lifecycle, from nothing to a torn-down cluster:

```bash
make up            # kubectl apply -f k8s/  (spins up the RustFS pod)
make wait           # wait for rollout + /health to respond
make bucket         # create the bucket, enable it as an Iceberg table bucket
make demo           # run the full walkthrough: create -> read -> update -> evolve -> delete
make down           # tear the k8s resources back down
```

Or run each step individually, in order, to see one stage at a time:

```bash
make demo-create    # scripts/01_create.py
make demo-read       # scripts/02_read.py
make demo-update     # scripts/03_update.py
make demo-evolve     # scripts/05_evolve.py
make demo-delete     # scripts/04_delete.py
```

Other targets:

```bash
make status          # pod / service / pvc status
make logs             # tail the RustFS pod's logs
make console           # print the web console URL + demo login
make clean              # down + rm -rf .venv
make help                # list all targets
```

### What `make demo` actually does

| Step | Script | Operations |
|---|---|---|
| Create | `01_create.py` | `create_namespace`, `create_table`, `append` (seed rows) |
| Read | `02_read.py` | `list_namespaces`, `list_tables`, `scan()` (full + filtered), schema, snapshot history |
| Update | `03_update.py` | `append` (new row), `overwrite(filter=...)` (Iceberg's equivalent of `UPDATE`), `update_schema().add_column()` |
| Evolve | `05_evolve.py` | see [Beyond CRUD](#beyond-crud) below |
| Delete | `04_delete.py` | `table.delete(filter=...)` (row-level delete), `drop_table`, `drop_namespace` |

Iceberg has no in-place `UPDATE` statement — "updating" a row means
overwriting the rows matched by a filter with their new values, which is
what `03_update.py` does.

### Beyond CRUD

RustFS's Iceberg REST catalog supports the full range of Iceberg table
evolution, not just insert/scan/delete. `scripts/05_evolve.py` exercises all
of this against a live RustFS pod:

| Capability | PyIceberg call | Notes |
|---|---|---|
| Rename column | `update_schema().rename_column()` | |
| Alter column type | `update_schema().update_column(field_type=...)` | widening only, e.g. int -> long |
| Change nullability | `update_schema().update_column(required=False)` | required -> optional |
| Reorder columns | `update_schema().move_after()` / `move_first()` | |
| Drop column | `update_schema().delete_column()` | |
| Table properties | `table.transaction().set_properties()` | arbitrary key/value metadata |
| Rename table | `catalog.rename_table()` | |
| Partition evolution | `table.update_spec().add_identity()` | adds a partition field without rewriting existing data |
| Time travel | `table.scan(snapshot_id=...)` | read the table as of any prior snapshot |

One real limit surfaced by this script: after a table has been through
enough churn (rename + partition evolution, in testing), `drop_namespace`
can fail with "namespace not empty" even once the table itself is dropped.
This lines up with the docs — no purge-on-drop means some catalog-side
bookkeeping can outlive the table. `05_evolve.py` catches this and prints a
note rather than failing; `make down && make up` always gives a fully clean
slate since it recreates the PVC from scratch.

### Talking to RustFS directly

The S3 API and console are reachable straight from your Mac — colima
forwards the NodePort to `localhost` automatically, no `kubectl
port-forward` needed:

```bash
export AWS_ACCESS_KEY_ID=rustfsadmin
export AWS_SECRET_ACCESS_KEY=rustfsadmin123
aws --endpoint-url http://localhost:30900 s3 ls
```

Console UI: http://localhost:30901 (login: `rustfsadmin` / `rustfsadmin123`).

### Why the demo scripts patch botocore

RustFS requires the `x-amz-content-sha256` header on every SigV4-signed
request (S3-style signing). PyIceberg's SigV4 signer uses botocore's generic
`SigV4Auth`, which only attaches that header for empty-body requests — so
calls with a JSON body (e.g. `create_namespace`) get rejected with `missing
header: x-amz-content-sha256`. `scripts/catalog.py` swaps in botocore's
`S3SigV4Auth`, which always attaches it, before loading the catalog.

## Credentials

The demo access/secret key (`rustfsadmin` / `rustfsadmin123`) in
`k8s/secret.yaml` is for this local, throwaway cluster only. Never reuse it
anywhere reachable from outside your machine.
