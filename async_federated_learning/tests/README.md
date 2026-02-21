# Tests & Comparison Scripts

## Convention

| Pattern | Type | How to run |
|---|---|---|
| `test_*.py` | **pytest unit/integration tests** | `python -m pytest tests/ -v` |
| `compare_*.py`, `*_comparison.py` | Comparison/benchmark scripts | `python tests/compare_*.py` (standalone) |
| `*_e2e.py`, `comprehensive_*.py` | End-to-end validation | `python tests/e2e_validation.py` (standalone) |

## Why both `tests/` and `experiments/`?

- **`tests/`** — Automated correctness checks. Run these with `pytest` in CI/CD.
- **`experiments/`** — Scientific experiment scripts for research evaluation
  (e.g. comparing aggregation strategies, privacy methods across rounds).
  These produce plots and results, not pass/fail assertions.
