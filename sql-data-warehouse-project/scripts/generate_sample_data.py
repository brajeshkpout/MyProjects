#!/usr/bin/env python3
"""Generate synthetic CRM and ERP source files for the SQL Data Warehouse project.

Deterministic (fixed seed). Uses only the Python standard library.
Deliberately injects data-quality problems (duplicates, NULL keys, stray
whitespace, coded values, invalid dates, inconsistent sales math) so the
bronze -> silver cleansing logic has real work to do.

Usage:  python scripts/generate_sample_data.py
"""
import csv
import random
import string
from datetime import date, timedelta
from pathlib import Path

SEED = 42
N_CUSTOMERS = 18_000
N_PRODUCTS = 300
N_SALES_LINES = 65_400
OUT = Path(__file__).resolve().parent.parent / "datasets"

# ERP category reference: id -> (category, subcategory, maintenance)
CATEGORIES = {
    "AC_BR": ("Accessories", "Bike Racks", "No"),
    "AC_BC": ("Accessories", "Bottles and Cages", "No"),
    "AC_HE": ("Accessories", "Helmets", "No"),
    "BI_MB": ("Bikes", "Mountain Bikes", "No"),
    "BI_RB": ("Bikes", "Road Bikes", "No"),
    "BI_TB": ("Bikes", "Touring Bikes", "No"),
    "CL_GL": ("Clothing", "Gloves", "No"),
    "CL_JE": ("Clothing", "Jerseys", "No"),
    "CL_SH": ("Clothing", "Shorts", "No"),
    "CO_PE": ("Components", "Pedals", "Yes"),
    "CO_RF": ("Components", "Road Frames", "Yes"),
    "CO_WH": ("Components", "Wheels", "Yes"),
}
BIKE_LINE = {"BI_MB": "M", "BI_RB": "R", "BI_TB": "T"}
FIRST = ["Jon", "Eugene", "Ruben", "Christy", "Elizabeth", "Julio", "Janet", "Marco", "Rob",
         "Shannon", "Jacquelyn", "Curtis", "Lauren", "Ian", "Sydney", "Chloe", "Wyatt",
         "Clarence", "Luke", "Jordan", "Destiny", "Ethan", "Seth", "Russell"]
LAST = ["Yang", "Huang", "Torres", "Zhu", "Johnson", "Ruiz", "Alvarez", "Mehta", "Verhoff",
        "Carlson", "Suarez", "Lu", "Walker", "Jenkins", "Bennett", "Young", "Hill", "Wood",
        "Sanchez", "Diaz", "Ross", "Ward", "Gray", "Perez", "Watson"]
COLORS = ["Red", "Black", "Blue", "Silver", "Yellow", "White"]
COUNTRY_CHOICES = (["Australia"] * 25 + ["United States"] * 12 + ["US"] * 6 + ["USA"] * 6 +
                   ["Germany"] * 10 + ["DE"] * 5 + ["Canada"] * 14 + ["France"] * 10 +
                   ["United Kingdom"] * 12)


