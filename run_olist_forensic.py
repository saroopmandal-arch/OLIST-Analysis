"""
OLIST-FORENSIC: End-to-End Database Setup & Empirical Analysis
Executes on the real Olist E-Commerce dataset in ./project/dataset/
Outputs SQLite database: ./project/olist_forensic.db
Outputs clean summary CSVs: ./project/output/
"""

import sqlite3
import pandas as pd
import numpy as np
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "dataset")
OUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(BASE_DIR, "olist_forensic.db")

os.makedirs(OUT_DIR, exist_ok=True)

import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

print("=" * 70)
print("[*] OLIST-FORENSIC: LOCAL SQLITE ENGINE & PERFORMANCE AUDIT")
print("=" * 70)
print(f"Data Source Directory: {DATA_DIR}")
print(f"Output Database:       {DB_PATH}")
print(f"Output Summaries:      {OUT_DIR}\n")

# 1. INGEST TABLES INTO SQLITE
start_time = time.time()
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

tables = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv"
}

print("--- STEP 1: Ingesting Relational CSV Tables into SQLite ---")
for tbl, fname in tables.items():
    fpath = os.path.join(DATA_DIR, fname)
    if os.path.exists(fpath):
        df = pd.read_csv(fpath)
        df.to_sql(tbl, conn, if_exists="replace", index=False)
        print(f"  [+] {tbl.ljust(22)}: {len(df):>7,} rows loaded")
    else:
        print(f"  [-] Missing: {fname}")

print("\n--- STEP 2: Creating Relational Indexes for High-Speed Joins ---")
indexes = [
    ("idx_orders_pk", "orders(order_id)"),
    ("idx_orders_cust", "orders(customer_id)"),
    ("idx_items_pk", "order_items(order_id)"),
    ("idx_items_seller", "order_items(seller_id)"),
    ("idx_items_prod", "order_items(product_id)"),
    ("idx_pay_pk", "order_payments(order_id)"),
    ("idx_rev_pk", "order_reviews(order_id)"),
    ("idx_cust_pk", "customers(customer_id)"),
    ("idx_cust_uniq", "customers(customer_unique_id)")
]

for idx_name, idx_target in indexes:
    cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_target};")
conn.commit()
print("  [+] All 9 relational indexes created successfully.")

print("\n--- STEP 3: Executing Empirical Forensic SQL Queries ---\n")

# QUERY 1: THE EXPECTATION-SETTING PARADOX
query_1 = """
WITH delivery_metrics AS (
    SELECT 
        o.order_id,
        r.review_score,
        ROUND(JULIANDAY(o.order_delivered_customer_date) - JULIANDAY(o.order_purchase_timestamp), 1) AS actual_days,
        ROUND(JULIANDAY(o.order_estimated_delivery_date) - JULIANDAY(o.order_purchase_timestamp), 1) AS promised_days,
        ROUND(JULIANDAY(o.order_delivered_customer_date) - JULIANDAY(o.order_estimated_delivery_date), 1) AS delivery_delta
    FROM orders o
    JOIN order_reviews r ON o.order_id = r.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_estimated_delivery_date IS NOT NULL
),
bucketed AS (
    SELECT 
        order_id,
        actual_days,
        promised_days,
        delivery_delta,
        review_score,
        CASE 
            WHEN delivery_delta <= -7 THEN '1. Early by >7 Days'
            WHEN delivery_delta < 0  THEN '2. Early by 1-6 Days'
            WHEN delivery_delta = 0  THEN '3. Exactly on Promised Day'
            WHEN delivery_delta <= 3 THEN '4. Late by 1-3 Days'
            ELSE '5. Late by >3 Days'
        END AS expectation_bucket
    FROM delivery_metrics
)
SELECT 
    expectation_bucket,
    COUNT(order_id) AS total_orders,
    ROUND(AVG(actual_days), 1) AS avg_actual_days,
    ROUND(AVG(promised_days), 1) AS avg_promised_days,
    ROUND(AVG(review_score), 2) AS avg_rating,
    ROUND(AVG(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0.0 END) * 100, 1) AS negative_review_pct
FROM bucketed
GROUP BY expectation_bucket
ORDER BY expectation_bucket;
"""

df_q1 = pd.read_sql_query(query_1, conn)
df_q1.to_csv(os.path.join(OUT_DIR, "summary_expectation_paradox.csv"), index=False)
print("1. [THE EXPECTATION PARADOX (Promised vs Actual Delta)]")
print(df_q1.to_string(index=False))
print("-" * 70)

