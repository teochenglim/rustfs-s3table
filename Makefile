.DEFAULT_GOAL := help

ENDPOINT        := http://localhost:30900
CONSOLE         := http://localhost:30901
BUCKET          := demo-table-bucket
ACCESS_KEY      := rustfsadmin
SECRET_KEY      := rustfsadmin123
REGION          := us-east-1

export AWS_ACCESS_KEY_ID := $(ACCESS_KEY)
export AWS_SECRET_ACCESS_KEY := $(SECRET_KEY)
export AWS_DEFAULT_REGION := $(REGION)
export RUSTFS_ENDPOINT := $(ENDPOINT)
export RUSTFS_BUCKET := $(BUCKET)

.PHONY: help up wait bucket demo demo-create demo-read demo-update demo-evolve demo-delete status logs console down clean

help:
	@echo "Cluster lifecycle:"
	@echo "  make up            - apply k8s/ manifests, spin up the RustFS pod"
	@echo "  make wait          - wait for the RustFS deployment to be ready (implied by bucket)"
	@echo "  make bucket        - create the demo bucket and enable it as an Iceberg table bucket"
	@echo "  make down          - delete the k8s resources"
	@echo "  make clean         - down, and wipe the local demo venv cache"
	@echo ""
	@echo "Demo (PyIceberg CRUD + evolve, implies bucket):"
	@echo "  make demo          - run the full demo in order: create, read, update, evolve, delete"
	@echo "  make demo-create   - Create: namespace + table, seeded with rows"
	@echo "  make demo-read     - Read: list namespaces/tables, scan, filtered scan"
	@echo "  make demo-update   - Update: append, filtered overwrite (UPDATE), add column"
	@echo "  make demo-evolve   - Evolve: rename/alter-type/reorder/drop column, table"
	@echo "                       properties, partition evolution, table rename, time travel"
	@echo "  make demo-delete   - Delete: row delete, drop table, drop namespace"
	@echo ""
	@echo "Inspection:"
	@echo "  make status        - show pod/service status"
	@echo "  make logs          - tail RustFS pod logs"
	@echo "  make console       - print the RustFS web console URL"
	@echo ""
	@echo "Full lifecycle: make up demo down"

up:
	kubectl apply -f k8s/

# Depends on `up` so that `make wait` (or anything that needs it) always has
# something to wait for, even if `up` wasn't run as a separate step first.
wait: up
	kubectl rollout status deployment/rustfs --timeout=120s
	@echo "Waiting for $(ENDPOINT)/health ..."
	@until curl --fail --silent --max-time 2 $(ENDPOINT)/health >/dev/null 2>&1; do sleep 1; done
	@echo "RustFS is up: $(ENDPOINT)"

# Depends on `wait`: creating the bucket needs a ready pod, not just an
# applied manifest, so `make up bucket` (without an explicit `wait` in
# between) is still safe and won't race the pod's startup.
bucket: wait
	@aws --endpoint-url $(ENDPOINT) s3api head-bucket --bucket $(BUCKET) >/dev/null 2>&1 \
		&& echo "Bucket already exists: $(BUCKET)" \
		|| aws --endpoint-url $(ENDPOINT) s3api create-bucket --bucket $(BUCKET)
	curl --fail-with-body --silent --show-error \
		--aws-sigv4 "aws:amz:$(REGION):s3" \
		--user "$(ACCESS_KEY):$(SECRET_KEY)" \
		--header "x-amz-content-sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" \
		--request PUT "$(ENDPOINT)/iceberg/v1/buckets/$(BUCKET)"
	@echo ""

# Depends on `bucket`, so `make demo` is safe to run on its own too.
demo: bucket demo-create demo-read demo-update demo-evolve demo-delete

demo-create:
	@echo ""
	@echo "================================================================"
	@echo " CREATE  (scripts/01_create.py)"
	@echo "================================================================"
	uv run scripts/01_create.py

demo-read:
	@echo ""
	@echo "================================================================"
	@echo " READ  (scripts/02_read.py)"
	@echo "================================================================"
	uv run scripts/02_read.py

demo-update:
	@echo ""
	@echo "================================================================"
	@echo " UPDATE  (scripts/03_update.py)"
	@echo "================================================================"
	uv run scripts/03_update.py

demo-evolve:
	@echo ""
	@echo "================================================================"
	@echo " EVOLVE  (scripts/05_evolve.py)"
	@echo "================================================================"
	uv run scripts/05_evolve.py

demo-delete:
	@echo ""
	@echo "================================================================"
	@echo " DELETE  (scripts/04_delete.py)"
	@echo "================================================================"
	uv run scripts/04_delete.py

status:
	kubectl get deployment,pod,svc,pvc -l app=rustfs
	kubectl get pvc rustfs-data

logs:
	kubectl logs deployment/rustfs -f --tail=100

console:
	@echo "RustFS console: $(CONSOLE)  (login: $(ACCESS_KEY) / $(SECRET_KEY))"

down:
	kubectl delete -f k8s/ --ignore-not-found

clean: down
	rm -rf .venv
