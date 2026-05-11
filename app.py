from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path




from typing import Any

import numpy as np
import pandas as pd
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from chatbot import ask_bot  # Import our working chatbot function

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "instance" / "users.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-production"
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
# Disable caching of static files for development
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

UPLOAD_FOLDER.mkdir(exist_ok=True)
DATABASE_PATH.parent.mkdir(exist_ok=True)


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_sales_file(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    raise ValueError("Unsupported file type")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df


def find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {col.lower().replace(" ", "").replace("_", ""): col for col in columns}
    for candidate in candidates:
        key = candidate.lower().replace(" ", "").replace("_", "")
        if key in normalized:
            return normalized[key]
    for col in columns:
        clean = col.lower().replace(" ", "").replace("_", "")
        for candidate in candidates:
            cand = candidate.lower().replace(" ", "").replace("_", "")
            if cand in clean or clean in cand:
                return col
    return None


def prepare_sales_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str | None]]:
    df = normalize_columns(df)
    columns = list(df.columns)

    mapping = {
        "date": find_column(columns, ["date", "orderdate", "invoice_date", "salesdate", "transactiondate"]),
        "sales": find_column(columns, ["sales", "amount", "revenue", "total", "total_sales", "sale_amount", "order_value"]),
        "quantity": find_column(columns, ["quantity", "qty", "units", "items_sold"]),
        "category": find_column(columns, ["category", "product_category", "segment", "department"]),
        "product": find_column(columns, ["product", "product_name", "item", "item_name"]),
        "region": find_column(columns, ["region", "location", "city", "state", "area", "branch"]),
        "order_id": find_column(columns, ["order_id", "orderno", "invoice_id", "invoice_no", "transaction_id", "bill_no"]),
    }

    if not mapping["sales"]:
        raise ValueError("Could not find a sales/revenue column. Add a column like Sales, Amount, Revenue, or Total.")

    sales_col = mapping["sales"]
    assert sales_col is not None

    df[sales_col] = pd.to_numeric(df[sales_col], errors="coerce")
    if mapping["quantity"]:
        df[mapping["quantity"]] = pd.to_numeric(df[mapping["quantity"]], errors="coerce")
    if mapping["date"]:
        df[mapping["date"]] = pd.to_datetime(df[mapping["date"]], errors="coerce")

    return df, mapping


