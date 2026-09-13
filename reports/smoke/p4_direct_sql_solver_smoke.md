# P4 Direct SQL Solver Smoke Set

Real `gpt-oss-120b` endpoint was not configured in this local environment, so these cases are recorded as fixture-based expected behavior for the mocked structured-output path.

| Case | Fixture | Expected shape | Status |
|---|---|---|---|
| simple projection | `sales_orders` | `SELECT region ... FROM warehouse.finance.sales_orders` | Mock path covered |
| single-table aggregate | `sales_orders` | `SUM(net_revenue) GROUP BY region` | Mock path covered |
| filtered aggregate | `sales_orders` + value binding | Date predicate for Q3/2026 | Mock path covered |
| two-table FK join | `sales_orders` + `customers` | Join on `customer_id` | Prompt fixture covered |
| ORDER BY / LIMIT | pending richer fixture | Candidate generation only; not benchmarked | Pending |
