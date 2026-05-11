# Retail Sales Analytics Website

A fully working local Python website for retail sales data analysis.

## Features
- User registration and login
- CSV / Excel sales file upload
- Automatic ETL-style cleaning and data quality checks
- KPI dashboard
- Daily, weekly, and monthly sales trends
- Month-over-month and week-over-week comparisons
- Forecast chart for upcoming months
- Category, region, and product analysis
- Interactive filters by region, category, product, and date range
- Insights and recommendations
- Preview table for uploaded data

## Run locally
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open in browser:
```bash
http://127.0.0.1:5000
```

## Supported columns
Best supported columns include:
- Date
- Sales / Revenue / Amount / Total
- Quantity
- Category
- Product
- Region
- Order_ID

## Demo file
Use `sample_sales_data.csv` for quick testing.
