"""Synthetic dataset generator for fine-tuning LLMs on structured welfare fact extraction.

Generates realistic ChatML/OpenAI JSONL training examples matching ADHIKAAR scheme schemas
(PM-Kisan and State Scholarship). Uses zero real citizen PII; produces domain-authentic
simulated OCR text, voice transcripts, and ground-truth JSON outputs across 15 Indian states.
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
    "Alok", "Vandana", "Bhavani", "Pradeep", "Madhavi", "Naveen", "Jyothi", "Dhanraj"
]

LAST_NAMES = [
    "Kumar", "Patel", "Singh", "Sharma", "Devi", "Reddy", "Rao", "Gowda", "Nadar",
    "Pillai", "Yadav", "Verma", "Gupta", "Kaur", "Das", "Mishra", "Joshi", "Bose",
    "Patil", "Choudhury", "Mehta", "Naidu", "Iyer", "Menon", "Bhatt", "Mukherjee",
    "Hegde", "Bishnoi", "Tripathi", "Banerjee", "Chatterjee", "Mondal", "Solanki"
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


def apply_ocr_noise(text: str, noise_level: float = 0.08) -> str:
    """Simulate realistic OCR imperfections (noisy chars, spacing, missing colons)."""
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
        if chars[idx] in replacements and random.random() < 0.15:
            chars[idx] = replacements[chars[idx]]
    return "".join(chars)


def random_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def make_aadhaar_sample() -> tuple[str, dict[str, Any]]:
    name = random_name()
    last4 = f"{random.randint(1000, 9999)}"
    dob_day = random.randint(1, 28)
    dob_month = random.randint(1, 12)
    dob_year = random.randint(1965, 2004)
    gender = random.choice(["Male", "Female"])
    state, districts = random.choice(STATES_DISTRICTS)
    district = random.choice(districts)
    pincode = random.randint(110001, 850000)
    father_name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

    ocr_layouts = [
        (
            f"GOVERNMENT OF INDIA\n"
            f"UNIQUE IDENTIFICATION AUTHORITY OF INDIA\n"
            f"Name: {name}\n"
            f"DOB: {dob_day:02d}/{dob_month:02d}/{dob_year}\n"
            f"Gender: {gender}\n\n"
            f"XXXX XXXX {last4}\n"
            f"VID: {random.randint(1000, 9999)} {random.randint(1000, 9999)} "
            f"{random.randint(1000, 9999)} {random.randint(1000, 9999)}\n"
            f"Address: S/O {father_name}, Vill Rampur, Dist {district}, {state} - {pincode}"
        ),
        (
            f"BHARAT SARKAR - ENROLMENT COPY\n"
            f"Enrolment No: 1024/{random.randint(10000, 99999)}/09124\n"
            f"To: {name}\n"
            f"Birth Date: {dob_day:02d}-{dob_month:02d}-{dob_year}\n"
            f"Sex: {gender}\n"
            f"Aadhaar Number: {random.randint(2000, 9999)} {random.randint(1000, 9999)} {last4}\n"
            f"Address: Near Primary School, {district}, {state}\n"
            f"Mera Aadhaar, Meri Pehchan"
        ),
        (
            f"UIDAI E-AADHAAR LETTER\n"
            f"Resident Name: {name}\n"
            f"Year of Birth: {dob_year}\n"
            f"Gender: {gender}\n"
            f"Card Number: **** **** {last4}\n"
            f"State: {state}"
        ),
    ]

    text = apply_ocr_noise(random.choice(ocr_layouts))
    target_keys = ["applicant_name", "aadhaar_last4"]
    expected = {
        "applicant_name": name,
        "aadhaar_last4": last4,
    }
    prompt = (
        f"Source Type: aadhaar\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{text}"
    )
    return prompt, expected


def make_land_record_sample() -> tuple[str, dict[str, Any]]:
    pattadar = random_name()
    state, districts = random.choice(STATES_DISTRICTS)
    district = random.choice(districts)
    khata_no = random.randint(101, 1500)
    subdiv = random.choice(["A", "B", "C", "/1", "/2A", ""])
    survey_no = f"{random.randint(10, 550)}{subdiv}"
    hectares = round(random.uniform(0.20, 4.50), 2)
    is_individual = random.random() > 0.12
    holder_type = "individual" if is_individual else "institutional"

    header = f"REVENUE DEPARTMENT - GOVT OF {state.upper()}\n"
    if is_individual:
        holder_line = f"Pattadar Name: {pattadar}\nHolder Category: Individual Cultivator"
    else:
        holder_line = (
            f"Pattadar Name: Gram Panchayat / Trust of {district}\nHolder Category: Institutional"
        )

    ocr_layouts = [
        (
            f"{header}"
            f"EXTRACT OF REGISTER OF RIGHTS (ROR-1B / PATTA)\n"
            f"District: {district} | Taluk/Mandal: {district} Rural\n"
            f"Khata Number: {khata_no}\n"
            f"Survey/Subdivision Number: {survey_no}\n"
            f"{holder_line}\n"
            f"Classification: Agricultural Dry/Wet Land\n"
            f"Total Extent: {hectares} Hectares\n"
            f"Status: Clear Title, Mutation Completed"
        ),
        (
            f"BHULEKH PORTAL - KHASRA KHATAUNI EXTRACT\n"
            f"State: {state} | District: {district}\n"
            f"Account Khata No: {khata_no}\n"
            f"Plot No: {survey_no}\n"
            f"Tenant/Owner: {pattadar if is_individual else 'Public Trust'}\n"
            f"Land Extent in Hectare: {hectares}\n"
            f"Land Holding Nature: {'Individual' if is_individual else 'Institutional'}\n"
            f"Remarks: Freehold"
        ),
    ]

    ocr_text = apply_ocr_noise(random.choice(ocr_layouts))
    target_keys = ["land_owned_hectares", "holder_type"]
    expected = {
        "land_owned_hectares": hectares,
        "holder_type": holder_type,
    }
    prompt = (
        f"Source Type: land_record\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def make_bank_passbook_sample() -> tuple[str, dict[str, Any]]:
    holder_name = random_name()
    bank_name, ifsc_prefix = random.choice(BANKS)
    branches = ["Main Branch", "Town Hall", "Station Road", "Bazaar Branch", "Rural Branch", "MIDC"]
    branch = random.choice(branches)
    ifsc = f"{ifsc_prefix}{random.randint(100000, 999999)}"
    acc_len = random.choice([11, 12, 14, 16])
    acc_no = "".join([str(random.randint(0, 9)) for _ in range(acc_len)])

    ocr_layouts = [
        (
            f"{bank_name.upper()}\n"
            f"Branch: {branch}\n"
            f"IFSC Code: {ifsc} | MICR: {random.randint(100000000, 999999999)}\n"
            f"Customer ID: CIF{random.randint(1000000, 9999999)}\n"
            f"Account Name: {holder_name}\n"
            f"Account Number: {acc_no}\n"
            f"Account Type: Regular Savings Bank (SB)\n"
            f"Nominee Registered: YES\n"
            f"Passbook Issue Date: 12-04-2023"
        ),
        (
            f"CUSTOMER ACCOUNT STATEMENT / PASSBOOK\n"
            f"Bank: {bank_name}\n"
            f"A/c Title: {holder_name}\n"
            f"Account No.: {acc_no}\n"
            f"RTGS/NEFT IFSC: {ifsc}\n"
            f"Branch Address: {branch}, City\n"
            f"Clear Balance: INR {random.randint(500, 45000)}.00"
        ),
    ]

    ocr_text = apply_ocr_noise(random.choice(ocr_layouts))
    target_keys = ["bank_account_number", "bank_ifsc"]
    expected = {
        "bank_account_number": acc_no,
        "bank_ifsc": ifsc,
    }
    prompt = (
        f"Source Type: bank_passbook\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def make_income_cert_sample() -> tuple[str, dict[str, Any]]:
    applicant = random_name()
    state, districts = random.choice(STATES_DISTRICTS)
    district = random.choice(districts)
    incomes = [36000, 48000, 60000, 75000, 90000, 110000, 140000, 180000, 220000, 280000]
    annual_income = random.choice(incomes)
    yr = random.randint(2023, 2024)
    seq = random.randint(100000, 999999)
    cert_no = f"INC/{state[:2].upper()}/{yr}/{seq}"

    ocr_text = (
        f"GOVERNMENT OF {state.upper()}\n"
        f"REVENUE ADMINISTRATION - TALUK OFFICE, {district.upper()}\n"
        f"INCOME CERTIFICATE\n"
        f"Certificate Identification: {cert_no}\n"
        f"This is to certify on careful inquiry that the annual income of "
        f"{applicant}, residing at Ward {random.randint(1, 15)}, {district}, "
        f"from all legal sources is Rs. {annual_income:,}/- per annum.\n"
        f"Purpose: For educational scholarship / government assistance.\n"
        f"Tahsildar / Authorized Revenue Officer Signature & Seal"
    )

    ocr_text = apply_ocr_noise(ocr_text)
    target_keys = ["family_income_annual"]
    expected = {
        "family_income_annual": float(annual_income),
    }
    prompt = (
        f"Source Type: income_certificate\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def make_marksheet_sample() -> tuple[str, dict[str, Any]]:
    student = random_name()
    state, districts = random.choice(STATES_DISTRICTS)
    roll_no = f"REG{random.randint(2023, 2024)}{random.randint(10000, 99999)}"
    percentage = round(random.uniform(52.0, 96.5), 1)

    ocr_text = (
        f"STATE BOARD OF SECONDARY & HIGHER EDUCATION - {state.upper()}\n"
        f"SENIOR SECONDARY EXAMINATION SCORE CARD\n"
        f"Candidate Name: {student}\n"
        f"Roll / Hall Ticket No: {roll_no}\n"
        f"Language I: {random.randint(60, 95)}/100\n"
        f"Language II: {random.randint(55, 95)}/100\n"
        f"Core Subject 1: {random.randint(50, 100)}/100\n"
        f"Core Subject 2: {random.randint(50, 100)}/100\n"
        f"Core Subject 3: {random.randint(50, 100)}/100\n"
        f"Aggregate Percentage: {percentage}%\n"
        f"Result Classification: PASSED"
    )

    ocr_text = apply_ocr_noise(ocr_text)
    target_keys = ["last_exam_percentage"]
    expected = {
        "last_exam_percentage": percentage,
    }
    prompt = (
        f"Source Type: marksheet\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Document OCR Text:\n{ocr_text}"
    )
    return prompt, expected


def make_declaration_sample() -> tuple[str, dict[str, Any]]:
    target = random.choice(["is_income_tax_payer", "institution_recognized"])

    if target == "is_income_tax_payer":
        scenario = random.choice(["explicit_false", "explicit_true", "omitted"])
        if scenario == "explicit_false":
            transcript = random.choice([
                "Namaste sir, I am a small farmer. Nobody in my family pays any income tax.",
                "Sir my father is a farmer and we have 2 acres land. We do not pay income tax.",
                "Vanakkam, cultivating groundnut on 1 acre land. No income tax paid by my family.",
                "Sir, we are rural cultivators, no one is an income tax payer in our household.",
            ])
            expected = {"is_income_tax_payer": False}
        elif scenario == "explicit_true":
            transcript = random.choice([
                "Sir my brother has a job in city and pays annual income tax on his salary.",
                "We pay income tax every year since we have a commercial shop in town.",
                "Yes sir, my father files ITR and pays income tax every assessment year.",
            ])
            expected = {"is_income_tax_payer": True}
        else:
            transcript = random.choice([
                "Hello sir, I have uploaded my Aadhaar and land passbook for PM-Kisan.",
                "Sir I want to apply for PM-Kisan scheme. Here is my land document.",
                "Greetings. Attached are my farm papers and Aadhaar for the farmer support scheme.",
                "Please submit my application for PM Kisan benefit.",
            ])
            expected = {"is_income_tax_payer": None}
        target_keys = ["is_income_tax_payer"]

    else:
        scenario = random.choice(["explicit_true", "explicit_false", "omitted"])
        if scenario == "explicit_true":
            transcript = random.choice([
                "Sir, I am enrolled in Government Degree College which is fully UGC recognized.",
                "I am studying in an AICTE approved government engineering college in Hyderabad.",
                "The college is an accredited university constituent college.",
            ])
            expected = {"institution_recognized": True}
        elif scenario == "explicit_false":
            transcript = random.choice([
                "Sir, I am doing an unaccredited private computer diploma course in town.",
                "I am studying in an unapproved private center for distance coaching.",
                "This coaching academy is not officially affiliated with any board.",
            ])
            expected = {"institution_recognized": False}
        else:
            transcript = random.choice([
                "Sir, please check my income certificate and marksheet for the scholarship.",
                "I have scored 82 percent in my 12th exam. Here is my application for fee support.",
                "Please review my marksheet for the state educational scholarship.",
            ])
            expected = {"institution_recognized": None}
        target_keys = ["institution_recognized"]

    prompt = (
        f"Source Type: declaration\n"
        f"Target Keys: {json.dumps(target_keys)}\n\n"
        f"Citizen Voice Transcript:\n{transcript}"
    )
    return prompt, expected


def build_chatml_example(user_prompt: str, assistant_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": json.dumps(assistant_dict, ensure_ascii=False)},
        ]
    }


def generate_dataset(total_count: int, seed: int = 42) -> list[dict[str, Any]]:
    random.seed(seed)
    generators = [
        make_aadhaar_sample,
        make_land_record_sample,
        make_bank_passbook_sample,
        make_income_cert_sample,
        make_marksheet_sample,
        make_declaration_sample,
    ]

    samples: list[dict[str, Any]] = []
    for _ in range(total_count):
        gen = random.choice(generators)
        prompt, expected = gen()
        samples.append(build_chatml_example(prompt, expected))

    random.shuffle(samples)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ChatML JSONL dataset for Llama-3-8B fine-tuning."
    )
    parser.add_argument("--train-size", type=int, default=1000, help="Number of training examples")
    parser.add_argument("--val-size", type=int, default=200, help="Number of validation examples")
    parser.add_argument(
        "--out-dir", type=str, default="ml_training/data", help="Output directory for jsonl files"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(
        f"Generating {args.train_size} train and {args.val_size} val examples across 15 states..."
    )
    train_data = generate_dataset(args.train_size, seed=args.seed)
    val_data = generate_dataset(args.val_size, seed=args.seed + 100)

    train_file = out_path / "train.jsonl"
    val_file = out_path / "val.jsonl"

    with open(train_file, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(val_file, "w", encoding="utf-8") as f:
        for item in val_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] Saved {len(train_data)} train examples to {train_file}")
    print(f"[OK] Saved {len(val_data)} val examples to {val_file}")


if __name__ == "__main__":
    main()
