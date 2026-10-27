"""Shared RustFS Iceberg REST catalog connection used by the scripts in this
directory. Not a standalone demo — imported by 01_create.py..04_delete.py.
"""

import os

import botocore.auth

# PyIceberg's SigV4 signer uses botocore's generic SigV4Auth, which only adds
# the X-Amz-Content-SHA256 header for empty-body requests. RustFS's Iceberg
# REST catalog requires that header on every signed request (S3-style
# signing), so swap in S3SigV4Auth, which always attaches it.
botocore.auth.SigV4Auth = botocore.auth.S3SigV4Auth

import pyarrow as pa  # noqa: E402
from pyiceberg.catalog import load_catalog  # noqa: E402

ENDPOINT = os.environ.get("RUSTFS_ENDPOINT", "http://localhost:30900")
BUCKET = os.environ.get("RUSTFS_BUCKET", "demo-table-bucket")
ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "rustfsadmin")
SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "rustfsadmin123")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

NAMESPACE = "demo"
TABLE = "orders"
IDENTIFIER = f"{NAMESPACE}.{TABLE}"

ORDERS_SCHEMA = pa.schema(
    [
        pa.field("order_id", pa.int64(), nullable=False),
        pa.field("customer", pa.string(), nullable=False),
        pa.field("amount", pa.float64(), nullable=False),
    ]
)


def get_catalog():
    return load_catalog(
        "rustfs",
        **{
            "uri": f"{ENDPOINT}/iceberg",
            "warehouse": BUCKET,
            "s3.endpoint": ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": REGION,
            "rest.sigv4-enabled": "true",
            "rest.signing-region": REGION,
            "rest.signing-name": "s3",
            "client.access-key-id": ACCESS_KEY,
            "client.secret-access-key": SECRET_KEY,
            "client.region": REGION,
        },
    )
