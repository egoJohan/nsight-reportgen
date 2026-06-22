"""Test reportbuilder.config module paths (Task 0.11)."""

from reportbuilder import config


def test_input_dir_name():
    """Assert INPUT_DIR resolves to a directory named 'input'."""
    assert config.INPUT_DIR.name == "input"


def test_work_dir_name():
    """Assert WORK_DIR resolves to a directory named 'work'."""
    assert config.WORK_DIR.name == "work"


def test_attendo_template_name():
    """Assert ATTENDO_TEMPLATE resolves to 'attendo_blanked.pptx'."""
    assert config.ATTENDO_TEMPLATE.name == "attendo_blanked.pptx"


def test_attendo_sav_ends_with_sav():
    """Assert ATTENDO_SAV path string ends with '.sav'."""
    assert str(config.ATTENDO_SAV).endswith(".sav")


def test_repo_root_has_pyproject():
    """Assert the resolved repo root contains pyproject.toml."""
    assert (config.INPUT_DIR.parent / "pyproject.toml").exists()
