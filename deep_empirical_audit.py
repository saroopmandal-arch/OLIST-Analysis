"""
Deep Empirical Audit of the real Olist Dataset
Computes exact ground-truth metrics across all tables.
"""

import pandas as pd
import numpy as np
import os
import sys

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DATA_DIR = './project/dataset'

# Load tables
print("Loading CSVs...")
orders = pd.read_csv(os.path.join(DATA_DIR, 'olist_orders_dataset.csv'))
customers = pd.read_csv(os.path.join(DATA_DIR, 'olist_customers_dataset.csv'))
items = pd.read_csv(os.path.join(DATA_DIR, 'olist_order_items_dataset.csv'))
payments = pd.read_csv(os.path.join(DATA_DIR, 'olist_order_payments_dataset.csv'))
reviews = pd.read_csv(os.path.join(DATA_DIR, 'olist_order_reviews_dataset.csv'))
products = pd.read_csv(os.path.join(DATA_DIR, 'olist_products_dataset.csv'))
trans = pd.read_csv(os.path.join(DATA_DIR, 'product_category_name_translation.csv'))

# Convert dates
for c in ['order_purchase_timestamp', 'order_approved_at', 'order_delivered_carrier_date', 
          'order_delivered_customer_date', 'order_estimated_delivery_date']:
    orders[c] = pd.to_datetime(orders[c])

print("="*60)
print("1. DATASET OVERVIEW & DATE BOUNDARIES")
print("="*60)
print(f"Total Orders: {len(orders):,}")
print(f"Min Purchase Date: {orders['order_purchase_timestamp'].min()}")
print(f"Max Purchase Date: {orders['order_purchase_timestamp'].max()}")
print("\nOrder Status Breakdown:")
print(orders['order_status'].value_counts(normalize=True).mul(100).round(2).to_string())

print("\n"+"="*60)
print("2. CUSTOMER RETENTION & CHURN REALITY")
print("="*60)
print(f"Total Customer Sessions (customer_id): {customers['customer_id'].nunique():,}")
print(f"Unique Human Buyers (customer_unique_id): {customers['customer_unique_id'].nunique():,}")

# Merge orders with customers
cust_orders = orders[orders['order_status'] == 'delivered'].merge(customers, on='customer_id', how='inner')
user_freq = cust_orders.groupby('customer_unique_id').size().value_counts()
print("\nRepeat Purchase Distribution (Delivered Orders Only):")
for orders_count, user_count in user_freq.items():
    pct = (user_count / customers['customer_unique_id'].nunique()) * 100
    print(f"  {orders_count} order(s): {user_count:>6,} customers ({pct:>5.2f}%)")

print("\n"+"="*60)
print("3. THE DELIVERY TIME & EXPECTATION PARADOX")
print("="*60)
deliv = orders[orders['order_status'] == 'delivered'].dropna(
    subset=['order_delivered_customer_date', 'order_estimated_delivery_date']
).merge(reviews[['order_id', 'review_score']], on='order_id', how='inner')

deliv['actual_days'] = (deliv['order_delivered_customer_date'] - deliv['order_purchase_timestamp']).dt.total_seconds() / 86400.0
deliv['promised_days'] = (deliv['order_estimated_delivery_date'] - deliv['order_purchase_timestamp']).dt.total_seconds() / 86400.0
deliv['delta_days'] = (deliv['order_delivered_customer_date'] - deliv['order_estimated_delivery_date']).dt.total_seconds() / 86400.0

print(f"Average Actual Delivery Time: {deliv['actual_days'].mean():.2f} days (Median: {deliv['actual_days'].median():.2f})")
print(f"Average Promised Delivery Time: {deliv['promised_days'].mean():.2f} days (Median: {deliv['promised_days'].median():.2f})")
print(f"Average Delta (Actual - Promised): {deliv['delta_days'].mean():.2f} days (Negative = Early)")

# Correlation
corr_actual = deliv['actual_days'].corr(deliv['review_score'])
corr_delta = deliv['delta_days'].corr(deliv['review_score'])
print(f"\nCorrelation between Actual Days & Review Score: {corr_actual:.4f}")
print(f"Correlation between Delta Days (Lateness) & Review Score: {corr_delta:.4f} (Stronger negative impact!)")

# Bucketing
def cat_delta(d):
    if d < -10: return '1. Early by >10 Days'
    elif d < -5: return '2. Early by 5-10 Days'
    elif d < 0: return '3. Early by 1-5 Days'
    elif d == 0: return '4. Exactly on Promised Day'
    elif d <= 3: return '5. Late by 1-3 Days'
    elif d <= 7: return '6. Late by 4-7 Days'
    else: return '7. Late by >7 Days'

