#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-full}"
RUN_ID="${2:-$(date -u +%Y%m%dT%H%M%SZ)-${MODE}}"
LOG_DIR="${ROOT_DIR}/logs/test-runs"
LOG_FILE="${LOG_DIR}/${RUN_ID}.log"
PID_FILE="${LOG_DIR}/${RUN_ID}.pid"
RUN_SCRIPT="${LOG_DIR}/${RUN_ID}.sh"
SESSION_NAME="v2_${RUN_ID//[^A-Za-z0-9_]/_}"

mkdir -p "${LOG_DIR}"

case "${MODE}" in
  full)
    COMMAND="if [ ! -d web/node_modules ]; then npm --prefix web ci; fi; PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with pydantic-settings --with fastapi --with pytest --with httpx --with pypdfium2 --with eval-type-backport python scripts/run_quality_checks.py"
    ;;
  backend)
    COMMAND="PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with pydantic-settings --with fastapi --with pytest --with httpx --with pypdfium2 --with eval-type-backport python scripts/run_quality_checks.py --skip-rag-health"
    ;;
  tests)
    COMMAND="PYTHONPATH=rag uv run --with pytest --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with pydantic-settings --with fastapi --with httpx --with pypdfium2 --with eval-type-backport python -m pytest tests -q"
    ;;
  frontend)
    COMMAND="if [ ! -d web/node_modules ]; then npm --prefix web ci; fi; npm --prefix web run quality"
    ;;
  phase29-browser-workflow)
    COMMAND="npm --prefix web ci; npm --prefix web run phase29:e2e -- --output-dir logs/phase29-browser-workflow"
    ;;
  ui-deployment-readiness)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase30_ui_deployment_readiness.py --output logs/readiness/phase30-ui-deployment-readiness.json"
    ;;
  ui-deployment-readiness-env)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase30_ui_deployment_readiness.py --include-environment --output logs/readiness/phase30-ui-deployment-readiness-env.json"
    ;;
  staging-cutover-dry-run)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase31_staging_cutover_dry_run.py --output logs/readiness/phase31-staging-cutover-dry-run.json"
    ;;
  hosted-staging-execution-pack)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase32_hosted_staging_execution_pack.py --output logs/readiness/phase32-hosted-staging-execution-pack.json"
    ;;
  hosted-staging-validation)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase33_hosted_staging_validation.py --output logs/readiness/phase33-hosted-staging-validation.json"
    ;;
  backend-db-staging-validation)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase34_backend_db_staging_validation.py --output logs/readiness/phase34-backend-db-staging-validation.json"
    ;;
  hosted-evidence-capture-plan)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase35_hosted_evidence_capture_plan.py --output logs/readiness/phase35-hosted-evidence-capture-plan.json"
    ;;
  hosted-evidence-capture-runner)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/run_phase36_hosted_evidence_capture.py --output logs/readiness/phase36-hosted-evidence-capture-run.json"
    ;;
  load)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/run_phase6_load_tests.py"
    ;;
  load-plan)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/run_phase6_load_tests.py --dry-run"
    ;;
  readiness-pack)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/run_phase8_readiness_pack.py --output logs/readiness/phase8-readiness-pack.json"
    ;;
  readiness-pack-production)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/run_phase8_readiness_pack.py --include-production --allow-blockers --output logs/readiness/phase8-readiness-pack-production.json"
    ;;
  artifact-report)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase9_release_artifacts.py --output logs/release-artifacts/phase9-artifact-report.json --write-bundle"
    ;;
  artifact-report-production)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase9_release_artifacts.py --include-production --allow-missing --output logs/release-artifacts/phase9-artifact-report-production.json --write-bundle --bundle logs/release-artifacts/phase9-release-evidence-production.tar.gz"
    ;;
  asset-publication-plan)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/publish_phase10_release_assets.py --output logs/release-artifacts/phase10-publication-plan.json"
    ;;
  asset-verification)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/verify_phase11_release_assets.py --output logs/release-artifacts/phase11-asset-verification.json"
    ;;
  release-provenance)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase12_release_provenance.py --output logs/release-artifacts/phase12-release-provenance-ledger.json"
    ;;
  release-attestation)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase13_release_attestation.py --output logs/release-artifacts/phase13-release-attestation.json"
    ;;
  signing-readiness)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase14_signing_readiness.py --output logs/release-artifacts/phase14-signing-readiness.json"
    ;;
  signing-plan)
    COMMAND="PYTHONPATH=rag uv run --with pydantic python scripts/build_phase15_signing_plan.py --output logs/release-artifacts/phase15-signing-plan.json"
    ;;
  *)
    echo "Unknown mode: ${MODE}" >&2
    echo "Usage: $0 [full|backend|tests|frontend|phase29-browser-workflow|ui-deployment-readiness|ui-deployment-readiness-env|staging-cutover-dry-run|hosted-staging-execution-pack|hosted-staging-validation|backend-db-staging-validation|hosted-evidence-capture-plan|hosted-evidence-capture-runner|load|load-plan|readiness-pack|readiness-pack-production|artifact-report|artifact-report-production|asset-publication-plan|asset-verification|release-provenance|release-attestation|signing-readiness|signing-plan] [run-id]" >&2
    exit 2
    ;;
esac

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}")"
  if ps -p "${OLD_PID}" >/dev/null 2>&1; then
    echo "Run already active: ${RUN_ID} pid=${OLD_PID}" >&2
    exit 1
  fi
fi

cat >"${RUN_SCRIPT}" <<EOF
#!/usr/bin/env bash
set +e
cd "${ROOT_DIR}"
echo "run_id=${RUN_ID}"
echo "mode=${MODE}"
echo "started_at_utc=\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "root=${ROOT_DIR}"
echo "command=${COMMAND}"
echo
${COMMAND}
STATUS=\$?
echo
echo "finished_at_utc=\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "exit_status=\${STATUS}"
exit "\${STATUS}"
EOF
chmod +x "${RUN_SCRIPT}"

if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "${SESSION_NAME}" >/dev/null 2>&1; then
    echo "tmux session already active: ${SESSION_NAME}" >&2
    exit 1
  fi
  tmux new-session -d -s "${SESSION_NAME}" "bash '${RUN_SCRIPT}' > '${LOG_FILE}' 2>&1"
  PID="$(tmux display-message -p -t "${SESSION_NAME}" "#{pane_pid}")"
else
  nohup bash "${RUN_SCRIPT}" >"${LOG_FILE}" 2>&1 &
  PID=$!
fi
echo "${PID}" >"${PID_FILE}"

echo "Started ${MODE} quality run."
echo "PID: ${PID}"
echo "PID file: ${PID_FILE}"
echo "Log file: ${LOG_FILE}"
echo "Run script: ${RUN_SCRIPT}"
echo "tmux session: ${SESSION_NAME}"
echo "Follow log: tail -f '${LOG_FILE}'"
