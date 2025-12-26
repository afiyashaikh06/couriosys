from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import bcrypt
import os
from dotenv import load_dotenv
import re

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

mongo = PyMongo(app)
# ========== HELPER FUNCTIONS ==========

def init_db():
    """Initialize database with default admin"""
    if not mongo.db.users.find_one({"email": "admin_09@gmail.com"}):
        hashed_password = bcrypt.hashpw("Admin_123".encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.insert_one({
            "name": "Admin",
            "email": "admin_09@gmail.com",
            "password": hashed_password,
            "phone": "0000000000",
            "role": "admin",
            "created_at": datetime.now(),
            "status": "active"
        })
        print("Default admin created: admin_09@gmail.com / Admin_123")
    
    # Create indexes
    mongo.db.parcels.create_index([("tracking_id", 1)], unique=True)
    mongo.db.users.create_index([("email", 1)], unique=True)
    mongo.db.users.create_index([("role", 1)])
    mongo.db.parcels.create_index([("status", 1)])
    mongo.db.parcels.create_index([("customer_id", 1)])
    mongo.db.parcels.create_index([("staff_id", 1)])
    mongo.db.notifications.create_index([("user_id", 1), ("read", 1)])

# Generate tracking ID
def generate_tracking_id():
    import random
    import string
    return 'TRK' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

# Calculate delivery cost
def calculate_cost(weight, parcel_type, delivery_type):
    base_cost = 50
    weight_cost = float(weight) * 10
    
    type_multiplier = {
        'document': 1.0,
        'box': 1.2,
        'fragile': 1.5,
        'electronics': 1.3
    }
    
    delivery_multiplier = {
        'standard': 1.0,
        'express': 1.5
    }
    
    cost = base_cost + weight_cost
    cost *= type_multiplier.get(parcel_type.lower(), 1.0)
    cost *= delivery_multiplier.get(delivery_type.lower(), 1.0)
    
    return round(cost, 2)

# Helper function to create notifications
def create_notification(user_id, title, message, notification_type):
    """
    Create a notification for a user
    """
    try:
        # Ensure user_id is string
        if isinstance(user_id, ObjectId):
            user_id = str(user_id)
        
        notification_data = {
            "user_id": ObjectId(user_id),
            "title": title,
            "message": message,
            "type": notification_type,
            "read": False,
            "created_at": datetime.now()
        }
        return mongo.db.notifications.insert_one(notification_data)
    except Exception as e:
        print(f"Error creating notification: {e}")
        return None

# ========== AUTH DECORATORS ==========

def login_required(f):
    """Simple login required decorator"""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    """Admin login required decorator"""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def staff_required(f):
    """Staff login required decorator"""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        if session.get('role') not in ['admin', 'staff']:
            flash('Staff access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ========== PUBLIC ROUTES ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/track', methods=['GET', 'POST'])
def track():
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id')
        parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
        if parcel:
            return render_template('track.html', parcel=parcel, found=True)
        else:
            flash('Tracking ID not found', 'danger')
    return render_template('track.html', found=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif role == 'staff':
            return redirect(url_for('staff_dashboard'))
        elif role == 'customer':
            return redirect(url_for('customer_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember')
        
        user = mongo.db.users.find_one({"email": email})
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            session['user_id'] = str(user['_id'])
            session['email'] = user['email']
            session['name'] = user['name']
            session['role'] = user['role']
            
            if remember:
                session.permanent = True
            
            # Redirect based on role
            if user['role'] == 'admin':
                flash('Welcome Admin!', 'success')
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'staff':
                flash('Welcome Staff!', 'success')
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Welcome back!', 'success')
                return redirect(url_for('customer_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        # Check if user exists
        if mongo.db.users.find_one({"email": email}):
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))
        
        # Validate password
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect(url_for('signup'))
        
        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create user
        user_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed_password,
            "role": "customer",
            "created_at": datetime.now(),
            "status": "active",
            "address": ""
        }
        
        mongo.db.users.insert_one(user_data)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

# ========== CUSTOMER ROUTES ==========

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    customer_id = session['user_id']
    parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)}).sort("created_at", -1))
    
    # Count notifications
    notification_count = mongo.db.notifications.count_documents({
        "user_id": ObjectId(customer_id),
        "read": False
    })
    
    return render_template('customer/dashboard.html', 
                         parcels=parcels[:5], 
                         notification_count=notification_count)

