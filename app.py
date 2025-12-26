# prooer customer 
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
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)  # Remember me functionality

mongo = PyMongo(app)

# ========== HELPER FUNCTIONS ==========

# Initialize database with default admin
def init_db():
    if not mongo.db.users.find_one({"email": "couriosysadmin@gmail.com"}):
        hashed_password = bcrypt.hashpw("Admin_123".encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.insert_one({
            "name": "Admin",
            "email": "couriosysadmin@gmail.com",
            "password": hashed_password,
            "phone": "0000000000",
            "role": "admin",
            "created_at": datetime.now(),
            "status": "active"
        })
        print("Default admin created: couriosysadmin@gmail.com / Admin_123")

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
def login_required():
    """Simple login required decorator"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login first', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
# Add after your existing decorator functions
def admin_required(f):
    """Admin login required decorator"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('customer_dashboard'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

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
        if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
        elif user['role'] == 'staff':
                return redirect(url_for('staff_dashboard'))
        elif user['role'] == 'customer':
                return redirect(url_for('customer_dashboard'))
            
            # Redirect based on role
        if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
        elif user['role'] == 'staff':
                return redirect(url_for('staff_dashboard'))
        elif user['role'] == 'customer':
                return redirect(url_for('customer_dashboard'))
        else:
                flash('Admin/Staff panel not available in this version', 'info')
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
def customer_dashboard():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))
    
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
def book_parcel():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))
    
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
            "customer_phone": sender_phone,  # Use form phone
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

# @app.route('/customer/parcels')
# def customer_parcels():
#     if 'user_id' not in session or session.get('role') != 'customer':
#         return redirect(url_for('login'))
    
#     customer_id = session['user_id']
#     parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)}).sort("created_at", -1))
    
#     return render_template('customer/my_parcels.html', parcels=parcels)
# new
@app.route('/customer/parcels')
def customer_parcels():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))

    customer_id = session['user_id']
    parcels = list(mongo.db.parcels.find({
        "customer_id": ObjectId(customer_id),
        "status": {"$ne": "cancelled"}      # hide cancelled parcels
    }).sort("created_at", -1))

    return render_template('customer/my_parcels.html', parcels=parcels)

@app.route('/customer/parcels/<tracking_id>')
def customer_parcel_detail(tracking_id):
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))

    customer_id = session['user_id']
    parcel = mongo.db.parcels.find_one({
        "tracking_id": tracking_id,
        "customer_id": ObjectId(customer_id)
    })

    if not parcel:
        flash('Parcel not found', 'danger')
        return redirect(url_for('customer_parcels'))

    return render_template('customer/parcel_detail.html', parcel=parcel)
@app.route('/cancel_parcel/<tracking_id>')
def cancel_parcel(tracking_id):
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))

    customer_id = session['user_id']
    parcel = mongo.db.parcels.find_one({
        "tracking_id": tracking_id,
        "customer_id": ObjectId(customer_id)
    })

    if not parcel:
        flash('Parcel not found', 'danger')
        return redirect(url_for('customer_parcels'))

    # Only cancel if still booked
    if parcel['status'] != 'booked':
        flash('Cannot cancel after parcel is picked up', 'danger')
        return redirect(url_for('customer_parcels'))

    # Only within 2 days of booking
    from datetime import datetime, timedelta
    if datetime.now() - parcel['created_at'] > timedelta(days=2):
        flash('Cancellation allowed only within 2 days of booking', 'danger')
        return redirect(url_for('customer_parcels'))

    mongo.db.parcels.update_one(
        {"_id": parcel['_id']},
        {"$set": {
            "status": "cancelled",
            "updated_at": datetime.now()
        }}
    )

    flash('Parcel cancelled successfully', 'success')
    return redirect(url_for('customer_parcels'))
from datetime import datetime, timedelta
from bson import ObjectId

