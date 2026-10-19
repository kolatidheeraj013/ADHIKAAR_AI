# ADHIKAAR Confidence Thresholds

Phase 3 uses the implementation defaults:

- `AUTO_SUBMIT_THRESHOLD=0.85`
- `REVIEW_THRESHOLD=0.60`

The fake-backed acceptance targets are intentionally shaped around these values:

- Scenario A/E: high-quality documents and grounded facts land above `0.85`.
- Scenario C: blurry land record quality factor `0.6` places confidence in the
  review band `[0.60, 0.85)`.

These are MOCK demo thresholds, not official welfare-program policy.
