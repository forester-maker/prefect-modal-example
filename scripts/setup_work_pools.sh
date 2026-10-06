#!/usr/bin/env bash
# Create the two work pools this repo deploys to. Idempotent.
#
#   PREFECT_API_URL / PREFECT_API_KEY must point at the target workspace
#   (`prefect cloud login` does this for you locally).
#
# The Modal pool needs a Modal token. `--provision-infra` creates the
# ModalCredentials block from your local `modal token new` credentials
# (~/.modal.toml) or from MODAL_TOKEN_ID / MODAL_TOKEN_SECRET if set.
set -euo pipefail

PROCESS_POOL="${PROCESS_POOL:-starter-process}"
MODAL_POOL="${MODAL_POOL:-starter-modal}"

echo "==> process pool: $PROCESS_POOL"
uv run prefect work-pool create "$PROCESS_POOL" --type process --overwrite

echo "==> modal push pool: $MODAL_POOL"
uv run prefect work-pool create "$MODAL_POOL" --type modal:push --provision-infra --overwrite

echo
echo "==> Modal job variables you can set per deployment (job_variables in prefect.yaml):"
uv run prefect work-pool get-default-base-job-template --type modal:push \
  | uv run python -c '
import json, sys
props = json.load(sys.stdin)["variables"]["properties"]
for k, v in props.items():
    print(f"   {k:18s} {v.get(\"type\", \"\"):8s} default={json.dumps(v.get(\"default\"))}")
'
echo "   NOTE: timeout defaults to 300s. Set job_variables.timeout per deployment for anything longer."

echo
echo "Start a worker for the process pool from this repo:"
echo "  uv run prefect worker start --pool $PROCESS_POOL"
