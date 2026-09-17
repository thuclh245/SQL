"""Generate authoritative, database-level, gold-independent metadata for all 4 synthetic databases."""

import json
from pathlib import Path

META_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "synthetic_solver_ceiling" / "metadata"

def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ==================== COMMERCE ====================
commerce_dir = META_DIR / "commerce"

write_json(commerce_dir / "tables.json", [
    {"table_name": "regions", "description": "Geographical sales regions."},
    {"table_name": "categories", "description": "Product taxonomy and categories."},
    {"table_name": "products", "description": "Master list of catalog products."},
    {"table_name": "customers", "description": "Registered buyer accounts."},
    {"table_name": "orders", "description": "Header records for customer orders."},
    {"table_name": "order_items", "description": "Line items belonging to an order."},
    {"table_name": "payments", "description": "Financial payment transaction attempts."},
    {"table_name": "refunds", "description": "Refund transactions issued against orders."},
    {"table_name": "suppliers", "description": "Third-party vendors and logistics suppliers."},
    {"table_name": "product_price_history", "description": "Historical supplier unit cost intervals."},
    {"table_name": "shipments", "description": "Logistics delivery shipments."},
    {"table_name": "shipment_lines", "description": "Product quantities inside shipments."},
    {"table_name": "stores", "description": "Physical retail store locations."},
    {"table_name": "sales", "description": "Point-of-sale transactions at physical stores."},
    {"table_name": "returns", "description": "Customer return records from store sales."},
])