@app.route('/customer/parcels/<tracking_id>/edit', methods=['GET', 'POST'])
def edit_parcel(tracking_id):
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))

    customer_id = session['user_id']
    parcel = mongo.db.parcels.find_one({
        "tracking_id": tracking_id,
        "customer_id": ObjectId(customer_id)
    })

    if not parcel:
        flash('Parcel not found', 'danger')
        return redirect(url_for('customer_parcels'))

    # Only allow edit when booked and within 2 days
    if parcel['status'] != 'booked' or datetime.now() - parcel['created_at'] > timedelta(days=2):
        flash('You can edit only booked parcels within 2 days of booking.', 'danger')
        return redirect(url_for('customer_parcels'))

    if request.method == 'POST':
        # Update only editable fields
        sender_address = request.form.get('sender_address')
        receiver_name = request.form.get('receiver_name')
        receiver_phone = request.form.get('receiver_phone')
        receiver_address = request.form.get('receiver_address')
        weight = request.form.get('weight')

        mongo.db.parcels.update_one(
            {"_id": parcel['_id']},
            {"$set": {
                "sender_address": sender_address,
                "receiver_name": receiver_name,
                "receiver_phone": receiver_phone,
                "receiver_address": receiver_address,
                "weight": float(weight),
                "updated_at": datetime.now()
            }}
        )

        flash('Parcel updated successfully.', 'success')
        return redirect(url_for('customer_parcels'))

    return render_template('customer/edit_parcel.html', parcel=parcel)

@app.route('/customer/track')
def customer_track():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))
    
    customer_id = session['user_id']
    # Fetch all necessary fields including created_at
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
def customer_notifications():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))
    
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
def customer_profile():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))
    
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


# ========== ADMIN ROUTES ==========
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Counts
    total_customers = mongo.db.users.count_documents({"role": "customer"})
    total_staff = mongo.db.users.count_documents({"role": "staff"})
    total_parcels = mongo.db.parcels.count_documents({})

    # Status counts
    status_list = ["booked", "picked", "in transit", "out for delivery", "delivered", "cancelled"]
    status_counts = {}
    for s in status_list:
        status_counts[s] = mongo.db.parcels.count_documents({"status": s})

    # Recent parcels
    recent_parcels = list(
        mongo.db.parcels.find().sort("created_at", -1).limit(5)
    )

    return render_template(
        'admin/dashboard.html',
        total_customers=total_customers,
        total_staff=total_staff,
        total_parcels=total_parcels,
        status_counts=status_counts,
        recent_parcels=recent_parcels
    )
@app.route('/admin/staff', methods=['GET', 'POST'])
@admin_required
def admin_staff():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if mongo.db.users.find_one({"email": email}):
            flash('Email already used', 'danger')
            return redirect(url_for('admin_staff'))

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "role": "staff",
            "status": "active",
            "created_at": datetime.now()
        })
        flash('Staff created successfully', 'success')
        return redirect(url_for('admin_staff'))

    staff_list = list(mongo.db.users.find({"role": "staff"}).sort("created_at", -1))
    return render_template('admin/staff.html', staff_list=staff_list)

@app.route('/admin/staff/<staff_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_staff(staff_id):
    staff = mongo.db.users.find_one({
        "_id": ObjectId(staff_id),
        "role": "staff"
    })
    if not staff:
        flash("Staff member not found", "danger")
        return redirect(url_for('manage_staff'))   # your staff list route

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        status = request.form.get('status')

        # Optional: prevent email duplicates
        existing = mongo.db.users.find_one({
            "email": email,
            "_id": {"$ne": staff["_id"]}
        })
        if existing:
            flash("Email already used by another user", "danger")
            return redirect(url_for('edit_staff', staff_id=staff_id))

        mongo.db.users.update_one(
            {"_id": staff["_id"]},
            {"$set": {
                "name": name,
                "email": email,
                "phone": phone,
                "status": status
            }}
        )

        flash("Staff details updated successfully", "success")
        return redirect(url_for('manage_staff'))

    return render_template('admin/edit_staff.html', staff=staff)

@app.route('/admin/staff/delete/<staff_id>')
@admin_required
def delete_staff(staff_id):
    mongo.db.users.delete_one({"_id": ObjectId(staff_id)})
    flash('Staff deleted', 'success')
    return redirect(url_for('admin_staff'))

@app.route('/admin/staff/assign', methods=['POST'])
@admin_required
def assign_parcel_to_staff():
    tracking_id = request.form.get('tracking_id')
    staff_id = request.form.get('staff_id')

    staff = mongo.db.users.find_one({"_id": ObjectId(staff_id), "role": "staff"})
    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})

    if not staff or not parcel:
        flash('Invalid staff or tracking ID', 'danger')
        return redirect(url_for('admin_staff'))

    mongo.db.parcels.update_one(
        {"_id": parcel['_id']},
        {
            "$set": {
                "staff_id": staff['_id'],
                "staff_name": staff['name'],
                "updated_at": datetime.now()
            },
            "$push": {
                "status_history": {
                    "status": parcel['status'],
                    "timestamp": datetime.now(),
                    "note": f"Assigned to staff {staff['name']}"
                }
            }
        }
    )

    # Optional notification to staff (if later you show staff notifications)
    create_notification(
        staff['_id'],
        "New Parcel Assigned",
        f"You have been assigned parcel {tracking_id}",
        "assignment"
    )

    flash('Parcel assigned to staff', 'success')
    return redirect(url_for('admin_staff'))

