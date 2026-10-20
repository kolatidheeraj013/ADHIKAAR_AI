# ML training

Phase 5 is intentionally offline-only. `synth_data.py` renders mock documents
for the seven document labels, applies the four quality degradations, and puts
`SAMPLE — NOT A REAL DOCUMENT` on every image. It never reads real documents or
makes network calls.

```bash
python ml_training/train.py
python ml_training/evaluate.py
```

PyTorch and Pillow are optional training dependencies. When they are not
installed, training/evaluation write a structured `status: fallback` report;
the backend's `DocumentClassifier` uses deterministic filename and image
quality heuristics with the same protocol-shaped result.
