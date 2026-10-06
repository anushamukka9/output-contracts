"""Tests for the output-contracts CLI."""

import json

import pytest

from output_contracts.cli import main

CONTRACT = {
    "type": "object",
    "properties": {"email": {"type": "string", "format": "email"}},
    "required": ["email"],
}


@pytest.fixture()
def files(tmp_path):
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(CONTRACT))
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"email": "a@b.com"}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"email": "nope"}))
    return contract, good, bad


def test_validate_valid(capsys, files):
    contract, good, _ = files
    code = main(["validate", "--contract", str(contract), "--input", str(good)])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True


def test_validate_invalid_exit_1(capsys, files):
    contract, _, bad = files
    code = main(["validate", "--contract", str(contract), "--input", str(bad)])
    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is False
    assert report["errors"][0]["path"] == "email"


def test_redact_full(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"note": "call (555) 123-4567"}))
    code = main(["redact", "--input", str(target)])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert "[REDACTED:phone]" in out["redacted"]["note"]
    assert out["redactions"] == [{"path": "note", "kind": "phone"}]


def test_redact_partial(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"card": "4111111111111111"}))
    code = main(["redact", "--input", str(target), "--style", "partial"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["redacted"]["card"] == "************1111"


def test_check_valid_quiet(capsys, files):
    contract, good, _ = files
    code = main(["check", "--contract", str(contract), "--input", str(good)])
    assert code == 0
    assert capsys.readouterr().out == ""


def test_check_invalid_exit_2(capsys, files):
    contract, _, bad = files
    code = main(["check", "--contract", str(contract), "--input", str(bad)])
    assert code == 2
    err = capsys.readouterr().err
    assert "email" in err


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "output-contracts" in capsys.readouterr().out
