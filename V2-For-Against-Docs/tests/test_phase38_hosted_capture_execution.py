from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import load_hosted_capture_execution_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase38_hosted_capture_execution.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "run_phase38_hosted_capture_execution.py"
    spec = importlib.util.spec_from_file_location("run_phase38_hosted_capture_execution", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def copy_text(source: Path, root: Path) -> None:
    target = root / source.relative_to(PROJECT_ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def prepare_project(root: Path) -> None:
    for source in [
        PROJECT_ROOT / "rag" / "evals" / "phase34_backend_db_staging_validation.json",
        PROJECT_ROOT / "rag" / "evals" / "phase35_hosted_evidence_capture.json",
        PROJECT_ROOT / "rag" / "evals" / "phase36_hosted_evidence_capture_runner.json",
        PROJECT_ROOT / "rag" / "evals" / "phase37_hosted_capture_acceptance.json",
        PROJECT_ROOT / "rag" / "evals" / "phase38_hosted_capture_execution.json",
    ]:
        copy_text(source, root)
    for path_value in [
        "rag/evals/phase33_hosted_staging_validation.json",
        "Docs/v2_phase_33_hosted_staging_validation_contract.md",
        "Docs/v2_phase_33_hosted_staging_validation_runbook.md",
        "Docs/releases/v2_phase_33_hosted_staging_validation.md",
        "Docs/v2_phase_34_backend_db_staging_validation_contract.md",
        "Docs/v2_phase_34_backend_db_staging_validation_runbook.md",
        "Docs/releases/v2_phase_34_backend_db_staging_validation.md",
        "Docs/v2_phase_35_hosted_evidence_capture_contract.md",
        "Docs/v2_phase_35_hosted_evidence_capture_runbook.md",
        "Docs/releases/v2_phase_35_hosted_evidence_capture.md",
        "Docs/v2_phase_36_hosted_evidence_capture_runner_contract.md",
        "Docs/v2_phase_36_hosted_evidence_capture_runner_runbook.md",
        "Docs/releases/v2_phase_36_hosted_evidence_capture_runner.md",
        "Docs/v2_phase_38_hosted_capture_execution_contract.md",
        "scripts/run_detached_quality_gate.sh",
        "scripts/run_phase36_hosted_evidence_capture.py",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def hosted_environment() -> dict[str, str]:
    return {
        "SL_LEGAL_STAGING_API_BASE_URL": "https://staging.example.test",
        "SL_LEGAL_STAGING_USER_ID": "reviewer-user",
        "SL_LEGAL_AUTH_HMAC_SECRET": "x" * 40,
        "SL_LEGAL_STAGING_CASE_ID": "case-123",
        "SL_LEGAL_STAGING_DOCUMENT_ID": "doc-456",
        "SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED": "true",
        "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT": "0",
        "SL_LEGAL_PHASE35_DB_MIGRATION_COUNT": "0",
        "SL_LEGAL_PHASE35_RAW_DATA_UPLOADED": "false",
    }


def write_phase33_validated(root: Path) -> None:
    path = root / "logs" / "readiness" / "phase33-hosted-staging-validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": "hosted_staging_validated"}), encoding="utf-8")


def sample_http_client(module):
    def client(method: str, url: str, headers: dict[str, str], timeout_seconds: int):
        if url.endswith("/health"):
            payload = {"status": "ok"}
        elif url.endswith("/status"):
            payload = {
                "documentId": "doc-456",
                "title": "Source",
                "documentType": "judgment",
                "sourceId": "source-1",
            }
        else:
            payload = {
                "activeCaseId": "case-123",
                "documents": [],
                "drafts": [],
                "reviewItems": [],
            }
        return module.HttpCaptureResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
        )

    return client


def test_phase38_manifest_loads():
    payload = load_hosted_capture_execution_manifest(MANIFEST_PATH)
    step_ids = {item["id"] for item in payload["execution_chain"]}

    assert payload["target_release_tag"] == "v2-phase-37-hosted-capture-acceptance"
    assert "phase36_hosted_capture" in step_ids
    assert payload["report_outputs"]["phase38_execution"].endswith("phase38-hosted-capture-execution.json")


