# ADHIKAAR Confidence Thresholds

# ADHIKAAR Confidence Thresholds

Phase 10 finalizes the implementation defaults:

- `AUTO_SUBMIT_THRESHOLD=0.85`
- `REVIEW_THRESHOLD=0.60`

The fake-backed acceptance targets are intentionally shaped around these values:

- Scenario A/E: high-quality documents and grounded facts land above `0.85`.
- Scenario C: blurry land record quality factor `0.6` places confidence in the
  review band `[0.60, 0.85)`.

The deterministic Phase 10 runner measured the following synthetic outputs:

| Scenario | Confidence | Routing/result |
|---|---:|---|
| A — complete high-quality documents | `0.9170` | `COMPLETED`, auto-submitted |
| B — missing land record, then re-entry | `0.9170` | `COMPLETED`, auto-submitted after upload |
| C — blurry land record | `0.7602` | reviewer band, then `COMPLETED` after approval |
| D1 — targeted IFSC extraction | `0.9170` | `COMPLETED` after two portal attempts |
| D2 — permanent portal rejection | `0.9170` | `NEEDS_REVIEW` / escalation |
| E — missing tax declaration | `0.9170` | question, then `COMPLETED` |

Run the evidence again with:

```bash
make demo
```

These are MOCK demo thresholds, not official welfare-program policy.