write_json(commerce_dir / "relationships.json", [
    {"from_table": "customers", "from_column": "region_id", "to_table": "regions", "to_column": "region_id", "type": "many_to_one"},
    {"from_table": "categories", "from_column": "parent_category_id", "to_table": "categories", "to_column": "category_id", "type": "many_to_one"},
    {"from_table": "products", "from_column": "category_id", "to_table": "categories", "to_column": "category_id", "type": "many_to_one"},
    {"from_table": "orders", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id", "type": "many_to_one"},
    {"from_table": "order_items", "from_column": "order_id", "to_table": "orders", "to_column": "order_id", "type": "many_to_one"},
    {"from_table": "order_items", "from_column": "product_id", "to_table": "products", "to_column": "product_id", "type": "many_to_one"},
    {"from_table": "payments", "from_column": "order_id", "to_table": "orders", "to_column": "order_id", "type": "many_to_one"},
    {"from_table": "refunds", "from_column": "order_id", "to_table": "orders", "to_column": "order_id", "type": "many_to_one"},
    {"from_table": "product_price_history", "from_column": "product_id", "to_table": "products", "to_column": "product_id", "type": "many_to_one"},
    {"from_table": "product_price_history", "from_column": "supplier_id", "to_table": "suppliers", "to_column": "supplier_id", "type": "many_to_one"},
    {"from_table": "shipments", "from_column": "order_id", "to_table": "orders", "to_column": "order_id", "type": "many_to_one"},
    {"from_table": "shipments", "from_column": "supplier_id", "to_table": "suppliers", "to_column": "supplier_id", "type": "many_to_one"},
    {"from_table": "shipment_lines", "from_column": "shipment_id", "to_table": "shipments", "to_column": "shipment_id", "type": "many_to_one"},
    {"from_table": "shipment_lines", "from_column": "product_id", "to_table": "products", "to_column": "product_id", "type": "many_to_one"},
    {"from_table": "stores", "from_column": "region_id", "to_table": "regions", "to_column": "region_id", "type": "many_to_one"},
    {"from_table": "sales", "from_column": "store_id", "to_table": "stores", "to_column": "store_id", "type": "many_to_one"},
    {"from_table": "sales", "from_column": "product_id", "to_table": "products", "to_column": "product_id", "type": "many_to_one"},
    {"from_table": "returns", "from_column": "sale_id", "to_table": "sales", "to_column": "sale_id", "type": "many_to_one"},
])

write_json(commerce_dir / "glossary.json", {
    "merchandise revenue": "Sum of (quantity * unit_price) across order items.",
    "net merchandise revenue": "Gross merchandise revenue minus completed refund amounts.",
    "net sales": "Gross completed store sales amount minus completed returns amount.",
    "shipment cost": "Sum of shipment line quantity multiplied by the effective product unit cost at time of shipment."
})

write_json(commerce_dir / "grain.json", {
    "orders": "1 row per customer order",
    "order_items": "1 row per product item in an order",
    "payments": "1 row per payment attempt (an order may have multiple split payments)",
    "refunds": "1 row per refund transaction (an order may have zero, one, or multiple partial refunds)",
    "product_price_history": "1 row per valid date interval [valid_from, valid_to] for a product and supplier",
    "stores": "1 row per retail store",
    "sales": "1 row per store sale transaction",
    "returns": "1 row per return incident against a sale"
})

write_json(commerce_dir / "time_semantics.json", {
    "orders.order_date": "Date when the order was placed (YYYY-MM-DD).",
    "product_price_history.valid_from": "Beginning of unit cost validity interval (inclusive).",
    "product_price_history.valid_to": "End of unit cost validity interval (inclusive).",
    "shipments.shipped_at": "Timestamp when the shipment was dispatched (YYYY-MM-DD)."
})

write_json(commerce_dir / "value_dictionary.json", {
    "orders.order_status": ["completed", "cancelled", "pending"],
    "refunds.status": ["completed", "rejected"],
    "payments.payment_status": ["captured", "failed"],
    "sales.status": ["completed", "void"],
    "returns.status": ["completed", "pending"]
})

# ==================== FINANCE ====================
finance_dir = META_DIR / "finance"

write_json(finance_dir / "tables.json", [
    {"table_name": "districts", "description": "Administrative territorial districts."},
    {"table_name": "households", "description": "Family or residential household groupings."},
    {"table_name": "customers", "description": "Individual banking customers."},
    {"table_name": "frequency_codes", "description": "Standard statement delivery frequency code dictionary."},
    {"table_name": "accounts", "description": "Bank account master records."},
    {"table_name": "account_holders", "description": "Many-to-many relationship linking customers to accounts."},
    {"table_name": "daily_account_balance", "description": "End-of-day ledger balances per account."},
    {"table_name": "transactions", "description": "Individual account transaction postings."},
])

write_json(finance_dir / "relationships.json", [
    {"from_table": "households", "from_column": "district_id", "to_table": "districts", "to_column": "district_id", "type": "many_to_one"},
    {"from_table": "customers", "from_column": "household_id", "to_table": "households", "to_column": "household_id", "type": "many_to_one"},
    {"from_table": "accounts", "from_column": "district_id", "to_table": "districts", "to_column": "district_id", "type": "many_to_one"},
    {"from_table": "accounts", "from_column": "frequency_code", "to_table": "frequency_codes", "to_column": "code", "type": "many_to_one"},
    {"from_table": "account_holders", "from_column": "account_id", "to_table": "accounts", "to_column": "account_id", "type": "many_to_one"},
    {"from_table": "account_holders", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id", "type": "many_to_one"},
    {"from_table": "daily_account_balance", "from_column": "account_id", "to_table": "accounts", "to_column": "account_id", "type": "many_to_one"},
    {"from_table": "transactions", "from_column": "account_id", "to_table": "accounts", "to_column": "account_id", "type": "many_to_one"},
])

write_json(finance_dir / "glossary.json", {
    "household account exposure": "Sum of distinct account balances belonging to members of the household.",
    "statement delivery frequency": "Governed by account frequency_code foreign key."
})

write_json(finance_dir / "grain.json", {
    "households": "1 row per household",
    "customers": "1 row per customer person",
    "accounts": "1 row per financial account",
    "account_holders": "1 row per customer-to-account ownership role (joint accounts have multiple rows)",
    "daily_account_balance": "1 row per account per balance_date"
})

write_json(finance_dir / "time_semantics.json", {
    "daily_account_balance.balance_date": "Calendar date for snapshot balance (YYYY-MM-DD)."
})

write_json(finance_dir / "value_dictionary.json", {
    "frequency_codes.code": ["PO_TRANS", "MONTHLY", "ANNUAL"],
    "account_holders.holder_role": ["primary", "joint", "beneficiary"]
})

# ==================== HEALTHCARE ====================
healthcare_dir = META_DIR / "healthcare"

write_json(healthcare_dir / "tables.json", [
    {"table_name": "facilities", "description": "Hospitals and clinical care centers."},
    {"table_name": "admission_types", "description": "Classification of admission urgency and planning."},
    {"table_name": "patients", "description": "Patient master demographic records."},
    {"table_name": "encounters", "description": "Inpatient and outpatient care encounters."},
    {"table_name": "lab_tests", "description": "Clinical laboratory measurements and normal reference ranges."},
    {"table_name": "diagnoses", "description": "Recorded ICD-10 medical diagnoses per encounter."},
])

write_json(healthcare_dir / "relationships.json", [
    {"from_table": "encounters", "from_column": "patient_id", "to_table": "patients", "to_column": "patient_id", "type": "many_to_one"},
    {"from_table": "encounters", "from_column": "facility_id", "to_table": "facilities", "to_column": "facility_id", "type": "many_to_one"},
    {"from_table": "encounters", "from_column": "admission_type_id", "to_table": "admission_types", "to_column": "admission_type_id", "type": "many_to_one"},
    {"from_table": "lab_tests", "from_column": "encounter_id", "to_table": "encounters", "to_column": "encounter_id", "type": "many_to_one"},
    {"from_table": "diagnoses", "from_column": "encounter_id", "to_table": "encounters", "to_column": "encounter_id", "type": "many_to_one"},
])

write_json(healthcare_dir / "glossary.json", {
    "planned admission": "An admission where admission_types.category = 'planned'.",
    "unplanned admission": "An admission where admission_types.category = 'unplanned'.",
    "30-day unplanned readmission": "A subsequent unplanned encounter for the same patient admitted within 30 days of index encounter discharge."
})

write_json(healthcare_dir / "grain.json", {
    "patients": "1 row per individual patient",
    "encounters": "1 row per hospital encounter from admission to discharge",
    "lab_tests": "1 row per laboratory test ordered during an encounter"
})

write_json(healthcare_dir / "time_semantics.json", {
    "encounters.admission_date": "Date patient was admitted (YYYY-MM-DD).",
    "encounters.discharge_date": "Date patient was discharged (YYYY-MM-DD)."
})

write_json(healthcare_dir / "value_dictionary.json", {
    "admission_types.category": ["planned", "unplanned"],
    "encounters.discharge_disposition": ["home", "transferred", "deceased"]
})

# ==================== ENTERPRISE ====================
enterprise_dir = META_DIR / "enterprise"

write_json(enterprise_dir / "tables.json", [
    {"table_name": "departments", "description": "Organizational cost centers and business units."},
    {"table_name": "employees", "description": "Staff roster including management reporting hierarchy."},
    {"table_name": "support_tickets", "description": "Internal customer and IT support requests."},
    {"table_name": "certification_types", "description": "Industry regulatory certification types."},
    {"table_name": "vendors", "description": "Approved supplier and vendor companies."},
    {"table_name": "vendor_certifications", "description": "Issued, expired, or revoked vendor certifications."},
    {"table_name": "purchase_orders", "description": "Procurement orders placed with external vendors."},
])

write_json(enterprise_dir / "relationships.json", [
    {"from_table": "employees", "from_column": "manager_id", "to_table": "employees", "to_column": "employee_id", "type": "many_to_one"},
    {"from_table": "employees", "from_column": "department_id", "to_table": "departments", "to_column": "department_id", "type": "many_to_one"},
    {"from_table": "support_tickets", "from_column": "assigned_employee_id", "to_table": "employees", "to_column": "employee_id", "type": "many_to_one"},
    {"from_table": "vendor_certifications", "from_column": "vendor_id", "to_table": "vendors", "to_column": "vendor_id", "type": "many_to_one"},
    {"from_table": "vendor_certifications", "from_column": "cert_type_id", "to_table": "certification_types", "to_column": "cert_type_id", "type": "many_to_one"},
    {"from_table": "purchase_orders", "from_column": "vendor_id", "to_table": "vendors", "to_column": "vendor_id", "type": "many_to_one"},
    {"from_table": "purchase_orders", "from_column": "department_id", "to_table": "departments", "to_column": "department_id", "type": "many_to_one"},
])

write_json(enterprise_dir / "glossary.json", {
    "open support ticket": "A support ticket where status = 'open'.",
    "valid certification on date D": "A certification where issued_at <= D and (expires_at >= D or expires_at is null) and (revoked_at > D or revoked_at is null)."
})

write_json(enterprise_dir / "grain.json", {
    "employees": "1 row per employee, manager_id self-references reporting line",
    "support_tickets": "1 row per ticket incident",
    "vendor_certifications": "1 row per certificate grant interval"
})

write_json(enterprise_dir / "time_semantics.json", {
    "purchase_orders.order_date": "Date purchase order was issued (YYYY-MM-DD).",
    "vendor_certifications.issued_at": "Date certification was granted (YYYY-MM-DD).",
    "vendor_certifications.expires_at": "Date certification expires (YYYY-MM-DD).",
    "vendor_certifications.revoked_at": "Date certification was revoked, if applicable (YYYY-MM-DD)."
})

write_json(enterprise_dir / "value_dictionary.json", {
    "support_tickets.status": ["open", "in_progress", "resolved", "closed"],
    "purchase_orders.status": ["approved", "pending", "rejected"]
})

print("Global metadata generated successfully for all 4 domains.")
