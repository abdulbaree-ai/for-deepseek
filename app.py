from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import sqlite3
from datetime import datetime, timedelta
import calendar
import csv
from io import StringIO

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

    # --- Prepare data for Chart.js ---
    chart_labels = []
    chart_sales_data = []
    chart_expenses_data = []
    chart_title_period = ""

    try:
        if month_filter == 'all':
            # Monthly trends for the year_filter (or all years if year_filter is 'all')
            chart_labels = [calendar.month_abbr[m] for m in range(1, 13)]
            chart_sales_data = [0] * 12
            chart_expenses_data = [0] * 12

            for i, month_abbr in enumerate(chart_labels):
                current_month_str = f"{i+1:02d}"
                # Sales
                sales_q = "SELECT SUM(total) FROM sales WHERE strftime('%m', date) = ?"
                sales_p = [current_month_str]
                if year_filter != 'all':
                    sales_q += " AND strftime('%Y', date) = ?"
                    sales_p.append(year_filter)
                c.execute(sales_q, sales_p)
                chart_sales_data[i] = c.fetchone()[0] or 0

                # Expenses
                expenses_q = "SELECT SUM(amount) FROM expenses WHERE strftime('%m', date) = ?"
                expenses_p = [current_month_str]
                if year_filter != 'all':
                    expenses_q += " AND strftime('%Y', date) = ?"
                    expenses_p.append(year_filter)
                c.execute(expenses_q, expenses_p)
                chart_expenses_data[i] = c.fetchone()[0] or 0
            chart_title_period = f"for {year_filter}" if year_filter != 'all' else "Overall (All Years)"

        else: # Daily trends for a specific month
            month_int = int(month_filter)
            year_for_daily_chart_int = 0

            if year_filter == 'all':
                year_for_daily_chart_int = datetime.now().year
                chart_title_period = f"for {calendar.month_name[month_int]} {year_for_daily_chart_int} (Daily - Current Year)"
            else:
                year_for_daily_chart_int = int(year_filter)
                chart_title_period = f"for {calendar.month_name[month_int]} {year_for_daily_chart_int} (Daily)"

            if not (1 <= month_int <= 12):
                raise ValueError("Month is out of valid range (1-12).")

            num_days = calendar.monthrange(year_for_daily_chart_int, month_int)[1]
            chart_labels = [str(d) for d in range(1, num_days + 1)]
            chart_sales_data = [0] * num_days
            chart_expenses_data = [0] * num_days

            year_for_daily_chart_str = str(year_for_daily_chart_int)

            # Sales
            sales_q = """SELECT CAST(strftime('%d', date) AS INTEGER) as day, SUM(total)\n                             FROM sales\n                             WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?\n                             GROUP BY day"""
            c.execute(sales_q, [month_filter, year_for_daily_chart_str])
            for day_val, total in c.fetchall():
                if day_val is not None and 1 <= day_val <= num_days:
                    chart_sales_data[day_val - 1] = total

            # Expenses
            expenses_q = """SELECT CAST(strftime('%d', date) AS INTEGER) as day, SUM(amount)\n                                FROM expenses\n                                WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?\n                                GROUP BY day"""
            c.execute(expenses_q, [month_filter, year_for_daily_chart_str])
            for day_val, total in c.fetchall():
                if day_val is not None and 1 <= day_val <= num_days:
                    chart_expenses_data[day_val - 1] = total

    except ValueError as e:
        flash(f"Chart data error: {e}", "danger")
    except Exception as e:
        flash(f"An unexpected error occurred while preparing chart data: {e}", "danger")

    # Fetch recent sales and expenses for the "Recent Activity" section
    c.execute("SELECT * FROM sales ORDER BY date DESC LIMIT 5")
    recent_sales = c.fetchall()

    c.execute("SELECT * FROM expenses ORDER BY date DESC LIMIT 5")
    recent_expenses = c.fetchall()

    conn.close()

    return render_template('dashboard.html',
                         total_sales=total_sales,
                         total_expenses=total_expenses,
                         total_salaries=total_salaries,
                         net_balance=net_balance,
                         current_month_filter=month_filter,
                         current_year_filter=year_filter,
                         chart_labels=chart_labels,
                         chart_sales_data=chart_sales_data,
                         chart_expenses_data=chart_expenses_data,
                         chart_title_period=chart_title_period,
                         current_hour=datetime.now().hour, # Pass current hour for personalized greeting
                         recent_sales=recent_sales,
                         recent_expenses=recent_expenses)

# --- Reporting Functions and Route (Existing) ---

