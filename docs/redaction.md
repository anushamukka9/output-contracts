# Redaction

Redaction runs over every string value in the validated copy, at any
depth. It is deterministic: the same input always yields the same
output.

## Detectors

In priority order (earlier wins when spans overlap):

| Kind | What it catches |
|---|---|
| `private_key` | PEM private key blocks, `-----BEGIN ... PRIVATE KEY-----` through the matching END line |
| `jwt` | `eyJ...` three-segment base64url strings |
| `bearer_token` | `Bearer <token>` authorization header values |
| `api_key` | Prefixed keys: `sk-`, `ghp_`, `gho_`, `ghu_`, `ghr_`, `xoxb-`, `xoxp-`, `xoxa-`, `xoxo-`; AWS `AKIA` + 16 chars; 40-char hex (ghp-style) |
| `email` | Standard email shape |
| `ssn` | `123-45-6789` shape, with obviously fake area/group/serial ranges (000, 666, 9xx, 00, 0000) excluded |
| `credit_card` | 13-19 digit runs that pass the Luhn check |
| `phone` | US shapes like `(555) 123-4567` and `555-123-4567`; international shapes starting with `+` and carrying 7-15 digits |
| `ipv4` | Dotted quads with every octet 0-255 |
| `generic_token` | Long opaque strings (24+ chars, mixed letters and digits) with Shannon entropy at or above 4.0 bits per char |

## Styles

- `full` (default): replaced with `[REDACTED:<kind>]`, for example `[REDACTED:email]`.
- `partial`: masked except for the last 4 characters, for example `************3456`. Values of 4 characters or fewer become `****`.

## Declared secrets

Any schema field can set `"secret": true`. Its string value is
redacted with kind `declared_secret` no matter what the detectors
think of it. Use this for fields you know are sensitive even when
they do not look like a known secret format, like internal tokens or
session ids.

## Configuration

- `scan_and_redact(data, style="full")` returns `(redacted, redactions)`.
  Each redaction is `{"path": ..., "kind": ...}` with paths like
  `"user.email"` and `"items[2].token"`.
- `redact_value(value, kind, style)` redacts a single string.
- The CLI: `output-contracts redact --input out.json [--style partial]`.

## False-positive notes

- The generic token detector needs high entropy plus mixed letters
  and digits. UUIDs, long hashes, and random-looking ids can still
  trip it; that is the intended trade. If a field must never be
  redacted, keep it out of the redacted copy or post-process it.
- Phone detection needs separators or a leading `+`. A bare 10-digit
  run like `5551234567` is left alone, on purpose.
- Luhn-passing digit runs are rare in prose, but order numbers and
  long serials can pass. Same trade as above.
- IPv4 detection can catch version-ish strings like `1.2.3.4`. It is
  low priority and only fires when enabled by default; there is no
  separate toggle in v1.