def test_phase38_local_run_awaits_hosted_configuration(tmp_path):
    module = load_script()
    prepare_project(tmp_path)
    manifest = load_hosted_capture_execution_manifest(tmp_path / "rag" / "evals" / "phase38_hosted_capture_execution.json")

    report = module.run_hosted_capture_execution(
        phase38_payload=manifest,
        project_root=tmp_path,
        environment={},
        include_environment=False,
        execute=False,
    )

    assert report["status"] == "awaiting_hosted_capture_configuration"
    assert report["phase35_capture_plan"]["status"] == "ready_for_hosted_capture_configuration"
    assert report["phase36_capture_run"]["status"] == "ready_for_hosted_capture_runner_configuration"


def test_phase38_hosted_dry_run_is_ready_to_execute(tmp_path):
    module = load_script()
    prepare_project(tmp_path)
    manifest = load_hosted_capture_execution_manifest(tmp_path / "rag" / "evals" / "phase38_hosted_capture_execution.json")

    report = module.run_hosted_capture_execution(
        phase38_payload=manifest,
        project_root=tmp_path,
        environment=hosted_environment(),
        include_environment=True,
        execute=False,
    )

    assert report["status"] == "ready_for_hosted_capture_execution"
    assert report["phase35_capture_plan"]["status"] == "ready_for_capture_execution"
    assert report["phase36_capture_run"]["status"] == "ready_for_hosted_capture_execution"


def test_phase38_execute_accepts_full_hosted_chain(tmp_path):
    module = load_script()
    prepare_project(tmp_path)
    write_phase33_validated(tmp_path)
    manifest = load_hosted_capture_execution_manifest(tmp_path / "rag" / "evals" / "phase38_hosted_capture_execution.json")

    report = module.run_hosted_capture_execution(
        phase38_payload=manifest,
        project_root=tmp_path,
        environment=hosted_environment(),
        include_environment=True,
        execute=True,
        http_client=sample_http_client(module),
    )

    assert report["status"] == "hosted_capture_execution_accepted"
    assert report["phase36_capture_run"]["status"] == "hosted_evidence_captured"
    assert report["phase34_backend_db_validation"]["status"] == "backend_db_staging_validated"
    assert report["phase37_capture_acceptance"]["status"] == "hosted_capture_accepted"


def test_phase38_execute_waits_for_phase34_when_phase33_is_pending(tmp_path):
    module = load_script()
    prepare_project(tmp_path)
    manifest = load_hosted_capture_execution_manifest(tmp_path / "rag" / "evals" / "phase38_hosted_capture_execution.json")

    report = module.run_hosted_capture_execution(
        phase38_payload=manifest,
        project_root=tmp_path,
        environment=hosted_environment(),
        include_environment=True,
        execute=True,
        http_client=sample_http_client(module),
    )

    assert report["status"] == "hosted_capture_executed_pending_backend_db_validation"
    assert report["phase36_capture_run"]["status"] == "hosted_evidence_captured"
    assert report["phase34_backend_db_validation"]["status"] == "awaiting_backend_db_staging_evidence"


def test_phase38_execute_blocks_without_environment(tmp_path):
    module = load_script()
    prepare_project(tmp_path)
    manifest = load_hosted_capture_execution_manifest(tmp_path / "rag" / "evals" / "phase38_hosted_capture_execution.json")

    report = module.run_hosted_capture_execution(
        phase38_payload=manifest,
        project_root=tmp_path,
        environment={},
        include_environment=False,
        execute=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase36_capture_run" for item in report["blockers"])


def test_phase38_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    prepare_project(tmp_path)
    output = tmp_path / "logs" / "readiness" / "phase38-hosted-capture-execution.json"

    status = module.main(["--manifest", str(tmp_path / "rag" / "evals" / "phase38_hosted_capture_execution.json"), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_hosted_capture_configuration"
