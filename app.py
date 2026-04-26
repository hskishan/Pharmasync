from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'super_secret_key_pharmasync'

# --- NEW SECURITY SETTINGS ---
# 1. Force the session to strictly expire after 30 minutes of inactivity
app.permanent_session_lifetime = timedelta(minutes=30)

# 2. Force the browser NOT to save history/cache (Fixes the ghost page issue)
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

def get_db_connection():
    return mysql.connector.connect(host='localhost', user='root', password='1234', database='pharmasync')
def get_db_connection():
    return mysql.connector.connect(host='localhost', user='root', password='1234', database='pharmasync')

# --- AUTHENTICATION ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        password = generate_password_hash(request.form['password'])
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''INSERT INTO users (role, name, email, phone, gender, age, pincode, password, address)
                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                           (request.form['role'], request.form['name'], request.form['email'], request.form['phone'], 
                            request.form['gender'], request.form['age'], request.form['pincode'], password, request.form['address']))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Email already exists.', 'error')
        finally:
            cursor.close()
            conn.close()
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role'] # Added role check for login
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE email = %s AND role = %s', (email, role))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session.clear() # Clear any old data
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['cart'] = {} # Initialize empty shopping cart
            
            if user['role'] == 'admin': return redirect(url_for('dashboard'))
            else: return redirect(url_for('shop'))
        else:
            flash('Invalid email, password, or role mismatch.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html')

# --- ADMIN ROUTES ---
@app.route('/add_category', methods=['GET', 'POST'])
def add_category():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO categories (name, description) VALUES (%s, %s)', (request.form['name'], request.form['description']))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Category added!', 'success')
        return redirect(url_for('view_category'))
    return render_template('add_category.html')

@app.route('/view_category')
def view_category():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT c.id, c.name, c.description, COALESCE(SUM(d.stock), 0) as total_stock
                      FROM categories c LEFT JOIN drugs d ON c.id = d.category_id GROUP BY c.id''')
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('view_category.html', categories=categories)

@app.route('/delete_category/<int:id>')
def delete_category(id):
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM categories WHERE id = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('view_category'))

@app.route('/add_drug', methods=['GET', 'POST'])
def add_drug():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        cursor.execute('''INSERT INTO drugs (name, category_id, price, discount, final_price, stock)
                          VALUES (%s, %s, %s, %s, %s, %s)''', 
                       (request.form['name'], request.form['category_id'], request.form['price'], 
                        request.form['discount'], request.form['final_price'], request.form['stock']))
        conn.commit()
        flash('Drug added!', 'success')
        return redirect(url_for('view_drugs'))
    cursor.execute('SELECT * FROM categories')
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('add_drug.html', categories=categories)

@app.route('/view_drugs', methods=['GET'])
def view_drugs():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Filter logic
    category_filter = request.args.get('category_filter', '')
    query = 'SELECT d.*, c.name as category_name FROM drugs d JOIN categories c ON d.category_id = c.id'
    params = []
    if category_filter:
        query += ' WHERE d.category_id = %s'
        params.append(category_filter)
    query += ' ORDER BY d.id DESC'
    
    cursor.execute(query, tuple(params))
    drugs = cursor.fetchall()
    cursor.execute('SELECT * FROM categories')
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('view_drugs.html', drugs=drugs, categories=categories, selected_category=category_filter)

@app.route('/update_stock', methods=['POST'])
def update_stock():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    drug_id = request.form['drug_id']
    new_stock = request.form['stock']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE drugs SET stock = %s WHERE id = %s', (new_stock, drug_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Stock updated successfully!', 'success')
    return redirect(url_for('view_drugs'))

# --- CUSTOMER SHOPPING & CART ---
@app.route('/shop')
def shop():
    if session.get('role') != 'customer': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT d.*, c.name as category_name FROM drugs d JOIN categories c ON d.category_id = c.id WHERE d.stock > 0')
    drugs = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('shop.html', drugs=drugs)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if session.get('role') != 'customer': return redirect(url_for('login'))
    drug_id = request.form['drug_id']
    name = request.form['name']
    price = float(request.form['price'])
    qty = int(request.form['quantity'])
    stock = int(request.form['stock'])
    
    if 'cart' not in session: session['cart'] = {}
    
    # Check if adding exceeds stock
    current_qty = session['cart'].get(drug_id, {}).get('qty', 0)
    if current_qty + qty > stock:
        flash(f'Cannot add more. Only {stock} left in stock.', 'error')
    else:
        if drug_id in session['cart']:
            session['cart'][drug_id]['qty'] += qty
        else:
            session['cart'][drug_id] = {'name': name, 'price': price, 'qty': qty}
        session.modified = True
        flash(f'{qty}x {name} added to cart.', 'success')
        
    return redirect(url_for('shop'))

@app.route('/view_cart')
def view_cart():
    if session.get('role') != 'customer': return redirect(url_for('dashboard'))
    total = sum(item['price'] * item['qty'] for item in session.get('cart', {}).values())
    return render_template('cart.html', total=total)

@app.route('/clear_cart')
def clear_cart():
    session['cart'] = {}
    session.modified = True
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['POST'])
def checkout():
    if session.get('role') != 'customer': return redirect(url_for('login'))
    cart = session.get('cart', {})
    if not cart:
        flash('Cart is empty!', 'error')
        return redirect(url_for('shop'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        for drug_id, item in cart.items():
            # Verify stock again before checkout
            cursor.execute('SELECT stock FROM drugs WHERE id = %s', (drug_id,))
            drug = cursor.fetchone()
            if drug['stock'] < item['qty']:
                flash(f"Sorry, {item['name']} is out of stock.", 'error')
                return redirect(url_for('view_cart'))
            
            # Deduct stock and Create Order
            new_stock = drug['stock'] - item['qty']
            total_price = item['price'] * item['qty']
            cursor.execute('UPDATE drugs SET stock = %s WHERE id = %s', (new_stock, drug_id))
            cursor.execute('''INSERT INTO orders (user_id, drug_id, quantity, total_price, status)
                              VALUES (%s, %s, %s, %s, 'Pending')''', 
                           (session['user_id'], drug_id, item['qty'], total_price))
        
        conn.commit()
        session['cart'] = {} # Empty the cart
        session.modified = True
        flash('Order placed successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash('An error occurred. Try again.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('my_orders'))

@app.route('/my_orders')
def my_orders():
    if session.get('role') != 'customer': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT o.id, d.name as drug_name, o.quantity, o.total_price, o.status, o.order_date 
                      FROM orders o JOIN drugs d ON o.drug_id = d.id 
                      WHERE o.user_id = %s ORDER BY o.order_date DESC''', (session['user_id'],))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_orders.html', orders=orders)

@app.route('/manage_orders')
def manage_orders():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT o.id, u.name as customer_name, d.name as drug_name, o.quantity, o.total_price, o.status, o.order_date 
                      FROM orders o JOIN users u ON o.user_id = u.id JOIN drugs d ON o.drug_id = d.id 
                      ORDER BY o.order_date DESC''')
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('manage_orders.html', orders=orders)

@app.route('/update_order_status', methods=['POST'])
def update_order_status():
    if session.get('role') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE orders SET status = %s WHERE id = %s', (request.form['status'], request.form['order_id']))
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Order #{request.form['order_id']} updated to {request.form['status']}.", 'success')
    return redirect(url_for('manage_orders'))

# Custom Jinja Filter for length
@app.template_filter('length')
def length_filter(d):
    return len(d)

if __name__ == '__main__':
    app.run(debug=True)