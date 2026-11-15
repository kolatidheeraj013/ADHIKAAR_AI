# Model Artifacts

## LM Studio Fact Extractor (Llama 3.1 8B)

ADHIKAAR uses a fine-tuned Llama 3.1 8B model for fact extraction from citizen welfare queries.

**Model ID:** `dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF`  
**Hosted on:** Hugging Face — [dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF](https://huggingface.co/dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF)

### Download & Setup

1. Install [LM Studio](https://lmstudio.ai) (free, runs locally)
2. In LM Studio → Search: `dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF`
3. Download the GGUF file (Q4_K_M recommended, ~4.9 GB)
4. Start the server: `lms server start`
5. Load the model: `lms load adhikaar-llama3.1-8b-v3`
6. Set in `.env.local`:
   ```
   LLM_PROVIDER=lm_studio
   LLM_BASE_URL=http://127.0.0.1:1234/v1
   LLM_MODEL=adhikaar-llama3.1-8b-v3
   ```

> **Offline mode:** Without LM Studio, ADHIKAAR falls back to a deterministic keyword-based classifier. All eligibility rules still run correctly — only LLM-based fact extraction is unavailable.

## Document Classifier (CNN)

A lightweight CNN trained on synthetic Indian government document images.

**Weights:** `ml_training/weights/doc_classifier.pt`  
**Training:** See `ml_training/train.py` and `ml_training/README.md`  
**Classes:** aadhaar, land_record, bank_passbook, income_certificate, marksheet, bonafide_certificate, other

The classifier weights are committed in `ml_training/weights/` for reproducibility.
