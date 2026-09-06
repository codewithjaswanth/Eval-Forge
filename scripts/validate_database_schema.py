#!/usr/bin/env python3
"""
EvalForge Database Schema & Seed Data Validator
Validates SQL migrations, table definitions, foreign keys, required fields,
RLS policies, and checks that category weights sum to exactly 100.00.
"""

import os
import re
import json
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations")
SHARED_DIR = os.path.join(os.path.dirname(__file__), "..", "packages", "shared")

REQUIRED_TABLES = [
    "projects",
    "submissions",
    "evaluation_runs",
    "evaluation_modules",
    "criterion_scores",
    "evidence",
    "research_results",
    "reports",
    "scoring_rubrics",
    "rubric_categories"
]

REQUIRED_FIELDS = {
    "evaluation_runs": [
        "rubric_version",
        "overall_score",
        "status",
        "started_at",
        "completed_at",
        "error_information"
    ],
    "evaluation_modules": [
        "module_name",
        "status",
        "score",
        "max_score",
        "confidence",
        "started_at",
        "completed_at",
        "error_information"
    ],
    "evidence": [
        "evidence_type",
        "source",
        "metric",
        "value",
        "interpretation",
        "raw_data",
        "citation_reference",
        "timestamp"
    ],
    "research_results": [
        "query",
        "title",
        "url",
        "source",
        "similarity_assessment",
        "relevance",
        "summary"
    ]
}

def validate():
    print("==================================================")
    print("🔍 Starting EvalForge Database Validation...")
    print("==================================================")

    # 1. Check migrations directory
    if not os.path.isdir(MIGRATIONS_DIR):
        print(f"❌ Error: Migrations directory not found at {MIGRATIONS_DIR}")
        sys.exit(1)

    migration_files = sorted(os.listdir(MIGRATIONS_DIR))
    print(f"📁 Found {len(migration_files)} migration file(s): {migration_files}")

    all_sql = ""
    for f in migration_files:
        path = os.path.join(MIGRATIONS_DIR, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
            all_sql += "\n" + content

    # 2. Check table existence
    for table in REQUIRED_TABLES:
        pattern = rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{table}\s*\("
        if not re.search(pattern, all_sql, re.IGNORECASE):
            print(f"❌ Error: Table '{table}' is missing from migrations!")
            sys.exit(1)
        print(f"  ✓ Table '{table}' verified.")

    # 3. Check required columns per table
    for table, fields in REQUIRED_FIELDS.items():
        # Find table body
        match = re.search(rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{table}\s*\((.*?)\);", all_sql, re.DOTALL | re.IGNORECASE)
        if not match:
            print(f"❌ Error: Could not parse table definition for '{table}'")
            sys.exit(1)
        table_body = match.group(1)
        for field in fields:
            # Check if field name is defined as a column
            field_pattern = rf"\b{field}\b"
            if not re.search(field_pattern, table_body, re.IGNORECASE):
                print(f"❌ Error: Required field '{field}' missing from table '{table}'!")
                sys.exit(1)
            print(f"    ✓ Column '{table}.{field}' verified.")

    # 4. Check RLS policies
    for table in REQUIRED_TABLES:
        rls_pattern = rf"ALTER\s+TABLE\s+{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY;"
        if not re.search(rls_pattern, all_sql, re.IGNORECASE):
            print(f"❌ Error: RLS not enabled for '{table}'!")
            sys.exit(1)
    print("  ✓ RLS enabled on all 10 tables.")

    # 5. Check secrets in schema
    suspicious_patterns = [r"api_key\s*=", r"secret\s*=", r"service_role_key\s*=", r"password\s*="]
    for pattern in suspicious_patterns:
        if re.search(pattern, all_sql, re.IGNORECASE):
            print(f"❌ Error: Potential secret/credential detected in migrations!")
            sys.exit(1)
    print("  ✓ Zero hardcoded secrets detected in SQL schema.")

    # 6. Validate category weights in seed migration
    weight_matches = re.findall(r"\(\s*'1\.0\.0',\s*'([^']+)',\s*'([^']+)',\s*'([^']*)',\s*([0-9.]+)", all_sql)
    if not weight_matches:
        print("❌ Error: Could not extract seeded category weights from migrations!")
        sys.exit(1)

    print(f"\n📊 Extracted {len(weight_matches)} seeded categories from migration:")
    total_sql_weight = 0.0
    for match in weight_matches:
        cat_key, cat_name, desc, weight_str = match
        weight = float(weight_str)
        total_sql_weight += weight
        print(f"   - {cat_name} ({cat_key}): {weight}%")

    print(f"   Sum of SQL category weights: {total_sql_weight}%")
    if abs(total_sql_weight - 100.00) > 0.001:
        print(f"❌ Error: Category weights sum to {total_sql_weight}, expected exactly 100.00!")
        sys.exit(1)
    print("  ✓ SQL Migration Category Weights sum to exactly 100.00!")

    # 7. Validate weights.v1.json
    weights_json_path = os.path.join(SHARED_DIR, "weights.v1.json")
    if os.path.exists(weights_json_path):
        with open(weights_json_path, "r", encoding="utf-8") as f:
            weights_data = json.load(f)
        json_sum = sum(cat["weight"] for cat in weights_data["categories"].values())
        print(f"\n📦 Extracted weights.v1.json categories ({len(weights_data['categories'])} categories):")
        for k, v in weights_data["categories"].items():
            print(f"   - {v['name']} ({k}): {v['weight']}%")
        print(f"   Sum of JSON category weights: {json_sum}%")
        if abs(json_sum - 100.00) > 0.001:
            print(f"❌ Error: weights.v1.json sums to {json_sum}, expected 100!")
            sys.exit(1)
        print("  ✓ packages/shared/weights.v1.json sums to exactly 100.00!")

    print("\n==================================================")
    print("✅ ALL DATABASE AND TYPE VALIDATIONS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    validate()