@app.route('/customer/book', methods=['GET', 'POST'])
@login_required
def book_parcel():
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    customer_id = session['user_id']
    customer = mongo.db.users.find_one({"_id": ObjectId(customer_id)})
    
    if request.method == 'POST':
        # Get form data
        sender_name = request.form.get('sender_name')
        sender_phone = request.form.get('sender_phone')
        sender_address = request.form.get('sender_address')
        sender_pincode = request.form.get('sender_pincode')
        
        receiver_name = request.form.get('receiver_name')
        receiver_phone = request.form.get('receiver_phone')
        receiver_address = request.form.get('receiver_address')
        receiver_pincode = request.form.get('receiver_pincode')
        
        weight = request.form.get('weight')
        parcel_type = request.form.get('parcel_type')
        description = request.form.get('description')
        delivery_type = request.form.get('delivery_type')
        pickup_date = request.form.get('pickup_date')
        
        # Calculate cost
        cost = calculate_cost(weight, parcel_type, delivery_type)
        
        # Create parcel
        parcel_data = {
            "tracking_id": generate_tracking_id(),
            "customer_id": ObjectId(customer_id),
            "customer_name": customer['name'],
            "customer_email": customer['email'],
            "customer_phone": sender_phone,
            "pickup_address": sender_address,
            "pickup_pincode": sender_pincode,
            "sender_name": sender_name,
            "sender_phone": sender_phone,
            "sender_address": sender_address,
            "sender_pincode": sender_pincode,
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
            "receiver_address": receiver_address,
            "receiver_pincode": receiver_pincode,
            "weight": float(weight),
            "parcel_type": parcel_type,
            "description": description,
            "delivery_type": delivery_type,
            "pickup_date": datetime.strptime(pickup_date, '%Y-%m-%d'),
            "cost": cost,
            "payment_mode": "cod",
            "payment_status": "pending",
            "status": "booked",
            "status_history": [{
                "status": "booked",
                "timestamp": datetime.now(),
                "note": "Parcel booked successfully"
            }],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "staff_id": None,
            "staff_name": None,
            "delivered_at": None
        }
        
        mongo.db.parcels.insert_one(parcel_data)
        
        # Create notification
        create_notification(
            customer_id,
            "Parcel Booked Successfully",
            f"Your parcel has been booked. Tracking ID: {parcel_data['tracking_id']}. Cost: ₹{cost}",
            "booking"
        )
        
        flash('Parcel booked successfully!', 'success')
        return redirect(url_for('customer_parcels'))
    
    return render_template('customer/book_parcel.html', customer=customer)

@app.route('/customer/parcels')
@login_required
def customer_parcels():
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    customer_id = session['user_id']
    parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)}).sort("created_at", -1))
    
    return render_template('customer/my_parcels.html', parcels=parcels)

@app.route('/customer/track')
@login_required
def customer_track():
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    customer_id = session['user_id']
    parcels = list(mongo.db.parcels.find(
        {"customer_id": ObjectId(customer_id)},
        {
            "tracking_id": 1,
            "status": 1,
            "created_at": 1,
            "updated_at": 1,
            "receiver_name": 1,
            "receiver_address": 1
        }
    ).sort("created_at", -1))
    
    return render_template('customer/track.html', parcels=parcels)

@app.route('/customer/notifications')
@login_required
def customer_notifications():
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    customer_id = session['user_id']
    notifications = list(mongo.db.notifications.find({"user_id": ObjectId(customer_id)})
                        .sort("created_at", -1))
    
    # Mark as read
    mongo.db.notifications.update_many(
        {"user_id": ObjectId(customer_id), "read": False},
        {"$set": {"read": True}}
    )
    
    return render_template('customer/notifications.html', notifications=notifications)