deliv['delta_cat'] = deliv['delta_days'].apply(cat_delta)
delta_stats = deliv.groupby('delta_cat').agg(
    orders=('order_id', 'count'),
    avg_actual_days=('actual_days', 'mean'),
    avg_rating=('review_score', 'mean'),
    star1_pct=('review_score', lambda x: (x == 1).mean() * 100),
    star5_pct=('review_score', lambda x: (x == 5).mean() * 100)
).reset_index()
print("\nPerformance by Delivery Delta:")
print(delta_stats.to_string(index=False))

# The Counter-Factual Experiment: Slow but Early vs Fast but Late
slow_but_early = deliv[(deliv['actual_days'] >= 18) & (deliv['delta_days'] < 0)]
fast_but_late = deliv[(deliv['actual_days'] <= 10) & (deliv['delta_days'] > 0)]

print("\n--- THE SMOKING GUN ---")
print(f"Orders taking 18+ days BUT arrived EARLY (n={len(slow_but_early)}):")
print(f"  Average Review Score: {slow_but_early['review_score'].mean():.2f} / 5.0  (5-star share: {(slow_but_early['review_score']==5).mean()*100:.1f}%)")
print(f"Orders delivered in under 10 days BUT arrived LATE (n={len(fast_but_late)}):")
print(f"  Average Review Score: {fast_but_late['review_score'].mean():.2f} / 5.0  (1-star share: {(fast_but_late['review_score']==1).mean()*100:.1f}%)")

print("\n"+"="*60)
print("4. BRAZILIAN PAYMENT MICROSTRUCTURE & INSTALLMENTS")
print("="*60)
pay_stats = payments.groupby('payment_type').agg(
    count=('order_id', 'count'),
    total_val=('payment_value', 'sum'),
    avg_val=('payment_value', 'mean'),
    avg_installments=('payment_installments', 'mean'),
    max_installments=('payment_installments', 'max')
).reset_index()
pay_stats['share_pct'] = pay_stats['total_val'].div(pay_stats['total_val'].sum()).mul(100).round(2)
print(pay_stats.to_string(index=False))

# Installments breakdown for credit card
cc = payments[payments['payment_type'] == 'credit_card']
inst = cc['payment_installments'].value_counts(normalize=True).head(10).mul(100).round(2)
print("\nTop Credit Card Installments (Parcelamento):")
for i, pct in inst.items():
    print(f"  {int(i)} installment(s): {pct}% of CC payments")

print("\n"+"="*60)
print("5. STATE LOGISTICS & FREIGHT BURDEN")
print("="*60)
cust_geo = orders[orders['order_status'] == 'delivered'].merge(customers, on='customer_id', how='inner')
cust_geo = cust_geo.merge(deliv[['order_id', 'actual_days', 'review_score']], on='order_id', how='inner')
items_agg = items.groupby('order_id').agg(
    total_price=('price', 'sum'),
    total_freight=('freight_value', 'sum')
).reset_index()
cust_geo = cust_geo.merge(items_agg, on='order_id', how='inner')

state_stats = cust_geo.groupby('customer_state').agg(
    orders=('order_id', 'count'),
    avg_delivery_days=('actual_days', 'mean'),
    avg_price=('total_price', 'mean'),
    avg_freight=('total_freight', 'mean'),
    avg_rating=('review_score', 'mean'),
    pct_bad_reviews=('review_score', lambda x: (x <= 2).mean() * 100)
).reset_index()
state_stats['freight_ratio_pct'] = (state_stats['avg_freight'] / state_stats['avg_price']) * 100
state_stats = state_stats.sort_values(by='orders', ascending=False)
print("Top 10 States by Volume:")
print(state_stats.head(10)[['customer_state', 'orders', 'avg_delivery_days', 'avg_freight', 'freight_ratio_pct', 'avg_rating', 'pct_bad_reviews']].to_string(index=False))

print("\n"+"="*60)
print("6. TEXT MINING REVIEW COMMENTS (1-STAR VS 5-STAR)")
print("="*60)
rev_text = reviews.dropna(subset=['review_comment_message'])
bad_reviews = rev_text[rev_text['review_score'] == 1]['review_comment_message'].str.lower()
good_reviews = rev_text[rev_text['review_score'] == 5]['review_comment_message'].str.lower()

keywords_bad = ['entrega', 'prazo', 'atraso', 'chegou', 'recebi', 'produto', 'veio', 'defeito']
print("Keyword occurrence in 1-Star Review comments:")
for kw in keywords_bad:
    pct = bad_reviews.str.contains(kw).mean() * 100
    print(f"  Contains '{kw}': {pct:.1f}% of 1-star reviews")

keywords_good = ['antes do prazo', 'chegou antes', 'recomendo', 'otimo', 'ótimo', 'perfeito', 'parabens', 'parabéns']
print("\nKeyword occurrence in 5-Star Review comments:")
for kw in keywords_good:
    pct = good_reviews.str.contains(kw).mean() * 100
    print(f"  Contains '{kw}': {pct:.1f}% of 5-star reviews")

