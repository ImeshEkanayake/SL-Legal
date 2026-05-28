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
  *)
    echo "Unknown mode: ${MODE}" >&2
    echo "Usage: $0 [full|backend|tests|frontend] [run-id]" >&2
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