# QUERY 2: BRAZILIAN PAYMENT MICROSTRUCTURE & GHOST CONVERSIONS
query_2 = """
WITH pay_data AS (
    SELECT 
        o.order_id,
        o.order_status,
        p.payment_type,
        p.payment_installments,
        p.payment_value
    FROM orders o
    JOIN order_payments p ON o.order_id = p.order_id
)
SELECT 
    payment_type,
    COUNT(order_id) AS total_payments,
    ROUND(AVG(payment_installments), 1) AS avg_installments,
    ROUND(SUM(payment_value), 2) AS total_gross_value_brl,
    ROUND(AVG(payment_value), 2) AS avg_ticket_brl,
    SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END) AS delivered_orders,
    SUM(CASE WHEN order_status IN ('canceled', 'unavailable') THEN 1 ELSE 0 END) AS unfulfilled_orders,
    ROUND(SUM(CASE WHEN order_status IN ('canceled', 'unavailable') THEN 1.0 ELSE 0.0 END) / COUNT(order_id) * 100, 2) AS unfulfilled_pct
FROM pay_data
GROUP BY payment_type
ORDER BY total_payments DESC;
"""

df_q2 = pd.read_sql_query(query_2, conn)
df_q2.to_csv(os.path.join(OUT_DIR, "summary_payment_installments.csv"), index=False)
print("\n2. [BRAZILIAN PAYMENT CULTURE & ORDER COMPLETION]")
print(df_q2.to_string(index=False))
print("-" * 70)

# QUERY 3: GEOGRAPHIC LOGISTICS & FREIGHT-TO-PRICE RATIO
query_3 = """
WITH order_geo AS (
    SELECT 
        o.order_id,
        c.customer_state,
        ROUND(JULIANDAY(o.order_delivered_customer_date) - JULIANDAY(o.order_purchase_timestamp), 1) AS delivery_days,
        r.review_score,
        oi.price,
        oi.freight_value
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    JOIN order_reviews r ON o.order_id = r.order_id
    JOIN (
        SELECT order_id, SUM(price) AS price, SUM(freight_value) AS freight_value
        FROM order_items
        GROUP BY order_id
    ) oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
SELECT 
    customer_state,
    COUNT(order_id) AS total_orders,
    ROUND(AVG(delivery_days), 1) AS avg_delivery_days,
    ROUND(AVG(price), 1) AS avg_order_price,
    ROUND(AVG(freight_value), 1) AS avg_freight_value,
    ROUND(AVG(freight_value) / AVG(price) * 100, 1) AS freight_to_price_ratio_pct,
    ROUND(AVG(review_score), 2) AS avg_rating,
    ROUND(AVG(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0.0 END) * 100, 1) AS negative_review_pct
FROM order_geo
GROUP BY customer_state
HAVING total_orders >= 500
ORDER BY total_orders DESC;
"""

df_q3 = pd.read_sql_query(query_3, conn)
df_q3.to_csv(os.path.join(OUT_DIR, "summary_geo_freight_logistics.csv"), index=False)
print("\n3. [GEOGRAPHIC LOGISTICS & FREIGHT BURDEN BY STATE (Top States)]")
print(df_q3.head(10).to_string(index=False))
print("-" * 70)

# QUERY 4: CUSTOMER RETENTION & THE 97% CHURN CLIFF
query_4 = """
WITH cust_orders AS (
    SELECT 
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id) AS order_count,
        SUM(p.payment_value) AS total_ltv,
        MIN(o.order_purchase_timestamp) AS first_order,
        MAX(o.order_purchase_timestamp) AS last_order
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_payments p ON o.order_id = p.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
),
retention_distribution AS (
    SELECT 
        order_count,
        COUNT(customer_unique_id) AS total_customers,
        ROUND(SUM(total_ltv), 2) AS total_segment_revenue,
        ROUND(AVG(total_ltv), 2) AS avg_customer_ltv
    FROM cust_orders
    GROUP BY order_count
)
SELECT 
    order_count,
    total_customers,
    ROUND(total_customers * 100.0 / (SELECT SUM(total_customers) FROM retention_distribution), 2) AS customer_pct,
    total_segment_revenue,
    avg_customer_ltv
FROM retention_distribution
ORDER BY order_count ASC
LIMIT 5;
"""

df_q4 = pd.read_sql_query(query_4, conn)
df_q4.to_csv(os.path.join(OUT_DIR, "summary_customer_retention.csv"), index=False)
print("\n4. [CUSTOMER RETENTION & LIFETIME VALUE CLIFF]")
print(df_q4.to_string(index=False))
print("-" * 70)

conn.close()
elapsed = time.time() - start_time
print(f"\n[SUCCESS] ALL SQL QUERIES COMPLETED & EXPORTED IN {elapsed:.2f}s!")
print(f"Database ready at: {DB_PATH}")