def write_csv(path, header, rows):
    """Write a comma-delimited, LF-terminated, header-first CSV (None -> empty field)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def main():
    rng = random.Random(SEED)

    def messy(s):
        x = rng.random()
        return f" {s}" if x < 0.03 else (f"{s} " if x < 0.06 else s)

    # ---------------- customers ----------------
    customers = []
    for i in range(N_CUSTOMERS):
        cid = 11000 + i
        customers.append({
            "id": cid, "key": f"AW{cid:08d}",
            "first": rng.choice(FIRST), "last": rng.choice(LAST),
            "marital": rng.choice("SM"), "gndr": rng.choice("MF"),
            "created": date(2019, 1, 1) + timedelta(days=rng.randint(0, 2400)),
        })
    cust_rows = []
    for c in customers:
        cust_rows.append([
            c["id"], c["key"], messy(c["first"]), messy(c["last"]),
            None if rng.random() < 0.02 else c["marital"],
            None if rng.random() < 0.015 else c["gndr"],
            c["created"].isoformat(),
        ])
    # stale duplicate rows (older create date) -> silver must keep the latest
    for c in rng.sample(customers, 300):
        cust_rows.append([
            c["id"], c["key"], c["first"], c["last"], rng.choice("SM"), c["gndr"],
            (c["created"] - timedelta(days=rng.randint(30, 400))).isoformat(),
        ])
    # rows with NULL customer id -> silver must drop them
    for _ in range(30):
        cust_rows.append([None, None, rng.choice(FIRST), rng.choice(LAST), None, None,
                          date(2024, 1, 1).isoformat()])
    rng.shuffle(cust_rows)
    write_csv(OUT / "source_crm" / "cust_info.csv",
              ["cst_id", "cst_key", "cst_firstname", "cst_lastname",
               "cst_marital_status", "cst_gndr", "cst_create_date"], cust_rows)

    # ---------------- products ----------------
    letters = string.ascii_uppercase
    used, products = set(), []
    cat_ids = list(CATEGORIES)
    while len(products) < N_PRODUCTS:
        cat = rng.choice(cat_ids)
        suffix = (f"{rng.choice(letters)}{rng.choice(letters)}-{rng.choice(letters)}"
                  f"{rng.randint(10, 99)}{rng.choice(letters)}-{rng.randint(38, 62)}")
        if suffix in used:
            continue
        used.add(suffix)
        line = BIKE_LINE.get(cat, rng.choice(["M", "R", "S", "T", None]))
        sub = CATEGORIES[cat][1]
        products.append({
            "cat": cat, "suffix": suffix, "line": line,
            "name": f"{sub} {rng.choice(COLORS)} {suffix[-2:]}",
            "base_cost": rng.randint(10, 1500), "price": rng.randint(8, 3500),
        })
    prd_rows, prd_id = [], 210
    for p in products:
        n_versions = rng.choices([1, 2, 3], [0.5, 0.35, 0.15])[0]
        starts = [date(2010, 1, 1) + timedelta(days=rng.randint(0, 1000))]
        for _ in range(n_versions - 1):
            starts.append(starts[-1] + timedelta(days=rng.randint(200, 500)))
        for v, s in enumerate(starts):
            if v == len(starts) - 1:
                end = None
            elif rng.random() < 0.2:
                end = s - timedelta(days=30)          # dirty: end before start
            else:
                end = starts[v + 1] - timedelta(days=1)
            cost = None if rng.random() < 0.03 else round(p["base_cost"] * (1 + 0.1 * v))
            line = p["line"]
            if line and rng.random() < 0.05:
                line = f" {line}"                     # dirty: leading space
            prd_rows.append([
                prd_id, f"{p['cat'].replace('_', '-')}-{p['suffix']}", p["name"], cost, line,
                s.isoformat(), end.isoformat() if end else None,
            ])
            prd_id += 1
    rng.shuffle(prd_rows)
    write_csv(OUT / "source_crm" / "prd_info.csv",
              ["prd_id", "prd_key", "prd_nm", "prd_cost", "prd_line",
               "prd_start_dt", "prd_end_dt"], prd_rows)

    # ---------------- sales ----------------
    cust_ids = [c["id"] for c in customers]
    sales_rows, order_no = [], 43697
    while len(sales_rows) < N_SALES_LINES:
        ord_num = f"SO{order_no}"
        order_no += 1
        odt = date(2010, 12, 29) + timedelta(days=rng.randint(0, 1126))
        cust = rng.choice(cust_ids)
        for _ in range(rng.choice([1, 1, 2, 3])):
            if len(sales_rows) >= N_SALES_LINES:
                break
            p = rng.choice(products)
            qty = rng.choices([1, 2, 3, 4], [0.8, 0.12, 0.05, 0.03])[0]
            price = p["price"]
            sales = qty * price
            o = int(odt.strftime("%Y%m%d"))
            sh = int((odt + timedelta(days=7)).strftime("%Y%m%d"))
            du = int((odt + timedelta(days=12)).strftime("%Y%m%d"))
            r = rng.random()
            if r < 0.02:
                o = 0                                   # dirty: zero date
            elif r < 0.023:
                o = o // 10                             # dirty: 7-digit date
            r = rng.random()                            # at most ONE money defect per row
            if r < 0.015:
                sales = None
            elif r < 0.025:
                sales = rng.choice([0, -sales])
            elif r < 0.035:
                sales = sales + rng.randint(1, 50)      # inconsistent with qty*price
            elif r < 0.045:
                price = None
            elif r < 0.055:
                price = -price
            sales_rows.append([ord_num, p["suffix"], cust, o, sh, du, sales, qty, price])
    write_csv(OUT / "source_crm" / "sales_details.csv",
              ["sls_ord_num", "sls_prd_key", "sls_cust_id", "sls_order_dt", "sls_ship_dt",
               "sls_due_dt", "sls_sales", "sls_quantity", "sls_price"], sales_rows)

    # ---------------- ERP ----------------
    az_rows, loc_rows = [], []
    for c in customers:
        cid = ("NAS" if rng.random() < 0.3 else "") + c["key"]
        if rng.random() < 0.005:
            bd = date(rng.randint(2028, 2040), 1, 1)    # dirty: birthdate in the future
        else:
            bd = date(1940, 1, 1) + timedelta(days=rng.randint(0, 24 * 365))
        gen = rng.choice(["Male", "M"] if c["gndr"] == "M" else ["Female", "F"])
        if rng.random() < 0.05:
            gen = rng.choice(["", None])
        az_rows.append([cid, bd.isoformat(), gen])
        cntry = None if rng.random() < 0.03 else rng.choice(COUNTRY_CHOICES)
        loc_rows.append([f"AW-{c['id']:08d}", cntry])
    write_csv(OUT / "source_erp" / "cust_az12.csv", ["cid", "bdate", "gen"], az_rows)
    write_csv(OUT / "source_erp" / "loc_a101.csv", ["cid", "cntry"], loc_rows)
    write_csv(OUT / "source_erp" / "px_cat_g1v2.csv", ["id", "cat", "subcat", "maintenance"],
              [[k, *v] for k, v in CATEGORIES.items()])

    print(f"cust_info.csv     {len(cust_rows):>7,} rows")
    print(f"prd_info.csv      {len(prd_rows):>7,} rows")
    print(f"sales_details.csv {len(sales_rows):>7,} rows")
    print(f"cust_az12.csv     {len(az_rows):>7,} rows")
    print(f"loc_a101.csv      {len(loc_rows):>7,} rows")
    print(f"px_cat_g1v2.csv   {len(CATEGORIES):>7,} rows")


if __name__ == "__main__":
    main()
