# Honest limitations

What this library is and is not. Read this before trusting it in
production.

## Detection is pattern matching, not understanding

Every detector is a regex or a small heuristic. It recognizes shapes,
not meaning. A secret in a format nobody listed passes through
untouched. A secret split across two string values, base64-encoded
twice, or described in words ("the password is hunter2 with a 3")
passes through untouched. If your threat model includes an adversary
actively exfiltrating, this is one layer, not the layer.

## Luhn is not proof

The credit card detector fires on 13-19 digit runs that pass the Luhn
check. Real card numbers pass Luhn, but so do some order numbers,
serial numbers, and long ids. Expect occasional false positives, and
expect misses on card numbers with every-other-digit typos or spaces
in odd places.

## Regex email and phone are approximations

The email pattern accepts the common shapes and rejects obvious
non-emails; it is not RFC 5322. International phone coverage is
"starts with + and carries 7-15 digits", which misses local-format
numbers in many countries and can catch things that are not phones.
Bare digit runs without separators are ignored on purpose to keep
false positives down.

## No semantic redaction

If a tool returns `{"internal_note": "the CEO's home address is ..."}`
under a plain key with no detectable pattern, nothing is redacted.
`secret: true` on the schema field is the fix for fields you know are
sensitive. The global scan only finds what it recognizes.

## Validation errors leak structure, not values

Error reports name paths and types but never values. They still reveal
the shape of your contract and which fields failed, so treat reports
as internal, not user-facing.

## Performance

Validation is recursive and allocation-heavy: each `validate()` call
deep-copies the payload and walks it twice (once for validation, once
for redaction). Measured throughput on the reference machine is in
[benchmarks/results.md](../benchmarks/results.md). It is fast enough
for per-tool-call use, not for bulk ETL. For very large payloads
(megabytes), validate in the tool and stream the clean copy.

## any_of error quality

When `any_of` fails, you get one error naming the option count, not
the detailed per-option failures. This keeps reports readable but can
make debugging a many-option schema slower. Narrow the options or
validate against them one at a time while debugging.

## Tuples and non-JSON types

Tuples are walked and returned as tuples; sets, bytes, and custom
objects pass through validation untouched and are not redacted. The
contract system is built for JSON-shaped data.
