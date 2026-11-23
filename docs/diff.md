# Comparing contract versions: diff

Contracts change. A tool adds a field, tightens a length limit, drops
something nobody thought anyone read. The diff command tells you,
before you ship the new contract, whether the change can break the
agents and consumers running against the old one.

```bash
output-contracts diff --old contract-v1.json --new contract-v2.json
# BREAKING score: field 'score' was removed; consumers reading it will find nothing
# safe     note: field 'note' was added as an optional field
# exit code 1 because a breaking change was found
```

Add `--format json` for a machine-readable report. In CI, the exit
code is the gate: 0 means no breaking changes, 1 means at least one.

In Python:

```python
from output_contracts import diff_contracts

diff = diff_contracts(old_schema, new_schema)  # dicts or Contract objects
diff.has_breaking          # True or False
diff.breaking_changes      # just the breaking ones
print(diff.summary())      # one line per change
```

## What counts as breaking

A change is breaking when an output that was valid under the old
contract could be invalid under the new one, or when something a
consumer could read goes away or stops being readable.

Breaking:

- A field is removed.
- A field becomes required that was not required before.
- A type changes, except integer widening to number (every integer is
  a number, so that one is safe and reported as non-breaking).
- A constraint tightens: a bound is added, a lower bound goes up, an
  upper bound comes down, a pattern or format is added or changed,
  enum values are removed, array items gain a schema or a uniqueness
  rule, or `additional_properties` closes.
- An `any_of` option is removed, or an option is edited (an edit shows
  up as a removal plus an addition, and is reported as one breaking
  change).
- A field is newly marked `secret`: the value will now be redacted
  before it reaches the model, so consumers reading it will see the
  redaction marker instead.

Non-breaking, but still reported:

- A field is added as optional, or a required field becomes optional.
- A constraint loosens: bounds move out, a pattern or format is
  removed, enum values are added, `additional_properties` opens.
- A field stops being marked `secret`. This is a security-relevant
  change even though it cannot break a consumer, which is exactly why
  it is reported instead of silently passed.

## Honest limitations

- The diff works on the schema, not on real traffic. A tightened bound
  is flagged breaking even if no real output ever came near the old
  bound. That is deliberate: the schema is the promise.
- `any_of` options are compared as whole schemas. An edit inside one
  option is reported as "options changed", not pinpointed to the inner
  field.
- Description text is ignored. Two contracts that differ only in
  descriptions have no changes.
- Redaction detectors are not part of the contract, so a change in what
  the global scanner catches is not something a contract diff can see.