from datetime import datetime  # Make sure this is at top

@app.route('/admin/customers')
@admin_required
def admin_customers():
    customers = list(mongo.db.users.find({"role": "customer"}).sort("created_at", -1))
    
    # Fix missing created_at for ALL customers
    for customer in customers:
        if 'created_at' not in customer:
            customer['created_at'] = datetime.now()
    
    return render_template('admin/customers.html', customers=customers)



@app.route('/admin/customers/delete/<customer_id>')
@admin_required
def delete_customer(customer_id):
    mongo.db.users.delete_one({"_id": ObjectId(customer_id)})
    # Optionally also remove their parcels or leave them for history
    flash('Customer deleted', 'success')
    return redirect(url_for('admin_customers'))

@app.route('/admin/parcels')
@admin_required
def admin_parcels():
    parcels = list(mongo.db.parcels.find().sort("created_at", -1))
    staff_list = list(mongo.db.users.find({"role": "staff"}))
    return render_template('admin/parcels.html', parcels=parcels, staff_list=staff_list)

@app.route('/admin/parcels/status', methods=['POST'])
@admin_required
def admin_update_parcel_status():
    tracking_id = request.form.get('tracking_id')
    new_status = request.form.get('status')

    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
    if not parcel:
        flash('Parcel not found', 'danger')
        return redirect(url_for('admin_parcels'))

    update = {
        "status": new_status,
        "updated_at": datetime.now()
    }
    if new_status == 'delivered':
        update["delivered_at"] = datetime.now()

    mongo.db.parcels.update_one(
        {"_id": parcel['_id']},
        {
            "$set": update,
            "$push": {
                "status_history": {
                    "status": new_status,
                    "timestamp": datetime.now(),
                    "note": f"Status updated by admin to {new_status}"
                }
            }
        }
    )

    # Notify customer
    create_notification(
        parcel['customer_id'],
        "Parcel Status Updated",
        f"Your parcel {tracking_id} status is now {new_status.upper()}",
        "status_update"
    )

    flash('Parcel status updated', 'success')
    return redirect(url_for('admin_parcels'))
@app.route('/admin/mark_paid/<tracking_id>', methods=['POST'])
def admin_mark_paid(tracking_id):
    if 'user_id' not in session or session.get('role') not in ['admin', 'staff']:
        return redirect(url_for('login'))
    
    mongo.db.parcels.update_one(
        {"tracking_id": tracking_id},
        {"$set": {
            "payment_status": "paid",
            "payment_mode": "cod", 
            "payment_collected_at": datetime.now()
        }}
    )
    flash('Payment marked as collected!')
    return redirect(url_for('admin_parcels'))


@app.route('/admin/parcels/add', methods=['GET', 'POST'])
@admin_required
def admin_add_parcel():
    # Admin chooses existing customer by email or ID
    customers = list(mongo.db.users.find({"role": "customer"}).sort("name", 1))

    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        customer = mongo.db.users.find_one({"_id": ObjectId(customer_id)})

        if not customer:
            flash('Customer not found', 'danger')
            return redirect(url_for('admin_add_parcel'))

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

        cost = calculate_cost(weight, parcel_type, delivery_type)

        parcel_data = {
            "tracking_id": generate_tracking_id(),
            "customer_id": customer["_id"],
            "customer_name": customer["name"],
            "customer_email": customer["email"],
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
                "note": "Parcel booked by admin"
            }],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "staff_id": None,
            "staff_name": None,
            "delivered_at": None
        }

        mongo.db.parcels.insert_one(parcel_data)
        flash(f"Parcel booked for {customer['name']} (TRK: {parcel_data['tracking_id']})", 'success')
        return redirect(url_for('admin_parcels'))

    return render_template('admin/add_parcel.html', customers=customers)

