# ADHIKAAR AI: Fine-Tuned Llama 3.1-8B & LM Studio Backend Integration

## 1. Can You Use LM Studio for Running the Fine-Tuned Model?

**Yes, absolutely!** In fact, LM Studio is one of the most reliable, high-performance, and cost-effective ways to run your fine-tuned model locally on Windows or any GPU workstation.

### Why LM Studio Works Out-of-the-Box:
1. **OpenAI-Compatible REST API**: LM Studio exposes an OpenAI-compatible `/v1/chat/completions` endpoint on `http://localhost:1234/v1`.
2. **Native Code Support in ADHIKAAR AI**: `backend/app/integrations/llm.py` (`ProviderLLMClient`) has built-in support for `lmstudio` and local providers, automatically bypassing proprietary cloud JSON formats and streaming via prompt-governed schemas.
3. **GPU Offloading via llama.cpp**: Automatically utilizes your NVIDIA RTX GPU (or Apple Metal / CPU) with high token generation speeds (~30-60 tokens/sec on modern GPUs) and 0 API cost.

---

## 2. Quick Setup: Running Your Fine-Tuned Model in LM Studio

### Step 1: Export or Obtain the `.gguf` File
In the new **v3 notebook** (`llama_3_8b_instruct_finetune_d13_FASTv3.ipynb`), **Step 11** exports the model directly into quantized GGUF format:
- **`q4_k_m`** (Recommended): ~4.9 GB. Balanced speed and precision; fits on 6GB–8GB VRAM.
- **`q5_k_m`**: ~5.7 GB. Higher precision; fits on 8GB+ VRAM.

### Step 2: Load into LM Studio
1. Open **LM Studio**.
2. Click the **'My Models'** folder icon on the left navigation bar.
3. Drag and drop your downloaded `.gguf` file into the window (or place it in `~/.cache/lm-studio/models/`).
4. Switch to the **Developer / Local Server tab** (`<->` icon).
5. At the top dropdown, select your model: `adhikaar-llama3.1-8b-v3`.
6. On the right panel under **GPU Settings**:
   - Turn **GPU Offload** to **Max** (offload all 33 layers to your GPU).
   - Set **Context Length** to `4096` or `2048`.
7. Click the green **"Start Server"** button. The server will start listening at:
   ```
   http://localhost:1234/v1
   ```

### Step 3: Configure ADHIKAAR AI Backend
In your `backend/.env` file (or system environment), configure:
```env
LLM_PROVIDER=lmstudio
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=adhikaar-llama3.1-8b-v3
LLM_API_KEY=lm-studio
DEMO_MODE=live
```

### Step 4: Verify Connection
Run a quick test curl or python script:
```bash
python -c "
import httpx
resp = httpx.post('http://localhost:1234/v1/chat/completions', json={
    'model': 'adhikaar-llama3.1-8b-v3',
    'messages': [
        {'role': 'system', 'content': 'Extract facts.'},
        {'role': 'user', 'content': 'Source Type: land_record\nTarget Keys: [\"land_owned_hectares\"]\n\nExtent: 1.40 Hectares'}
    ]
}, timeout=30.0)
print(resp.json()['choices'][0]['message']['content'])
"
```
Output:
```json
{"land_owned_hectares": 1.4}
```

---

## 3. What's New in Notebook v3 (`llama_3_8b_instruct_finetune_d13_FASTv3.ipynb`)

| Feature | FASTv2 (Previous) | FASTv3 (Current) |
|---|---|---|
| **Supported Tasks** | Simple single-field extraction (6 templates) | **Multi-task**: multi-field extraction, single-field recovery, out-of-domain rejection, Indic code-mixing, explanations |
| **Noise Resilience** | Synthetic clean strings | Realistic OCR noise, character swaps (`0`/`O`, `1`/`l`), and watermarks (`SAMPLE — NOT A REAL DOCUMENT`) |
| **Portal Recovery** | None | Targeted single-field recovery (`extract_field`) when portal returns errors (e.g. `INVALID_IFSC`) |
| **Hallucination Guardrails** | None | Rejects non-welfare documents (electricity bills, receipts, selfies) with explicit rejection JSON |
| **Transliterated Indic** | English only | Handles Hinglish, Teluglish, and Tamglish citizen voice/chat transcripts |
| **LM Studio Export** | Unstructured Colab cells with broken paths | **1-Click GGUF export** (`q4_k_m`) with direct download helper |
| **Dataset Generation** | Hardcoded basic samples | Built-in fallback + standalone generator script (`scripts/generate_llm_training_data_v3.py`) |

---

## 4. Provided Datasets & Generator

We have created ready-to-train JSONL datasets in `ml_training/data/`:
- **`ml_training/data/train_v3.jsonl`**: 1,200 diverse multi-task training samples.
- **`ml_training/data/val_v3.jsonl`**: 250 diverse validation samples.

To regenerate or expand the dataset (e.g. to 5,000 or 10,000 samples):
```bash
python scripts/generate_llm_training_data_v3.py --train-count 5000 --val-count 500
```
