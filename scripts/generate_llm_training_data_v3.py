"""Comprehensive synthetic dataset generator for ADHIKAAR AI v3 Llama 3.1-8B fine-tuning.

Covers:
1. Multi-document Fact Extraction (Aadhaar, Land Record, Bank Passbook, Income, Marksheet, Caste, Ration Card)
2. Targeted Single-Field Portal Recovery (extract_field)
3. Out-of-Domain Document Rejection Guardrails (hallucination prevention)
4. Code-Mixed Indic Voice/Chat Queries (Hinglish, Teluglish, Tamglish)
5. Multilingual Decision Explanations (Hindi, Telugu, Tamil, English)
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

FIRST_NAMES = [
    "Ramesh", "Suresh", "Murugan", "Kavitha", "Priya", "Ananya", "Ramu", "Venkatesh",
    "Lakshmi", "Rajesh", "Manish", "Sunita", "Deepak", "Pooja", "Arun", "Selvakumar",
    "Muthu", "Satish", "Meena", "Geeta", "Balaji", "Subba Rao", "Gurpreet", "Harpreet",
    "Amit", "Sneha", "Kiran", "Vijay", "Rohit", "Anita", "Sita", "Govind", "Radha",
    "Chandra", "Devendra", "Manjula", "Srinivas", "Mallikarjun", "Basavaraj", "Santosh",
    "Alok", "Vandana", "Bhavani", "Pradeep", "Madhavi", "Naveen", "Jyothi", "Dhanraj",
]

LAST_NAMES = [
    "Kumar", "Patel", "Singh", "Sharma", "Devi", "Reddy", "Rao", "Gowda", "Nadar",
    "Pillai", "Yadav", "Verma", "Gupta", "Kaur", "Das", "Mishra", "Joshi", "Bose",
    "Patil", "Choudhury", "Mehta", "Naidu", "Iyer", "Menon", "Bhatt", "Mukherjee",
    "Hegde", "Bishnoi", "Tripathi", "Banerjee", "Chatterjee", "Mondal", "Solanki",
]

STATES_DISTRICTS = [
    ("Tamil Nadu", ["Thanjavur", "Madurai", "Salem", "Coimbatore", "Tiruchirappalli", "Dindigul"]),
    ("Andhra Pradesh", ["Guntur", "Krishna", "West Godavari", "Kurnool", "Anantapur", "Chittoor"]),
    ("Telangana", ["Warangal", "Nalgonda", "Karimnagar", "Khammam", "Medak", "Nizamabad"]),
    ("Uttar Pradesh", ["Varanasi", "Gorakhpur", "Meerut", "Prayagraj", "Bareilly", "Ayodhya"]),
    ("Maharashtra", ["Kolhapur", "Solapur", "Nashik", "Satara", "Amravati", "Pune"]),
    ("Karnataka", ["Mandya", "Hassan", "Belagavi", "Tumakuru", "Mysuru", "Dharwad"]),
    ("Punjab", ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda", "Gurdaspur"]),
    ("Bihar", ["Patna", "Gaya", "Muzaffarpur", "Bhagalpur", "Darbhanga", "Purnia"]),
    ("West Bengal", ["Bardhaman", "Murshidabad", "Nadia", "Hooghly", "Birbhum"]),
    ("Rajasthan", ["Jaipur", "Jodhpur", "Alwar", "Kota", "Bikaner", "Udaipur"]),
    ("Madhya Pradesh", ["Indore", "Bhopal", "Jabalpur", "Gwalior", "Ujjain", "Rewa"]),
    ("Gujarat", ["Mehsana", "Rajkot", "Surat", "Vadodara", "Bhavnagar", "Kheda"]),
    ("Odisha", ["Cuttack", "Balasore", "Ganjam", "Sambalpur", "Puri", "Bhadrak"]),
    ("Kerala", ["Palakkad", "Kozhikode", "Thrissur", "Kollam", "Kottayam"]),
    ("Haryana", ["Karnal", "Hisar", "Ambala", "Rohtak", "Sirsa", "Panipat"]),
]

BANKS = [
    ("State Bank of India", "SBIN0"),
    ("Punjab National Bank", "PUNB0"),
    ("Canara Bank", "CNRB0"),
    ("Bank of Baroda", "BARB0"),
    ("Union Bank of India", "UBIN0"),
    ("Indian Bank", "IDIB0"),
    ("Central Bank of India", "CBIN0"),
    ("Bank of India", "BKID0"),
    ("HDFC Bank", "HDFC0"),
    ("ICICI Bank", "ICIC0"),
    ("Kotak Mahindra Bank", "KKBK0"),
    ("Axis Bank", "UTIB0"),
]

SYSTEM_PROMPT = (
    "You are ADHIKAAR's structured fact extraction engine for Indian welfare schemes. "
    "Your job is to extract ONLY explicitly stated facts from the provided text into the "
    "requested JSON schema. If a requested field is not mentioned or cannot be verified from the "
    "text, you must set its value to null. Output strictly valid JSON with no markdown fences, "
    "no preamble, and no explanation."
)


def apply_ocr_noise(text: str, noise_level: float = 0.10) -> str:
    """Simulate realistic OCR imperfections (noisy chars, spacing, missing colons, watermarks)."""
    if random.random() > noise_level:
        return text

    replacements = {
        "O": "0", "0": "O",
        "I": "1", "1": "l",
        ":": " ",
        "-": " ",
        "B": "8",
    }
    chars = list(text)
    for idx in range(len(chars)):
        if chars[idx] in replacements and random.random() < 0.12:
            chars[idx] = replacements[chars[idx]]

    res = "".join(chars)
    if random.random() < 0.20:
        res = f"*** SAMPLE — NOT A REAL DOCUMENT ***\n{res}\n*** VERIFIED COPY ***"
    return res


def random_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


# --- Sample Generators ---

def sample_aadhaar() -> tuple[str, dict[str, Any]]:
    name = random_name()
    last4 = f"{random.randint(1000, 9999)}"
    dob_day = random.randint(1, 28)
    dob_month = random.randint(1, 12)
    dob_year = random.randint(1965, 2004)
    gender = random.choice(["Male", "Female"])
    state, districts = random.choice(STATES_DISTRICTS)
    district = random.choice(districts)
    pincode = random.randint(110001, 850000)

    ocr_text = apply_ocr_noise(
        f"GOVERNMENT OF INDIA\n"
        f"UNIQUE IDENTIFICATION AUTHORITY OF INDIA\n"
        f"Name: {name}\n"
        f"DOB: {dob_day:02d}/{dob_month:02d}/{dob_year}\n"
        f"Gender: {gender}\n"
        f"XXXX XXXX {last4}\n"
        f"Address: Dist {district}, {state} - {pincode}\n"
        f"Mera Aadhaar, Meri Pehchan"
    )
    target_keys = ["applicant_name", "aadhaar_last4"]
    expected = {"applicant_name": name, "aadhaar_last4": last4}
    prompt = (
        f"Source Type: aadhaar\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def sample_land_record() -> tuple[str, dict[str, Any]]:
    pattadar = random_name()
    state, districts = random.choice(STATES_DISTRICTS)
    district = random.choice(districts)
    khata_no = random.randint(101, 1500)
    survey_no = f"{random.randint(10, 550)}/{random.randint(1, 4)}"
    hectares = round(random.uniform(0.20, 4.50), 2)
    is_individual = random.random() > 0.12
    holder_type = "individual" if is_individual else "institutional"

    holder_line = (
        f"Pattadar: {pattadar}"
        if is_individual
        else f"Holder: Gram Panchayat of {district}"
    )
    ocr_text = apply_ocr_noise(
        f"REVENUE DEPARTMENT - GOVT OF {state.upper()}\n"
        f"EXTRACT OF REGISTER OF RIGHTS (ROR-1B / PATTA / BHULEKH)\n"
        f"District: {district} | Taluk: {district} Rural\n"
        f"Khata Number: {khata_no} | Survey No: {survey_no}\n"
        f"{holder_line}\n"
        f"Category: {'Individual Cultivator' if is_individual else 'Institutional Trust'}\n"
        f"Extent: {hectares} Hectares\n"
        f"Classification: Agricultural Dry/Wet Land"
    )
    target_keys = ["land_owned_hectares", "holder_type"]
    expected = {"land_owned_hectares": hectares, "holder_type": holder_type}
    prompt = (
        f"Source Type: land_record\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def sample_bank_passbook() -> tuple[str, dict[str, Any]]:
    holder_name = random_name()
    bank_name, ifsc_prefix = random.choice(BANKS)
    branch = random.choice(["Main Branch", "Market Branch", "Station Road", "Rural Branch", "Town Hall"])
    ifsc = f"{ifsc_prefix}{random.randint(100000, 999999)}"
    acc_len = random.choice([11, 12, 14])
    acc_no = "".join([str(random.randint(0, 9)) for _ in range(acc_len)])

    ocr_text = apply_ocr_noise(
        f"{bank_name.upper()}\n"
        f"Branch: {branch} | IFSC: {ifsc}\n"
        f"Account Holder: {holder_name}\n"
        f"Account No: {acc_no}\n"
        f"Type: Regular Savings Account\n"
        f"MICR: {random.randint(100000000, 999999999)}"
    )
    target_keys = ["bank_account_number", "bank_ifsc"]
    expected = {"bank_account_number": acc_no, "bank_ifsc": ifsc}
    prompt = (
        f"Source Type: bank_passbook\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def sample_income_cert() -> tuple[str, dict[str, Any]]:
    applicant = random_name()
    state, districts = random.choice(STATES_DISTRICTS)
    district = random.choice(districts)
    annual_income = random.choice([36000, 48000, 60000, 75000, 95000, 120000, 160000, 220000])
    cert_no = f"INC/{state[:2].upper()}/2024/{random.randint(100000, 999999)}"

    ocr_text = apply_ocr_noise(
        f"GOVERNMENT OF {state.upper()} - TALUK REVENUE OFFICE\n"
        f"INCOME CERTIFICATE - No: {cert_no}\n"
        f"This is to certify that annual family income of {applicant}, "
        f"resident of {district}, {state}, from all sources is Rs. {annual_income:,}/- per annum.\n"
        f"Issued by Tahsildar / Authorized Officer."
    )
    target_keys = ["family_income_annual"]
    expected = {"family_income_annual": float(annual_income)}
    prompt = (
        f"Source Type: income_certificate\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def sample_marksheet() -> tuple[str, dict[str, Any]]:
    student = random_name()
    state, _ = random.choice(STATES_DISTRICTS)
    percentage = round(random.uniform(55.0, 96.0), 1)

    ocr_text = apply_ocr_noise(
        f"STATE BOARD OF SECONDARY EDUCATION - {state.upper()}\n"
        f"SENIOR SECONDARY EXAMINATION SCORE CARD\n"
        f"Student Name: {student}\n"
        f"Roll No: REG{random.randint(100000, 999999)}\n"
        f"Aggregate Marks Percentage: {percentage}%\n"
        f"Result: PASSED FIRST CLASS"
    )
    target_keys = ["last_exam_percentage"]
    expected = {"last_exam_percentage": percentage}
    prompt = (
        f"Source Type: marksheet\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def sample_portal_field_recovery() -> tuple[str, dict[str, Any]]:
    """Task: Targeted single-field recovery when portal rejects initial payload."""
    field = random.choice(["bank_ifsc", "land_owned_hectares", "bank_account_number", "applicant_name"])
    if field == "bank_ifsc":
        bank_name, ifsc_prefix = random.choice(BANKS)
        ifsc = f"{ifsc_prefix}{random.randint(100000, 999999)}"
        doc_text = f"Customer passbook for {bank_name}. Branch Guntur. IFSC CODE is {ifsc}. Verified."
        prompt = (
            f"Source Type: portal_field_recovery\n"
            f"Target Field: bank_ifsc\n"
            f"Error Reason: INVALID_IFSC: IFSC code could not be verified by the portal\n\n"
            f"Document OCR Text:\n{doc_text}"
        )
        expected = {"bank_ifsc": ifsc}
    elif field == "land_owned_hectares":
        ha = round(random.uniform(0.5, 3.2), 2)
        doc_text = f"ROR-1B Patta record. Total cultivated land area is {ha} Hectares. Owner active."
        prompt = (
            f"Source Type: portal_field_recovery\n"
            f"Target Field: land_owned_hectares\n"
            f"Error Reason: INVALID_LAND_AREA: Land holding magnitude missing or unparsed\n\n"
            f"Document OCR Text:\n{doc_text}"
        )
        expected = {"land_owned_hectares": ha}
    elif field == "bank_account_number":
        acc = "".join([str(random.randint(0, 9)) for _ in range(12)])
        doc_text = f"Account statement header. Account Number: {acc}. State Bank of India."
        prompt = (
            f"Source Type: portal_field_recovery\n"
            f"Target Field: bank_account_number\n"
            f"Error Reason: INVALID_ACCOUNT: Account number did not match portal record\n\n"
            f"Document OCR Text:\n{doc_text}"
        )
        expected = {"bank_account_number": acc}
    else:
        name = random_name()
        doc_text = f"UIDAI Aadhaar Card. Resident Name: {name}. Year of Birth 1988."
        prompt = (
            f"Source Type: portal_field_recovery\n"
            f"Target Field: applicant_name\n"
            f"Error Reason: NAME_MISMATCH: Name mismatch with portal database\n\n"
            f"Document OCR Text:\n{doc_text}"
        )
        expected = {"applicant_name": name}

    return prompt, expected


def sample_out_of_domain_rejection() -> tuple[str, dict[str, Any]]:
    """Task: Hallucination guardrail rejecting non-welfare documents."""
    doc_type = random.choice(["electricity_bill", "driving_license", "restaurant_bill", "generic_selfie"])
    if doc_type == "electricity_bill":
        txt = (
            "STATE POWER DISTRIBUTION COMPANY LTD\n"
            f"Consumer No: {random.randint(1000000, 9999999)}\n"
            "Units Consumed: 142 kWh\n"
            f"Current Bill Amount: INR {random.randint(400, 2200)}.00\n"
            "Due Date: 15/11/2026"
        )
    elif doc_type == "driving_license":
        txt = (
            "TRANSPORT DEPARTMENT - DRIVING LICENCE\n"
            f"DL No: DL-{random.randint(10, 99)}-2018{random.randint(1000, 9999)}\n"
            "Authorised to drive: LMV, MCWG\n"
            "Valid Till: 24/09/2038"
        )
    elif doc_type == "restaurant_bill":
        txt = (
            "HOTEL ANNAPOORNA RESTAURANT - TAX INVOICE\n"
            "Table 4 | Guests: 2\n"
            "2 Masala Dosa: 160.00\n"
            "2 Filter Coffee: 60.00\n"
            "CGST + SGST (5%): 11.00\n"
            "Total Amount: INR 231.00 - Paid via UPI"
        )
    else:
        txt = "[Image of a personal portrait photograph / selfie taken with mobile camera - No readable text]"

    target_keys = ["applicant_name", "land_owned_hectares", "bank_account_number"]
    prompt = (
        f"Source Type: {doc_type}\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{txt}"
    )
    expected = {
        "is_valid_welfare_doc": False,
        "reason": "unsupported_document_type",
        "extracted_facts": {},
    }
    return prompt, expected


def sample_indic_codemixed_query() -> tuple[str, dict[str, Any]]:
    """Task: Transliterated / code-mixed citizen statements (Hinglish, Teluglish, Tamglish)."""
    lang = random.choice(["hinglish", "teluglish", "tamglish"])
    name = random_name()
    ha = round(random.uniform(0.6, 2.8), 2)
    state, districts = random.choice(STATES_DISTRICTS)
    dist = random.choice(districts)

    if lang == "hinglish":
        txt = (
            f"Namaste sir, mera naam {name} hai. Hum {dist}, {state} se hain. "
            f"Humare paas {ha} hectare khet hai aur family me koi bhi income tax nahi bharta. "
            f"PM Kisan aur kisan yojana ke liye apply karna hai."
        )
    elif lang == "teluglish":
        txt = (
            f"Namaskaram sir, naa peru {name}. Maadi {dist}, {state}. "
            f"Maaku {ha} hectares vyavasaya bhoomi undi. Maa intlo evaru income tax kattaru. "
            f"Rythu scheme benefit kavali sir."
        )
    else:
        txt = (
            f"Vanakkam sir, en peyar {name}. {dist}, {state} la irukken. "
            f"Engalukku {ha} hectare velanmai nilam irukku. Yarume income tax kattavillai. "
            f"Govt scheme ku apply panna vendum."
        )

    target_keys = ["applicant_name", "land_owned_hectares", "is_income_tax_payer"]
    prompt = (
        f"Source Type: voice_transcript_indic\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Citizen Transcript:\n{txt}"
    )
    expected = {
        "applicant_name": name,
        "land_owned_hectares": ha,
        "is_income_tax_payer": False,
    }
    return prompt, expected


def sample_explanation() -> tuple[str, dict[str, Any]]:
    """Task: Empathetic multilingual decision explanation generation with PII masked."""
    outcome = random.choice(["ELIGIBLE", "NOT_ELIGIBLE", "NEEDS_DOCUMENTS"])
    lang = random.choice(["en", "hi", "te", "ta"])

    if outcome == "ELIGIBLE":
        if lang == "hi":
            exp_text = "बधाई हो! आपका आवेदन स्वीकृत हो गया है। आपके भूमि और बैंक विवरण सत्यापित हो चुके हैं।"
        elif lang == "te":
            exp_text = "శుభవార్త! మీ దరఖాస్తు అర్హత పొందింది. మీ భూమి మరియు బ్యాంక్ వివరాలు విజయవంతంగా ధృవీకరించబడ్డాయి."
        elif lang == "ta":
            exp_text = "வாழ்த்துக்கள்! உங்கள் விண்ணப்பம் தகுதி பெற்றுள்ளது. உங்கள் நிலம் மற்றும் வங்கி விவரங்கள் சரிபார்க்கப்பட்டன."
        else:
            exp_text = "Good news! Your application is eligible. All landholding and bank details have been verified."
    elif outcome == "NOT_ELIGIBLE":
        if lang == "hi":
            exp_text = "योजना नियमों के अनुसार आपका आवेदन पात्र नहीं है, क्योंकि जोत सीमा या पात्रता शर्तें पूरी नहीं हुईं।"
        elif lang == "te":
            exp_text = "పథకం నిబంధనల ప్రకారం మీ దరఖాస్తు అర్హత పొందలేదు, ఎందుకంటే భూమి పరిమితి నిబంధనలకు అనుగుణంగా లేదు."
        elif lang == "ta":
            exp_text = "திட்ட விதிகளின்படி உங்கள் விண்ணப்பம் தகுதி பெறவில்லை, ஏனெனில் நில வரம்பு நிபந்தனைகள் பூர்த்தி செய்யப்படவில்லை."
        else:
            exp_text = "Your application is not eligible under scheme rules because the landholding exceeds the threshold."
    else:
        if lang == "hi":
            exp_text = "कृपया अपना बैंक पासबुक और भूमि दस्तावेज अपलोड करें ताकि आवेदन पूरा किया जा सके।"
        elif lang == "te":
            exp_text = "దయచేసి మీ బ్యాంక్ పాస్‌బుక్ మరియు భూమి పత్రాలను అప్‌లోడ్ చేసి దరఖాస్తును పూర్తి చేయండి."
        elif lang == "ta":
            exp_text = "விண்ணப்பத்தை நிறைவு செய்ய உங்கள் வங்கி பாஸ்புக் மற்றும் நில ஆவணங்களை பதிவேற்றவும்."
        else:
            exp_text = "Please upload your bank passbook and land record to complete your application."

    prompt = (
        f"Task: explain_outcome\n"
        f"Decision Outcome: {outcome}\n"
        f"Target Language: {lang}\n"
        f"Context: Applicant Murugan K, Aadhaar XXXX-XXXX-8942, Scheme: PM-Kisan"
    )
    expected = {
        "explanation": exp_text,
        "language": lang,
        "outcome": outcome,
    }
    return prompt, expected


def build_chatml_example(user_prompt: str, assistant_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": json.dumps(assistant_dict, ensure_ascii=False)},
        ]
    }


def generate_v3_dataset(count: int, seed: int = 42) -> list[dict[str, Any]]:
    random.seed(seed)
    generators = [
        (sample_aadhaar, 0.20),
        (sample_land_record, 0.20),
        (sample_bank_passbook, 0.15),
        (sample_income_cert, 0.10),
        (sample_marksheet, 0.05),
        (sample_portal_field_recovery, 0.10),
        (sample_out_of_domain_rejection, 0.08),
        (sample_indic_codemixed_query, 0.07),
        (sample_explanation, 0.05),
    ]

    samples: list[dict[str, Any]] = []
    funcs, weights = zip(*generators)

    for _ in range(count):
        gen_func = random.choices(funcs, weights=weights, k=1)[0]
        user_prompt, expected_dict = gen_func()
        samples.append(build_chatml_example(user_prompt, expected_dict))

    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ADHIKAAR v3 fine-tuning dataset.")
    parser.add_argument("--train-count", type=int, default=1200, help="Number of train samples")
    parser.add_argument("--val-count", type=int, default=250, help="Number of validation samples")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "ml_training" / "data",
        help="Target data directory",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    train_file = args.output_dir / "train_v3.jsonl"
    val_file = args.output_dir / "val_v3.jsonl"

    print(f"Generating {args.train_count} train samples to {train_file}...")
    train_data = generate_v3_dataset(args.train_count, seed=42)
    with open(train_file, "w", encoding="utf-8") as f:
        for row in train_data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Generating {args.val_count} validation samples to {val_file}...")
    val_data = generate_v3_dataset(args.val_count, seed=1337)
    with open(val_file, "w", encoding="utf-8") as f:
        for row in val_data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("Generation complete! Dataset ready for Llama 3.1-8B v3 fine-tuning.")


if __name__ == "__main__":
    main()