def get_weekly_summary(start_date_str, end_date_str):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    sales_q = "SELECT SUM(total) FROM sales WHERE date BETWEEN ? AND ?"
    expenses_q = "SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?"

    c.execute(sales_q, (start_date_str, end_date_str))
    total_sales = c.fetchone()[0] or 0

    c.execute(expenses_q, (start_date_str, end_date_str))
    total_expenses = c.fetchone()[0] or 0

    total_salaries = 0

    net_balance = total_sales - total_expenses

    conn.close()
    return total_sales, total_expenses, total_salaries, net_balance

def get_monthly_summary(month, year):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    month_str = f"{int(month):02d}"
    year_str = str(year)

    sales_q = "SELECT SUM(total) FROM sales WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?"
    c.execute(sales_q, (month_str, year_str))
    total_sales = c.fetchone()[0] or 0

    expenses_q = "SELECT SUM(amount) FROM expenses WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?"
    c.execute(expenses_q, (month_str, year_str))
    total_expenses = c.fetchone()[0] or 0

    salaries_q = "SELECT SUM(amount) FROM salaries WHERE status = 'Paid' AND month = ? AND year = ?"
    c.execute(salaries_q, (month_str, year_str))
    total_salaries = c.fetchone()[0] or 0

    net_balance = total_sales - (total_expenses + total_salaries)

    conn.close()
    return total_sales, total_expenses, total_salaries, net_balance

@app.route('/reports', methods=['GET', 'POST'])
def reports():
    report_type = request.args.get('report_type', 'monthly')
    
    report_data = []
    report_title = "Financial Reports"
    
    current_year = datetime.now().year
    current_month_num = datetime.now().month
    
    years_available = range(current_year - 5, current_year + 2)
    months_available = [{'num': f"{i:02d}", 'name': calendar.month_name[i]} for i in range(1, 13)]

    # Initialize 'data' to an empty dictionary for the initial GET request
    # This prevents the 'data' undefined error when first loading the page
    data = {
        'sales_chart_labels': [],
        'sales_chart_data': [],
        'expenses_chart_labels': [],
        'expenses_chart_data': [],
        'sales_table_data': [],
        'expenses_table_data': [],
        'data': [] # For financial summary and staff salaries data
    } 

    if request.method == 'POST':
        report_type = request.form.get('report_type')

        if report_type == 'weekly':
            start_date_str = request.form.get('week_start_date')
            end_date_str = request.form.get('week_end_date') # Get end date from hidden input
            if start_date_str and end_date_str: # Ensure both dates are present
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d') # Parse end date
                    
                    total_sales, total_expenses, total_salaries, net_balance = get_weekly_summary(start_date_str, end_date_str)
                    report_data.append({
                        'period': f"Week of {start_date_str} to {end_date_str}",
                        'sales': total_sales,
                        'expenses': total_expenses,
                        'salaries': 'N/A',
                        'net_balance': net_balance
                    })
                    report_title = f"Weekly Report for {start_date_str} - {end_date_str}"
                except ValueError:
                    flash("Invalid date format for weekly report. Please use YYYY-MM-DD.", "danger")
            else:
                flash("Please select a start and end date for the weekly report.", "danger")

        elif report_type == 'monthly':
            month_param = request.form.get('month_select')
            year_param = request.form.get('year_select')

            if month_param and year_param:
                try:
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
                           years=sorted(list(years_available)),
                           months=months_available,
                           current_year=current_year,
                           current_month=f"{current_month_num:02d}",
                           data=data) # Ensure 'data' is always passed

# --- NEW REPORTING FEATURES (from your snippet) ---

@app.route('/generate_report', methods=['POST'])
def generate_report():
    report_type = request.form['report_type']
    period = request.form['period']
    year = request.form.get('year', str(datetime.now().year))
    month = request.form.get('month', f"{datetime.now().month:02d}")

    # Initialize data with all possible keys to prevent Undefined errors in template
    data = {
        'title': '',
        'period': period,
        'year': year,
        'month': month,
        'data': [], # For financial summary and staff salaries table data
        'sales_table_data': [],
        'expenses_table_data': [],
        'sales_chart_labels': [],
        'sales_chart_data': [],
        'expenses_chart_labels': [],
        'expenses_chart_data': []
    }

    if report_type == 'financial_summary':
        financial_data = generate_financial_summary(period, year, month)
        data.update(financial_data) # Update only relevant keys
    elif report_type == 'category_breakdown':
        category_data = generate_category_breakdown(period, year, month)
        data.update(category_data) # Update only relevant keys
    elif report_type == 'staff_salaries':
        salaries_data = generate_staff_salaries_report(period, year, month)
        data.update(salaries_data) # Update only relevant keys
    else:
        flash("Invalid report type selected.", "danger")
        return redirect(url_for('reports'))

    format = request.form['format']

    if format == 'pdf':
        flash("PDF generation requires additional libraries and is not fully implemented in this example.", "warning")
        return redirect(url_for('reports'))

    elif format == 'csv':
        return generate_csv_report(data, report_type)
    elif format == 'html':
        # Pass the data directly to the HTML report rendering
        # This allows reports.html to access the chart data directly
        return render_template('reports.html', 
                               data=data, 
                               report_type=report_type, 
                               calendar=calendar,
                               # Re-pass filter selections for context on the report page
                               current_year_filter=year,
                               current_month_filter=month,
                               current_period_filter=period)
    else:
        flash("Invalid report format selected.", "danger")
        return redirect(url_for('reports'))


