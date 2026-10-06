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
uv run prefect work-pool inspect "$MODAL_POOL" 2>/dev/null \
  | python3 -c '
import sys, re
txt = sys.stdin.read()
m = re.search(r"properties.*", txt, re.S)
keys = sorted(set(re.findall(r"\x27([a-z_]+)\x27: \{", txt)))
print("   " + ", ".join(k for k in keys if k not in ("properties","variables","job_configuration")))
' || echo "   (run: uv run prefect work-pool inspect $MODAL_POOL)"

echo
echo "Start a worker for the process pool from this repo:"
echo "  uv run prefect worker start --pool $PROCESS_POOL"
