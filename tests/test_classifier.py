from __future__ import annotations

from ai_workflow_observatory.classifier import project_name_from_cwd


def test_conversation_slug_is_not_treated_as_project() -> None:
    assert project_name_from_cwd("C:\\Users\\syfsy\\projekty\\poni-ej-masz-gotowe-readme-tej") == "conversation"


def test_workspace_root_is_named_explicitly() -> None:
    assert project_name_from_cwd("C:\\Users\\syfsy\\projekty") == "workspace-root"


def test_system32_is_external_system() -> None:
    assert project_name_from_cwd("C:\\Windows\\System32") == "external-system"
