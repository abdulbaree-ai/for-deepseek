from flask import Flask, render_template, request, redirect, url_for, flash, make_response # Added make_response
import sqlite3
from datetime import datetime, timedelta
import calendar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
import csv # Added csv
from io import StringIO # Added StringIO

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here' # Change this in a real application

# Make datetime and calendar available in all templates
@app.context_processor
def inject_global_vars():
    return {'datetime': datetime, 'calendar': calendar}

# Initialize database
def init_db():
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT NOT NULL,
                  item TEXT NOT NULL,
                  category TEXT NOT NULL,
                  quantity REAL NOT NULL,
                  price REAL NOT NULL,
                  total REAL NOT NULL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT NOT NULL,
                  category TEXT NOT NULL,
                  description TEXT NOT NULL,
                  amount REAL NOT NULL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS salaries
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  role TEXT NOT NULL,
                  month TEXT NOT NULL,
                  year TEXT NOT NULL,
                  amount REAL NOT NULL,
                  status TEXT NOT NULL)''') # e.g., 'Pending', 'Paid'

    conn.commit()
    conn.close()

# Home page/dashboard
@app.route('/')
def dashboard():
    # Get filter parameters
    month_filter = request.args.get('month', 'all') # e.g., '01', '02', ..., '12', or 'all'
    year_filter = request.args.get('year', str(datetime.now().year)) # e.g., '2023', 'all'

    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    # Sales total
    sales_query = "SELECT SUM(total) FROM sales"
    sales_params = []
    conditions = []
    if month_filter != 'all':
        conditions.append("strftime('%m', date) = ?")
        sales_params.append(month_filter)
    if year_filter != 'all':
        conditions.append("strftime('%Y', date) = ?")
        sales_params.append(year_filter)
    if conditions:
        sales_query += " WHERE " + " AND ".join(conditions)
    c.execute(sales_query, sales_params)
    total_sales = c.fetchone()[0] or 0

    # Expenses total
    expenses_query = "SELECT SUM(amount) FROM expenses"
    expenses_params = []
    conditions = []
    if month_filter != 'all':
        conditions.append("strftime('%m', date) = ?")
        expenses_params.append(month_filter)
    if year_filter != 'all':
        conditions.append("strftime('%Y', date) = ?")
        expenses_params.append(year_filter)
    if conditions:
        expenses_query += " WHERE " + " AND ".join(conditions)
    c.execute(expenses_query, expenses_params)
    total_expenses = c.fetchone()[0] or 0

    # Salaries total (only 'Paid' status)
    salaries_query = "SELECT SUM(amount) FROM salaries WHERE status = 'Paid'"
    salaries_params = [] # Parameters for salaries query
    # Note: Salaries table uses 'month' and 'year' columns directly, not 'date'
    if month_filter != 'all':
        salaries_query += " AND month = ?"
        salaries_params.append(month_filter)
    if year_filter != 'all':
        salaries_query += " AND year = ?"
        salaries_params.append(year_filter)
    c.execute(salaries_query, salaries_params)
    total_salaries = c.fetchone()[0] or 0

    net_balance = total_sales - (total_expenses + total_salaries)

    # Generate chart
    chart_url = generate_trend_chart(month_filter, year_filter)

    conn.close()

    return render_template('dashboard.html',
                         total_sales=total_sales,
                         total_expenses=total_expenses,
                         total_salaries=total_salaries,
                         net_balance=net_balance,
                         # Pass current filter values back to template for display/selection
                         current_month_filter=month_filter,
                         current_year_filter=year_filter,
                         chart_url=chart_url)

def generate_trend_chart(month_param, year_param):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    labels = []
    sales_data = []
    expenses_data = []
    chart_xlabel = ""
    chart_title_period = ""
    chart_generated_successfully = True

    try:
        if month_param == 'all':
            # Monthly trends for the year_param (or all years if year_param is 'all')
            labels = [calendar.month_abbr[m] for m in range(1, 13)]
            sales_data = [0] * 12
            expenses_data = [0] * 12

            for i, month_abbr in enumerate(labels):
                current_month_str = f"{i+1:02d}"
                # Sales
                sales_q = "SELECT SUM(total) FROM sales WHERE strftime('%m', date) = ?"
                sales_p = [current_month_str]
                if year_param != 'all':
                    sales_q += " AND strftime('%Y', date) = ?"
                    sales_p.append(year_param)
                c.execute(sales_q, sales_p)
                sales_data[i] = c.fetchone()[0] or 0

                # Expenses
                expenses_q = "SELECT SUM(amount) FROM expenses WHERE strftime('%m', date) = ?"
                expenses_p = [current_month_str]
                if year_param != 'all':
                    expenses_q += " AND strftime('%Y', date) = ?"
                    expenses_p.append(year_param)
                c.execute(expenses_q, expenses_p)
                expenses_data[i] = c.fetchone()[0] or 0
            chart_xlabel = 'Month'
            chart_title_period = f"for {year_param}" if year_param != 'all' else "Overall (All Years)"

        else: # Daily trends for a specific month
            month_int = int(month_param)
            year_for_daily_chart_int = 0

            if year_param == 'all':
                year_for_daily_chart_int = datetime.now().year
                chart_title_period = f"for {calendar.month_name[month_int]} {year_for_daily_chart_int} (Daily - Current Year)"
            else:
                year_for_daily_chart_int = int(year_param)
                chart_title_period = f"for {calendar.month_name[month_int]} {year_for_daily_chart_int} (Daily)"

            if not (1 <= month_int <= 12):
                raise ValueError("Month is out of valid range (1-12).")

            num_days = calendar.monthrange(year_for_daily_chart_int, month_int)[1]
            labels = [str(d) for d in range(1, num_days + 1)]
            sales_data = [0] * num_days
            expenses_data = [0] * num_days

            year_for_daily_chart_str = str(year_for_daily_chart_int)

            # Sales
            sales_q = """SELECT CAST(strftime('%d', date) AS INTEGER) as day, SUM(total)
                             FROM sales
                             WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?
                             GROUP BY day"""
            c.execute(sales_q, [month_param, year_for_daily_chart_str])
            for day_val, total in c.fetchall():
                if day_val is not None and 1 <= day_val <= num_days:
                    sales_data[day_val - 1] = total

            # Expenses
            expenses_q = """SELECT CAST(strftime('%d', date) AS INTEGER) as day, SUM(amount)
                                FROM expenses
                                WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?
                                GROUP BY day"""
            c.execute(expenses_q, [month_param, year_for_daily_chart_str])
            for day_val, total in c.fetchall():
                if day_val is not None and 1 <= day_val <= num_days:
                    expenses_data[day_val - 1] = total
            chart_xlabel = 'Day of Month'

    except ValueError as e: # Catch issues with int conversion or month/year validity for calendar
        flash(f"Chart generation error: {e}", "danger")
        chart_generated_successfully = False
    except Exception as e: # Catch any other unexpected errors during data fetching
        flash(f"An unexpected error occurred while preparing chart data: {e}", "danger")
        chart_generated_successfully = False

    conn.close()

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 5))

    if chart_generated_successfully and labels:
        # Original plotting style: two bars at same x-positions (will overlap)
        ax.bar(labels, sales_data, label='Sales', color='#2c7a4d', alpha=0.7)
        ax.bar(labels, expenses_data, label='Expenses', color='#e74c3c', alpha=0.7)

        ax.set_ylabel('Amount ($)')
        ax.set_xlabel(chart_xlabel)
        ax.set_title(f'Sales vs Expenses Trend {chart_title_period}')
        ax.legend()
    else:
        # Display a message if chart generation failed or no data
        ax.text(0.5, 0.5, 'No data available or error in chart generation.',
                horizontalalignment='center', verticalalignment='center',
                transform=ax.transAxes, fontsize=12, color='gray')
        ax.set_title('Sales vs Expenses Trend')
        ax.axis('off') # Hide axes for message display

    fig.tight_layout() # Adjust plot to prevent labels from being cut off

    # Save plot to a bytes buffer
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig) # Important to close the figure object

    # Encode the image for HTML
    chart_url_encoded = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{chart_url_encoded}"

# --- NEW SECTION: Reporting Functions and Route (Existing) ---

def get_weekly_summary(start_date_str, end_date_str):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    # Calculate totals for the specified week
    # Note: SQLite date comparisons on TEXT fields work correctly if format is YYYY-MM-DD
    sales_q = "SELECT SUM(total) FROM sales WHERE date BETWEEN ? AND ?"
    expenses_q = "SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?"

    c.execute(sales_q, (start_date_str, end_date_str))
    total_sales = c.fetchone()[0] or 0

    c.execute(expenses_q, (start_date_str, end_date_str))
    total_expenses = c.fetchone()[0] or 0

    # Salaries are typically monthly, so they are not included in a weekly financial summary
    total_salaries = 0 # Explicitly set to 0 or handled as 'N/A' in template

    net_balance = total_sales - total_expenses # Salaries excluded from weekly net

    conn.close()
    return total_sales, total_expenses, total_salaries, net_balance

def get_monthly_summary(month, year):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    month_str = f"{int(month):02d}" # Ensure two digits for month
    year_str = str(year)

    # Sales total
    sales_q = "SELECT SUM(total) FROM sales WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?"
    c.execute(sales_q, (month_str, year_str))
    total_sales = c.fetchone()[0] or 0

    # Expenses total
    expenses_q = "SELECT SUM(amount) FROM expenses WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?"
    c.execute(expenses_q, (month_str, year_str))
    total_expenses = c.fetchone()[0] or 0

    # Salaries total (only 'Paid' status)
    salaries_q = "SELECT SUM(amount) FROM salaries WHERE status = 'Paid' AND month = ? AND year = ?"
    c.execute(salaries_q, (month_str, year_str))
    total_salaries = c.fetchone()[0] or 0

    net_balance = total_sales - (total_expenses + total_salaries)

    conn.close()
    return total_sales, total_expenses, total_salaries, net_balance

# This is the existing /reports route from previous instruction
@app.route('/reports', methods=['GET', 'POST'])
def reports():
    report_type = request.args.get('report_type', 'monthly') # Default to monthly on initial GET
    
    report_data = []
    report_title = "Financial Reports"
    
    # Get current year and month for default selections in the form
    current_year = datetime.now().year
    current_month_num = datetime.now().month
    
    # Options for year and month dropdowns
    years_available = range(current_year - 5, current_year + 2) # 5 years back, current, 1 year forward
    months_available = [{'num': f"{i:02d}", 'name': calendar.month_name[i]} for i in range(1, 13)]

    if request.method == 'POST':
        report_type = request.form.get('report_type')

        if report_type == 'weekly':
            start_date_str = request.form.get('week_start_date')
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    end_date = start_date + timedelta(days=6) # A week is 7 days (start to end inclusive)
                    end_date_str = end_date.strftime('%Y-%m-%d')

                    total_sales, total_expenses, total_salaries, net_balance = get_weekly_summary(start_date_str, end_date_str)
                    report_data.append({
                        'period': f"Week of {start_date_str} to {end_date_str}",
                        'sales': total_sales,
                        'expenses': total_expenses,
                        'salaries': 'N/A', # Salaries not included in weekly breakdown
                        'net_balance': net_balance
                    })
                    report_title = f"Weekly Report for {start_date_str} - {end_date_str}"
                except ValueError:
                    flash("Invalid date format for weekly report. Please use YYYY-MM-DD.", "danger")
            else:
                flash("Please select a start date for the weekly report.", "danger")

        elif report_type == 'monthly':
            month_param = request.form.get('month_select')
            year_param = request.form.get('year_select')

            if month_param and year_param:
                try:
                    # Generate report for the selected month/year
                    total_sales, total_expenses, total_salaries, net_balance = get_monthly_summary(month_param, year_param)
                    report_data.append({
                        'period': f"{calendar.month_name[int(month_param)]} {year_param}",
                        'sales': total_sales,
                        'expenses': total_expenses,
                        'salaries': total_salaries,
                        'net_balance': net_balance
                    })
                    report_title = f"Monthly Report for {calendar.month_name[int(month_param)]} {year_param}"
                except ValueError:
                    flash("Invalid month or year selected for monthly report.", "danger")
            else:
                flash("Please select both month and year for the monthly report.", "danger")

    return render_template('reports.html',
                           report_type=report_type,
                           report_data=report_data,
                           report_title=report_title,
                           years=sorted(list(years_available)), # Ensure sorted for dropdown
                           months=months_available,
                           current_year=current_year,
                           current_month=f"{current_month_num:02d}") # Pass as 2-digit string for comparison


# --- NEW REPORTING FEATURES (from your snippet) ---

@app.route('/generate_report', methods=['POST'])
def generate_report():
    report_type = request.form['report_type']
    period = request.form['period']  # 'monthly' or 'annual'
    year = request.form.get('year', str(datetime.now().year)) # Ensure year is string for SQL comparison
    month = request.form.get('month', f"{datetime.now().month:02d}") # Ensure month is 2-digit string

    data = {} # Initialize data dictionary

    # Generate the appropriate report
    if report_type == 'financial_summary':
        data = generate_financial_summary(period, year, month)
    elif report_type == 'category_breakdown':
        data = generate_category_breakdown(period, year, month)
    elif report_type == 'staff_salaries':
        data = generate_staff_salaries_report(period, year, month)
    else:
        flash("Invalid report type selected.", "danger")
        return redirect(url_for('reports')) # Redirect back if invalid

    format = request.form['format']

    if format == 'pdf':
        flash("PDF generation requires additional libraries and is not fully implemented in this example.", "warning")
        # For now, redirect or show a message instead of a broken PDF response
        return redirect(url_for('reports'))
        # return generate_pdf_report(data, report_type) # Uncomment if you implement PDF

    elif format == 'csv':
        return generate_csv_report(data, report_type)
    elif format == 'html':
        return generate_html_report(data, report_type)
    else:
        flash("Invalid report format selected.", "danger")
        return redirect(url_for('reports'))


# Report generation functions (corrected SQL for financial summary)
def generate_financial_summary(period, year, month):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()
    
    if period == 'monthly':
        # Monthly summary
        c.execute("""
            SELECT strftime('%Y-%m', date) as period,
                   SUM(total) as sales,
                   (SELECT SUM(amount) FROM expenses WHERE strftime('%Y-%m', date) = strftime('%Y-%m', s.date)) as expenses,
                   (SELECT SUM(amount) FROM salaries WHERE status='Paid' 
                    AND year || '-' || month = strftime('%Y-%m', s.date)) as salaries
            FROM sales s
            WHERE strftime('%Y', date) = ?
            GROUP BY strftime('%Y-%m', date)
            ORDER BY period
        """, (year,))
    else:
        # Annual summary
        c.execute("""
            SELECT strftime('%Y', date) as period,
                   SUM(total) as sales,
                   (SELECT SUM(amount) FROM expenses WHERE strftime('%Y', date) = strftime('%Y', s.date)) as expenses,
                   (SELECT SUM(amount) FROM salaries WHERE status='Paid' 
                    AND year = strftime('%Y', s.date)) as salaries
            FROM sales s
            GROUP BY strftime('%Y', date)
            ORDER BY period
        """)
    
    results = c.fetchall()
    conn.close()
    
    return {
        'title': 'Financial Summary Report',
        'period': period,
        'year': year,
        'month': month,
        'data': results
    }

def generate_category_breakdown(period, year, month):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    sales = []
    expenses = []

    if period == 'monthly':
        # Monthly category breakdown
        c.execute("""
            SELECT category, SUM(total) as amount
            FROM sales
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
            GROUP BY category
        """, (year, month)) # Use year and month directly
        sales = c.fetchall()

        c.execute("""
            SELECT category, SUM(amount) as amount
            FROM expenses
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
            GROUP BY category
        """, (year, month)) # Use year and month directly
        expenses = c.fetchall()
    else: # annual
        # Annual category breakdown
        c.execute("""
            SELECT category, SUM(total) as amount
            FROM sales
            WHERE strftime('%Y', date) = ?
            GROUP BY category
        """, (year,))
        sales = c.fetchall()

        c.execute("""
            SELECT category, SUM(amount) as amount
            FROM expenses
            WHERE strftime('%Y', date) = ?
            GROUP BY category
        """, (year,))
        expenses = c.fetchall()

    conn.close()

    return {
        'title': 'Category Breakdown Report',
        'period': period,
        'year': year,
        'month': month,
        'sales': sales,
        'expenses': expenses
    }

def generate_staff_salaries_report(period, year, month):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    results = []

    if period == 'monthly':
        # Monthly staff salaries
        c.execute("""
            SELECT name, role, amount, status
            FROM salaries
            WHERE year = ? AND month = ?
            ORDER BY status, role, name
        """, (year, month)) # Ensure month is 2-digit string
        results = c.fetchall()
    else: # annual
        # Annual staff salaries
        c.execute("""
            SELECT name, role, SUM(amount) as total_amount,
                   SUM(CASE WHEN status='Paid' THEN amount ELSE 0 END) as paid_amount,
                   SUM(CASE WHEN status='Pending' THEN amount ELSE 0 END) as pending_amount
            FROM salaries
            WHERE year = ?
            GROUP BY name, role
            ORDER BY role, name
        """, (year,))
        results = c.fetchall() # Fetches (name, role, total_amount, paid_amount, pending_amount)

        # Transform for display/CSV: (name, role, Annual Total, Paid Months, Unpaid Months)
        # We need to calculate paid/unpaid months separately or adjust the query to count status entries.
        # Let's adjust the query to count months as per the original snippet's intent.
        conn.close() # Close and re-open to ensure fresh cursor if needed, or just run new query
        conn = sqlite3.connect('zoo_finance.db')
        c = conn.cursor()
        c.execute("""
            SELECT name, role, SUM(amount) as total_amount,
                   COUNT(CASE WHEN status='Paid' THEN 1 ELSE NULL END) as paid_months,
                   COUNT(CASE WHEN status='Pending' THEN 1 ELSE NULL END) as pending_months_count -- Renamed to avoid confusion with original snippet's 'unpaid_months'
            FROM salaries
            WHERE year = ?
            GROUP BY name, role
            ORDER BY role, name
        """, (year,))
        results = c.fetchall()

    conn.close()

    return {
        'title': 'Staff Salaries Report',
        'period': period,
        'year': year,
        'month': month,
        'data': results
    }

# Report format generators
def generate_pdf_report(data, report_type):
    # This would use a library like ReportLab or WeasyPrint
    # For now, we'll return a placeholder
    response = make_response("PDF report would be generated here")
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={report_type}_report.pdf'
    return response

def generate_csv_report(data, report_type):
    si = StringIO()
    cw = csv.writer(si)

    # Write header
    cw.writerow([data['title']])
    period_info = f"Period: {data['period'].capitalize()}"
    if data['period'] == 'monthly':
        period_info += f", Year: {data['year']}, Month: {calendar.month_name[int(data['month'])]}"
    else: # Annual
        period_info += f", Year: {data['year']}" if data['year'] != 'all' else ", All Years" # Handle 'all' years for annual
    cw.writerow([period_info])
    cw.writerow([])

    # Write data based on report type
    if report_type == 'financial_summary':
        cw.writerow(['Period', 'Sales', 'Expenses', 'Salaries', 'Net Balance'])
        for row in data['data']:
            period_key, sales, expenses, salaries = row
            net = sales - (expenses + salaries)
            cw.writerow([period_key, f"{sales:.2f}", f"{expenses:.2f}", f"{salaries:.2f}", f"{net:.2f}"])

    elif report_type == 'category_breakdown':
        cw.writerow(['Sales by Category'])
        cw.writerow(['Category', 'Amount'])
        for row in data['sales']:
            cw.writerow([row[0], f"{row[1]:.2f}"])

        cw.writerow([])
        cw.writerow(['Expenses by Category'])
        cw.writerow(['Category', 'Amount'])
        for row in data['expenses']:
            cw.writerow([row[0], f"{row[1]:.2f}"])

    elif report_type == 'staff_salaries':
        if data['period'] == 'monthly':
            cw.writerow(['Name', 'Role', 'Amount', 'Status'])
            for row in data['data']:
                cw.writerow([row[0], row[1], f"{row[2]:.2f}", row[3]])
        else: # Annual
            # Adjusted headers for annual to reflect the query results (Total amount, Paid Months, Pending Months)
            cw.writerow(['Name', 'Role', 'Annual Total Amount', 'Paid Months', 'Pending Months'])
            for row in data['data']:
                cw.writerow([row[0], row[1], f"{row[2]:.2f}", row[3], row[4]])

    output = make_response(si.getvalue())
    output.headers['Content-Type'] = 'text/csv'
    output.headers['Content-Disposition'] = f'attachment; filename={report_type}_report.csv'
    return output

def generate_html_report(data, report_type):
    # This will render a dedicated HTML template for the report data
    return render_template('report_template.html', data=data, report_type=report_type, calendar=calendar) # Pass calendar for month names

# Sales routes
@app.route('/sales', methods=['GET', 'POST'])
def sales():
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    if request.method == 'POST':
        try:
            date = request.form['date']
            item = request.form['item']
            category = request.form['category']
            quantity = float(request.form['quantity'])
            price = float(request.form['price'])
            if quantity <= 0 or price < 0:
                flash('Quantity must be positive and price cannot be negative.', 'danger')
            else:
                total = quantity * price
                c.execute("INSERT INTO sales (date, item, category, quantity, price, total) VALUES (?, ?, ?, ?, ?, ?)",
                         (date, item, category, quantity, price, total))
                conn.commit()
                flash('Sale added successfully!', 'success')
        except ValueError:
            flash('Invalid input for quantity or price. Please enter numbers.', 'danger')
        except Exception as e:
            flash(f'Error adding sale: {e}', 'danger')
        conn.close()
        return redirect(url_for('sales'))

    # GET request: Display sales
    # Get filter parameters
    month_filter = request.args.get('month', 'all')
    category_filter = request.args.get('category', 'all')

    sales_query = "SELECT * FROM sales"
    params = []
    conditions = []

    if month_filter != 'all':
        conditions.append("strftime('%m', date) = ?")
        params.append(month_filter)
    if category_filter != 'all':
        conditions.append("category = ?")
        params.append(category_filter)

    if conditions:
        sales_query += " WHERE " + " AND ".join(conditions)

    sales_query += " ORDER BY date DESC"
    c.execute(sales_query, params)
    sales_records = c.fetchall()
    conn.close()

    return render_template('sales.html',
                           sales=sales_records,
                           current_month_filter=month_filter,
                           current_category_filter=category_filter)

# Expenses routes
@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    if request.method == 'POST':
        try:
            date = request.form['date']
            category = request.form['category']
            description = request.form['description']
            amount = float(request.form['amount'])
            if amount <= 0:
                 flash('Amount must be a positive value.', 'danger')
            else:
                c.execute("INSERT INTO expenses (date, category, description, amount) VALUES (?, ?, ?, ?)",
                         (date, category, description, amount))
                conn.commit()
                flash('Expense added successfully!', 'success')
        except ValueError:
            flash('Invalid input for amount. Please enter a number.', 'danger')
        except Exception as e:
            flash(f'Error adding expense: {e}', 'danger')
        conn.close()
        return redirect(url_for('expenses'))

    # GET request: Display expenses
    month_filter = request.args.get('month', 'all')
    category_filter = request.args.get('category', 'all')

    expenses_query = "SELECT * FROM expenses"
    params = []
    conditions = []

    if month_filter != 'all':
        conditions.append("strftime('%m', date) = ?")
        params.append(month_filter)
    if category_filter != 'all':
        conditions.append("category = ?")
        params.append(category_filter)

    if conditions:
        expenses_query += " WHERE " + " AND ".join(conditions)

    expenses_query += " ORDER BY date DESC"
    c.execute(expenses_query, params)
    expenses_records = c.fetchall()
    conn.close()

    return render_template('expenses.html',
                           expenses=expenses_records,
                           current_month_filter=month_filter,
                           current_category_filter=category_filter)

# Salaries routes
@app.route('/salaries', methods=['GET', 'POST'])
def salaries():
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    if request.method == 'POST':
        try:
            name = request.form['name']
            role = request.form['role']
            salary_month = request.form['month'] # This is '01'-'12'
            salary_year = request.form['year']   # This is 'YYYY'
            amount = float(request.form['amount'])
            status = request.form['status']
            if amount <=0:
                flash('Salary amount must be positive.', 'danger')
            else:
                c.execute("INSERT INTO salaries (name, role, month, year, amount, status) VALUES (?, ?, ?, ?, ?, ?)",
                         (name, role, salary_month, salary_year, amount, status))
                conn.commit()
                flash('Salary record added successfully!', 'success')
        except ValueError:
            flash('Invalid input for amount. Please enter a number.', 'danger')
        except Exception as e:
            flash(f'Error adding salary: {e}', 'danger')
        conn.close()
        return redirect(url_for('salaries'))

    # GET request: Display salaries
    month_filter = request.args.get('month', 'all') # Filter by salary_month
    status_filter = request.args.get('status', 'all')

    salaries_query = "SELECT * FROM salaries"
    params = []
    conditions = []

    if month_filter != 'all':
        conditions.append("month = ?") # Direct match for month column
        params.append(month_filter)
    if status_filter != 'all':
        conditions.append("status = ?")
        params.append(status_filter)

    if conditions:
        salaries_query += " WHERE " + " AND ".join(conditions)

    salaries_query += " ORDER BY year DESC, month DESC, name ASC"
    c.execute(salaries_query, params)
    salaries_records = c.fetchall()
    conn.close()

    return render_template('salaries.html',
                           salaries=salaries_records,
                           current_month_filter=month_filter,
                           current_status_filter=status_filter)

# Delete routes
@app.route('/delete/sale/<int:id>')
def delete_sale(id):
    try:
        conn = sqlite3.connect('zoo_finance.db')
        c = conn.cursor()
        c.execute("DELETE FROM sales WHERE id = ?", (id,))
        conn.commit()
        flash('Sale deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting sale: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('sales'))

@app.route('/delete/expense/<int:id>')
def delete_expense(id):
    try:
        conn = sqlite3.connect('zoo_finance.db')
        c = conn.cursor()
        c.execute("DELETE FROM expenses WHERE id = ?", (id,))
        conn.commit()
        flash('Expense deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting expense: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('expenses'))

@app.route('/delete/salary/<int:id>')
def delete_salary(id):
    try:
        conn = sqlite3.connect('zoo_finance.db')
        c = conn.cursor()
        c.execute("DELETE FROM salaries WHERE id = ?", (id,))
        conn.commit()
        flash('Salary record deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting salary record: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('salaries'))

@app.route('/mark_paid/salary/<int:id>')
def mark_paid(id):
    try:
        conn = sqlite3.connect('zoo_finance.db')
        c = conn.cursor()
        c.execute("UPDATE salaries SET status = 'Paid' WHERE id = ?", (id,))
        conn.commit()
        flash('Salary marked as paid!', 'success')
    except Exception as e:
        flash(f'Error marking salary as paid: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('salaries'))

if __name__ == '__main__':
    init_db() # Initialize the database and tables if they don't exist
    app.run(debug=True, host='0.0.0.0', port=5001) # Changed port for potential conflict avoidance