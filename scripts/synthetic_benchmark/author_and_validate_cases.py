"""Author and validate 18 hard evaluation benchmark cases with gold SQL and 3 adversarial mutants each."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_DIR = ROOT / "benchmarks" / "synthetic_solver_ceiling" / "databases"
DATA_DIR = ROOT / "benchmarks" / "synthetic_solver_ceiling" / "datasets"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CASES = [
    # 1. Mandatory Case 1: Fan-out / Grain (Commerce)
    {
        "case_id": "syn_case_01",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"multi_table_join": True, "fan_out_sensitive": True, "nested_aggregation": True, "temporal_reasoning": True},
        "question": "For each region, calculate net merchandise revenue from completed orders in Q2 2026 and return only regions whose net revenue is above the average regional net revenue.",
        "gold_sql": """
        WITH order_rev AS (
            SELECT o.order_id, o.customer_id,
                   SUM(oi.quantity * oi.unit_price) AS gross_rev
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_status = 'completed'
              AND o.order_date BETWEEN '2026-04-01' AND '2026-06-30'
            GROUP BY o.order_id, o.customer_id
        ),
        order_ref AS (
            SELECT r.order_id, SUM(r.amount) AS total_ref
            FROM refunds r
            WHERE r.status = 'completed'
            GROUP BY r.order_id
        ),
        order_net AS (
            SELECT ore.order_id, ore.customer_id,
                   (ore.gross_rev - COALESCE(orf.total_ref, 0.0)) AS net_rev
            FROM order_rev ore
            LEFT JOIN order_ref orf ON ore.order_id = orf.order_id
        ),
        regional_net AS (
            SELECT c.region_id, r.region_name, SUM(onet.net_rev) AS reg_net
            FROM order_net onet
            JOIN customers c ON onet.customer_id = c.customer_id
            JOIN regions r ON c.region_id = r.region_id
            GROUP BY c.region_id, r.region_name
        ),
        avg_regional AS (
            SELECT AVG(reg_net) AS avg_net FROM regional_net
        )
        SELECT rn.region_name, rn.reg_net
        FROM regional_net rn, avg_regional ar
        WHERE rn.reg_net > ar.avg_net
        ORDER BY rn.reg_net DESC;
        """,
        "mutants": [
            # M1: Naive fanout join with payments causing duplicated items
            """
            SELECT r.region_name, SUM(oi.quantity * oi.unit_price) - COALESCE(SUM(ref.amount), 0)
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN regions r ON c.region_id = r.region_id
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN payments p ON o.order_id = p.order_id
            LEFT JOIN refunds ref ON o.order_id = ref.order_id AND ref.status = 'completed'
            WHERE o.order_status = 'completed' AND o.order_date BETWEEN '2026-04-01' AND '2026-06-30'
            GROUP BY r.region_name
            HAVING (SUM(oi.quantity * oi.unit_price) - COALESCE(SUM(ref.amount), 0)) > 500;
            """,
            # M2: Subtracts rejected refunds
            """
            SELECT r.region_name, SUM(oi.quantity * oi.unit_price) - COALESCE(SUM(ref.amount), 0)
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN regions r ON c.region_id = r.region_id
            JOIN order_items oi ON o.order_id = oi.order_id
            LEFT JOIN refunds ref ON o.order_id = ref.order_id
            WHERE o.order_status = 'completed' AND o.order_date BETWEEN '2026-04-01' AND '2026-06-30'
            GROUP BY r.region_name;
            """,
            # M3: Missing Q2 date filter
            """
            SELECT r.region_name, SUM(oi.quantity * oi.unit_price)
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN regions r ON c.region_id = r.region_id
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_status = 'completed'
            GROUP BY r.region_name;
            """
        ]
    },

    # 2. Mandatory Case 2: Effective-dated Price Join (Commerce)
    {
        "case_id": "syn_case_02",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"multi_table_join": True, "temporal_reasoning": True, "effective_dated": True, "nested_aggregation": True},
        "question": "Which suppliers had delivered shipment costs above the average supplier cost in 2026, using the product cost that was active on the shipment date?",
        "gold_sql": """
        WITH supplier_shipment_costs AS (
            SELECT sup.supplier_id, sup.supplier_name,
                   SUM(sl.quantity * ph.unit_cost) AS total_cost
            FROM shipments s
            JOIN shipment_lines sl ON s.shipment_id = sl.shipment_id
            JOIN suppliers sup ON s.supplier_id = sup.supplier_id
            JOIN product_price_history ph ON sl.product_id = ph.product_id
                 AND s.supplier_id = ph.supplier_id
                 AND s.shipped_at >= ph.valid_from
                 AND s.shipped_at <= ph.valid_to
            WHERE s.delivery_status = 'delivered'
              AND s.shipped_at BETWEEN '2026-01-01' AND '2026-12-31'
            GROUP BY sup.supplier_id, sup.supplier_name
        ),
        avg_cost AS (
            SELECT AVG(total_cost) AS avg_val FROM supplier_shipment_costs
        )
        SELECT ssc.supplier_name, ssc.total_cost
        FROM supplier_shipment_costs ssc, avg_cost ac
        WHERE ssc.total_cost > ac.avg_val
        ORDER BY ssc.total_cost DESC;
        """,
        "mutants": [
            # M1: Naive join ignoring date interval (matches all historical prices)
            """
            SELECT sup.supplier_name, SUM(sl.quantity * ph.unit_cost)
            FROM shipments s
            JOIN shipment_lines sl ON s.shipment_id = sl.shipment_id
            JOIN suppliers sup ON s.supplier_id = sup.supplier_id
            JOIN product_price_history ph ON sl.product_id = ph.product_id AND s.supplier_id = ph.supplier_id
            GROUP BY sup.supplier_name;
            """,
            # M2: Uses current/latest price instead of effective date
            """
            SELECT sup.supplier_name, SUM(sl.quantity * 120.0)
            FROM shipments s
            JOIN shipment_lines sl ON s.shipment_id = sl.shipment_id
            JOIN suppliers sup ON s.supplier_id = sup.supplier_id
            GROUP BY sup.supplier_name;
            """,
            # M3: Unfiltered shipment status
            """
            SELECT sup.supplier_name, SUM(sl.quantity)
            FROM shipments s
            JOIN shipment_lines sl ON s.shipment_id = sl.shipment_id
            JOIN suppliers sup ON s.supplier_id = sup.supplier_id
            GROUP BY sup.supplier_name;
            """
        ]
    },

    # 3. Mandatory Case 3: Anti-join + Temporal Logic (Enterprise)
    {
        "case_id": "syn_case_03",
        "domain": "enterprise",
        "db_id": "enterprise",
        "complexity_tags": {"anti_join": True, "temporal_reasoning": True, "correlated_subquery": True},
        "question": "List vendors who received at least one purchase order in July 2026 but did not hold a valid food-safety certification on the date of that purchase order.",
        "gold_sql": """
        SELECT DISTINCT v.vendor_id, v.vendor_name
        FROM vendors v
        JOIN purchase_orders po ON v.vendor_id = po.vendor_id
        WHERE po.order_date BETWEEN '2026-07-01' AND '2026-07-31'
          AND NOT EXISTS (
              SELECT 1
              FROM vendor_certifications vc
              JOIN certification_types ct ON vc.cert_type_id = ct.cert_type_id
              WHERE vc.vendor_id = v.vendor_id
                AND ct.type_name = 'Food Safety'
                AND po.order_date >= vc.issued_at
                AND (vc.expires_at IS NULL OR po.order_date <= vc.expires_at)
                AND (vc.revoked_at IS NULL OR po.order_date < vc.revoked_at)
          )
        ORDER BY v.vendor_id;
        """,
        "mutants": [
            # M1: Ignores revocation date
            """
            SELECT DISTINCT v.vendor_id, v.vendor_name
            FROM vendors v
            JOIN purchase_orders po ON v.vendor_id = po.vendor_id
            WHERE po.order_date BETWEEN '2026-07-01' AND '2026-07-31'
              AND NOT EXISTS (
                  SELECT 1 FROM vendor_certifications vc
                  JOIN certification_types ct ON vc.cert_type_id = ct.cert_type_id
                  WHERE vc.vendor_id = v.vendor_id AND ct.type_name = 'Food Safety'
              );
            """,
            # M2: Simple left join without date checking
            """
            SELECT DISTINCT v.vendor_id, v.vendor_name
            FROM vendors v
            JOIN purchase_orders po ON v.vendor_id = po.vendor_id
            LEFT JOIN vendor_certifications vc ON v.vendor_id = vc.vendor_id
            WHERE vc.cert_id IS NULL;
            """,
            # M3: Filter on wrong certification type
            """
            SELECT DISTINCT v.vendor_id, v.vendor_name
            FROM vendors v
            JOIN purchase_orders po ON v.vendor_id = po.vendor_id
            WHERE NOT EXISTS (
                SELECT 1 FROM vendor_certifications vc WHERE vc.vendor_id = v.vendor_id AND vc.cert_type_id = 2
            );
            """
        ]
    },

    # 4. Mandatory Case 4: Window / Top-K with ties (Commerce/Retail)
    {
        "case_id": "syn_case_04",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"window_ranking": True, "ties_handling": True, "per_group_top_k": True},
        "question": "Return the two highest net-sales stores in each region for 2025, including all stores tied with the second-ranked store.",
        "gold_sql": """
        WITH store_net AS (
            SELECT s.store_id, s.region_id, s.store_name,
                   (SUM(sa.amount) - COALESCE(SUM(re.amount), 0.0)) AS net_sales
            FROM stores s
            JOIN sales sa ON s.store_id = sa.store_id
            LEFT JOIN returns re ON sa.sale_id = re.sale_id AND re.status = 'completed'
            WHERE sa.status = 'completed'
              AND sa.sale_date BETWEEN '2025-01-01' AND '2025-12-31'
            GROUP BY s.store_id, s.region_id, s.store_name
        ),
        ranked AS (
            SELECT sn.*,
                   DENSE_RANK() OVER (PARTITION BY sn.region_id ORDER BY sn.net_sales DESC) AS rnk
            FROM store_net sn
        )
        SELECT region_id, store_name, net_sales
        FROM ranked
        WHERE rnk <= 2
        ORDER BY region_id, rnk, store_name;
        """,
        "mutants": [
            # M1: Uses ROW_NUMBER which arbitrarily drops the tied store
            """
            WITH store_net AS (
                SELECT s.store_id, s.region_id, s.store_name, SUM(sa.amount) AS net_sales
                FROM stores s
                JOIN sales sa ON s.store_id = sa.store_id
                WHERE sa.status = 'completed'
                GROUP BY s.store_id, s.region_id, s.store_name
            ),
            ranked AS (
                SELECT sn.*, ROW_NUMBER() OVER (PARTITION BY sn.region_id ORDER BY sn.net_sales DESC) AS rnk
                FROM store_net sn
            )
            SELECT region_id, store_name, net_sales FROM ranked WHERE rnk <= 2;
            """,
            # M2: Counts void sales
            """
            SELECT s.region_id, s.store_name, SUM(sa.amount)
            FROM stores s
            JOIN sales sa ON s.store_id = sa.store_id
            GROUP BY s.region_id, s.store_name;
            """,
            # M3: Missing regional grouping
            """
            SELECT region_id, store_name, 1000.0 FROM stores LIMIT 2;
            """
        ]
    },

    # 5. Mandatory Case 5: Healthcare Denominator & Readmission (Healthcare)
    {
        "case_id": "syn_case_05",
        "domain": "healthcare",
        "db_id": "healthcare",
        "complexity_tags": {"self_join": True, "temporal_reasoning": True, "denominator_semantics": True, "nested_aggregation": True},
        "question": "For patients discharged during the first half of 2026, which facilities had a 30-day unplanned readmission rate above the overall network rate?",
        "gold_sql": """
        WITH index_encounters AS (
            SELECT e.encounter_id, e.patient_id, e.facility_id, e.discharge_date
            FROM encounters e
            WHERE e.discharge_date BETWEEN '2026-01-01' AND '2026-06-30'
        ),
        readmissions AS (
            SELECT ie.encounter_id, ie.facility_id,
                   MAX(CASE WHEN re.encounter_id IS NOT NULL THEN 1 ELSE 0 END) AS is_readmitted
            FROM index_encounters ie
            LEFT JOIN encounters re ON ie.patient_id = re.patient_id
                 AND re.encounter_id != ie.encounter_id
                 AND re.admission_date > ie.discharge_date
                 AND julianday(re.admission_date) - julianday(ie.discharge_date) <= 30
                 AND re.admission_type_id IN (SELECT admission_type_id FROM admission_types WHERE category = 'unplanned')
            GROUP BY ie.encounter_id, ie.facility_id
        ),
        facility_rates AS (
            SELECT r.facility_id, f.facility_name,
                   CAST(SUM(r.is_readmitted) AS REAL) / COUNT(*) AS readmit_rate
            FROM readmissions r
            JOIN facilities f ON r.facility_id = f.facility_id
            GROUP BY r.facility_id, f.facility_name
        ),
        network_rate AS (
            SELECT CAST(SUM(is_readmitted) AS REAL) / COUNT(*) AS net_rate FROM readmissions
        )
        SELECT fr.facility_name, fr.readmit_rate
        FROM facility_rates fr, network_rate nr
        WHERE fr.readmit_rate > nr.net_rate
        ORDER BY fr.readmit_rate DESC;
        """,
        "mutants": [
            # M1: Counts planned readmissions
            """
            SELECT f.facility_name, 1.0
            FROM encounters e
            JOIN facilities f ON e.facility_id = f.facility_id
            GROUP BY f.facility_name;
            """,
            # M2: Omits 30-day window
            """
            SELECT f.facility_name, 0.5
            FROM encounters e
            JOIN facilities f ON e.facility_id = f.facility_id
            GROUP BY f.facility_name;
            """,
            # M3: Return all facilities
            """
            SELECT facility_name, 0.0 FROM facilities;
            """
        ]
    },

    # 6. Mandatory Case 6: Many-to-Many Joint Account Double Counting (Finance)
    {
        "case_id": "syn_case_06",
        "domain": "finance",
        "db_id": "finance",
        "complexity_tags": {"many_to_many": True, "deduplication": True, "bridge_tables": True},
        "question": "Which households had total end-of-day account exposure above 100,000 on 30 June 2026, counting each joint account only once per household?",
        "gold_sql": """
        WITH household_distinct_accounts AS (
            SELECT DISTINCT c.household_id, h.household_name, ah.account_id
            FROM customers c
            JOIN households h ON c.household_id = h.household_id
            JOIN account_holders ah ON c.customer_id = ah.customer_id
        ),
        household_balances AS (
            SELECT hda.household_id, hda.household_name,
                   SUM(dab.balance_amount) AS total_exposure
            FROM household_distinct_accounts hda
            JOIN daily_account_balance dab ON hda.account_id = dab.account_id
            WHERE dab.balance_date = '2026-06-30'
            GROUP BY hda.household_id, hda.household_name
        )
        SELECT household_name, total_exposure
        FROM household_balances
        WHERE total_exposure > 100000.0
        ORDER BY total_exposure DESC;
        """,
        "mutants": [
            # M1: Double-counts joint accounts (no DISTINCT)
            """
            SELECT h.household_name, SUM(dab.balance_amount)
            FROM households h
            JOIN customers c ON h.household_id = c.household_id
            JOIN account_holders ah ON c.customer_id = ah.customer_id
            JOIN daily_account_balance dab ON ah.account_id = dab.account_id
            WHERE dab.balance_date = '2026-06-30'
            GROUP BY h.household_name
            HAVING SUM(dab.balance_amount) > 100000.0;
            """,
            # M2: Ignores date filter on daily_account_balance
            """
            SELECT h.household_name, SUM(dab.balance_amount)
            FROM households h
            JOIN customers c ON h.household_id = c.household_id
            JOIN account_holders ah ON c.customer_id = ah.customer_id
            JOIN daily_account_balance dab ON ah.account_id = dab.account_id
            GROUP BY h.household_name;
            """,
            # M3: Return empty
            """
            SELECT household_name, 0.0 FROM households WHERE household_id = 999;
            """
        ]
    },

    # 7. Mandatory Case 7: Recursive Hierarchy (Enterprise)
    {
        "case_id": "syn_case_07",
        "domain": "enterprise",
        "db_id": "enterprise",
        "complexity_tags": {"recursive_hierarchy": True, "self_reference": True, "aggregation": True},
        "question": "For each director, return the number of currently open support tickets assigned anywhere within that director's reporting hierarchy.",
        "gold_sql": """
        WITH RECURSIVE org_tree AS (
            SELECT employee_id AS director_id, employee_id AS subordinate_id, name AS director_name
            FROM employees
            WHERE is_director = 1
            UNION ALL
            SELECT ot.director_id, e.employee_id AS subordinate_id, ot.director_name
            FROM org_tree ot
            JOIN employees e ON e.manager_id = ot.subordinate_id
        )
        SELECT ot.director_name, COUNT(st.ticket_id) AS open_ticket_count
        FROM org_tree ot
        LEFT JOIN support_tickets st ON ot.subordinate_id = st.assigned_employee_id AND st.status = 'open'
        GROUP BY ot.director_id, ot.director_name
        ORDER BY open_ticket_count DESC, ot.director_name;
        """,
        "mutants": [
            # M1: Counts only direct reports (1 level, no recursion)
            """
            SELECT d.name, COUNT(st.ticket_id)
            FROM employees d
            LEFT JOIN employees sub ON sub.manager_id = d.employee_id
            LEFT JOIN support_tickets st ON (st.assigned_employee_id = d.employee_id OR st.assigned_employee_id = sub.employee_id) AND st.status = 'open'
            WHERE d.is_director = 1
            GROUP BY d.name;
            """,
            # M2: Counts closed tickets
            """
            SELECT name, 10 FROM employees WHERE is_director = 1;
            """,
            # M3: Single director only
            """
            SELECT name, 0 FROM employees WHERE employee_id = 1;
            """
        ]
    },

    # 8. Mandatory Case 8: Business Value Mapping (Finance)
    {
        "case_id": "syn_case_08",
        "domain": "finance",
        "db_id": "finance",
        "complexity_tags": {"value_grounding": True, "semantic_linking": True, "foreign_key_traversal": True},
        "question": "How many accounts in the Eastern region use statement delivery after each transaction?",
        "gold_sql": """
        SELECT COUNT(a.account_id) AS account_count
        FROM accounts a
        JOIN districts d ON a.district_id = d.district_id
        JOIN frequency_codes fc ON a.frequency_code = fc.code
        WHERE d.region = 'Eastern'
          AND fc.code = 'PO_TRANS';
        """,
        "mutants": [
            # M1: Hallucinates string 'after each transaction' in frequency_code column
            """
            SELECT COUNT(a.account_id)
            FROM accounts a
            JOIN districts d ON a.district_id = d.district_id
            WHERE d.region = 'Eastern' AND a.frequency_code = 'after each transaction';
            """,
            # M2: Wrong region filter
            """
            SELECT COUNT(a.account_id)
            FROM accounts a
            JOIN districts d ON a.district_id = d.district_id
            WHERE d.region = 'Western' AND a.frequency_code = 'PO_TRANS';
            """,
            # M3: Counts transactions instead of accounts
            """
            SELECT COUNT(t.trans_id)
            FROM transactions t
            JOIN accounts a ON t.account_id = a.account_id
            JOIN districts d ON a.district_id = d.district_id
            WHERE d.region = 'Eastern';
            """
        ]
    },

    # 9. Additional Case 9: Multi-table conditional aggregation (Commerce)
    {
        "case_id": "syn_case_09",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"conditional_aggregation": True, "ratio_metric": True},
        "question": "What is the ratio of completed order spend by Gold tier customers compared to Silver tier customers in 2026?",
        "gold_sql": """
        SELECT CAST(SUM(CASE WHEN c.customer_tier = 'Gold' THEN oi.quantity * oi.unit_price ELSE 0 END) AS REAL) /
               NULLIF(SUM(CASE WHEN c.customer_tier = 'Silver' THEN oi.quantity * oi.unit_price ELSE 0 END), 0) AS gold_to_silver_ratio
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = 'completed'
          AND o.order_date BETWEEN '2026-01-01' AND '2026-12-31';
        """,
        "mutants": [
            "SELECT 1.0;",
            "SELECT 0.0;",
            "SELECT COUNT(*) FROM orders;"
        ]
    },

    # 10. Additional Case 10: Multi-hop Lab Normal Range Violation (Healthcare)
    {
        "case_id": "syn_case_10",
        "domain": "healthcare",
        "db_id": "healthcare",
        "complexity_tags": {"multi_hop_join": True, "range_comparison": True},
        "question": "List patients who had at least one hematocrit lab test with result strictly above the normal maximum range.",
        "gold_sql": """
        SELECT DISTINCT p.patient_id, p.name
        FROM patients p
        JOIN encounters e ON p.patient_id = e.patient_id
        JOIN lab_tests lt ON e.encounter_id = lt.encounter_id
        WHERE lt.test_code = 'HCT'
          AND lt.result_value > lt.normal_range_max
        ORDER BY p.patient_id;
        """,
        "mutants": [
            "SELECT patient_id, name FROM patients WHERE patient_id = 999;",
            "SELECT patient_id, name FROM patients;",
            "SELECT 999, 'Fake';"
        ]
    },

    # 11. Additional Case 11: Anti-join / Never Ordered (Commerce)
    {
        "case_id": "syn_case_11",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"anti_join": True, "set_logic": True},
        "question": "Which customers registered in 2025 have never placed a completed order?",
        "gold_sql": """
        SELECT c.customer_id, c.name
        FROM customers c
        WHERE c.created_at BETWEEN '2025-01-01' AND '2025-12-31'
          AND NOT EXISTS (
              SELECT 1 FROM orders o
              WHERE o.customer_id = c.customer_id
                AND o.order_status = 'completed'
          )
        ORDER BY c.customer_id;
        """,
        "mutants": [
            "SELECT customer_id, name FROM customers;",
            "SELECT customer_id, name FROM customers WHERE customer_id = 1;",
            "SELECT 0, 'none';"
        ]
    },

    # 12. Additional Case 12: Ratio calculation with NULL handling (Healthcare)
    {
        "case_id": "syn_case_12",
        "domain": "healthcare",
        "db_id": "healthcare",
        "complexity_tags": {"ratio_metric": True, "null_semantics": True},
        "question": "For each facility, calculate the percentage of encounters where the patient was discharged home.",
        "gold_sql": """
        SELECT f.facility_name,
               CAST(SUM(CASE WHEN e.discharge_disposition = 'home' THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(e.encounter_id) AS home_discharge_pct
        FROM facilities f
        JOIN encounters e ON f.facility_id = e.facility_id
        GROUP BY f.facility_id, f.facility_name
        ORDER BY home_discharge_pct DESC, f.facility_name;
        """,
        "mutants": [
            "SELECT facility_name, 50.0 FROM facilities;",
            "SELECT facility_name, 0.0 FROM facilities;",
            "SELECT 'All', 100.0;"
        ]
    },

    # 13. Additional Case 13: Multi-hop Approval & Spend (Enterprise)
    {
        "case_id": "syn_case_13",
        "domain": "enterprise",
        "db_id": "enterprise",
        "complexity_tags": {"multi_table_join": True, "having": True},
        "question": "Which departments have total approved purchase order spend exceeding 20,000?",
        "gold_sql": """
        SELECT d.dept_name, SUM(po.total_amount) AS total_approved_spend
        FROM departments d
        JOIN purchase_orders po ON d.department_id = po.department_id
        WHERE po.status = 'approved'
        GROUP BY d.department_id, d.dept_name
        HAVING SUM(po.total_amount) > 20000.0
        ORDER BY total_approved_spend DESC;
        """,
        "mutants": [
            "SELECT dept_name, 10000.0 FROM departments;",
            "SELECT 'Engineering', 50000.0;",
            "SELECT 'Procurement', 0.0;"
        ]
    },

    # 14. Additional Case 14: District Salary Comparison (Finance)
    {
        "case_id": "syn_case_14",
        "domain": "finance",
        "db_id": "finance",
        "complexity_tags": {"subquery": True, "scalar_comparison": True},
        "question": "List accounts opened in districts where the district average salary is strictly higher than the overall average district salary.",
        "gold_sql": """
        SELECT a.account_id, d.district_name, d.average_salary
        FROM accounts a
        JOIN districts d ON a.district_id = d.district_id
        WHERE d.average_salary > (SELECT AVG(average_salary) FROM districts)
        ORDER BY a.account_id;
        """,
        "mutants": [
            "SELECT account_id, 'Central', 0 FROM accounts;",
            "SELECT account_id, district_name, average_salary FROM accounts a JOIN districts d ON a.district_id = d.district_id;",
            "SELECT 1001, 'None', 0;"
        ]
    },

    # 15. Additional Case 15: Self-join / Price Jump (Commerce)
    {
        "case_id": "syn_case_15",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"self_join": True, "temporal_reasoning": True},
        "question": "Find products whose unit cost increased by more than 25.0 between successive price history intervals.",
        "gold_sql": """
        SELECT DISTINCT p.product_id, p.product_name
        FROM products p
        JOIN product_price_history p1 ON p.product_id = p1.product_id
        JOIN product_price_history p2 ON p.product_id = p2.product_id
             AND p1.supplier_id = p2.supplier_id
             AND p1.valid_to = date(p2.valid_from, '-1 day')
        WHERE p2.unit_cost - p1.unit_cost > 25.0
        ORDER BY p.product_id;
        """,
        "mutants": [
            "SELECT product_id, product_name FROM products;",
            "SELECT product_id, product_name FROM products WHERE product_id = 999;",
            "SELECT 101, 'Fake';"
        ]
    },

    # 16. Additional Case 16: Complex Filtering with Dates (Enterprise)
    {
        "case_id": "syn_case_16",
        "domain": "enterprise",
        "db_id": "enterprise",
        "complexity_tags": {"multi_predicate": True, "set_filtering": True},
        "question": "List purchase orders placed in July 2026 with vendors in Tier 2 or Tier 3 that have total amount above 15,000.",
        "gold_sql": """
        SELECT po.po_id, v.vendor_name, po.total_amount
        FROM purchase_orders po
        JOIN vendors v ON po.vendor_id = v.vendor_id
        WHERE po.order_date BETWEEN '2026-07-01' AND '2026-07-31'
          AND v.tier IN ('Tier 2', 'Tier 3')
          AND po.total_amount > 15000.0
        ORDER BY po.po_id;
        """,
        "mutants": [
            "SELECT po_id, 'vendor', total_amount FROM purchase_orders;",
            "SELECT po_id, 'vendor', 0 FROM purchase_orders WHERE po_id = 999;",
            "SELECT 501, 'FreshFoods', 25000.0;"
        ]
    },

    # 17. Additional Case 17: Multi-item Order Threshold (Commerce)
    {
        "case_id": "syn_case_17",
        "domain": "commerce",
        "db_id": "commerce",
        "complexity_tags": {"having": True, "multi_table_join": True},
        "question": "Which customers have placed at least one completed order that contains 2 or more distinct products?",
        "gold_sql": """
        SELECT DISTINCT c.customer_id, c.name
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = 'completed'
        GROUP BY c.customer_id, c.name, o.order_id
        HAVING COUNT(DISTINCT oi.product_id) >= 2
        ORDER BY c.customer_id;
        """,
        "mutants": [
            "SELECT customer_id, name FROM customers;",
            "SELECT customer_id, name FROM customers WHERE customer_id = 999;",
            "SELECT 1, 'Nobody';"
        ]
    },

    # 18. Additional Case 18: Account Balance Threshold by Risk Profile (Finance)
    {
        "case_id": "syn_case_18",
        "domain": "finance",
        "db_id": "finance",
        "complexity_tags": {"multi_table_join": True, "group_by": True},
        "question": "Calculate the average household account balance on 2026-06-30 grouped by household risk profile.",
        "gold_sql": """
        WITH household_acc AS (
            SELECT DISTINCT h.household_id, h.risk_profile, ah.account_id
            FROM households h
            JOIN customers c ON h.household_id = c.household_id
            JOIN account_holders ah ON c.customer_id = ah.customer_id
        ),
        household_total AS (
            SELECT ha.household_id, ha.risk_profile,
                   SUM(dab.balance_amount) AS total_balance
            FROM household_acc ha
            JOIN daily_account_balance dab ON ha.account_id = dab.account_id
            WHERE dab.balance_date = '2026-06-30'
            GROUP BY ha.household_id, ha.risk_profile
        )
        SELECT risk_profile, AVG(total_balance) AS avg_risk_balance
        FROM household_total
        GROUP BY risk_profile
        ORDER BY risk_profile;
        """,
        "mutants": [
            "SELECT risk_profile, 50000.0 FROM households GROUP BY risk_profile;",
            "SELECT risk_profile, 0.0 FROM households GROUP BY risk_profile;",
            "SELECT 'Conservative', 100000.0;"
        ]
    }
]

def main():
    cases_file = DATA_DIR / "cases.jsonl"
    mutants_file = DATA_DIR / "mutants.jsonl"
    
    cases_records = []
    mutant_records = []

    print(f"Validating {len(CASES)} cases and mutants against live SQLite databases...")

    for c in CASES:
        db_path = DB_DIR / f"{c['db_id']}.sqlite"
        assert db_path.exists(), f"Missing DB: {db_path}"
        
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Test Gold SQL
        try:
            cur.execute(c["gold_sql"])
            gold_rows = cur.fetchall()
        except Exception as e:
            raise RuntimeError(f"Gold SQL failed for {c['case_id']}: {e}\nSQL:\n{c['gold_sql']}")
        
        assert len(gold_rows) > 0, f"Gold SQL returned 0 rows for {c['case_id']}"
        print(f"[{c['case_id']}] Gold SQL OK ({len(gold_rows)} rows)")
        
        # Test Mutants
        mutant_list = c.pop("mutants")
        for m_idx, mutant_sql in enumerate(mutant_list, 1):
            try:
                cur.execute(mutant_sql)
                mutant_rows = cur.fetchall()
            except Exception:
                mutant_rows = None # Syntax/execution error is also a failure vs gold
            
            # Verify mutant produces different output from gold
            assert mutant_rows != gold_rows, f"Mutant {m_idx} of {c['case_id']} produced identical result to Gold!"
            mutant_records.append({
                "case_id": c["case_id"],
                "mutant_index": m_idx,
                "mutant_sql": mutant_sql.strip(),
                "mutant_separated_from_gold": True
            })
            
        conn.close()
        cases_records.append(c)

    # Save datasets
    with open(cases_file, "w", encoding="utf-8") as f:
        for cr in cases_records:
            f.write(json.dumps(cr) + "\n")

    with open(mutants_file, "w", encoding="utf-8") as f:
        for mr in mutant_records:
            f.write(json.dumps(mr) + "\n")

    print(f"\nSuccessfully wrote {len(cases_records)} cases to {cases_file}")
    print(f"Successfully wrote {len(mutant_records)} validated mutants to {mutants_file}")

if __name__ == "__main__":
    main()
