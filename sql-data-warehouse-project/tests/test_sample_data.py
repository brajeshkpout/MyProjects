"""Sanity tests for the generated source files (standard library only).

Run:  python -m unittest discover -s tests -v
These tests run without SQL Server. They verify the file contract the bronze
loader relies on (headers, delimiters, line endings) and that the keys needed
by the silver/gold joins line up across CRM and ERP sources.
"""
import csv
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "datasets"

HEADERS = {
    "source_crm/cust_info.csv": ["cst_id", "cst_key", "cst_firstname", "cst_lastname",
                                 "cst_marital_status", "cst_gndr", "cst_create_date"],
    "source_crm/prd_info.csv": ["prd_id", "prd_key", "prd_nm", "prd_cost", "prd_line",
                                "prd_start_dt", "prd_end_dt"],
    "source_crm/sales_details.csv": ["sls_ord_num", "sls_prd_key", "sls_cust_id",
                                     "sls_order_dt", "sls_ship_dt", "sls_due_dt",
                                     "sls_sales", "sls_quantity", "sls_price"],
    "source_erp/cust_az12.csv": ["cid", "bdate", "gen"],
    "source_erp/loc_a101.csv": ["cid", "cntry"],
    "source_erp/px_cat_g1v2.csv": ["id", "cat", "subcat", "maintenance"],
}


def read(rel):
    with (DATA / rel).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class SourceFileContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Regenerate so the test also proves the generator works from a clean state.
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_sample_data.py")],
                       check=True, capture_output=True)

    def test_headers_match_bronze_column_order(self):
        for rel, expected in HEADERS.items():
            with (DATA / rel).open(encoding="utf-8") as f:
                self.assertEqual(f.readline().rstrip("\n").split(","), expected, rel)

    def test_lf_line_endings_only(self):
        for rel in HEADERS:
            self.assertNotIn(b"\r", (DATA / rel).read_bytes(), rel)

    def test_every_row_has_expected_field_count(self):
        for rel, expected in HEADERS.items():
            with (DATA / rel).open(newline="", encoding="utf-8") as f:
                for i, row in enumerate(csv.reader(f), 1):
                    self.assertEqual(len(row), len(expected), f"{rel} line {i}")

    def test_sales_volume_is_65k_plus(self):
        self.assertGreaterEqual(len(read("source_crm/sales_details.csv")), 65_000)

    def test_six_datasets_present(self):
        self.assertEqual(len(HEADERS), 6)
        for rel in HEADERS:
            self.assertTrue((DATA / rel).is_file(), rel)


class CrossSourceKeys(unittest.TestCase):
    def test_keys_join_across_sources(self):
        cust = {r["cst_key"]: r["cst_id"] for r in read("source_crm/cust_info.csv") if r["cst_id"]}
        cust_ids = set(cust.values())
        az = {r["cid"][3:] if r["cid"].startswith("NAS") else r["cid"]
              for r in read("source_erp/cust_az12.csv")}
        loc = {r["cid"].replace("-", "") for r in read("source_erp/loc_a101.csv")}
        self.assertTrue(set(cust) <= az, "CRM customers missing in ERP cust_az12")
        self.assertTrue(set(cust) <= loc, "CRM customers missing in ERP loc_a101")

        prd = read("source_crm/prd_info.csv")
        prd_keys = {r["prd_key"][6:] for r in prd}
        cat_ids = {r["id"] for r in read("source_erp/px_cat_g1v2.csv")}
        self.assertTrue({r["prd_key"][:5].replace("-", "_") for r in prd} <= cat_ids)

        for r in read("source_crm/sales_details.csv"):
            self.assertIn(r["sls_cust_id"], cust_ids)
            self.assertIn(r["sls_prd_key"], prd_keys)

    def test_injected_defects_exist(self):
        """The silver layer is only meaningful if the bronze data is actually dirty."""
        cust = read("source_crm/cust_info.csv")
        ids = [r["cst_id"] for r in cust if r["cst_id"]]
        self.assertGreater(len(ids), len(set(ids)), "expected duplicate customer ids")
        self.assertTrue(any(not r["cst_id"] for r in cust), "expected NULL customer ids")
        sales = read("source_crm/sales_details.csv")
        self.assertTrue(any(r["sls_order_dt"] == "0" for r in sales), "expected zero dates")
        self.assertTrue(any(not r["sls_price"] for r in sales), "expected NULL prices")


if __name__ == "__main__":
    unittest.main()
