"""Tests for detectors, styles, and the redaction walk."""

import pytest

from output_contracts import Contract, redact_value, scan_and_redact
from output_contracts.redact import find_matches, redact_text


def kinds(text):
    return [kind for _, _, kind in find_matches(text)]


def test_email_detected():
    assert "email" in kinds("contact jane.doe@example.com today")


def test_email_not_detected_in_plain_sentence():
    assert kinds("nothing sensitive in this sentence at all") == []


def test_us_phone_formats():
    assert "phone" in kinds("call (555) 123-4567")
    assert "phone" in kinds("call 555-123-4567")
    assert "phone" in kinds("call 555.123.4567")


def test_international_phone():
    assert "phone" in kinds("dial +44 20 7946 0958")


def test_bare_digits_not_phone():
    assert "phone" not in kinds("order 5551234567 shipped")


def test_ssn_detected():
    assert "ssn" in kinds("SSN 078-05-1120 on file")


def test_ssn_fake_ranges_ignored():
    assert "ssn" not in kinds("000-12-3456")
    assert "ssn" not in kinds("666-12-3456")
    assert "ssn" not in kinds("900-12-3456")


def test_credit_card_luhn():
    assert "credit_card" in kinds("card 4111 1111 1111 1111 charged")
    assert "credit_card" in kinds("card 4111-1111-1111-1111 charged")


def test_credit_card_bad_luhn_ignored():
    assert "credit_card" not in kinds("serial 4111 1111 1111 1112")


def test_ipv4():
    assert "ipv4" in kinds("host 10.0.4.15 went down")


def test_ipv4_octet_out_of_range_ignored():
    assert "ipv4" not in kinds("version 999.1.1.1 released")


def test_prefixed_api_keys():
    assert "api_key" in kinds("key sk-test-NOT-A-REAL-KEY-0123456789ab here")
    assert "api_key" in kinds("token " + "ghp_" + "a" * 38)
    assert "api_key" in kinds("token " + "xoxb-" + "b" * 24)


def test_akia_key():
    assert "api_key" in kinds("key AKIAIOSFODNN7EXAMPLE disabled")


def test_40char_hex():
    assert "api_key" in kinds("token " + "c" * 40)


def test_jwt_shape():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0." + "s" * 20
    assert "jwt" in kinds("auth " + token)


def test_bearer_token():
    assert "bearer_token" in kinds("Authorization: Bearer test-bearer-token-abc123")


def test_private_key_block():
    block = (
        "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgw\n"
        "-----END PRIVATE KEY-----"
    )
    assert "private_key" in kinds(block)


def test_generic_high_entropy_token():
    assert "generic_token" in kinds("id dGhlIHNhbXBsZSB0b2tlbiB2YWx1ZSBmb3IgdGVzdHM")


def test_plain_words_not_generic_tokens():
    assert "generic_token" not in kinds("the quick brown fox jumps over the lazy dog")


def test_overlap_priority_private_key_over_generic():
    block = "-----BEGIN PRIVATE KEY-----\n" + "M1" * 20 + "\n-----END PRIVATE KEY-----"
    detected = kinds(block)
    assert "private_key" in detected
    assert "generic_token" not in detected


def test_redact_value_full():
    assert redact_value("jane@example.com", "email") == "[REDACTED:email]"


def test_redact_value_partial_keeps_last_4():
    assert redact_value("4111111111111111", "credit_card", style="partial") == "************1111"


def test_redact_value_partial_short():
    assert redact_value("abc", "email", style="partial") == "****"


def test_redact_value_bad_style():
    with pytest.raises(ValueError, match="unknown redaction style"):
        redact_value("x", "email", style="sideways")


def test_redact_text_full():
    redacted, matches = redact_text("email jane.doe@example.com ok")
    assert redacted == "email [REDACTED:email] ok"
    assert matches[0][2] == "email"


def test_redact_text_partial():
    redacted, _ = redact_text("card 4111111111111111 ok", style="partial")
    assert "************1111" in redacted
    assert "4111111111111111" not in redacted


def test_scan_and_redact_nested_paths():
    data = {
        "user": {"email": "a@b.com"},
        "items": [{"token": "sk-test-NOT-A-REAL-KEY-0123456789ab"}, "x"],
    }
    redacted, redactions = scan_and_redact(data)
    assert redacted["user"]["email"] == "[REDACTED:email]"
    assert redacted["items"][0]["token"] == "[REDACTED:api_key]"
    assert redacted["items"][1] == "x"
    paths = {r["path"]: r["kind"] for r in redactions}
    assert paths["user.email"] == "email"
    assert paths["items[0].token"] == "api_key"


def test_scan_and_redact_global_without_secret_flag():
    data = {"note": "call (555) 123-4567"}
    redacted, redactions = scan_and_redact(data)
    assert "[REDACTED:phone]" in redacted["note"]
    assert redactions == [{"path": "note", "kind": "phone"}]


def test_secret_true_forces_redaction_of_plain_value():
    contract = Contract(
        {"type": "object", "properties": {"session": {"type": "string", "secret": True}}}
    )
    report = contract.validate({"session": "abc123"})
    assert report.clean["session"] == "[REDACTED:declared_secret]"
    assert report.redactions[0]["kind"] == "declared_secret"


def test_secret_true_inside_array_items():
    contract = Contract(
        {
            "type": "object",
            "properties": {
                "tokens": {"type": "array", "items": {"type": "string", "secret": True}}
            },
        }
    )
    report = contract.validate({"tokens": ["aaa", "bbb"]})
    assert report.clean["tokens"] == ["[REDACTED:declared_secret]"] * 2
    assert {r["path"] for r in report.redactions} == {"tokens[0]", "tokens[1]"}


def test_deterministic():
    data = {"a": "jane@example.com", "b": ["4111 1111 1111 1111"]}
    first = scan_and_redact(data)
    second = scan_and_redact(data)
    assert first == second


def test_input_not_mutated():
    data = {"email": "a@b.com"}
    scan_and_redact(data)
    assert data["email"] == "a@b.com"


def test_non_string_values_untouched():
    data = {"n": 42, "ok": True, "nothing": None}
    redacted, redactions = scan_and_redact(data)
    assert redacted == data
    assert redactions == []
