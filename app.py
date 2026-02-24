from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# simple session secret for demo purposes
app.secret_key = 'change-this-secret'

# Upload folder configuration
UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


class Product(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(120), nullable=False)
	price = db.Column(db.Float, nullable=False)
	image_url = db.Column(db.String(255))


class Order(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
	customer_name = db.Column(db.String(120), nullable=False)
	phone = db.Column(db.String(20), nullable=False)
	address = db.Column(db.Text, nullable=False)
	payment_method = db.Column(db.String(50), nullable=False)  # 'cod' or 'bank'
	created_at = db.Column(db.DateTime, default=lambda: __import__('datetime').datetime.now())
	
	product = db.relationship('Product', backref='orders')
	
	def __repr__(self):
		return f'<Order {self.id}: {self.customer_name}>'


def seed_data():
	"""Insert sample products if none exist."""
	if Product.query.first():
		return
	samples = [
		Product(name='Coffee Mug', price=9.99, image_url='https://source.unsplash.com/600x400/?mug,coffee'),
		Product(name='T-Shirt', price=14.99, image_url='https://source.unsplash.com/600x400/?tshirt,clothing'),
		Product(name='Notebook', price=4.50, image_url='https://source.unsplash.com/600x400/?notebook,office'),
		Product(name='Sticker Pack', price=2.99, image_url='https://source.unsplash.com/600x400/?sticker,design'),
	]
	db.session.add_all(samples)
	db.session.commit()
	print('Seeded sample products.')


@app.route('/')
def index():
	products = Product.query.all()
	return render_template('index.html', products=products)


@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
	try:
		product_id = request.form.get('product_id')
		customer_name = request.form.get('customer_name')
		phone = request.form.get('phone')
		address = request.form.get('address')
		payment_method = request.form.get('payment_method')
		
		print(f"[DEBUG] Adding to cart: product_id={product_id}, customer={customer_name}, phone={phone}, method={payment_method}")
		
		if not all([product_id, customer_name, phone, address, payment_method]):
			return {'success': False, 'message': 'All fields are required'}, 400
		
		# Verify product exists
		product = Product.query.get(product_id)
		if not product:
			return {'success': False, 'message': 'Product not found'}, 404
		
		# Create order
		order = Order(
			product_id=product_id,
			customer_name=customer_name,
			phone=phone,
			address=address,
			payment_method=payment_method
		)
		db.session.add(order)
		db.session.commit()
		print(f"[DEBUG] Order created: {order.id}")
		
		return {'success': True, 'message': 'Added to cart successfully', 'order_id': order.id}
	except Exception as e:
		print(f"[ERROR] Error in add_to_cart: {str(e)}")
		import traceback
		traceback.print_exc()
		return {'success': False, 'message': f'Error: {str(e)}'}, 500


@app.route('/cart')
def cart():
	orders = Order.query.order_by(Order.created_at.desc()).all()
	return render_template('cart.html', orders=orders)


@app.route('/order/<int:order_id>/delete', methods=['POST'])
def delete_order(order_id):
	order = Order.query.get_or_404(order_id)
	db.session.delete(order)
	db.session.commit()
	return redirect(url_for('cart'))


@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		username = request.form.get('username')
		password = request.form.get('password')
		if username == 'admin' and password == '1234':
			session['admin'] = True
			return redirect(url_for('admin_dashboard'))
		flash('Invalid credentials', 'error')
		return redirect(url_for('login'))
	return render_template('login.html')


@app.route('/logout')
def logout():
	session.pop('admin', None)
	return redirect(url_for('login'))


def admin_required(func):
	from functools import wraps

	@wraps(func)
	def wrapper(*args, **kwargs):
		if not session.get('admin'):
			return redirect(url_for('login'))
		return func(*args, **kwargs)

	return wrapper


def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/admin')
@admin_required
def admin_dashboard():
	products = Product.query.all()
	return render_template('admin.html', products=products)


@app.route('/admin/add', methods=['POST'])
@admin_required
def add_product():
	try:
		name = request.form.get('name')
		price = request.form.get('price')
		image_file = request.files.get('image')
		
		print(f"[DEBUG] Adding product: name={name}, price={price}, image={image_file.filename if image_file else 'None'}")
		
		if not name or not price:
			flash('Name and price are required', 'error')
			return redirect(url_for('admin_dashboard'))
		
		if not image_file or image_file.filename == '':
			flash('Image file is required', 'error')
			return redirect(url_for('admin_dashboard'))
		
		if not allowed_file(image_file.filename):
			flash('Invalid image format. Allowed: png, jpg, jpeg, gif, webp', 'error')
			return redirect(url_for('admin_dashboard'))
		
		try:
			price_val = float(price)
		except ValueError:
			flash('Invalid price value', 'error')
			return redirect(url_for('admin_dashboard'))
		
		# Save file
		filename = secure_filename(image_file.filename)
		# Add timestamp to filename to avoid conflicts
		import time
		filename = f"{int(time.time())}_{filename}"
		image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
		print(f"[DEBUG] Saving image to: {image_path}")
		image_file.save(image_path)
		print(f"[DEBUG] Image saved successfully")
		
		# Create product with image URL
		image_url = f'/static/uploads/{filename}'
		p = Product(name=name, price=price_val, image_url=image_url)
		db.session.add(p)
		db.session.commit()
		print(f"[DEBUG] Product added to DB: {name} - {price_val}")
		flash('Product added successfully', 'success')
		return redirect(url_for('admin_dashboard'))
	except Exception as e:
		print(f"[ERROR] Exception in add_product: {str(e)}")
		import traceback
		traceback.print_exc()
		flash(f'Error adding product: {str(e)}', 'error')
		return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
	p = Product.query.get_or_404(product_id)
	db.session.delete(p)
	db.session.commit()
	flash('Product deleted', 'success')
	return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    with app.app_context():
        # Create database file and tables if they don't exist
        db.create_all()
        # Seed sample data when DB is empty
        seed_data()
    db_path = os.path.join(basedir, 'shop.db')
    print(f"Database file created (or already exists): {db_path}")
    # Start Flask development server
    app.run(debug=True)

