# Contributing to output-contracts

Thanks for considering a contribution. This is a small, focused library
and we want to keep it that way.

## What fits here

- New secret/PII detectors with adversarial tests: near-misses that
  must not match, and tricky real shapes that must.
- Schema types or formats people actually need, with docs and tests.
- Framework adapters that wrap tool outputs with zero extra code on
  the caller's side.
- Docs, examples, and benchmark additions.

## What does not fit

- A network service, a hosted dashboard, or anything that phones home.
- Dependencies. The core is stdlib-only and it should stay that way.
- ML-based detection. Regex and heuristics are boring on purpose:
  deterministic, fast, and readable in an afternoon.

## How to contribute

1. Fork the repo and create a branch: `git checkout -b fix/short-desc`.
2. Add your change plus tests. Detectors need adversarial tests: show
   the near-miss that must not fire alongside the shape that must.
3. Run the gates: `pytest` and `ruff check` / `ruff format --check`.
   Both must be clean.
4. Write your feature's limitations honestly. Every part of this
   library documents what it cannot do. That is a requirement, not a
   suggestion.
5. Open a PR with a short description: what it does, why, and the test
   evidence. Keep the human voice: plain sentences, no hype.

## A note on example secrets

GitHub's secret scanner blocks pushes containing real provider key
formats, even obviously fake ones. If a test fixture or example needs
a secret-shaped value, keep it clearly fake (`sk-test-NOT-A-REAL-KEY`)
and never in a real provider's exact format. Where a full-shaped
token is needed to exercise a detector, build it in code (for example
`"ghp_" + "a" * 38`) instead of writing the literal token. Do not
disable push protection to land a fixture.

## Style

- Python 3.10+, `src/` layout, type hints on public APIs.
- Line length 100, ruff-enforced.
- No em-dashes anywhere. This is a hard rule for this repo.
- Commit messages in imperative mood: `fix: catch bare AKIA keys`,
  not `fixed AKIA key detection`.