def clean_and_enrich_dataframe(df: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = df.copy()
    original_rows = len(df)
    sales_col = mapping["sales"]
    assert sales_col is not None

    null_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    invalid_sales_rows = int(df[sales_col].isna().sum())
    invalid_date_rows = 0
    if mapping["date"]:
        invalid_date_rows = int(df[mapping["date"]].isna().sum())

    df = df.drop_duplicates().dropna(subset=[sales_col]).copy()
    if mapping["quantity"]:
        df[mapping["quantity"]] = df[mapping["quantity"]].fillna(0)

    if mapping["date"]:
        valid_date_count = int(df[mapping["date"]].notna().sum())
    else:
        valid_date_count = 0

    quality = {
        "original_rows": int(original_rows),
        "clean_rows": int(len(df)),
        "removed_rows": int(original_rows - len(df)),
        "null_cells": null_cells,
        "duplicate_rows": duplicate_rows,
        "invalid_sales_rows": invalid_sales_rows,
        "invalid_date_rows": invalid_date_rows,
        "valid_date_rows": valid_date_count,
        "quality_score": max(0, round(100 - ((original_rows - len(df)) / max(original_rows, 1)) * 100, 1)),
    }
    return df, quality


def make_chart_dataset(labels: list[Any], values: list[float]) -> dict[str, list[Any]]:
    return {
        "labels": [str(x) for x in labels],
        "values": [round(float(v), 2) for v in values],
    }


def safe_group_sum(df: pd.DataFrame, by_col: str | None, sales_col: str, limit: int = 8) -> pd.Series:
    if not by_col or by_col not in df.columns:
        return pd.Series(dtype=float)
    grouped = df.groupby(by_col)[sales_col].sum().sort_values(ascending=False)
    return grouped.head(limit)


def build_time_series(df: pd.DataFrame, date_col: str | None, sales_col: str, start_date: str = "", end_date: str = "") -> tuple[pd.Series, pd.Series, pd.Series]:
    if not date_col or date_col not in df.columns:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    dated_df = df.dropna(subset=[date_col]).copy()
    if dated_df.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    try:
        min_date = pd.to_datetime(start_date) if start_date else dated_df[date_col].min()
        max_date = pd.to_datetime(end_date) if end_date else dated_df[date_col].max()
    except Exception:
        min_date = dated_df[date_col].min()
        max_date = dated_df[date_col].max()

    daily = dated_df.groupby(dated_df[date_col].dt.date)[sales_col].sum().sort_index()
    daily.index = pd.to_datetime(daily.index)
    if pd.notna(min_date) and pd.notna(max_date) and min_date <= max_date:
        idx_daily = pd.date_range(start=min_date, end=max_date, freq='D')
        daily = daily.reindex(idx_daily, fill_value=0)
    daily.index = pd.Index([str(i.date()) for i in daily.index])

    weekly = dated_df.groupby(dated_df[date_col].dt.to_period("W"))[sales_col].sum().sort_index()
    if pd.notna(min_date) and pd.notna(max_date) and min_date <= max_date:
        w_min = pd.Period(min_date, freq='W')
        w_max = pd.Period(max_date, freq='W')
        idx_weekly = pd.period_range(w_min, w_max, freq='W')
        weekly = weekly.reindex(idx_weekly, fill_value=0)
    weekly.index = weekly.index.astype(str)

    monthly = dated_df.groupby(dated_df[date_col].dt.to_period("M"))[sales_col].sum().sort_index()
    if pd.notna(min_date) and pd.notna(max_date) and min_date <= max_date:
        m_min = pd.Period(min_date, freq='M')
        m_max = pd.Period(max_date, freq='M')
        idx_monthly = pd.period_range(m_min, m_max, freq='M')
        monthly = monthly.reindex(idx_monthly, fill_value=0)
    monthly.index = monthly.index.astype(str)

    return daily, weekly, monthly


def comparison_block(series: pd.Series, label: str) -> dict[str, Any]:
    if len(series) < 2:
        return {
            "label": label,
            "current": None,
            "previous": None,
            "change": None,
            "change_pct": None,
            "direction": "not_available",
        }

    current = float(series.iloc[-1])
    previous = float(series.iloc[-2])
    change = current - previous
    change_pct = (change / previous * 100) if previous else None
    return {
        "label": label,
        "current": round(current, 2),
        "previous": round(previous, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
    }


def generate_forecast(monthly_series: pd.Series, periods: int = 3) -> dict[str, list[Any]]:
    if len(monthly_series) < 2:
        return {"labels": [], "values": []}

    values = monthly_series.astype(float).values
    x = np.arange(len(values))
    slope, intercept = np.polyfit(x, values, 1)
    future_x = np.arange(len(values), len(values) + periods)
    future_values = np.maximum(0, slope * future_x + intercept)

    last_period = pd.Period(monthly_series.index[-1], freq="M")
    labels = [str(last_period + i) for i in range(1, periods + 1)]
    return make_chart_dataset(labels, future_values.tolist())


def build_recommendations(summary: dict[str, Any], monthly_comp: dict[str, Any], weekly_comp: dict[str, Any], top_region: str, top_category: str) -> list[str]:
    items: list[str] = []

    if monthly_comp["direction"] == "down":
        items.append("Monthly sales are down. Consider reviewing promotions, discount strategy, and product visibility for the latest month.")
    elif monthly_comp["direction"] == "up":
        items.append("Monthly sales are improving. Maintain stock levels and continue campaigns that supported the recent growth.")

    if weekly_comp["direction"] == "down":
        items.append("Weekly performance dropped. Check whether one region, product group, or weekend period caused the decline.")

    if top_region != "N/A":
        items.append(f"{top_region} is the strongest region. Use it as a benchmark for marketing and inventory planning in other regions.")

    if top_category != "N/A":
        items.append(f"{top_category} is the best-performing category. Prioritize stock availability and bundle offers around this category.")

    if summary["average_sale"] and summary["average_sale"] < 1000:
        items.append("Average sale value is on the lower side. Upselling and combo offers may help increase basket value.")

    return items[:5]


def build_insights(df: pd.DataFrame, mapping: dict[str, str | None], quality: dict[str, Any], monthly_comp: dict[str, Any], weekly_comp: dict[str, Any]) -> list[str]:
    insights: list[str] = []
    sales_col = mapping["sales"]
    assert sales_col is not None

    total_sales = df[sales_col].sum()
    insights.append(f"Cleaned dataset contains {len(df)} usable rows and total revenue of {total_sales:,.2f}.")
    insights.append(f"Data quality score is {quality['quality_score']}%, after removing invalid or duplicate rows.")

    if mapping["category"] and not df.empty:
        top_category = df.groupby(mapping["category"])[sales_col].sum().sort_values(ascending=False).head(1)
        if not top_category.empty:
            insights.append(f"Top category is {top_category.index[0]} with revenue of {top_category.iloc[0]:,.2f}.")

    if mapping["region"] and not df.empty:
        top_region = df.groupby(mapping["region"])[sales_col].sum().sort_values(ascending=False).head(1)
        if not top_region.empty:
            insights.append(f"Best-performing region is {top_region.index[0]} with revenue of {top_region.iloc[0]:,.2f}.")

    if monthly_comp["direction"] in {"up", "down"}:
        insights.append(
            f"Month-over-month sales moved {monthly_comp['direction']} by {abs(monthly_comp['change']):,.2f} ({abs(monthly_comp['change_pct'] or 0):.2f}%)."
        )

    if weekly_comp["direction"] in {"up", "down"}:
        insights.append(
            f"Week-over-week sales moved {weekly_comp['direction']} by {abs(weekly_comp['change']):,.2f} ({abs(weekly_comp['change_pct'] or 0):.2f}%)."
        )

    return insights


def generate_sql_queries(
    mapping: dict[str, str | None],
    selected_filters: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Generate SQL-equivalent queries for every analytics operation performed."""
    sales = mapping['sales'] or 'Sales'
    date = mapping['date'] or 'Date'
    category = mapping['category'] or 'Category'
    product = mapping['product'] or 'Product'
    region = mapping['region'] or 'Region'
    quantity = mapping['quantity'] or 'Quantity'
    order_id = mapping['order_id'] or 'Order_ID'
    tbl = 'sales_data'

    # Build WHERE clause from active filters
    where_parts: list[str] = []
    if selected_filters:
        if selected_filters.get('region'):
            where_parts.append(f"{region} = '{selected_filters['region']}'")
        if selected_filters.get('category'):
            where_parts.append(f"{category} = '{selected_filters['category']}'")
        if selected_filters.get('product'):
            where_parts.append(f"{product} = '{selected_filters['product']}'")
        if selected_filters.get('start_date'):
            where_parts.append(f"{date} >= '{selected_filters['start_date']}'")
        if selected_filters.get('end_date'):
            where_parts.append(f"{date} <= '{selected_filters['end_date']}'")

    where_sql = ''
    if where_parts:
        where_sql = '\nWHERE ' + '\n  AND '.join(where_parts)

    queries: dict[str, dict[str, str]] = {}

    # ── KPI summary ──
    queries['summary_kpis'] = {
        'title': 'Summary KPIs',
        'sql': (
            f"SELECT\n"
            f"  SUM({sales})            AS total_revenue,\n"
            f"  COUNT(*)               AS total_records,\n"
            f"  AVG({sales})            AS average_sale,\n"
            f"  COUNT(DISTINCT {order_id}) AS order_count,\n"
            f"  SUM({quantity})         AS total_quantity\n"
            f"FROM {tbl}{where_sql};"
        ),
    }

    # ── Category distribution chart ──
    queries['category_distribution'] = {
        'title': 'Category Sales Distribution',
        'sql': (
            f"SELECT {category}, SUM({sales}) AS revenue\n"
            f"FROM {tbl}{where_sql}\n"
            f"GROUP BY {category}\n"
            f"ORDER BY revenue DESC\n"
            f"LIMIT 8;"
        ),
    }

    # ── Regional sales chart ──
    queries['regional_sales'] = {
        'title': 'Regional Sales',
        'sql': (
            f"SELECT {region}, SUM({sales}) AS revenue\n"
            f"FROM {tbl}{where_sql}\n"
            f"GROUP BY {region};"
        ),
    }

    # ── Daily sales trend ──
    queries['daily_sales'] = {
        'title': 'Daily Sales Trend',
        'sql': (
            f"SELECT CAST({date} AS DATE) AS day,\n"
            f"       SUM({sales}) AS revenue\n"
            f"FROM {tbl}{where_sql}\n"
            f"GROUP BY day\n"
            f"ORDER BY day;"
        ),
    }

    # ── Monthly sales ──
    queries['monthly_sales'] = {
        'title': 'Monthly Sales Growth',
        'sql': (
            f"SELECT DATE_TRUNC('month', {date}) AS month,\n"
            f"       SUM({sales}) AS revenue\n"
            f"FROM {tbl}{where_sql}\n"
            f"GROUP BY month\n"
            f"ORDER BY month;"
        ),
    }

    # ── Top category ──
    queries['top_category'] = {
        'title': 'Top Category by Revenue',
        'sql': (
            f"SELECT {category}, SUM({sales}) AS revenue\n"
            f"FROM {tbl}{where_sql}\n"
            f"GROUP BY {category}\n"
            f"ORDER BY revenue DESC\n"
            f"LIMIT 5;"
        ),
    }

    # ── Data quality / cleaning ──
    queries['data_quality'] = {
        'title': 'Data Quality Check',
        'sql': (
            f"-- Duplicate rows\n"
            f"SELECT COUNT(*) - COUNT(DISTINCT *) AS duplicate_rows\n"
            f"FROM {tbl};\n\n"
            f"-- Null sales values\n"
            f"SELECT COUNT(*) AS invalid_sales\n"
            f"FROM {tbl}\n"
            f"WHERE {sales} IS NULL;\n\n"
            f"-- Clean dataset (remove dups + null sales)\n"
            f"SELECT DISTINCT *\n"
            f"FROM {tbl}\n"
            f"WHERE {sales} IS NOT NULL;"
        ),
    }

    # ── Data preview ──
    queries['data_preview'] = {
        'title': 'Data Preview',
        'sql': (
            f"SELECT *\n"
            f"FROM {tbl}{where_sql}\n"
            f"LIMIT 12;"
        ),
    }

    # ── Filter options ──
    queries['filter_options'] = {
        'title': 'Available Filter Values',
        'sql': (
            f"SELECT DISTINCT {region} FROM {tbl} ORDER BY {region};\n"
            f"SELECT DISTINCT {category} FROM {tbl} ORDER BY {category};\n"
            f"SELECT DISTINCT {product} FROM {tbl} ORDER BY {product};\n"
            f"SELECT MIN({date}) AS date_min, MAX({date}) AS date_max FROM {tbl};"
        ),
    }

    return queries



def serialize_preview(df: pd.DataFrame, limit: int = 12) -> dict[str, Any]:
    recent_rows = df.head(limit).copy()
    for col in recent_rows.columns:
        if pd.api.types.is_datetime64_any_dtype(recent_rows[col]):
            recent_rows[col] = recent_rows[col].dt.strftime("%Y-%m-%d")
        else:
            recent_rows[col] = recent_rows[col].astype(str)
    return {"columns": recent_rows.columns.tolist(), "rows": recent_rows.to_dict(orient="records")}


def get_filter_options(df: pd.DataFrame, mapping: dict[str, str | None]) -> dict[str, Any]:
    def col_values(col_name: str | None) -> list[str]:
        if not col_name or col_name not in df.columns:
            return []
        vals = sorted([str(v) for v in df[col_name].dropna().astype(str).unique().tolist()])
        return vals

    date_min = ""
    date_max = ""
    if mapping["date"] and mapping["date"] in df.columns and df[mapping["date"]].notna().any():
        date_min = str(df[mapping["date"]].min().date())
        date_max = str(df[mapping["date"]].max().date())

    category_product_map = {}
    if mapping["category"] and mapping["product"] and mapping["category"] in df.columns and mapping["product"] in df.columns:
        grouped = df.dropna(subset=[mapping["category"], mapping["product"]]).groupby(mapping["category"])[mapping["product"]].unique()
        for cat, prods in grouped.items():
            category_product_map[str(cat)] = sorted([str(p) for p in prods])

    return {
        "regions": col_values(mapping["region"]),
        "categories": col_values(mapping["category"]),
        "products": col_values(mapping["product"]),
        "category_product_map": category_product_map,
        "date_min": date_min,
        "date_max": date_max,
    }


def apply_filters(df: pd.DataFrame, mapping: dict[str, str | None], selected: dict[str, Any]) -> pd.DataFrame:
    filtered = df.copy()

    for filter_key in ["region", "category", "product"]:
        selected_value = str(selected.get(filter_key, "")).strip()
        mapped_col = mapping.get(filter_key)
        if selected_value and mapped_col and mapped_col in filtered.columns:
            filtered = filtered[filtered[mapped_col].astype(str) == selected_value]

    if mapping["date"] and mapping["date"] in filtered.columns:
        start_date = str(selected.get("start_date", "")).strip()
        end_date = str(selected.get("end_date", "")).strip()
        if start_date:
            filtered = filtered[filtered[mapping["date"]] >= pd.to_datetime(start_date, errors="coerce")]
        if end_date:
            filtered = filtered[filtered[mapping["date"]] <= pd.to_datetime(end_date, errors="coerce")]

    return filtered


def analyze_sales_data(df: pd.DataFrame, selected_filters: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_df, mapping = prepare_sales_dataframe(df)
    clean_df, quality = clean_and_enrich_dataframe(raw_df, mapping)

    if selected_filters:
        clean_df = apply_filters(clean_df, mapping, selected_filters)

    sales_col = mapping["sales"]
    assert sales_col is not None

    if clean_df.empty:
        return {
            "summary": {
                "total_revenue": 0,
                "total_records": 0,
                "average_sale": 0,
                "order_count": 0,
                "total_quantity": 0,
                "top_category": "N/A",
                "top_product": "N/A",
                "top_region": "N/A",
            },
            "charts": {k: {"labels": [], "values": []} for k in ["daily_sales", "weekly_sales", "monthly_sales", "forecast_sales", "category_sales", "region_sales", "top_products"]},
            "insights": ["No records matched the selected filters."],
            "recommendations": [],
            "table": {"columns": raw_df.columns.tolist(), "rows": []},
            "detected_columns": mapping,
            "quality": quality,
            "comparisons": {"monthly": comparison_block(pd.Series(dtype=float), "month_over_month"), "weekly": comparison_block(pd.Series(dtype=float), "week_over_week")},
            "filters": get_filter_options(clean_df, mapping),
        }

    total_revenue = round(float(clean_df[sales_col].sum()), 2)
    total_records = int(len(clean_df))
    average_sale = round(float(clean_df[sales_col].mean()), 2) if total_records else 0.0

    order_count = total_records
    if mapping["order_id"] and mapping["order_id"] in clean_df.columns:
        order_count = int(clean_df[mapping["order_id"]].nunique())

    total_quantity = 0
    if mapping["quantity"] and mapping["quantity"] in clean_df.columns:
        total_quantity = int(clean_df[mapping["quantity"]].fillna(0).sum())

    category_group = safe_group_sum(clean_df, mapping["category"], sales_col, 8)
    product_group = safe_group_sum(clean_df, mapping["product"], sales_col, 10)
    region_group = safe_group_sum(clean_df, mapping["region"], sales_col, 8)

    global_start = ""
    global_end = ""
    if mapping["date"] and mapping["date"] in raw_df.columns:
        valid_dates = raw_df[mapping["date"]].dropna()
        if not valid_dates.empty:
            global_start = str(valid_dates.min().date())
            global_end = str(valid_dates.max().date())

    start_date = selected_filters.get("start_date", "") if selected_filters else ""
    end_date = selected_filters.get("end_date", "") if selected_filters else ""
    
    if not start_date:
        start_date = global_start
    if not end_date:
        end_date = global_end

    daily_group, weekly_group, monthly_group = build_time_series(clean_df, mapping["date"], sales_col, start_date, end_date)
    monthly_comp = comparison_block(monthly_group, "month_over_month")
    weekly_comp = comparison_block(weekly_group, "week_over_week")

    top_category = str(category_group.index[0]) if not category_group.empty else "N/A"
    top_product = str(product_group.index[0]) if not product_group.empty else "N/A"
    top_region = str(region_group.index[0]) if not region_group.empty else "N/A"

    summary = {
        "total_revenue": total_revenue,
        "total_records": total_records,
        "average_sale": average_sale,
        "order_count": order_count,
        "total_quantity": total_quantity,
        "top_category": top_category,
        "top_product": top_product,
        "top_region": top_region,
    }

    sql_queries = generate_sql_queries(mapping, selected_filters)

    return {
        "summary": summary,
        "charts": {
            "daily_sales": make_chart_dataset(daily_group.index.tolist(), daily_group.values.tolist()) if not daily_group.empty else {"labels": [], "values": []},
            "weekly_sales": make_chart_dataset(weekly_group.index.tolist(), weekly_group.values.tolist()) if not weekly_group.empty else {"labels": [], "values": []},
            "monthly_sales": make_chart_dataset(monthly_group.index.tolist(), monthly_group.values.tolist()) if not monthly_group.empty else {"labels": [], "values": []},
            "forecast_sales": generate_forecast(monthly_group),
            "category_sales": make_chart_dataset(category_group.index.tolist(), category_group.values.tolist()) if not category_group.empty else {"labels": [], "values": []},
            "region_sales": make_chart_dataset(region_group.index.tolist(), region_group.values.tolist()) if not region_group.empty else {"labels": [], "values": []},
            "top_products": make_chart_dataset(product_group.index.tolist(), product_group.values.tolist()) if not product_group.empty else {"labels": [], "values": []},
        },
        "insights": build_insights(clean_df, mapping, quality, monthly_comp, weekly_comp),
        "recommendations": build_recommendations(summary, monthly_comp, weekly_comp, top_region, top_category),
        "table": serialize_preview(clean_df),
        "detected_columns": mapping,
        "quality": quality,
        "comparisons": {"monthly": monthly_comp, "weekly": weekly_comp},
        "filters": get_filter_options(clean_df, mapping),
        "sql_queries": sql_queries,
    }


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill in all fields.", "danger")
            return render_template("register.html")

        password_hash = generate_password_hash(password)
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, email, password_hash, datetime.now().isoformat()),
            )
            conn.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username or email already exists.", "danger")
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["email"] = user["email"]
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=session.get("username", "User"))


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Please choose a file."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV and Excel files are allowed."}), 400

    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    saved_path = UPLOAD_FOLDER / f"{timestamp}_{filename}"
    file.save(saved_path)
    session["last_file"] = str(saved_path)

    try:
        df = read_sales_file(saved_path)
        analysis_result = analyze_sales_data(df)
        
        # Cache essential data for chatbot to speed up response
        session["last_analysis_cache"] = {
            "summary": analysis_result["summary"],
            "insights": analysis_result["insights"],
            "filters": analysis_result["filters"],
            "detected_columns": analysis_result["detected_columns"]
        }
        
        return jsonify(analysis_result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/filter-analysis", methods=["POST"])
@login_required
def filter_analysis():
    last_file = session.get("last_file")
    if not last_file or not Path(last_file).exists():
        return jsonify({"error": "Please upload and analyze a sales file first."}), 400

    try:
        filters = request.get_json(silent=True) or {}
        df = read_sales_file(Path(last_file))
        analysis_result = analyze_sales_data(df, filters)
        
        # Update cache when filters change
        session["last_analysis_cache"] = {
            "summary": analysis_result["summary"],
            "insights": analysis_result["insights"],
            "filters": analysis_result["filters"],
            "detected_columns": analysis_result["detected_columns"]
        }
        
        return jsonify(analysis_result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        if not user_message:
            return jsonify({"error": "Empty message"}), 400
        
        # Build context from the last uploaded file
        context = ""
        last_file = session.get("last_file")
        
        # Check if we have a cached analysis to save time
        analysis = session.get("last_analysis_cache")
        
        if not analysis and last_file and Path(last_file).exists():
            try:
                df = read_sales_file(Path(last_file))
                analysis = analyze_sales_data(df)
                # We don't cache the whole thing (it's too big for session), just the summary
            except:
                pass

        if analysis:
            summary = analysis.get("summary", {})
            insights = analysis.get("insights", [])
            
            context = f"Dataset Summary:\n"
            context += f"- Total Revenue: {summary.get('total_revenue')}\n"
            context += f"- Total Records: {summary.get('total_records')}\n"
            context += f"- Order Count: {summary.get('order_count')}\n"
            context += f"- Total Quantity: {summary.get('total_quantity')}\n"
            context += f"- Average Sale Value: {summary.get('average_sale')}\n"
            
            # Add Date Range
            filters = analysis.get("filters", {})
            if filters.get("date_min"):
                context += f"- Date Range: {filters['date_min']} to {filters['date_max']}\n"

            # Add Category Performance
            cat_data = analysis.get("charts", {}).get("category_sales", {})
            if cat_data.get("labels"):
                context += "\nSales by Category:\n"
                for i in range(len(cat_data["labels"])):
                    context += f"- {cat_data['labels'][i]}: {cat_data['values'][i]}\n"

            # Add Regional Performance
            reg_data = analysis.get("charts", {}).get("region_sales", {})
            if reg_data.get("labels"):
                context += "\nSales by Region:\n"
                for i in range(len(reg_data["labels"])):
                    context += f"- {reg_data['labels'][i]}: {reg_data['values'][i]}\n"
            
            # Include the actual list of top products from the charts data
            top_prods_data = analysis.get("charts", {}).get("top_products", {})
            if top_prods_data.get("labels"):
                context += "\nTop 10 Products:\n"
                for i in range(len(top_prods_data["labels"])):
                    context += f"- {top_prods_data['labels'][i]}: {top_prods_data['values'][i]}\n"

            context += f"\nKey Insights:\n" + "\n".join([f"- {i}" for i in insights])
            
            # Add a bit of the table data as well
            table_preview = analysis.get("table", {}).get("rows", [])[:10]
            context += f"\n\nSample Data Preview (First 10 rows):\n{json.dumps(table_preview, indent=2)}"

        bot_response = ask_bot(user_message, context=context)
        return jsonify({"response": bot_response})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/health")
def health():
    return {"status": "ok", "message": "Retail Sales Analyzer is running."}


if __name__ == "__main__":
    app.run(debug=True)