# Report generation functions (corrected SQL for financial summary)
def generate_financial_summary(period, year, month):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    if period == 'monthly':
        query = """
            SELECT
                strftime('%Y-%m', s.date) AS period_key,
                SUM(s.total) AS sales_total,
                (SELECT SUM(e.amount) FROM expenses e WHERE strftime('%Y-%m', e.date) = strftime('%Y-%m', s.date)) AS expenses_total,
                (SELECT SUM(sal.amount) FROM salaries sal WHERE sal.year || '-' || sal.month = strftime('%Y-%m', s.date) AND sal.status = 'Paid') AS salaries_total
            FROM sales s
            WHERE strftime('%Y', s.date) = ?
            GROUP BY period_key
            ORDER BY period_key
        """
        c.execute(query, (year,))
    else: # annual
        # Corrected subqueries to filter by year directly, not 'period_key'
        query = """
            SELECT
                strftime('%Y', s.date) AS period_key,
                SUM(s.total) AS sales_total,
                (SELECT SUM(e.amount) FROM expenses e WHERE strftime('%Y', e.date) = strftime('%Y', s.date)) AS expenses_total,
                (SELECT SUM(sal.amount) FROM salaries sal WHERE sal.year = strftime('%Y', s.date) AND sal.status = 'Paid') AS salaries_total
            FROM sales s
        """
        if year != 'all':
             query += " WHERE strftime('%Y', s.date) = ?"
             query += " GROUP BY period_key ORDER BY period_key"
             c.execute(query, (year,))
        else:
             query += " GROUP BY period_key ORDER BY period_key"
             c.execute(query)

    results = c.fetchall()
    conn.close()

    formatted_results = []
    for row in results:
        period_key, sales, expenses, salaries = row
        formatted_results.append((
            period_key,
            sales or 0.0,
            expenses or 0.0,
            salaries or 0.0
        ))

    return {
        'title': 'Financial Summary Report',
        'period': period,
        'year': year,
        'month': month,
        'data': formatted_results
    }

def generate_category_breakdown(period, year, month):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    sales_data = [] # List of tuples (category, amount)
    expenses_data = [] # List of tuples (category, amount)

    if period == 'monthly':
        c.execute("""
            SELECT category, SUM(total) as amount
            FROM sales
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
            GROUP BY category
            ORDER BY amount DESC
        """, (year, month))
        sales_data = c.fetchall()

        c.execute("""
            SELECT category, SUM(amount) as amount
            FROM expenses
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
            GROUP BY category
            ORDER BY amount DESC
        """, (year, month))
        expenses_data = c.fetchall()
    else: # annual or all years
        sales_query = """
            SELECT category, SUM(total) as amount
            FROM sales
        """
        expenses_query = """
            SELECT category, SUM(amount) as amount
            FROM expenses
        """
        params = []
        if year != 'all':
            sales_query += " WHERE strftime('%Y', date) = ?"
            expenses_query += " WHERE strftime('%Y', date) = ?"
            params.append(year)
        
        sales_query += " GROUP BY category ORDER BY amount DESC"
        expenses_query += " GROUP BY category ORDER BY amount DESC"

        c.execute(sales_query, params)
        sales_data = c.fetchall()

        c.execute(expenses_query, params)
        expenses_data = c.fetchall()

    conn.close()

    # Prepare data for Chart.js
    sales_labels = [row[0] for row in sales_data]
    sales_amounts = [row[1] for row in sales_data]
    
    expenses_labels = [row[0] for row in expenses_data]
    expenses_amounts = [row[1] for row in expenses_data]

    return {
        'title': 'Category Breakdown Report',
        'period': period,
        'year': year,
        'month': month,
        'sales_table_data': sales_data, # For display in HTML table
        'expenses_table_data': expenses_data, # For display in HTML table
        'sales_chart_labels': sales_labels, # For Chart.js
        'sales_chart_data': sales_amounts, # For Chart.js
        'expenses_chart_labels': expenses_labels, # For Chart.js
        'expenses_chart_data': expenses_amounts # For Chart.js
    }