@app.route('/admin/parcels/delete/<tracking_id>')
@admin_required
def admin_delete_parcel(tracking_id):
    mongo.db.parcels.delete_one({"tracking_id": tracking_id})
    flash('Parcel deleted', 'success')
    return redirect(url_for('admin_parcels'))

# View single customer details
@app.route('/admin/customers/view/<customer_id>')
@admin_required
def view_customer(customer_id):
    customer = mongo.db.users.find_one({"_id": ObjectId(customer_id), "role": "customer"})
    if not customer:
        flash("Customer not found", "danger")
        return redirect(url_for('admin_customers'))
    
    # All parcels of this customer (optional)
    parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)}).sort("created_at", -1))
    
    return render_template(
        'admin/view_customer.html',
        customer=customer,
        parcels=parcels
    )


# Add customer (admin-created)
@app.route('/admin/customers/add', methods=['GET', 'POST'])
@admin_required
def add_customer():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if mongo.db.users.find_one({"email": email}):
            flash('Email already registered', 'danger')
            return redirect(url_for('add_customer'))

        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect(url_for('add_customer'))

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "role": "customer",
            "status": "active",
            "address": "",
            "created_at": datetime.now()
        })

        flash('Customer added successfully', 'success')
        return redirect(url_for('admin_customers'))

    return render_template('admin/add_customer.html')


@app.route('/admin/track', methods=['GET', 'POST'])
@admin_required
def admin_track():
    parcel = None
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id')
        parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
        if not parcel:
            flash('Tracking ID not found', 'danger')
    return render_template('admin/track.html', parcel=parcel)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    from_date = datetime(datetime.now().year, datetime.now().month, 1)
    total_month = mongo.db.parcels.count_documents({"created_at": {"$gte": from_date}})
    delivered = mongo.db.parcels.count_documents({
        "status": "delivered",
        "created_at": {"$gte": from_date}
    })
    pending = mongo.db.parcels.count_documents({
        "status": {"$in": ["booked", "picked", "in transit", "out for delivery"]},
        "created_at": {"$gte": from_date}
    })
    cancelled = mongo.db.parcels.count_documents({
        "status": "cancelled",
        "created_at": {"$gte": from_date}
    })

    # Cash collected for COD
    cash_collected = 0
    for p in mongo.db.parcels.find({
        "payment_mode": "cod",
        "payment_status": "paid"
    }):
        cash_collected += float(p.get("cost", 0))

    return render_template(
        'admin/reports.html',
        total_month=total_month,
        delivered=delivered,
        pending=pending,
        cancelled=cancelled,
        cash_collected=cash_collected
    )

   

# ========== API ENDPOINTS FOR ADMIN ==========

@app.route('/api/admin/notifications')
@admin_required
def admin_notifications():
    # Admin can see all notifications
    notifications = list(mongo.db.notifications.find({})
                        .sort("created_at", -1)
                        .limit(50))
    
    # Convert ObjectId to string for JSON
    for note in notifications:
        note['_id'] = str(note['_id'])
        note['user_id'] = str(note['user_id'])
    
    return jsonify(notifications)

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    stats = {
        "total_customers": mongo.db.users.count_documents({"role": "customer"}),
        "total_staff": mongo.db.users.count_documents({"role": "staff"}),
        "total_parcels": mongo.db.parcels.count_documents({}),
        "booked_parcels": mongo.db.parcels.count_documents({"status": "booked"}),
        "in_transit": mongo.db.parcels.count_documents({"status": "in transit"}),
        "delivered_today": mongo.db.parcels.count_documents({
            "status": "delivered",
            "delivered_at": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
        })
    }
    return jsonify(stats)



# ========== API ENDPOINTS ==========

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
        # Create database indexes
        mongo.db.notifications.create_index([("user_id", 1), ("read", 1)])
        mongo.db.parcels.create_index([("tracking_id", 1)], unique=True)
        mongo.db.users.create_index([("email", 1)], unique=True)
        mongo.db.parcels.create_index([("status", 1)])
        print("Database initialized and indexes created")
    
    app.run(debug=True, port=3000, host='0.0.0.0')