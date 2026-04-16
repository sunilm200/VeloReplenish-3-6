import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="VeloReplenish 3-6", layout="wide")
st.title("📦 VeloReplenish 3-6: Advanced Stock Planner")

# --- SIDEBAR UPLOADS ---
st.sidebar.header("Upload Data")
master_file = st.sidebar.file_uploader("1. Item Master (Totals & Lead Time)", type=['csv', 'xlsx'])
stock_file = st.sidebar.file_uploader("2. Daily Closing Stock", type=['csv', 'xlsx'])
orders_file = st.sidebar.file_uploader("3. Open Sales Orders (Sold soon)", type=['csv', 'xlsx'])
transit_file = st.sidebar.file_uploader("4. Transit Inward (Arriving soon)", type=['csv', 'xlsx'])

if master_file and stock_file and orders_file and transit_file:
    def load_and_clean(file):
        df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        df.columns = df.columns.str.strip().str.lower()
        return df

    try:
        master = load_and_clean(master_file)
        stock = load_and_clean(stock_file)
        orders = load_and_clean(orders_file)
        transit = load_and_clean(transit_file)

        # Multi-merge on item_id
        df = master.merge(stock, on='item_id', how='left') \
                   .merge(orders, on='item_id', how='left') \
                   .merge(transit, on='item_id', how='left')
        df.fillna(0, inplace=True)

        # --- CALCULATIONS ---
        df['avg_3m_monthly'] = df['total_sale_3m'] / 3
        df['avg_6m_monthly'] = df['total_sale_6m'] / 6
        df['avg_sale_used'] = df[['avg_3m_monthly', 'avg_6m_monthly']].max(axis=1)
        df['daily_velocity'] = df['avg_sale_used'] / 30
        
        # Net Virtual Inventory = (Physical + Incoming) - Promised to Customers
        df['net_virtual_inv'] = (df['closing_stock'] + df['transit_qty']) - df['on_order_qty']
        
        # Coverage based on Virtual Inventory
        df['days_of_cover'] = np.where(df['daily_velocity'] > 0, df['net_virtual_inv'] / df['daily_velocity'], 0)
        
        # Target = Daily Sale * Lead Time (Buffer = 0)
        df['target_stock'] = df['daily_velocity'] * df['lead_time_days']
        
        # Reorder Qty
        df['suggested_order_qty'] = (df['target_stock'] - df['net_virtual_inv']).clip(lower=0).round(0)

        def get_status(row):
            if row['days_of_cover'] > 25: return "Overstocked"
            elif row['days_of_cover'] <= 5: return "CRITICAL"
            elif row['net_virtual_inv'] < row['target_stock']: return "REORDER"
            else: return "Healthy"

        df['status'] = df.apply(get_status, axis=1)

        # --- DISPLAY ---
        display_cols = [
            'item_id', 'item_name', 'status', 'avg_sale_used', 
            'closing_stock', 'transit_qty', 'on_order_qty', 
            'days_of_cover', 'suggested_order_qty'
        ]
        
        styled_df = df[display_cols].style.apply(
            lambda row: ['background-color: #ffcccc' if row['status'] == "Overstocked" 
                         else 'background-color: #ffcc99' if row['status'] == "CRITICAL" 
                         else '' for _ in row], axis=1
        ).format({'avg_sale_used': '{:.1f}', 'days_of_cover': '{:.1f}'})
        
        st.subheader("📊 Stock Required Report (Including Transit)")
        st.dataframe(styled_df, use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            styled_df.to_excel(writer, index=False, sheet_name='Report')
        
        st.download_button("📥 Download Excel Report", data=output.getvalue(), file_name="VeloReplenish_Transit_Report.xlsx")

    except KeyError as e:
        st.error(f"❌ Missing Column: {e}. Check your file headers.")
else:
    st.info("Please upload all four files (Master, Stock, Orders, Transit) to see the report.")