def generate_staff_salaries_report(period, year, month):
    conn = sqlite3.connect('zoo_finance.db')
    c = conn.cursor()

    results = []

    if period == 'monthly':
        c.execute("""
            SELECT name, role, amount, status
            FROM salaries
            WHERE year = ? AND month = ?
            ORDER BY status, role, name
        """, (year, month))
        results = c.fetchall()
    else: # annual
        conn.close()
        conn = sqlite3.connect('zoo_finance.db')
        c = conn.cursor()
        c.execute("""
            SELECT name, role, SUM(amount) as total_amount,
                   COUNT(CASE WHEN status='Paid' THEN 1 ELSE NULL END) as paid_months,
                   COUNT(CASE WHEN status='Pending' THEN 1 ELSE NULL END) as pending_months_count
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

def generate_pdf_report(data, report_type):
    response = make_response("PDF report would be generated here")
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={report_type}_report.pdf'
    return response

def generate_csv_report(data, report_type):
    si = StringIO()
    cw = csv.writer(si)

    cw.writerow([data['title']])
    period_info = f"Period: {data['period'].capitalize()}"
    if data['period'] == 'monthly':
        period_info += f", Year: {data['year']}, Month: {calendar.month_name[int(data['month'])]}"
    else:
        period_info += f", Year: {data['year']}" if data['year'] != 'all' else ", All Years"
    cw.writerow([period_info])
    cw.writerow([])

    if report_type == 'financial_summary':
        cw.writerow(['Period', 'Sales', 'Expenses', 'Salaries', 'Net Balance'])
        for row in data['data']:
            period_key, sales, expenses, salaries = row
            net = sales - (expenses + salaries)
            cw.writerow([period_key, f"{sales:.2f}", f"{expenses:.2f}", f"{salaries:.2f}", f"{net:.2f}"])

    elif report_type == 'category_breakdown':
        cw.writerow(['Sales by Category'])
        cw.writerow(['Category', 'Amount'])
        # Use sales_table_data for CSV output
        for row in data['sales_table_data']: 
            cw.writerow([row[0], f"{row[1]:.2f}"])

    elif report_type == 'staff_salaries':
        if data['period'] == 'monthly':
            cw.writerow(['Name', 'Role', 'Amount', 'Status'])
            for row in data['data']:
                cw.writerow([row[0], row[1], f"{row[2]:.2f}", row[3]])
        else:
            cw.writerow(['Name', 'Role', 'Annual Total Amount', 'Paid Months', 'Pending Months'])
            for row in data['data']:
                cw.writerow([row[0], row[1], f"{row[2]:.2f}", row[3], row[4]])

    output = make_response(si.getvalue())
    output.headers['Content-Type'] = 'text/csv'
    output.headers['Content-Disposition'] = f'attachment; filename={report_type}_report.csv'
    return output


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

# NEW: Edit Sale Route
@app.route('/edit_sale/<int:sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
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
                c.execute("UPDATE sales SET date = ?, item = ?, category = ?, quantity = ?, price = ?, total = ? WHERE id = ?",
                         (date, item, category, quantity, price, total, sale_id))
                conn.commit()
                flash('Sale updated successfully!', 'success')
                conn.close()
                return redirect(url_for('sales'))
        except ValueError:
            flash('Invalid input for quantity or price. Please enter numbers.', 'danger')
        except Exception as e:
            flash(f'Error updating sale: {e}', 'danger')
        finally:
            conn.close()
            # If there was an error, re-render the edit page with the current data and error message
            # This is important to not lose user input if they made a mistake
            return redirect(url_for('edit_sale', sale_id=sale_id))
    else: # GET request
        c.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
        sale = c.fetchone()
        conn.close()
        if sale:
            return render_template('edit_sale.html', sale=sale)
        else:
            flash('Sale not found.', 'danger')
            return redirect(url_for('sales'))

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
            salary_month = request.form['month']
            salary_year = request.form['year']
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
    month_filter = request.args.get('month', 'all')
    status_filter = request.args.get('status', 'all')

    salaries_query = "SELECT * FROM salaries"
    params = []
    conditions = []

    if month_filter != 'all':
        conditions.append("month = ?")
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
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
