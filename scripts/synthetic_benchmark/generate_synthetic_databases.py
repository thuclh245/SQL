"""Script to generate 4 synthetic databases for P2 Solver Capability Boundary Benchmark.

Databases:
1. commerce.sqlite (Orders, Items, Payments, Refunds, Shipments, Price History, Stores, Sales)
2. finance.sqlite (Households, Customers, Accounts, Joint Holders, Balances, Districts, Codes)
3. healthcare.sqlite (Facilities, Patients, Encounters, Admissions, Lab Tests, Diagnoses)
4. enterprise.sqlite (Employees hierarchy, Departments, Tickets, Vendors, POs, Certifications)
"""

import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "synthetic_solver_ceiling" / "databases"
DB_DIR.mkdir(parents=True, exist_ok=True)


def build_commerce_db(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE regions (
        region_id INTEGER PRIMARY KEY,
        region_name TEXT NOT NULL,
        country_code TEXT NOT NULL
    );

    CREATE TABLE categories (
        category_id INTEGER PRIMARY KEY,
        category_name TEXT NOT NULL,
        parent_category_id INTEGER,
        FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
    );

    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        sku TEXT NOT NULL UNIQUE,
        is_active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
    );

    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        region_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        customer_tier TEXT NOT NULL,
        FOREIGN KEY (region_id) REFERENCES regions(region_id)
    );

    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        order_status TEXT NOT NULL,
        fulfillment_channel TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE order_items (
        item_id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        discount_amount REAL NOT NULL DEFAULT 0.0,
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );

    CREATE TABLE payments (
        payment_id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL,
        payment_method TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_status TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(order_id)
    );

    CREATE TABLE refunds (
        refund_id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        refund_date TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(order_id)
    );

    CREATE TABLE suppliers (
        supplier_id INTEGER PRIMARY KEY,
        supplier_name TEXT NOT NULL,
        country_code TEXT NOT NULL
    );

    CREATE TABLE product_price_history (
        price_history_id INTEGER PRIMARY KEY,
        product_id INTEGER NOT NULL,
        supplier_id INTEGER NOT NULL,
        valid_from TEXT NOT NULL,
        valid_to TEXT NOT NULL,
        unit_cost REAL NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(product_id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
    );

    CREATE TABLE shipments (
        shipment_id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL,
        supplier_id INTEGER NOT NULL,
        shipped_at TEXT NOT NULL,
        delivery_status TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
    );

    CREATE TABLE shipment_lines (
        line_id INTEGER PRIMARY KEY,
        shipment_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );

    CREATE TABLE stores (
        store_id INTEGER PRIMARY KEY,
        region_id INTEGER NOT NULL,
        store_name TEXT NOT NULL,
        opened_date TEXT NOT NULL,
        FOREIGN KEY (region_id) REFERENCES regions(region_id)
    );

    CREATE TABLE sales (
        sale_id INTEGER PRIMARY KEY,
        store_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        sale_date TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );

    CREATE TABLE returns (
        return_id INTEGER PRIMARY KEY,
        sale_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (sale_id) REFERENCES sales(sale_id)
    );
    """)

    # Seed data
    cur.executemany("INSERT INTO regions VALUES (?, ?, ?)", [
        (1, "North", "US"),
        (2, "South", "US"),
        (3, "East", "US"),
        (4, "West", "US"),
    ])

    cur.executemany("INSERT INTO categories VALUES (?, ?, ?)", [
        (1, "Electronics", None),
        (2, "Apparel", None),
        (3, "Home", None),
    ])

    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", [
        (101, 1, "Laptop", "SKU-LAP-01", 1),
        (102, 1, "Mouse", "SKU-MOU-01", 1),
        (103, 2, "Jacket", "SKU-JAC-01", 1),
        (104, 3, "Blender", "SKU-BLE-01", 1),
    ])

    cur.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", [
        (1, 1, "Alice North", "2025-01-10", "Gold"),
        (2, 2, "Bob South", "2025-02-15", "Silver"),
        (3, 3, "Charlie East", "2025-03-20", "Platinum"),
        (4, 4, "Diana West", "2025-04-25", "Standard"),
        (5, 1, "Edward North", "2025-05-30", "Silver"),
        (6, 2, "Frank South", "2025-06-15", "Standard"),
    ])

    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", [
        (1, 1, "2026-04-15", "completed", "standard"),
        (2, 2, "2026-05-10", "completed", "express"),
        (3, 3, "2026-06-01", "completed", "standard"),
        (4, 4, "2026-06-20", "completed", "standard"),
        (5, 5, "2026-07-05", "completed", "standard"),
        (6, 1, "2026-04-20", "cancelled", "standard"),
    ])

    cur.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)", [
        (1, 1, 101, 1, 1000.0, 0.0),
        (2, 1, 102, 2, 100.0, 0.0),
        (3, 2, 103, 5, 100.0, 0.0),
        (4, 3, 104, 8, 100.0, 0.0),
        (5, 4, 102, 2, 100.0, 0.0),
        (6, 5, 101, 1, 1000.0, 0.0),
        (7, 6, 101, 2, 1000.0, 0.0),
    ])

    cur.executemany("INSERT INTO payments VALUES (?, ?, ?, ?, ?)", [
        (1, 1, "card", 600.0, "captured"),
        (2, 1, "gift_card", 600.0, "captured"),
        (3, 2, "card", 500.0, "captured"),
        (4, 3, "card", 800.0, "captured"),
        (5, 4, "card", 200.0, "captured"),
        (6, 5, "card", 1000.0, "captured"),
    ])

    cur.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?, ?)", [
        (1, 1, 100.0, "2026-04-25", "completed"),
        (2, 1, 50.0, "2026-04-26", "rejected"),
        (3, 2, 200.0, "2026-05-15", "completed"),
        (4, 4, 50.0, "2026-06-25", "completed"),
    ])

    cur.executemany("INSERT INTO suppliers VALUES (?, ?, ?)", [
        (1, "Acme Logistics", "US"),
        (2, "Apex Global", "US"),
        (3, "Atlas Freight", "CA"),
    ])

    cur.executemany("INSERT INTO product_price_history VALUES (?, ?, ?, ?, ?, ?)", [
        (1, 101, 1, "2026-01-01", "2026-03-31", 50.0),
        (2, 101, 1, "2026-04-01", "2026-06-30", 80.0),
        (3, 101, 1, "2026-07-01", "2026-12-31", 120.0),
        (4, 102, 2, "2026-01-01", "2026-12-31", 20.0),
        (5, 103, 3, "2026-01-01", "2026-12-31", 30.0),
    ])

    cur.executemany("INSERT INTO shipments VALUES (?, ?, ?, ?, ?)", [
        (1, 1, 1, "2026-05-15", "delivered"),
        (2, 2, 2, "2026-05-20", "delivered"),
        (3, 3, 3, "2026-06-10", "delivered"),
    ])

    cur.executemany("INSERT INTO shipment_lines VALUES (?, ?, ?, ?)", [
        (1, 1, 101, 10),
        (2, 2, 102, 5),
        (3, 3, 103, 10),
    ])

    cur.executemany("INSERT INTO stores VALUES (?, ?, ?, ?)", [
        (10, 1, "Store North-A", "2024-01-01"),
        (11, 1, "Store North-B", "2024-01-01"),
        (12, 1, "Store North-C", "2024-01-01"),
        (13, 1, "Store North-D", "2024-01-01"),
        (20, 2, "Store South-A", "2024-01-01"),
        (21, 2, "Store South-B", "2024-01-01"),
        (22, 2, "Store South-C", "2024-01-01"),
    ])

    cur.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)", [
        (1, 10, 101, "2025-06-01", 1200.0, "completed"),
        (2, 11, 101, "2025-06-01", 850.0, "completed"),
        (3, 12, 101, "2025-06-01", 800.0, "completed"),
        (4, 13, 101, "2025-06-01", 500.0, "completed"),
        (5, 20, 101, "2025-06-01", 1200.0, "completed"),
        (6, 21, 101, "2025-06-01", 900.0, "completed"),
        (7, 22, 101, "2025-06-01", 700.0, "completed"),
        (8, 10, 101, "2025-06-02", 300.0, "void"),
    ])

    cur.executemany("INSERT INTO returns VALUES (?, ?, ?, ?)", [
        (1, 1, 200.0, "completed"),
        (2, 2, 50.0, "completed"),
        (3, 3, 0.0, "completed"),
        (4, 3, 50.0, "pending"),
    ])

    conn.commit()
    conn.close()
    print("Created commerce.sqlite successfully.")


def build_finance_db(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE districts (
        district_id INTEGER PRIMARY KEY,
        district_name TEXT NOT NULL,
        region TEXT NOT NULL,
        average_salary REAL NOT NULL
    );

    CREATE TABLE households (
        household_id INTEGER PRIMARY KEY,
        district_id INTEGER NOT NULL,
        household_name TEXT NOT NULL,
        risk_profile TEXT NOT NULL,
        FOREIGN KEY (district_id) REFERENCES districts(district_id)
    );

    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        household_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        tax_id TEXT NOT NULL UNIQUE,
        join_date TEXT NOT NULL,
        FOREIGN KEY (household_id) REFERENCES households(household_id)
    );

    CREATE TABLE frequency_codes (
        code TEXT PRIMARY KEY,
        description TEXT NOT NULL
    );

    CREATE TABLE accounts (
        account_id INTEGER PRIMARY KEY,
        district_id INTEGER NOT NULL,
        account_type TEXT NOT NULL,
        open_date TEXT NOT NULL,
        frequency_code TEXT NOT NULL,
        FOREIGN KEY (district_id) REFERENCES districts(district_id),
        FOREIGN KEY (frequency_code) REFERENCES frequency_codes(code)
    );

    CREATE TABLE account_holders (
        id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        holder_role TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE daily_account_balance (
        balance_id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL,
        balance_date TEXT NOT NULL,
        balance_amount REAL NOT NULL,
        currency TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id)
    );

    CREATE TABLE transactions (
        trans_id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL,
        trans_date TEXT NOT NULL,
        amount REAL NOT NULL,
        trans_type TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id)
    );
    """)

    cur.executemany("INSERT INTO frequency_codes VALUES (?, ?)", [
        ("PO_TRANS", "Statement issued after each transaction"),
        ("MONTHLY", "Monthly statement"),
        ("ANNUAL", "Annual statement"),
    ])

    cur.executemany("INSERT INTO districts VALUES (?, ?, ?, ?)", [
        (1, "Central Prague", "Eastern", 35000.0),
        (2, "East Bohemia", "Eastern", 28000.0),
        (3, "Pilsen", "Western", 30000.0),
    ])

    cur.executemany("INSERT INTO households VALUES (?, ?, ?, ?)", [
        (1, 1, "Smith Household", "Conservative"),
        (2, 1, "Johnson Household", "Aggressive"),
        (3, 2, "Williams Household", "Moderate"),
    ])

    cur.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", [
        (101, 1, "John Smith", "TX-01", "2020-01-01"),
        (102, 1, "Mary Smith", "TX-02", "2020-01-01"),
        (103, 2, "Robert Johnson", "TX-03", "2021-05-10"),
        (104, 3, "Emily Williams", "TX-04", "2022-03-15"),
    ])

    cur.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?, ?)", [
        (1001, 1, "Savings", "2020-02-01", "PO_TRANS"),
        (1002, 1, "Checking", "2020-03-01", "MONTHLY"),
        (1003, 1, "Investment", "2021-06-01", "MONTHLY"),
        (1004, 2, "Checking", "2022-04-01", "PO_TRANS"),
    ])

    cur.executemany("INSERT INTO account_holders VALUES (?, ?, ?, ?)", [
        (1, 1001, 101, "primary"),
        (2, 1001, 102, "joint"),
        (3, 1002, 101, "primary"),
        (4, 1003, 103, "primary"),
        (5, 1004, 104, "primary"),
    ])

    cur.executemany("INSERT INTO daily_account_balance VALUES (?, ?, ?, ?, ?)", [
        (1, 1001, "2026-06-30", 70000.0, "USD"),
        (2, 1002, "2026-06-30", 40000.0, "USD"),
        (3, 1003, "2026-06-30", 60000.0, "USD"),
        (4, 1004, "2026-06-30", 15000.0, "USD"),
        (5, 1001, "2026-06-29", 68000.0, "USD"),
    ])

    conn.commit()
    conn.close()
    print("Created finance.sqlite successfully.")


