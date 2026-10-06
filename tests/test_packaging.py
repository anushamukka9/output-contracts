"""Packaging tests. No tomllib: version is read with a regex fallback
so this file runs unchanged on Python 3.10."""

import re
from pathlib import Path

import output_contracts

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_text() -> str:
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_version_matches_pyproject():
    text = _pyproject_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "no version line found in pyproject.toml"
    assert output_contracts.__version__ == match.group(1)


def test_console_script_declared():
    text = _pyproject_text()
    assert 'output-contracts = "output_contracts.cli:main"' in text


def test_requires_python_310():
    text = _pyproject_text()
    assert 'requires-python = ">=3.10"' in text


def test_public_exports_importable():
    for name in output_contracts.__all__:
        assert getattr(output_contracts, name, None) is not None, name