@app.route('/customer/profile', methods=['GET', 'POST'])
@login_required
def customer_profile():
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    customer_id = session['user_id']
    customer = mongo.db.users.find_one({"_id": ObjectId(customer_id)})
    
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        mongo.db.users.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {
                "name": name,
                "phone": phone,
                "address": address,
                "updated_at": datetime.now()
            }}
        )
        
        session['name'] = name
        flash('Profile updated successfully', 'success')
        return redirect(url_for('customer_profile'))
    
    return render_template('customer/profile.html', customer=customer)

@app.route('/cancel_parcel/<tracking_id>')
@login_required
def cancel_parcel(tracking_id):
    if session.get('role') != 'customer':
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
    
    if not parcel:
        flash('Parcel not found', 'danger')
        return redirect(url_for('customer_parcels'))
    
    # Check if parcel is still in booked status
    if parcel['status'] != 'booked':
        flash('Cannot cancel parcel after it has been picked up', 'danger')
        return redirect(url_for('customer_parcels'))
    
    # Update status
    mongo.db.parcels.update_one(
        {"tracking_id": tracking_id},
        {"$set": {
            "status": "cancelled",
            "updated_at": datetime.now()
        }}
    )
    
    flash('Parcel cancelled successfully', 'success')
    return redirect(url_for('customer_parcels'))

