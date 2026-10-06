# Schema DSL reference

Every schema is a dict with a `"type"` key. Unknown type names raise
`ContractBuildError` when the `Contract` is built. Every node accepts
`"secret": true` (force redaction of string values at that node, no
matter what they look like) and `"description"` (free text, ignored by
validation).

## object

```python
{
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],          # list of required field names
    "additional_properties": True, # default True; False rejects unknown fields
}
```

## array

```python
{
    "type": "array",
    "items": {"type": "string"},  # schema for every item
    "min_items": 1,
    "max_items": 10,
    "unique_items": False,        # duplicate detection via JSON canonicalization
}
```

## string

```python
{
    "type": "string",
    "min_length": 1,
    "max_length": 280,
    "pattern": r"^[a-z0-9-]+$",   # checked with re.search; must compile at build time
    "enum": ["red", "green"],     # exact match against the list
    "format": "email",            # one of: email, uuid, date, datetime, uri
}
```

Formats: `email` (regex), `uuid` (parsed by `uuid.UUID`), `date`
(`YYYY-MM-DD` via `strptime`), `datetime` (ISO 8601 via
`fromisoformat`; a trailing `Z` is accepted), `uri` (scheme plus
`://` plus non-space remainder).

## integer

```python
{"type": "integer", "minimum": 0, "maximum": 100,
 "exclusive_minimum": 0, "exclusive_maximum": 100}
```

Bounds are inclusive unless marked exclusive. Booleans are rejected:
`True` is not an integer here, even though Python subclasses bool from
int.

## number

Same bounds as integer. Accepts ints and floats, rejects booleans.

## boolean

```python
{"type": "boolean"}
```

Accepts only `True` and `False`. No string coercion: `"true"` is
invalid.

## null

```python
{"type": "null"}
```

Accepts only `None`.

## any_of

```python
{"type": "any_of", "any_of": [{"type": "string"}, {"type": "null"}]}
```

Valid when at least one option validates with zero errors. The error
report records a single `any_of` failure naming the option count, not
the union of every option's errors.

## Errors

Each validation error is a dict:

```python
{
    "path": "items[2].token",   # "user.email" style; "$" for the root
    "message": "expected string at items[2].token",
    "expected": "string",        # what the schema asked for
    "actual": "integer",         # the Python type found (strings show length, not content)
}
```

`actual` deliberately shows the type and, for strings, the length -
never the value - so error reports are safe to log without leaking
secrets.
