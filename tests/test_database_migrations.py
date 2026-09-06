import unittest
import os
import re
import json

class TestDatabaseMigrations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.migrations_dir = os.path.join(cls.root_dir, "supabase", "migrations")
        cls.shared_dir = os.path.join(cls.root_dir, "packages", "shared")

        cls.all_sql = ""
        for f in sorted(os.listdir(cls.migrations_dir)):
            with open(os.path.join(cls.migrations_dir, f), "r", encoding="utf-8") as file:
                cls.all_sql += "\n" + file.read()

    def test_required_tables_exist(self):
        tables = [
            "projects", "submissions", "evaluation_runs", "evaluation_modules",
            "criterion_scores", "evidence", "research_results", "reports",
            "scoring_rubrics", "rubric_categories"
        ]
        for table in tables:
            pattern = rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{table}\s*\("
            self.assertRegex(self.all_sql, pattern, f"Table {table} must be declared in migrations.")

    def test_evaluation_runs_fields(self):
        required = ["rubric_version", "overall_score", "status", "started_at", "completed_at", "error_information"]
        match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?evaluation_runs\s*\((.*?)\);", self.all_sql, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(match, "evaluation_runs table body must exist")
        body = match.group(1)
        for field in required:
            self.assertRegex(body, rf"\b{field}\b", f"Field {field} must exist in evaluation_runs")

    def test_evaluation_modules_fields(self):
        required = ["module_name", "status", "score", "max_score", "confidence", "started_at", "completed_at", "error_information"]
        match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?evaluation_modules\s*\((.*?)\);", self.all_sql, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(match, "evaluation_modules table body must exist")
        body = match.group(1)
        for field in required:
            self.assertRegex(body, rf"\b{field}\b", f"Field {field} must exist in evaluation_modules")

    def test_evidence_fields(self):
        required = ["evidence_type", "source", "metric", "value", "interpretation", "raw_data", "citation_reference", "timestamp"]
        match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?evidence\s*\((.*?)\);", self.all_sql, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(match, "evidence table body must exist")
        body = match.group(1)
        for field in required:
            self.assertRegex(body, rf"\b{field}\b", f"Field {field} must exist in evidence")

    def test_research_results_fields(self):
        required = ["query", "title", "url", "source", "similarity_assessment", "relevance", "summary"]
        match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?research_results\s*\((.*?)\);", self.all_sql, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(match, "research_results table body must exist")
        body = match.group(1)
        for field in required:
            self.assertRegex(body, rf"\b{field}\b", f"Field {field} must exist in research_results")

    def test_category_weights_sum_to_100(self):
        weight_matches = re.findall(r"\(\s*'1\.0\.0',\s*'([^']+)',\s*'([^']+)',\s*'([^']*)',\s*([0-9.]+)", self.all_sql)
        self.assertEqual(len(weight_matches), 10, "Must seed exactly 10 categories for v1.0.0")
        total_sql_weight = sum(float(m[3]) for m in weight_matches)
        self.assertAlmostEqual(total_sql_weight, 100.00, places=2, msg="SQL category weights must sum to 100.00")

    def test_json_weights_sum_to_100(self):
        weights_json_path = os.path.join(self.shared_dir, "weights.v1.json")
        with open(weights_json_path, "r", encoding="utf-8") as f:
            weights_data = json.load(f)
        total_json_weight = sum(cat["weight"] for cat in weights_data["categories"].values())
        self.assertEqual(total_json_weight, 100, "packages/shared/weights.v1.json must sum to 100")

    def test_no_hardcoded_secrets(self):
        suspicious = [r"api_key\s*=", r"secret\s*=", r"service_role_key\s*=", r"password\s*="]
        for pattern in suspicious:
            self.assertNotRegex(self.all_sql, pattern, "No credentials or secrets in database migrations")

if __name__ == "__main__":
    unittest.main()