# ========== ADMIN ROUTES ==========

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin Dashboard"""
    # Get counts
    total_customers = mongo.db.users.count_documents({"role": "customer", "status": "active"})
    total_staff = mongo.db.users.count_documents({"role": "staff", "status": "active"})
    total_parcels = mongo.db.parcels.count_documents({})
    
    # Status counts
    status_counts = {
        'booked': mongo.db.parcels.count_documents({"status": "booked"}),
        'picked': mongo.db.parcels.count_documents({"status": "picked"}),
        'in_transit': mongo.db.parcels.count_documents({"status": "in_transit"}),
        'out_for_delivery': mongo.db.parcels.count_documents({"status": "out_for_delivery"}),
        'delivered': mongo.db.parcels.count_documents({"status": "delivered"}),
        'cancelled': mongo.db.parcels.count_documents({"status": "cancelled"})
    }
    
    # Monthly revenue
    today = datetime.now()
    first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    delivered_parcels = mongo.db.parcels.find({
        "status": "delivered",
        "delivered_at": {"$gte": first_day_of_month}
    })
    monthly_revenue = sum([p.get('cost', 0) for p in delivered_parcels])
    
    # Recent parcels
    recent_parcels = list(mongo.db.parcels.find().sort("created_at", -1).limit(5))
    
    return render_template('Admin/Dashboard.html',
                         total_customers=total_customers,
                         total_staff=total_staff,
                         total_parcels=total_parcels,
                         status_counts=status_counts,
                         monthly_revenue=monthly_revenue,
                         recent_parcels=recent_parcels)

# @app.route('/admin/staff')
# @admin_required
# def admin_staff():
#     """Staff Management"""
#     staff_list = list(mongo.db.users.find({"role": "staff"}).sort("created_at", -1))
#     return render_template('Admin/Staff.html', staff_list=staff_list)

# @app.route('/admin/staff/add', methods=['GET', 'POST'])
# @admin_required
# def add_staff():
#     """Add new staff"""
#     if request.method == 'POST':
#         name = request.form.get('name')
#         email = request.form.get('email')
#         phone = request.form.get('phone')
#         password = request.form.get('password')
        
#         # Check if exists
#         if mongo.db.users.find_one({"email": email}):
#             flash('Email already registered', 'danger')
#             return redirect(url_for('add_staff'))
        
#         # Create staff
#         hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
#         staff_data = {
#             "name": name,
#             "email": email,
#             "phone": phone,
#             "password": hashed_password,
#             "role": "staff",
#             "status": "active",
#             "created_at": datetime.now(),
#             "assigned_parcels": [],
#             "total_deliveries": 0,
#             "last_login": None
#         }
        
#         mongo.db.users.insert_one(staff_data)
#         flash('Staff added successfully!', 'success')
#         return redirect(url_for('admin_staff'))
    
#     return render_template('Admin/add_staff.html')
# ========== STAFF MANAGEMENT ==========

# ========== STAFF MANAGEMENT ==========

@app.route('/admin/staff')
@admin_required
def admin_staff():
    """Simple staff list"""
    staff_list = list(mongo.db.users.find({"role": "staff"}).sort("created_at", -1))
    
    # Get unassigned parcels for quick assign
    unassigned_parcels = list(mongo.db.parcels.find({
        "assigned_staff_id": {"$exists": False},
        "status": {"$in": ["booked", "picked"]}
    }).limit(10))
    
    return render_template('Admin/Staff.html',
                         staff_list=staff_list,
                         unassigned_parcels=unassigned_parcels)

@app.route('/admin/add-staff', methods=['GET', 'POST'])
@admin_required
def add_staff():
    """Add new staff (simple form)"""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        
        if mongo.db.users.find_one({"email": email}):
            flash('Email already exists', 'danger')
            return redirect(url_for('add_staff'))
        
        hashed = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "role": "staff",
            "status": "active",
            "current_assignment_count": 0,
            "assigned_parcels": [],
            "created_at": datetime.now()
        })
        
        flash('Staff added successfully', 'success')
        return redirect(url_for('admin_staff'))
    
    return render_template('Admin/add_staff.html')

@app.route('/admin/quick-assign-parcel', methods=['POST'])
@admin_required
def quick_assign_parcel():
    """Quick assign - minimal"""
    staff_id = request.form.get('staff_id')
    parcel_id = request.form.get('parcel_id')
    
    if not staff_id or not parcel_id:
        flash('Select staff and parcel', 'danger')
        return redirect(url_for('admin_staff'))
    
    try:
        # Update parcel
        mongo.db.parcels.update_one(
            {"_id": ObjectId(parcel_id)},
            {"$set": {
                "assigned_staff_id": ObjectId(staff_id),
                "status": "picked",
                "updated_at": datetime.now()
            }}
        )
        
        # Update staff count
        mongo.db.users.update_one(
            {"_id": ObjectId(staff_id)},
            {"$inc": {"current_assignment_count": 1}}
        )
        
        flash('Parcel assigned successfully', 'success')
        
    except Exception as e:
        flash('Assignment failed', 'danger')
    
    return redirect(url_for('admin_staff'))

@app.route('/admin/toggle-staff-status/<staff_id>', methods=['POST'])
@admin_required
def toggle_staff_status(staff_id):
    """Toggle status only"""
    try:
        data = request.get_json()
        new_status = data.get('status', 'inactive')
        
        mongo.db.users.update_one(
            {"_id": ObjectId(staff_id)},
            {"$set": {"status": new_status}}
        )
        
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})
@app.route('/admin/edit-staff/<staff_id>')
@admin_required
def edit_staff(staff_id):
    """Edit staff member details"""
    staff = mongo.db.users.find_one({"_id": ObjectId(staff_id)})
    if not staff:
        flash('Staff member not found', 'danger')
        return redirect(url_for('admin_staff'))
    
    return render_template('Admin/edit_staff.html', staff=staff)

@app.route('/admin/update-staff/<staff_id>', methods=['POST'])
@admin_required
def update_staff(staff_id):
    """Update staff info"""
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    status = request.form.get('status')
    
    mongo.db.users.update_one(
        {"_id": ObjectId(staff_id)},
        {"$set": {
            "name": name,
            "email": email,
            "phone": phone,
            "status": status,
            "updated_at": datetime.now()
        }}
    )
    
    flash('Staff updated successfully', 'success')
    return redirect(url_for('admin_staff'))

@app.route('/admin/customers')
@admin_required
def admin_customers():
    """View all customers"""
    customers = list(mongo.db.users.find({"role": "customer"}).sort("created_at", -1))
    return render_template('Admin/Customer.html', customers=customers)

@app.route('/admin/parcels')
@admin_required
def admin_parcels():
    """View all parcels"""
    parcels = list(mongo.db.parcels.find().sort("created_at", -1))
    
    # Get staff names for display
    for parcel in parcels:
        if parcel.get('staff_id'):
            staff = mongo.db.users.find_one({"_id": parcel['staff_id']})
            parcel['staff_name_display'] = staff['name'] if staff else 'Unknown'
        else:
            parcel['staff_name_display'] = 'Not Assigned'
    
    return render_template('Admin/Parcel.html', parcels=parcels)

@app.route('/admin/track', methods=['GET', 'POST'])
@admin_required
def admin_track():
    """Admin tracking"""
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id')
        parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
        if parcel:
            return render_template('Admin/Track_parcel.html', parcel=parcel, found=True)
        else:
            flash('Tracking ID not found', 'danger')
    return render_template('Admin/Track_parcel.html', found=False)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    """Admin reports"""
    # Monthly stats
    today = datetime.now()
    first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    monthly_parcels = mongo.db.parcels.count_documents({
        "created_at": {"$gte": first_day_of_month}
    })
    
    monthly_delivered = mongo.db.parcels.count_documents({
        "status": "delivered",
        "delivered_at": {"$gte": first_day_of_month}
    })
    
    monthly_pending = mongo.db.parcels.count_documents({
        "status": {"$in": ["booked", "picked", "in_transit", "out_for_delivery"]}
    })
    
    # Top staff
    top_staff = list(mongo.db.users.find(
        {"role": "staff", "status": "active"}
    ).sort("total_deliveries", -1).limit(5))
    
    return render_template('Admin/Reports.html',
                         monthly_parcels=monthly_parcels,
                         monthly_delivered=monthly_delivered,
                         monthly_pending=monthly_pending,
                         top_staff=top_staff)

# ========== STAFF ROUTES ==========

@app.route('/staff/dashboard')
@staff_required
def staff_dashboard():
    """Staff Dashboard"""
    staff_id = session['user_id']
    
    # Get assigned parcels
    assigned_parcels = list(mongo.db.parcels.find({
        "staff_id": ObjectId(staff_id),
        "status": {"$in": ["booked", "picked", "in_transit", "out_for_delivery"]}
    }).sort("created_at", -1).limit(5))
    
    # Get stats
    total_assigned = mongo.db.parcels.count_documents({"staff_id": ObjectId(staff_id)})
    total_delivered = mongo.db.parcels.count_documents({
        "staff_id": ObjectId(staff_id),
        "status": "delivered"
    })
    
    return render_template('Staff/dashboard.html',
                         assigned_parcels=assigned_parcels,
                         total_assigned=total_assigned,
                         total_delivered=total_delivered)

# ========== API ENDPOINTS ==========

@app.route('/api/notifications/mark-read', methods=['POST'])
def mark_all_read():
    """Mark all notifications as read"""
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    customer_id = session['user_id']
    
    # Mark all notifications as read
    mongo.db.notifications.update_many(
        {"user_id": ObjectId(customer_id), "read": False},
        {"$set": {"read": True}}
    )
    
    return jsonify({"success": True})

@app.route('/api/track/<tracking_id>')
def api_track(tracking_id):
    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
    if parcel:
        # Convert ObjectId to string for JSON serialization
        parcel['_id'] = str(parcel['_id'])
        if 'customer_id' in parcel:
            parcel['customer_id'] = str(parcel['customer_id'])
        if 'staff_id' in parcel and parcel['staff_id']:
            parcel['staff_id'] = str(parcel['staff_id'])
        return jsonify(parcel)
    else:
        return jsonify({"error": "Tracking ID not found"}), 404

# ========== CONTEXT PROCESSORS & ERROR HANDLERS ==========

@app.context_processor
def utility_processor():
    def format_date(date_obj):
        if date_obj:
            return date_obj.strftime('%Y-%m-%d %H:%M')
        return ''
    return dict(format_date=format_date, now=datetime.now)

# Simple error handlers that redirect to home
@app.errorhandler(404)
def not_found_error(error):
    flash('Page not found', 'warning')
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    flash('Server error occurred', 'danger')
    return redirect(url_for('index'))

# ========== MAIN EXECUTION ==========

if __name__ == '__main__':
    with app.app_context():
        init_db()
        print("🚀 Courier Management System Ready!")
        print("🔐 Admin: admin@parcel.com / admin123")
        print("👥 Role-based access: Admin, Staff, Customer")
    
    app.run(debug=True, port=5001, host='0.0.0.0')