def build_healthcare_db(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE facilities (
        facility_id INTEGER PRIMARY KEY,
        facility_name TEXT NOT NULL,
        facility_type TEXT NOT NULL,
        region TEXT NOT NULL
    );

    CREATE TABLE admission_types (
        admission_type_id INTEGER PRIMARY KEY,
        type_name TEXT NOT NULL,
        category TEXT NOT NULL
    );

    CREATE TABLE patients (
        patient_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        gender TEXT NOT NULL,
        birth_date TEXT NOT NULL,
        blood_type TEXT NOT NULL
    );

    CREATE TABLE encounters (
        encounter_id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        facility_id INTEGER NOT NULL,
        admission_type_id INTEGER NOT NULL,
        admission_date TEXT NOT NULL,
        discharge_date TEXT NOT NULL,
        discharge_disposition TEXT NOT NULL,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
        FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
        FOREIGN KEY (admission_type_id) REFERENCES admission_types(admission_type_id)
    );

    CREATE TABLE lab_tests (
        test_id INTEGER PRIMARY KEY,
        encounter_id INTEGER NOT NULL,
        test_name TEXT NOT NULL,
        test_code TEXT NOT NULL,
        test_date TEXT NOT NULL,
        result_value REAL NOT NULL,
        normal_range_min REAL NOT NULL,
        normal_range_max REAL NOT NULL,
        unit TEXT NOT NULL,
        FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
    );

    CREATE TABLE diagnoses (
        diagnosis_id INTEGER PRIMARY KEY,
        encounter_id INTEGER NOT NULL,
        icd10_code TEXT NOT NULL,
        diagnosis_type TEXT NOT NULL,
        FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
    );
    """)

    cur.executemany("INSERT INTO facilities VALUES (?, ?, ?, ?)", [
        (1, "Metro General", "Hospital", "Urban"),
        (2, "St. Jude Clinic", "Clinic", "Suburban"),
        (3, "Valley Hospital", "Hospital", "Rural"),
    ])

    cur.executemany("INSERT INTO admission_types VALUES (?, ?, ?)", [
        (1, "Emergency", "unplanned"),
        (2, "Urgent Inpatient", "unplanned"),
        (3, "Elective Surgery", "planned"),
    ])

    cur.executemany("INSERT INTO patients VALUES (?, ?, ?, ?, ?)", [
        (1, "Alice White", "F", "1955-04-12", "O+"),
        (2, "Bob Brown", "M", "1960-08-22", "A+"),
        (3, "Carol Green", "F", "1972-11-05", "B-"),
        (4, "David Black", "M", "1980-01-30", "AB+"),
    ])

    cur.executemany("INSERT INTO encounters VALUES (?, ?, ?, ?, ?, ?, ?)", [
        (1, 1, 1, 1, "2026-01-25", "2026-02-01", "home"),
        (2, 1, 1, 1, "2026-02-20", "2026-02-25", "home"),
        (3, 2, 1, 1, "2026-02-20", "2026-03-01", "home"),
        (4, 2, 1, 3, "2026-03-15", "2026-03-18", "home"),
        (5, 3, 1, 2, "2026-03-25", "2026-04-01", "home"),
        (6, 4, 2, 1, "2026-01-02", "2026-01-10", "home"),
    ])

    cur.executemany("INSERT INTO lab_tests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (1, 1, "Hematocrit", "HCT", "2026-01-26", 55.0, 37.0, 48.0, "%"),
        (2, 2, "Hematocrit", "HCT", "2026-02-21", 54.0, 37.0, 48.0, "%"),
        (3, 3, "Glucose", "GLU", "2026-02-21", 110.0, 70.0, 99.0, "mg/dL"),
    ])

    conn.commit()
    conn.close()
    print("Created healthcare.sqlite successfully.")


def build_enterprise_db(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE departments (
        department_id INTEGER PRIMARY KEY,
        dept_name TEXT NOT NULL,
        cost_center TEXT NOT NULL
    );

    CREATE TABLE employees (
        employee_id INTEGER PRIMARY KEY,
        manager_id INTEGER,
        department_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        is_director INTEGER NOT NULL DEFAULT 0,
        hire_date TEXT NOT NULL,
        FOREIGN KEY (manager_id) REFERENCES employees(employee_id),
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    );

    CREATE TABLE support_tickets (
        ticket_id INTEGER PRIMARY KEY,
        assigned_employee_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        priority TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (assigned_employee_id) REFERENCES employees(employee_id)
    );

    CREATE TABLE certification_types (
        cert_type_id INTEGER PRIMARY KEY,
        type_name TEXT NOT NULL,
        governing_body TEXT NOT NULL,
        is_mandatory INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE vendors (
        vendor_id INTEGER PRIMARY KEY,
        vendor_name TEXT NOT NULL,
        tier TEXT NOT NULL,
        country TEXT NOT NULL
    );

    CREATE TABLE vendor_certifications (
        cert_id INTEGER PRIMARY KEY,
        vendor_id INTEGER NOT NULL,
        cert_type_id INTEGER NOT NULL,
        issued_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id),
        FOREIGN KEY (cert_type_id) REFERENCES certification_types(cert_type_id)
    );

    CREATE TABLE purchase_orders (
        po_id INTEGER PRIMARY KEY,
        vendor_id INTEGER NOT NULL,
        department_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id),
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    );
    """)

    cur.executemany("INSERT INTO departments VALUES (?, ?, ?)", [
        (1, "Engineering", "CC-ENG"),
        (2, "Operations", "CC-OPS"),
        (3, "Procurement", "CC-PRO"),
    ])

    cur.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?)", [
        (1, None, 1, "Sarah Connor", "Director of Engineering", 1, "2020-01-01"),
        (2, 1, 1, "Kyle Reese", "Engineering Manager", 0, "2020-06-01"),
        (3, 2, 1, "John Connor", "Senior Engineer", 0, "2021-01-01"),
        (4, None, 2, "Ellen Ripley", "Director of Operations", 1, "2019-03-01"),
        (5, 4, 2, "Dwayne Hicks", "Operations Manager", 0, "2020-02-01"),
    ])

    cur.executemany("INSERT INTO support_tickets VALUES (?, ?, ?, ?, ?, ?)", [
        (101, 3, "Crash on startup", "High", "open", "2026-05-01"),
        (102, 3, "Memory leak", "Medium", "open", "2026-05-02"),
        (103, 2, "Database latency", "High", "open", "2026-05-03"),
        (104, 1, "Architecture review", "Low", "open", "2026-05-04"),
        (105, 3, "Old bug", "Low", "closed", "2026-04-01"),
        (106, 5, "Ops deployment issue", "High", "open", "2026-05-05"),
    ])

    cur.executemany("INSERT INTO certification_types VALUES (?, ?, ?, ?)", [
        (1, "Food Safety", "FDA/ISO", 1),
        (2, "ISO-9001", "ISO", 0),
    ])

    cur.executemany("INSERT INTO vendors VALUES (?, ?, ?, ?)", [
        (10, "FreshFoods Inc", "Tier 1", "US"),
        (20, "OrganicWorld Ltd", "Tier 2", "US"),
        (30, "QuickSnack Corp", "Tier 3", "US"),
    ])

    cur.executemany("INSERT INTO vendor_certifications VALUES (?, ?, ?, ?, ?, ?)", [
        (1, 10, 1, "2026-01-01", "2026-12-31", None),
        (2, 20, 1, "2026-01-01", "2026-12-31", "2026-07-10"),
        (3, 30, 2, "2026-01-01", "2026-12-31", None),
    ])

    cur.executemany("INSERT INTO purchase_orders VALUES (?, ?, ?, ?, ?, ?)", [
        (501, 10, 3, "2026-07-05", 25000.0, "approved"),
        (502, 20, 3, "2026-07-15", 18000.0, "approved"),
        (503, 30, 3, "2026-07-08", 12000.0, "approved"),
        (504, 10, 3, "2026-06-25", 30000.0, "approved"),
    ])

    conn.commit()
    conn.close()
    print("Created enterprise.sqlite successfully.")


if __name__ == "__main__":
    build_commerce_db(DB_DIR / "commerce.sqlite")
    build_finance_db(DB_DIR / "finance.sqlite")
    build_healthcare_db(DB_DIR / "healthcare.sqlite")
    build_enterprise_db(DB_DIR / "enterprise.sqlite")
    print("All 4 synthetic databases built successfully.")
