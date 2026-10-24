"""Builder script to generate llama_3_8b_instruct_finetune_d13_FASTv3.ipynb."""

import json
from pathlib import Path


def create_markdown_cell(source_lines: list[str]) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source_lines],
    }


def create_code_cell(source_lines: list[str]) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source_lines],
    }


def build_v3_notebook() -> dict:
    cells = []

    # Title & Overview
    cells.append(
        create_markdown_cell([
            "# **ADHIKAAR AI v3: Meta-Llama-3.1-8B-Instruct Fine-Tuning**",
            "### *High-Speed QLoRA with Unsloth | Optimized for Colab (Free T4 / L4 / A100) & LM Studio Export*",
            "",
            "This notebook fine-tunes **Meta-Llama-3.1-8B-Instruct** for the updated **ADHIKAAR AI** multi-task welfare pipeline:",
            "1. **Multi-Document Fact Extraction**: Aadhaar, Land Records (Patta/ROR-1B), Bank Passbooks, Income Certificates, Marksheets, Caste & Ration Cards.",
            "2. **Targeted Single-Field Portal Recovery**: High-precision targeted re-extraction (`extract_field`) when government portals reject specific fields.",
            "3. **Out-of-Domain Document Rejection Guardrails**: Hallucination suppression when citizens upload electricity bills, selfies, or receipts.",
            "4. **Code-Mixed Indic Queries**: Hinglish, Teluglish, and Tamglish voice/chat queries.",
            "5. **Empathetic Multilingual Decision Explanations**: Empathetic explanations in Hindi, Telugu, Tamil, and English with masked PII.",
            "6. **1-Click LM Studio Export**: Export to GGUF (`q4_k_m` and `q5_k_m`) to run locally inside LM Studio with zero cloud costs.",
        ])
    )

    # Step 1: Install packages
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 1: Install Fast Fine-Tuning Dependencies (Unsloth)**",
            "Installs Unsloth and pinned PyTorch / xformers dependencies optimized for NVIDIA T4/L4/A100 GPUs.",
        ])
    )
    cells.append(
        create_code_cell([
            "# Install Unsloth and essential libraries",
            "!pip install --no-deps \"xformers<0.0.29\" \"trl<0.9.0\" peft accelerate bitsandbytes",
            "!pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"",
            "!pip install datasets huggingface_hub httpx",
        ])
    )

    # Step 2: Import & GPU Check
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 2: Import Libraries & Verify GPU**",
        ])
    )
    cells.append(
        create_code_cell([
            "import os",
            "import json",
            "import random",
            "import torch",
            "from unsloth import FastLanguageModel, is_bfloat16_supported",
            "from datasets import Dataset, DatasetDict, load_dataset",
            "from trl import SFTTrainer",
            "from transformers import TrainingArguments, TextStreamer",
            "",
            "print(f\"CUDA Available: {torch.cuda.is_available()}\")",
            "if torch.cuda.is_available():",
            "    print(f\"Device: {torch.cuda.get_device_name(0)}\")",
            "    print(f\"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB\")",
            "    print(f\"bfloat16 Supported: {is_bfloat16_supported()}\")",
        ])
    )

    # Step 3: HF Login
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 3: (Optional) Login to Hugging Face**",
            "Run this cell if you plan to push your fine-tuned LoRA weights or GGUF files to Hugging Face.",
        ])
    )
    cells.append(
        create_code_cell([
            "from huggingface_hub import notebook_login",
            "# notebook_login()  # Uncomment if you wish to login interactively",
        ])
    )

    # Step 4: Dataset Loading & Built-in Generator
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 4: Load or Generate ADHIKAAR v3 Dataset**",
            "Checks if `train_v3.jsonl` or `train.jsonl` is uploaded to Colab. If not found, it automatically generates a diverse, multi-task dataset (1,200 train / 250 validation examples).",
        ])
    )
    cells.append(
        create_code_cell([
            "# Globally defined system prompt for both dataset generation and inference",
            "SYS_PROMPT = (",
            "    \"You are ADHIKAAR's structured fact extraction engine for Indian welfare schemes. \"",
            "    \"Extract ONLY explicitly stated facts into the requested JSON schema. If missing, set to null. \"",
            "    \"Output strictly valid JSON without markdown fences.\"",
            ")",
            "",
            "train_path = \"train_v3.jsonl\"",
            "val_path = \"val_v3.jsonl\"",
            "",
            "# Check alternative paths",
            "for cand in [\"train_v3.jsonl\", \"/content/train_v3.jsonl\", \"ml_training/data/train_v3.jsonl\", \"train.jsonl\", \"/content/train.jsonl\"]:",
            "    if os.path.exists(cand):",
            "        train_path = cand",
            "        val_cand = cand.replace(\"train\", \"val\")",
            "        if os.path.exists(val_cand):",
            "            val_path = val_cand",
            "        break",
            "",
            "print(f\"Resolved dataset train path: {train_path}\")",
            "print(f\"Resolved dataset validation path: {val_path}\")",
            "",
            "if not os.path.exists(train_path):",
            "    print(\"Dataset not found in session. Generating 1,200 train and 250 val samples on the fly...\")",
            "    FIRST_NAMES = [\"Ramesh\", \"Suresh\", \"Murugan\", \"Kavitha\", \"Priya\", \"Ananya\", \"Ramu\", \"Venkatesh\", \"Lakshmi\", \"Rajesh\", \"Manish\", \"Sunita\", \"Deepak\", \"Pooja\", \"Selvakumar\", \"Subba Rao\", \"Gurpreet\", \"Sita\", \"Balaji\", \"Bhavani\"]",
            "    LAST_NAMES = [\"Kumar\", \"Patel\", \"Singh\", \"Sharma\", \"Devi\", \"Reddy\", \"Rao\", \"Gowda\", \"Nadar\", \"Pillai\", \"Yadav\", \"Verma\", \"Gupta\", \"Kaur\", \"Joshi\", \"Patil\", \"Naidu\", \"Iyer\", \"Menon\", \"Bhatt\"]",
            "    STATES_DISTRICTS = [(\"Tamil Nadu\", [\"Thanjavur\", \"Madurai\", \"Salem\"]), (\"Andhra Pradesh\", [\"Guntur\", \"Krishna\", \"Kurnool\"]), (\"Telangana\", [\"Warangal\", \"Nalgonda\"]), (\"Uttar Pradesh\", [\"Varanasi\", \"Meerut\"]), (\"Karnataka\", [\"Mandya\", \"Hassan\"])]",
            "    BANKS = [(\"State Bank of India\", \"SBIN0\"), (\"Punjab National Bank\", \"PUNB0\"), (\"Canara Bank\", \"CNRB0\"), (\"Bank of Baroda\", \"BARB0\"), (\"Union Bank of India\", \"UBIN0\"), (\"HDFC Bank\", \"HDFC0\"), (\"ICICI Bank\", \"ICIC0\")]",
            "",
            "    def gen_dataset(count):",
            "        rows = []",
            "        for _ in range(count):",
            "            task = random.choice([\"aadhaar\", \"land\", \"bank\", \"income\", \"marks\", \"recovery\", \"rejection\", \"indic\", \"explain\"])",
            "            name = f\"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}\"",
            "            state, dists = random.choice(STATES_DISTRICTS)",
            "            dist = random.choice(dists)",
            "            if task == \"aadhaar\":",
            "                l4 = str(random.randint(1000, 9999))",
            "                txt = f\"GOVT OF INDIA - UIDAI\\nName: {name}\\nDOB: 12/04/1985\\nXXXX XXXX {l4}\\nAddress: Dist {dist}, {state}\"",
            "                prompt = f\"Source Type: aadhaar\\nTarget Keys: [\\\"applicant_name\\\", \\\"aadhaar_last4\\\"]\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"applicant_name\": name, \"aadhaar_last4\": l4}",
            "            elif task == \"land\":",
            "                ha = round(random.uniform(0.3, 3.8), 2)",
            "                txt = f\"REVENUE DEPT - GOVT OF {state.upper()}\\nROR-1B PATTA\\nPattadar: {name}\\nTotal Extent: {ha} Hectares\\nCategory: Individual\"",
            "                prompt = f\"Source Type: land_record\\nTarget Keys: [\\\"land_owned_hectares\\\", \\\"holder_type\\\"]\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"land_owned_hectares\": ha, \"holder_type\": \"individual\"}",
            "            elif task == \"bank\":",
            "                bname, ipref = random.choice(BANKS)",
            "                ifsc = f\"{ipref}{random.randint(100000, 999999)}\"",
            "                acc = str(random.randint(10000000000, 999999999999))",
            "                txt = f\"{bname}\\nBranch: {dist}\\nIFSC: {ifsc}\\nAccount Holder: {name}\\nAccount No: {acc}\"",
            "                prompt = f\"Source Type: bank_passbook\\nTarget Keys: [\\\"bank_account_number\\\", \\\"bank_ifsc\\\"]\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"bank_account_number\": acc, \"bank_ifsc\": ifsc}",
            "            elif task == \"income\":",
            "                inc = random.choice([48000, 60000, 75000, 90000, 120000, 180000])",
            "                txt = f\"TALUK OFFICE {dist.upper()}\\nINCOME CERTIFICATE\\nAnnual family income of {name} is Rs. {inc:,}/- per annum.\"",
            "                prompt = f\"Source Type: income_certificate\\nTarget Keys: [\\\"family_income_annual\\\"]\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"family_income_annual\": float(inc)}",
            "            elif task == \"marks\":",
            "                pct = round(random.uniform(55.0, 95.0), 1)",
            "                txt = f\"BOARD OF SECONDARY EDUCATION {state.upper()}\\nCandidate: {name}\\nAggregate: {pct}% PASSED\"",
            "                prompt = f\"Source Type: marksheet\\nTarget Keys: [\\\"last_exam_percentage\\\"]\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"last_exam_percentage\": pct}",
            "            elif task == \"recovery\":",
            "                _, ipref = random.choice(BANKS)",
            "                ifsc = f\"{ipref}{random.randint(100000, 999999)}\"",
            "                txt = f\"Bank statement. Account {name}. Bank IFSC code is {ifsc}. Verified.\"",
            "                prompt = f\"Source Type: portal_field_recovery\\nTarget Field: bank_ifsc\\nError Reason: INVALID_IFSC\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"bank_ifsc\": ifsc}",
            "            elif task == \"rejection\":",
            "                txt = f\"STATE ELECTRICITY BOARD\\nConsumer: {random.randint(100000, 999999)}\\nUnits: 120 kWh\\nAmount Due: Rs. 650.00\"",
            "                prompt = f\"Source Type: electricity_bill\\nTarget Keys: [\\\"applicant_name\\\", \\\"land_owned_hectares\\\"]\\n\\nDocument OCR Text:\\n{txt}\"",
            "                exp = {\"is_valid_welfare_doc\": False, \"reason\": \"unsupported_document_type\", \"extracted_facts\": {}}",
            "            elif task == \"indic\":",
            "                ha = round(random.uniform(0.5, 2.5), 2)",
            "                txt = f\"Namaste sir, mera naam {name} hai, {dist} se. Humare paas {ha} hectare khet hai, koi tax nahi bharte.\"",
            "                prompt = f\"Source Type: voice_transcript_indic\\nTarget Keys: [\\\"applicant_name\\\", \\\"land_owned_hectares\\\", \\\"is_income_tax_payer\\\"]\\n\\nCitizen Transcript:\\n{txt}\"",
            "                exp = {\"applicant_name\": name, \"land_owned_hectares\": ha, \"is_income_tax_payer\": False}",
            "            else:",
            "                prompt = f\"Task: explain_outcome\\nDecision Outcome: ELIGIBLE\\nTarget Language: hi\\nContext: Applicant {name}, PM-Kisan\"",
            "                exp = {\"explanation\": f\"बधाई हो {name}! आपका आवेदन स्वीकृत हो गया है। भूमि और बैंक विवरण सत्यापित हैं।\", \"language\": \"hi\", \"outcome\": \"ELIGIBLE\"}",
            "            rows.append({\"messages\": [",
            "                {\"role\": \"system\", \"content\": SYS_PROMPT},",
            "                {\"role\": \"user\", \"content\": prompt},",
            "                {\"role\": \"assistant\", \"content\": json.dumps(exp, ensure_ascii=False)}",
            "            ]})",
            "        return rows",
            "",
            "    with open(\"train_v3.jsonl\", \"w\", encoding=\"utf-8\") as f:",
            "        for row in gen_dataset(1200):",
            "            f.write(json.dumps(row, ensure_ascii=False) + \"\\n\")",
            "    with open(\"val_v3.jsonl\", \"w\", encoding=\"utf-8\") as f:",
            "        for row in gen_dataset(250):",
            "            f.write(json.dumps(row, ensure_ascii=False) + \"\\n\")",
            "    train_path = \"train_v3.jsonl\"",
            "    val_path = \"val_v3.jsonl\"",
            "",
            "dataset = load_dataset(\"json\", data_files={\"train\": train_path, \"validation\": val_path})",
            "print(f\"Dataset loaded: {len(dataset['train'])} train rows, {len(dataset['validation'])} val rows.\")",
            "print(f\"Sample user prompt:\\n{dataset['train'][0]['messages'][1]['content'][:160]}...\")",
        ])
    )

    # Step 5: LoRA Hyperparameters
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 5: LoRA & Hardware Configuration**",
            "Uses 4-bit NormalFloat (NF4) quantization via BitsAndBytes. Optimized to fit comfortably in 16 GB VRAM with fast training speed.",
        ])
    )
    cells.append(
        create_code_cell([
            "MAX_SEQ_LENGTH = 2048",
            "BASE_MODEL_NAME = \"unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit\"",
            "OUTPUT_MODEL_NAME = \"adhikaar-llama3.1-8b-v3\"",
            "",
            "model, tokenizer = FastLanguageModel.from_pretrained(",
            "    model_name=BASE_MODEL_NAME,",
            "    max_seq_length=MAX_SEQ_LENGTH,",
            "    load_in_4bit=True,",
            "    dtype=None,",
            ")",
            "",
            "# Add LoRA adapters targeting all attention and MLP projection layers",
            "model = FastLanguageModel.get_peft_model(",
            "    model,",
            "    r=16,",
            "    target_modules=[\"q_proj\", \"k_proj\", \"v_proj\", \"o_proj\", \"gate_proj\", \"up_proj\", \"down_proj\"],",
            "    lora_alpha=16,",
            "    lora_dropout=0,",
            "    bias=\"none\",",
            "    use_gradient_checkpointing=\"unsloth\",",
            "    random_state=3407,",
            ")",
            "print(\"PEFT LoRA model initialized successfully.\")",
        ])
    )

    # Step 6: Format with Chat Template
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 6: Apply Llama 3 Chat Template**",
            "Converts the `messages` list into standard Llama 3 token stream with `<|begin_of_text|>`, `<|start_header_id|>`, and `<|eot_id|>`. Enables training packing for 2x faster throughput.",
        ])
    )
    cells.append(
        create_code_cell([
            "from unsloth.chat_templates import get_chat_template",
            "",
            "# Apply standard Llama-3 chat template for OpenAI messages format",
            "tokenizer = get_chat_template(",
            "    tokenizer,",
            "    chat_template=\"llama-3\",",
            ")",
            "",
            "def format_prompts(batch):",
            "    texts = []",
            "    for msgs in batch[\"messages\"]:",
            "        formatted = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)",
            "        texts.append(formatted)",
            "    return {\"text\": texts}",
            "",
            "dataset = dataset.map(format_prompts, batched=True)",
            "print(\"Formatted sample text:\\n\", dataset[\"train\"][0][\"text\"][:300])",
        ])
    )

    # Step 7: Train with SFTTrainer
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 7: Train the Model (Option B: Full 1-Epoch Coverage)**",
            "Runs 1 full epoch across all 5,000 samples (625 steps, ~25-30 minutes on T4 GPU) with `packing=False` (dynamic padding to ~300 tokens) for maximum state/district coverage without overfitting.",
        ])
    )
    cells.append(
        create_code_cell([
            "trainer = SFTTrainer(",
            "    model=model,",
            "    tokenizer=tokenizer,",
            "    train_dataset=dataset[\"train\"],",
            "    eval_dataset=dataset[\"validation\"],",
            "    dataset_text_field=\"text\",",
            "    max_seq_length=MAX_SEQ_LENGTH,",
            "    dataset_num_proc=1,",
            "    packing=False,  # False is 5-10x faster because OCR samples are ~300 tokens",
            "    args=TrainingArguments(",
            "        per_device_train_batch_size=2,",
            "        gradient_accumulation_steps=4,  # Effective batch size = 8",
            "        warmup_steps=30,  # 30 steps gentle warmup (~5% of 625 total steps)",
            "        num_train_epochs=1,  # 1 full epoch across 5,000 samples (625 steps, ~25-30 min)",
            "        learning_rate=2e-4,",
            "        fp16=not is_bfloat16_supported(),",
            "        bf16=is_bfloat16_supported(),",
            "        logging_steps=20,",
            "        optim=\"adamw_8bit\",",
            "        weight_decay=0.01,",
            "        lr_scheduler_type=\"cosine\",",
            "        seed=3407,",
            "        output_dir=\"outputs_v3\",",
            "        report_to=\"none\",",
            "    ),",
            ")",
            "",
            "print(\"Starting full 1-epoch fine-tuning on 5,000 samples...\")",
            "trainer_stats = trainer.train()",
            "print(\"Fine-tuning complete!\")",
        ])
    )

    # Step 8: Metrics
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 8: View Training Metrics & VRAM Usage**",
        ])
    )
    cells.append(
        create_code_cell([
            "gpu_stats = torch.cuda.get_device_properties(0)",
            "max_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 2)",
            "print(f\"GPU: {gpu_stats.name}\")",
            "print(f\"Peak VRAM reserved: {max_memory} GB ({max_memory / (gpu_stats.total_memory / 1024**3) * 100:.1f}%)\")",
            "print(f\"Training time: {trainer_stats.metrics.get('train_runtime', 0):.1f} seconds\")",
        ])
    )

    # Step 9: Save LoRA
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 9: Save LoRA Adapter Locally & to Google Drive**",
        ])
    )
    cells.append(
        create_code_cell([
            "lora_output_dir = f\"{OUTPUT_MODEL_NAME}-lora\"",
            "model.save_pretrained(lora_output_dir)",
            "tokenizer.save_pretrained(lora_output_dir)",
            "print(f\"LoRA adapter saved locally to: {lora_output_dir}\")",
            "",
            "# Optional: Copy to Google Drive to prevent Colab timeout data loss",
            "# from google.colab import drive",
            "# import shutil",
            "# drive.mount('/content/drive')",
            "# shutil.copytree(lora_output_dir, f\"/content/drive/MyDrive/{lora_output_dir}\")",
        ])
    )

    # Step 10: Test Inference
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 10: Test Inference Across All 5 Real-World Scenarios**",
        ])
    )
    cells.append(
        create_code_cell([
            "import torch",
            "torch.cuda.empty_cache()  # Clear residual training VRAM allocations",
            "FastLanguageModel.for_inference(model)",
            "",
            "test_prompts = [",
            "    # 1. Fact Extraction: Land Record",
            "    \"Source Type: land_record\\nTarget Keys: [\\\"land_owned_hectares\\\", \\\"holder_type\\\"]\\n\\nDocument OCR Text:\\nREVENUE DEPT - GOVT OF TELANGANA\\nROR-1B PATTA Khata: 412\\nPattadar: Murugan K\\nExtent: 1.40 Hectares\\nCategory: Individual Cultivator\",",
            "    # 2. Portal Error Recovery: Single Field IFSC",
            "    \"Source Type: portal_field_recovery\\nTarget Field: bank_ifsc\\nError Reason: INVALID_IFSC: Code not found\\n\\nDocument OCR Text:\\nSBI Guntur Branch Passbook. Account 31094819201. IFSC: SBIN0004128. Holder: Murugan K.\",",
            "    # 3. Out-of-Domain Guardrail: Electricity Bill Rejection",
            "    \"Source Type: electricity_bill\\nTarget Keys: [\\\"applicant_name\\\", \\\"land_owned_hectares\\\"]\\n\\nDocument OCR Text:\\nDISCOM POWER BILL Consumer 982142 Units 180 Amount Due: Rs. 920.00 Due Date 12/11/2026\",",
            "    # 4. Code-Mixed Voice Transcript",
            "    \"Source Type: voice_transcript_indic\\nTarget Keys: [\\\"applicant_name\\\", \\\"land_owned_hectares\\\", \\\"is_income_tax_payer\\\"]\\n\\nCitizen Transcript:\\nNamaste sir, mera naam Ramesh Kumar hai, Guntur se. Humare paas 1.8 hectare khet hai, koi tax nahi bharte.\",",
            "    # 5. Multilingual Decision Explanation (Telugu)",
            "    \"Task: explain_outcome\\nDecision Outcome: ELIGIBLE\\nTarget Language: te\\nContext: Applicant Murugan K, Aadhaar XXXX-XXXX-8942, Scheme: PM-Kisan\",",
            "]",
            "",
            "for i, p in enumerate(test_prompts, 1):",
            "    messages = [",
            "        {\"role\": \"system\", \"content\": SYS_PROMPT},",
            "        {\"role\": \"user\", \"content\": p},",
            "    ]",
            "    inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors=\"pt\").to(\"cuda\")",
            "    print(f\"\\n=== Test Case {i} ===\")",
            "    print(f\"User Input:\\n{p}\\n\")",
            "    outputs = model.generate(input_ids=inputs, max_new_tokens=256, do_sample=False, use_cache=True)",
            "    resp = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)",
            "    print(f\"Model Output:\\n{resp}\")",
        ])
    )

    # Step 11: Export to GGUF for LM Studio
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 11: 1-Click Export to GGUF for LM Studio**",
            "LM Studio natively runs `.gguf` quantized models with high-speed GPU offloading and zero configuration.",
            "",
            "- **`q4_k_m`** (Recommended): ~4.9 GB file size. Extremely fast, fits into 6GB-8GB VRAM (NVIDIA RTX 3060/4060 or Apple Silicon / CPU).",
            "- **`q5_k_m`**: ~5.7 GB file size. Higher precision, recommended if you have 8GB+ VRAM.",
        ])
    )
    cells.append(
        create_code_cell([
            "gguf_output_dir = f\"{OUTPUT_MODEL_NAME}-GGUF\"",
            "",
            "# Save in q4_k_m for LM Studio (fastest, lightweight)",
            "print(\"Exporting model to GGUF (q4_k_m format)... This takes ~3-5 minutes.\")",
            "model.save_pretrained_gguf(gguf_output_dir, tokenizer, quantization_method=\"q4_k_m\")",
            "print(f\"GGUF export finished! Saved inside directory: {gguf_output_dir}\")",
            "",
            "# List generated .gguf files",
            "for root, dirs, files in os.walk(gguf_output_dir):",
            "    for file in files:",
            "        if file.endswith(\".gguf\"):",
            "            full_p = os.path.join(root, file)",
            "            print(f\"Found GGUF file: {full_p} ({os.path.getsize(full_p) / 1024**3:.2f} GB)\")",
        ])
    )

    # Step 12: Download & Connect to LM Studio
    cells.append(
        create_markdown_cell([
            "---",
            "## **Step 12: How to Run in LM Studio & Connect to ADHIKAAR AI**",
            "",
            "### **1. Download the `.gguf` file to your PC**",
            "Run the cell below to download the file directly, or copy it to Google Drive:",
        ])
    )
    cells.append(
        create_code_cell([
            "from google.colab import files",
            "import glob",
            "",
            "gguf_files = glob.glob(f\"{gguf_output_dir}/**/*.gguf\", recursive=True)",
            "if gguf_files:",
            "    target_file = gguf_files[0]",
            "    print(f\"Ready to download: {target_file}\")",
            "    # files.download(target_file)  # Uncomment to trigger browser download in Colab",
            "else:",
            "    print(\"No .gguf file found. Run Step 11 first.\")",
        ])
    )

    cells.append(
        create_markdown_cell([
            "### **2. Load in LM Studio**",
            "1. Open **LM Studio** on your PC.",
            "2. Click the **'My Models'** folder icon (left sidebar).",
            "3. Click **'Show models directory'** (or drag the downloaded `.gguf` file directly into LM Studio).",
            "4. Go to the **Developer / Local Server tab** (`<->` icon).",
            "5. Select your fine-tuned `adhikaar-llama3.1-8b-v3` model from the top dropdown.",
            "6. In GPU Settings, toggle **GPU Offload: Max** (offloads layers to CUDA).",
            "7. Click **'Start Server'** (runs by default on `http://localhost:1234/v1`).",
            "",
            "### **3. Connect ADHIKAAR AI Backend to LM Studio**",
            "In your ADHIKAAR AI `.env` file or environment variables, configure:",
            "```bash",
            "LLM_PROVIDER=lmstudio",
            "LLM_BASE_URL=http://localhost:1234/v1",
            "LLM_MODEL=adhikaar-llama3.1-8b-v3",
            "LLM_API_KEY=lm-studio",
            "DEMO_MODE=live",
            "```",
            "Then start the backend:",
            "```bash",
            "uv run --project backend uvicorn app.main:app --reload --port 8000",
            "```",
            "The ADHIKAAR AI pipeline will now process all citizen document extractions, recovery, and explanations directly through your local fine-tuned model!",
        ])
    )

    return {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"gpuType": "T4", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


def main():
    target_path = Path(__file__).resolve().parents[1] / "llama_3_8b_instruct_finetune_d13_FASTv3.ipynb"
    nb = build_v3_notebook()
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print(f"Created notebook v3 at: {target_path}")


if __name__ == "__main__":
    main()
