from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify,
    make_response, send_file
)
from flask_pymongo import PyMongo
from flask_socketio import SocketIO
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from functools import wraps
import bcrypt
import os
import requests
import time
from flask_mail import Mail, Message
from collections import defaultdict
from calendar import month_abbr
import qrcode
from io import BytesIO
import calendar
from dotenv import load_dotenv
import random
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
# ========== PARCEL STATUS CONSTANTS ==========
STATUS_BOOKED = "booked"
STATUS_PICKED = "picked"
STATUS_IN_TRANSIT = "in_transit"
STATUS_OUT_FOR_DELIVERY = "out_for_delivery"
STATUS_DELIVERED = "delivered"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed_delivery"

ALL_STATUSES = [
    STATUS_BOOKED,
    STATUS_PICKED,
    STATUS_IN_TRANSIT,
    STATUS_OUT_FOR_DELIVERY,
    STATUS_DELIVERED,
    STATUS_CANCELLED,
    STATUS_FAILED
]
STATUS_FLOW = {
    STATUS_BOOKED: [STATUS_PICKED],
    STATUS_PICKED: [STATUS_IN_TRANSIT],
    STATUS_IN_TRANSIT: [STATUS_OUT_FOR_DELIVERY],
    STATUS_OUT_FOR_DELIVERY: [STATUS_DELIVERED, STATUS_FAILED],
    STATUS_FAILED: [STATUS_OUT_FOR_DELIVERY]  # retry delivery
}

# ========== EXTERNAL API TRACKING FUNCTION ==========
def track_with_ship24(tracking_id):
    """Enhanced Ship24 with location + NA fallback"""
    try:
        url = f"https://api.ship24.com/public/v1/trackers"
        params = {'trackingNumber': tracking_id, 'country': 'IN'}
        response = requests.get(url, params=params, timeout=8)
        data = response.json()
        
        if data.get('data', {}).get('trackers'):
            tracker = data['data']['trackers'][0]
            latest_event = tracker.get('events', [{}])[0] if tracker.get('events') else {}
            
            return {
                'success': True,
                'carrier': tracker.get('courier_name', 'Unknown Carrier'),
                'status': tracker.get('status', 'In Transit'),
                'location': latest_event.get('location', 'Processing Hub') or 'NA',
                'events': tracker.get('events', []),
                'estimated_delivery': tracker.get('estimated_delivery', 'NA')
            }
    except:
        pass
    return {'success': False, 'error': 'Not found'}


load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", manage_session=True)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-2026")
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/courio_db")

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)  # Remember me functionality

mongo = PyMongo(app)
app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_PORT=int(os.getenv("MAIL_PORT")),
    MAIL_USE_TLS=os.getenv("MAIL_USE_TLS") == "true",
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER")
)
mail = Mail(app)


def serialize_parcel(p):
    p = dict(p)

    # Convert ObjectIds
    for key in ["_id", "customer_id", "staff_id", "branch_id"]:
        if p.get(key):
            p[key] = str(p[key])

    # Convert all datetimes in root
    for k, v in list(p.items()):
        if isinstance(v, datetime):
            p[k] = v.strftime("%Y-%m-%d %H:%M:%S")

    # Convert nested status_history timestamps
    if isinstance(p.get("status_history"), list):
        for h in p["status_history"]:
            if isinstance(h.get("timestamp"), datetime):
                h["timestamp"] = h["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

    return p

def deep_serialize(obj):
    if isinstance(obj, dict):
        return {k: deep_serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_serialize(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    return obj

def update_live_stats():
    global live_stats_cache

    while True:
        try:
            status_counts = {}
            for s in mongo.db.parcels.aggregate([
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]):
                status_counts[str(s.get("_id") or "unknown")] = int(s.get("count", 0))

            recent = list(
                mongo.db.parcels.find()
                .sort("created_at", -1)
                .limit(10)
            )

            recent_serialized = [serialize_parcel(p) for p in recent]

            live_stats_cache = {
                "customers": mongo.db.users.count_documents({"role": "customer"}),
                "active_staff": mongo.db.users.count_documents({"role": "staff", "status": "active"}),
                "total_staff": mongo.db.users.count_documents({"role": "staff"}),
                "parcels": mongo.db.parcels.count_documents({}),
                "pending": mongo.db.parcels.count_documents({"status": "booked"}),
                "delivered": mongo.db.parcels.count_documents({"status": "delivered"}),
                "status_counts": status_counts,
                "recent_parcels": recent_serialized
            }

            socketio.emit("live_update", deep_serialize(live_stats_cache))

        except Exception as e:
            print("❌ Live stats error:", e)

        time.sleep(30)

live_thread_started = False
live_stats_cache = {}
from flask_socketio import join_room

@socketio.on('connect')
def handle_connect():
    global live_thread_started

    if not live_thread_started:
        socketio.start_background_task(update_live_stats)
        live_thread_started = True

    if session.get("role") == "staff":
        join_room(str(session.get("user_id")))

# ========== HELPER FUNCTIONS ==========
def send_email(to, subject, body):
    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            body=body
        )
        mail.send(msg)
        print(f"📧 Email sent to {to}")
    except Exception as e:
        print(f"❌ Email error: {e}")


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


def generate_tracking_id():
    """Find NEXT available numeric ID (handles duplicates)"""
    try:
        # Find highest existing number
        pipeline = [
            {"$match": {"tracking_id": {"$regex": "^\\d+$"}}},
            {"$group": {"_id": None, "max_id": {"$max": {"$toInt": "$tracking_id"}}}},
            {"$project": {"next_id": {"$add": ["$max_id", 1]}}}
        ]
        
        result = list(mongo.db.parcels.aggregate(pipeline))
        
        if result:
            next_id = result[0]['next_id']
        else:
            next_id = 1000001
            
        # Keep trying until unique
        tracking_id = str(next_id).zfill(7)
        while mongo.db.parcels.find_one({"tracking_id": tracking_id}):
            next_id += 1
            tracking_id = str(next_id).zfill(7)
            
        return tracking_id
        
    except:
        # Fallback: start from 1000001 and increment
        for i in range(1000001, 9999999):
            tracking_id = str(i).zfill(7)
            if not mongo.db.parcels.find_one({"tracking_id": tracking_id}):
                return tracking_id
        return "9999999"
    
def calculate_cost(weight, parcel_type, delivery_type, is_same_city=True):

    try:
        weight = float(weight)
    except:
        weight = 0

    base = 50
    weight_cost = weight * 12

    distance_cost = 20 if is_same_city else 40

    parcel_type = parcel_type.lower()
    delivery_type = delivery_type.lower()

    type_cost = {
        "document": 10,
        "box": 20,
        "fragile": 40,
        "electronics": 50
    }

    delivery_cost = {
        "standard": 30,
        "express": 80,
        "same_day": 120  
    }

    total = base + weight_cost
    total += distance_cost
    total += type_cost.get(parcel_type, 20)
    total += delivery_cost.get(delivery_type, 30)

    return round(total, 2)

# def calculate_cost(weight, parcel_type, delivery_type, is_same_city=True):

#     base = 50

#     weight_cost = float(weight) * 12

#     # distance
#     if is_same_city:
#         distance_cost = 20
#     else:
#         distance_cost = 40

#     # parcel type
#     type_cost = {
#         "document": 10,
#         "box": 20,
#         "fragile": 40,
#         "electronics": 50
#     }

#     # delivery speed
#     delivery_cost = {
#         "standard": 30,
#         "express": 80,
#         "same_day": 120  
#     }
    
#     total = base + weight_cost
#     total += distance_cost
#     total += type_cost.get(parcel_type, 20)
#     # total += delivery_cost.get(delivery_type, 30)
#     # total += delivery_cost.get(delivery_type.lower(), 30)
#     delivery_type = delivery_type.lower()
#     total += delivery_cost.get(delivery_type, 30)

#     return round(total, 2)

def calculate_real_expense(weight, delivery_type, is_same_city=True):

    weight = float(weight)

    fuel_cost = weight * 3
    distance_cost = 15 if is_same_city else 40

    staff_cost = 12
    handling_cost = 8
    warehouse_cost = 6
    risk_cost = 4

    multiplier = {
        "standard": 1.0,
        "express": 1.25
    }

    expense = (
        fuel_cost +
        distance_cost +
        staff_cost +
        handling_cost +
        warehouse_cost +
        risk_cost
    )

    expense *= multiplier.get(delivery_type, 1.0)

    return round(expense, 2)

# new kpi 
def get_kpi_stats():
    today = datetime.now()
    last_30_days = today - timedelta(days=30)

    revenue = sum(
        float(p.get("cost", 0)) for p in mongo.db.parcels.find({
            "status": STATUS_DELIVERED,
            "payment_status": "paid",
            "created_at": {"$gte": last_30_days}
        })
    )

    profit = round(revenue * 0.2, 2)

    total_parcels = mongo.db.parcels.count_documents({})
    delivered = mongo.db.parcels.count_documents({"status": STATUS_DELIVERED})
    pending = mongo.db.parcels.count_documents({
        "status": {"$in": [STATUS_BOOKED, STATUS_PICKED, STATUS_IN_TRANSIT, STATUS_OUT_FOR_DELIVERY, STATUS_FAILED]}
    })
    cancelled = mongo.db.parcels.count_documents({"status": STATUS_CANCELLED})

    return {
        "revenue": round(revenue, 2),
        "profit": profit,
        "total_parcels": total_parcels,
        "delivered": delivered,
        "pending": pending,
        "cancelled": cancelled
    }

def auto_assign_staff(branch_id):
    staff_list = list(mongo.db.users.find({
        "role": "staff",
        "status": "active",
        "branch_id": branch_id
    }))

    print("DEBUG STAFF LIST:", staff_list)   # 🔥 Add this line

    if not staff_list:
        return None

    staff_load = []

    for staff in staff_list:
        active_count = mongo.db.parcels.count_documents({
            "staff_id": staff["_id"],
            "status": {"$in": ["booked", "picked", "in_transit", "out_for_delivery", "failed_delivery"]}
        })
        staff_load.append((staff, active_count))

    staff_load.sort(key=lambda x: x[1])

    for staff, count in staff_load:
        if count < 5:
            return staff

    return None


import re

def is_strong_password(password):
    if len(password) < 8:
        return False

    # At least 1 letter (uppercase or lowercase)
    if not re.search(r"[A-Za-z]", password):
        return False

    # At least 1 number
    if not re.search(r"\d", password):
        return False

    # At least 1 special character (including _)
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False

    return True

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def staff_required(f):  # NEW - Staff only
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'staff':
            flash('Staff access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# Helper function to create notifications
def create_notification(user_id, title, message, notification_type):

    
    try:
        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})

        mongo.db.notifications.insert_one({
            "user_id": ObjectId(user_id),
            "title": title,
            "message": message,
            "type": notification_type,
            "read": False,
            "created_at": datetime.now()
        })

        if user and user.get("email"):
            send_email(
                to=user["email"],
                subject=title,
                body=f"Hello {user.get('name')},\n\n{message}\n\n– Courio"
            )

    except Exception as e:
        print("Notification error:", e)

# ========== PUBLIC ROUTES ==========

@app.route('/')
def index():
    return render_template('index.html')

# @app.route('/about')
# def about():
#     return render_template('about.html')
@app.route('/about')
def about():
    total_parcels = mongo.db.parcels.count_documents({})
    total_customers = mongo.db.users.count_documents({"role": "customer"})

    return render_template(
        'about.html',
        total_parcels=total_parcels,
        total_customers=total_customers
    )


@app.route('/track', methods=['GET', 'POST'])
def track():
    tracking_id = request.args.get('tracking_id') or request.form.get('tracking_id')
    
    if tracking_id:
        # 1. Check local parcels FIRST (ALWAYS FRESH)
        local_parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
        if local_parcel:
            # ✅ ADD CACHE-BUSTER - Forces fresh data
            response = make_response(render_template('track.html', 
                                                   parcel=local_parcel,
                                                   tracking_id=tracking_id))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response
        
        # 2. External API
        api_result = track_with_ship24(tracking_id)
        if api_result['success']:
            response = make_response(render_template('track.html', 
                                                   api_result=api_result,
                                                   tracking_id=tracking_id))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response
        
        flash('Tracking ID not found', 'warning')
    
    return render_template('track.html', tracking_id=tracking_id or '')
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
        
        # ✅ SAFE CHECK - No more NoneType crash!
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            session['user_id'] = str(user['_id'])
            session['email'] = user['email']
            session['name'] = user['name']
            session['role'] = user['role']
            
            if remember:
                session.permanent = True
            

            # ✅ SAFE ROLE REDIRECT
            role = user['role']
            if role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif role == 'staff':
                return redirect(url_for('staff_dashboard'))
            elif role == 'customer':
                return redirect(url_for('customer_dashboard'))
            else:
                flash('Role not recognized', 'warning')
                return redirect(url_for('customer_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')
import random
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = mongo.db.users.find_one({"email": email})

        if not user:
            flash("Email not found", "danger")
            return redirect(url_for('forgot_password'))

        #  ONLY customers
        if user.get("role") != "customer":
            flash("Password reset is allowed only for customers. Please contact admin.", "warning")
            return redirect(url_for('login'))

        otp = str(random.randint(100000, 999999))

        result = mongo.db.users.update_one(
        {"email": email},
        {"$set": {
            "reset_otp": otp,
            "reset_otp_time": datetime.now()
    }}
)

        print("DEBUG UPDATE RESULT:", result.matched_count, result.modified_count)

        send_email(
            to=email,
            subject="Password Reset OTP - Courio",
            body=f"Your OTP for password reset is: {otp}\n\nThis OTP is valid for 10 minutes."
        )

        # session["reset_email"] = email
        session["reset_email"] = email.strip().lower()
        flash("OTP sent to your email", "success")
        return redirect(url_for('verify_otp'))

    return render_template('forgot_password.html')
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = (session.get("reset_email") or "").strip().lower()
    if not email:
        return redirect(url_for("forgot_password"))

    if request.method == 'POST':
        otp = (request.form.get("otp") or "").strip()

        user = mongo.db.users.find_one({"email": email})

        if not user:
            flash("Session expired. Try again.", "danger")
            return redirect(url_for("forgot_password"))

        db_otp = str(user.get("reset_otp", "")).strip()

        print("DEBUG FORM OTP:", otp)
        print("DEBUG DB OTP:", db_otp)

        if db_otp != otp:
            flash("Invalid OTP", "danger")
            return redirect(url_for("verify_otp"))

        return redirect(url_for("reset_password"))

    return render_template("verify_otp.html")

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = (session.get("reset_email") or "").strip().lower()
    if not email:
        return redirect(url_for("forgot_password"))

    user = mongo.db.users.find_one({"email": email})

    if not user or user.get("role") != "customer":
        flash("Password reset is not allowed for this account.", "danger")
        return redirect(url_for("login"))

    if request.method == 'POST':
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(url_for("reset_password"))

        if not is_strong_password(new_password):
            flash("Password must be at least 8 characters and include a letter, number, and special character.", "danger")
            return redirect(url_for("reset_password"))

        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

        print("DEBUG RESET EMAIL:", email)

        result = mongo.db.users.update_one(
            {"email": email},
            {
                "$set": {"password": hashed},
                "$unset": {"reset_otp": "", "reset_otp_time": ""}
            }
        )

        print("DEBUG RESET RESULT:", result.matched_count, result.modified_count)

        session.pop("reset_email", None)
        flash("Password reset successfully. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        
    
        if mongo.db.users.find_one({"email": email}):
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))
        
        if not is_strong_password(password):
            flash("Password must be at least 8 characters and include a letter, number, and special character.", "danger")
            return redirect(url_for('signup'))
        


        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        


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

@app.route('/feedback', methods=['GET', 'POST'])
def public_feedback():
    if request.method == 'POST':
        feedback = {
            'name': request.form.get('name', 'Anonymous'),
            'phone': request.form.get('phone', ''),
            'email': request.form.get('email', ''),
            'rating': int(request.form.get('rating', 3)),
            'service': request.form.get('service', ''),
            'comments': request.form.get('comments', ''),
            'created_at': datetime.now()
        }
        mongo.db.feedback.insert_one(feedback)
        flash('Thank you for your valuable feedback!', 'success')
        return redirect(url_for('public_feedback'))
    
    return render_template('feedback.html')

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})

    old = request.form.get("old_password")
    new = request.form.get("new_password")

    if not bcrypt.checkpw(old.encode('utf-8'), user['password']):
        flash("Wrong current password", "danger")
        return redirect(url_for('customer_profile'))

    hashed = bcrypt.hashpw(new.encode('utf-8'), bcrypt.gensalt())

    mongo.db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": hashed}}
    )

    flash("Password updated successfully", "success")
    return redirect(url_for('customer_profile'))
    
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

    # ✅ GET ACTIVE BRANCH CITIES FOR DROPDOWN
    branches = list(mongo.db.branches.find({"status": "active"}))
    cities = sorted(set(b["city"] for b in branches if b.get("city")))
    
    if request.method == 'POST':
        # Get form data
        sender_name = request.form.get('sender_name')
        sender_phone = request.form.get('sender_phone')
        sender_address = request.form.get('sender_address')
        sender_pincode = request.form.get('sender_pincode')
        sender_city = (request.form.get('sender_city') or "").strip()
        
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
        # cost = calculate_cost(weight, parcel_type, delivery_type)
        cost = calculate_cost(weight, parcel_type, delivery_type, True)

        branch = mongo.db.branches.find_one({
            "city": {"$regex": f"^{sender_city}$", "$options": "i"},
            "status": "active"
})

        if not branch:
            flash(f"No active branch found in {sender_city}. Please contact admin.", "danger")
            return redirect(url_for('customer_dashboard'))

# AUTO ASSIGN STAFF FROM SAME BRANCH
        assigned_staff = auto_assign_staff(branch["_id"])
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

            # BRANCH INFO
            "branch_id": branch["_id"],
            "branch_name": branch["name"],
            "branch_city": branch["city"],
            "branch_address": branch.get("address", ""),
            "branch_phone": branch.get("phone", "NA"),

            "status_history": [{
                "status": "booked",
                "timestamp": datetime.now(),
                "note": f"Parcel booked at {branch['name']}"
            }],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "staff_id": assigned_staff["_id"] if assigned_staff else None,
            "staff_name": assigned_staff["name"] if assigned_staff else None,
            "delivered_at": None
        }
        
        mongo.db.parcels.insert_one(parcel_data)
        if assigned_staff:
            mongo.db.notifications.insert_one({
                "user_id": assigned_staff["_id"],
                "title": "New Parcel Assigned",
                "message": f"Parcel #{parcel_data['tracking_id']} assigned to you.",
                "read": False,
                "created_at": datetime.now()
        })
       

        create_notification(
            customer_id,
            "Parcel Booked Successfully",
            f"Your parcel has been booked. Tracking ID: {parcel_data['tracking_id']}. Cost: ₹{cost}",
            "booking"
        )
        
        flash('Parcel booked successfully!', 'success')
        return redirect(url_for('customer_parcels'))
    
    return render_template('customer/book_parcel.html', customer=customer,cities=cities)

@app.route('/customer/parcels')  # ← URL path
def customer_parcels():          # ← Function name = endpoint name
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login'))

    customer_id = session['user_id']
    parcels = list(mongo.db.parcels.find({
        "customer_id": ObjectId(customer_id),
        "status": {"$ne": "cancelled"}
    }).sort("created_at", -1))
    
    # Add can_edit flag
    cutoff_time = datetime.now() - timedelta(days=2)
    for parcel in parcels:
        parcel['can_edit'] = (parcel['status'] == 'booked' and 
                            parcel['created_at'] > cutoff_time)
    
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

    # ✅ MUST be defined first
    nearby_branches = []

    branch_city = parcel.get("branch_city")
    branch_id = parcel.get("branch_id")

    if branch_city:
        nearby_branches = list(mongo.db.branches.find({
            "city": branch_city,
            "status": "active",
            "_id": {"$ne": branch_id} if branch_id else {"$exists": True}
        }))

    return render_template(
        'customer/parcel_detail.html',
        parcel=parcel,
        nearby_branches=nearby_branches
    )

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


@app.route('/customer/invoice/<tracking_id>')
@login_required
def generate_invoice(tracking_id):

    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})

    if not parcel:
        flash("Parcel not found", "danger")
        return redirect(url_for("customer_parcels"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        alignment=1
    )

    center_style = ParagraphStyle(
        "Center",
        parent=styles["Normal"],
        alignment=1
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading3"],
        spaceAfter=10
    )

    elements = []

    # HEADER
    elements.append(Paragraph("COURIOSYS COURIER SERVICE ", title_style))
    elements.append(Paragraph("Parcel Delivery Invoice", center_style))
    elements.append(Spacer(1, 25))

    # INVOICE INFO
    invoice_data = [
        ["Invoice No", f"INV-{parcel['tracking_id']}"],
        ["Tracking ID", parcel.get("tracking_id")],
        ["Date", parcel.get("created_at").strftime("%d %B %Y")]
    ]

    invoice_table = Table(invoice_data, colWidths=[150, 350])
    invoice_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),
    ]))

    elements.append(invoice_table)
    elements.append(Spacer(1, 25))

    # CUSTOMER DETAILS
    elements.append(Paragraph("Customer Details", section_style))

    customer_data = [
        ["Name", parcel.get("customer_name")],
        ["Phone", parcel.get("customer_phone")],
        ["Email", parcel.get("customer_email")]
    ]

    customer_table = Table(customer_data, colWidths=[150, 350])
    customer_table.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),1,colors.lightgrey),
        ('BACKGROUND',(0,0),(0,-1),colors.whitesmoke)
    ]))

    elements.append(customer_table)
    elements.append(Spacer(1,25))

    # SENDER / RECEIVER (SIDE BY SIDE)
    elements.append(Paragraph("Shipment Details", section_style))

    shipment_data = [
    ["Sender", Paragraph(parcel.get("sender_name"), styles['Normal'])],
    ["Sender Address", Paragraph(parcel.get("sender_address"), styles['Normal'])],
    ["Receiver", Paragraph(parcel.get("receiver_name"), styles['Normal'])],
    ["Receiver Address", Paragraph(parcel.get("receiver_address"), styles['Normal'])]
]

    shipment_table = Table(shipment_data, colWidths=[250,250])
    shipment_table.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),1,colors.lightgrey),
        ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
        ('VALIGN',(0,0),(-1,-1),'TOP')
    ]))

    elements.append(shipment_table)
    elements.append(Spacer(1,25))

    # PARCEL DETAILS
    elements.append(Paragraph("Parcel Information", section_style))

    parcel_data = [
        ["Weight", f"{parcel.get('weight')} kg"],
        ["Parcel Type", parcel.get("parcel_type")],
        ["Delivery Type", parcel.get("delivery_type")],
        ["Status", parcel.get("status")]
    ]

    parcel_table = Table(parcel_data, colWidths=[150,350])
    parcel_table.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),1,colors.lightgrey),
        ('BACKGROUND',(0,0),(0,-1),colors.whitesmoke)
    ]))

    elements.append(parcel_table)
    elements.append(Spacer(1,25))

    # PAYMENT DETAILS
    elements.append(Paragraph("Payment Details", section_style))

    payment_data = [
        ["Cost", f"Rs {parcel.get('cost')}"],
        ["Payment Mode", parcel.get("payment_mode")],
        ["Payment Status", parcel.get("payment_status")]
    ]

    payment_table = Table(payment_data, colWidths=[150,350])
    payment_table.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),1,colors.grey),
        ('BACKGROUND',(0,0),(0,-1),colors.lightgrey)
    ]))

    elements.append(payment_table)
    elements.append(Spacer(1,40))

    # FOOTER
    elements.append(Paragraph(
        "Thank you for choosing Courio Delivery Service.",
        center_style
    ))

    doc.build(elements)

    buffer.seek(0)

    invoice_data = {
    "invoice_no": f"INV-{parcel['tracking_id']}",
    "tracking_id": parcel["tracking_id"],
    "customer_name": parcel.get("customer_name"),
    "sender_name": parcel.get("sender_name"),
    "receiver_name": parcel.get("receiver_name"),
    "weight": parcel.get("weight"),
    "parcel_type": parcel.get("parcel_type"),
    "delivery_type": parcel.get("delivery_type"),
    "cost": parcel.get("cost"),
    "payment_mode": parcel.get("payment_mode"),
    "payment_status": parcel.get("payment_status"),
    "created_at": datetime.now()
}

    existing_invoice = mongo.db.invoices.find_one({"tracking_id": tracking_id})

    if not existing_invoice:
        mongo.db.invoices.insert_one(invoice_data)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{tracking_id}.pdf",
        mimetype="application/pdf"
    )
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

# feedback 
# ✅ CUSTOMER PANEL FEEDBACK (Login required)
@app.route('/customer/feedback', methods=['GET', 'POST'])
@login_required
def customer_feedback_panel():
    if session.get('role') != 'customer':
        return redirect(url_for('login'))
    
    customer_id = session['user_id']
    if request.method == 'POST':
        feedback = {
            'customer_id': ObjectId(customer_id),
            'customer_name': session.get('name', ''),
            'email': request.form.get('email', ''),
            'phone': request.form.get('phone', ''),
            'rating': int(request.form.get('rating', 3)),
            'service': request.form.get('service', ''),
            'comments': request.form.get('comments', ''),
            'created_at': datetime.now()
        }
        mongo.db.feedback.insert_one(feedback)
        flash('Feedback submitted successfully!', 'success')
        return redirect(url_for('customer_dashboard'))
    
    return render_template('customer/feedback_panel.html')

# ========== ADMIN ROUTES ==========
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():

    total_customers = mongo.db.users.count_documents({"role": "customer"})
    total_staff = mongo.db.users.count_documents({"role": "staff"})
    total_parcels = mongo.db.parcels.count_documents({})

    pending_count = mongo.db.parcels.count_documents({
        "status": {"$ne": "delivered"}
    })

    delivered_count = mongo.db.parcels.count_documents({
        "status": "delivered"
    })

    # ======================
    # 💰 ALL-TIME FINANCIAL LOGIC (FIXED ✅)
    # ======================
    total_revenue = 0
    total_expense = 0
    total_profit = 0

    for p in mongo.db.parcels.find():

        # Only valid business cases
        if p.get("status") != "delivered":
            continue
        if p.get("payment_status") != "paid":
            continue

        cost = float(p.get("cost", 0))
        weight = p.get("weight", 0)
        delivery_type = p.get("delivery_type", "standard")

        expense = calculate_real_expense(weight, delivery_type)
        profit = cost - expense

        total_revenue += cost
        total_expense += expense
        total_profit += profit

    total_revenue = round(total_revenue, 2)
    total_expense = round(total_expense, 2)
    total_profit = round(total_profit, 2)

    # ======================
    # 📊 STATUS CHART
    # ======================
    status_data = defaultdict(int)

    for p in mongo.db.parcels.find():
        status_data[p.get("status", "unknown")] += 1

    status_labels = list(status_data.keys())
    status_values = list(status_data.values())

    # ======================
    # 🏢 BRANCH CHART
    # ======================
    branch_data = defaultdict(lambda: {"total": 0, "delivered": 0})

    for p in mongo.db.parcels.find():
        branch = p.get("branch_name", "Unknown")
        branch_data[branch]["total"] += 1

        if p.get("status") == "delivered":
            branch_data[branch]["delivered"] += 1

    branch_labels = list(branch_data.keys())
    branch_parcels = [b["total"] for b in branch_data.values()]
    branch_delivered = [b["delivered"] for b in branch_data.values()]

    # ======================
    # 📊 PROFIT VS EXPENSE
    # ======================
    profit_loss_labels = ["Profit", "Expense"]
    profit_loss_values = [
        total_profit,
        total_expense
    ]

    # ======================
    # 🎯 DELIVERY RATE
    # ======================
    total = total_parcels if total_parcels > 0 else 1
    on_time_percentage = round((delivered_count / total) * 100, 2)

    # ======================
    # 📦 RECENT PARCELS
    # ======================
    recent_parcels = list(
        mongo.db.parcels.find().sort("created_at", -1).limit(5)
    )
    daily_labels = []
    daily_values = []
    profit_labels = []
    profit_values = []

    
    trend_data = defaultdict(int) 
    today = datetime.now() 
    for p in mongo.db.parcels.find():
        created = p.get("created_at") 
        if not created:
            continue 
        # Only last 7 days 
        if created >= today - timedelta(days=7):
             day = created.strftime("%d %b")
             trend_data[day] += 1
              # Prepare labels
        daily_labels = []
        daily_values = [] 

        for i in range(7):
            d = (today - timedelta(days=6 - i)).strftime("%d %b")
            daily_labels.append(d) 
            daily_values.append(trend_data.get(d, 0))

    return render_template(
        "admin/dashboard.html",

        total_customers=total_customers,
        total_staff=total_staff,
        total_parcels=total_parcels,
        pending_count=pending_count,
        delivered_count=delivered_count,

        # ✅ NEW VALUES
        total_revenue=total_revenue,
        total_expense=total_expense,
        total_profit=total_profit,

        status_labels=status_labels,
        status_values=status_values,

        branch_labels=branch_labels,
        branch_parcels=branch_parcels,
        branch_delivered=branch_delivered,

        profit_loss_labels=profit_loss_labels,
        profit_loss_values=profit_loss_values,

        on_time_percentage=on_time_percentage,
        recent_parcels=recent_parcels,
        daily_labels=daily_labels,
daily_values=daily_values,
profit_labels=profit_labels,
profit_values=profit_values
    )

@app.route('/admin/branches')
@admin_required
def admin_branches():
    branches = list(mongo.db.branches.find().sort("created_at", -1))

    # Add staff & parcel count per branch
    for branch in branches:
        branch['staff_count'] = mongo.db.users.count_documents({
            "role": "staff",
            "branch_id": branch["_id"]
        })

        branch['parcel_count'] = mongo.db.parcels.count_documents({
            "branch_id": branch["_id"]
        })

    return render_template('admin/branches.html', branches=branches)
@app.route('/admin/branches/add', methods=['GET', 'POST'])
@admin_required
def admin_add_branch():
    if request.method == 'POST':
        mongo.db.branches.insert_one({
            "name": request.form.get('name'),
            "city": request.form.get('city'),
            "pincode": request.form.get('pincode'),
            "address": request.form.get('address'),
            "phone": request.form.get('phone'),
            "email": request.form.get('email'),
            "status": "active",
            "created_at": datetime.now()
        })

        flash("Branch added successfully", "success")
        return redirect(url_for('admin_branches'))

    return render_template('admin/add_branch.html')

@app.route('/admin/branches/<branch_id>')
@admin_required
def view_branch(branch_id):
    branch = mongo.db.branches.find_one({"_id": ObjectId(branch_id)})

    if not branch:
        flash("Branch not found", "danger")
        return redirect(url_for('admin_branches'))

    # Staff count
    branch['staff_count'] = mongo.db.users.count_documents({
        "role": "staff",
        "branch_id": branch["_id"]
    })

    # Parcel count
    branch['parcel_count'] = mongo.db.parcels.count_documents({
        "branch_id": branch["_id"]
    })

    return render_template('admin/view_branch.html', branch=branch)

@app.route('/admin/branches/<branch_id>/manager', methods=['GET', 'POST'])
@admin_required
def assign_branch_manager(branch_id):
    branch = mongo.db.branches.find_one({"_id": ObjectId(branch_id)})

    staff_list = list(mongo.db.users.find({
        "role": "staff",
        "branch_id": branch["_id"]
    }))

    if request.method == 'POST':
        staff_id = ObjectId(request.form.get('staff_id'))
        staff = mongo.db.users.find_one({"_id": staff_id})

        # Remove old manager
        mongo.db.users.update_many(
            {"branch_id": branch["_id"]},
            {"$set": {"is_branch_manager": False}}
        )

        # Set new manager
        mongo.db.users.update_one(
            {"_id": staff_id},
            {"$set": {"is_branch_manager": True}}
        )

        mongo.db.branches.update_one(
            {"_id": branch["_id"]},
            {"$set": {
                "manager_id": staff["_id"],
                "manager_name": staff["name"],
                "manager_phone": staff["phone"],
                "manager_email": staff["email"]
            }}
        )

        flash("Branch manager assigned successfully", "success")
        return redirect(url_for('view_branch', branch_id=branch_id))

    return render_template(
        'admin/assign_branch_manager.html',
        branch=branch,
        staff_list=staff_list
    )

@app.route('/admin/staff', methods=['GET', 'POST'])
@admin_required
def admin_staff():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        branch_id = request.form.get('branch_id')

        # 1️⃣ Validate branch selection
        if not branch_id:
            flash("Please select a branch for staff", "danger")
            return redirect(url_for('admin_staff'))

        branch = mongo.db.branches.find_one({"_id": ObjectId(branch_id)})
        if not branch:
            flash("Invalid branch selected", "danger")
            return redirect(url_for('admin_staff'))

        # 2️⃣ Prevent duplicate email
        if mongo.db.users.find_one({"email": email}):
            flash('Email already used', 'danger')
            return redirect(url_for('admin_staff'))

        # 3️⃣ Hash password
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # 4️⃣ Insert staff
        mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "role": "staff",
            "status": "active",
            "branch_id": branch["_id"],
            "branch_name": branch["name"],
            "created_at": datetime.now()
        })

        flash('Staff created successfully', 'success')
        return redirect(url_for('admin_staff'))

    # GET request
    staff_list = list(mongo.db.users.find({"role": "staff"}).sort("created_at", -1))
    branches = list(mongo.db.branches.find({"status": "active"}))

    return render_template(
        'admin/staff.html',
        staff_list=staff_list,
        branches=branches
    )
    #  return render_template('admin/staff.html', staff_list=staff_list)


@app.route('/admin/staff/<staff_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_staff(staff_id):
    staff = mongo.db.users.find_one({
        "_id": ObjectId(staff_id),
        "role": "staff"
    })
    if not staff:
        flash("Staff member not found", "danger")
        return redirect(url_for('admin_staff'))

    branches = list(mongo.db.branches.find({"status": "active"}))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        status = request.form.get('status')
        branch_id = request.form.get('branch_id')

        # Prevent duplicate email
        existing = mongo.db.users.find_one({
            "email": email,
            "_id": {"$ne": staff["_id"]}
        })
        if existing:
            flash("Email already used by another user", "danger")
            return redirect(url_for('edit_staff', staff_id=staff_id))

        update_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "status": status
        }

        # ✅ If branch selected
        if branch_id:
            branch = mongo.db.branches.find_one({"_id": ObjectId(branch_id)})
            if branch:
                update_data["branch_id"] = branch["_id"]
                update_data["branch_name"] = branch["name"]

        mongo.db.users.update_one(
            {"_id": staff["_id"]},
            {"$set": update_data}
        )

        flash("Staff details updated successfully", "success")
        return redirect(url_for('admin_staff'))

    return render_template('admin/edit_staff.html', staff=staff, branches=branches)

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



    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
    staff = mongo.db.users.find_one({"_id": ObjectId(staff_id), "role": "staff"})

    if not parcel or not staff:
        flash("Invalid parcel or staff", "danger")
        return redirect(url_for('admin_staff'))

    mongo.db.parcels.update_one(
        {"_id": parcel["_id"]},
        {"$set": {
            "staff_id": staff["_id"],
            "staff_name": staff["name"],
            "branch_id": staff.get("branch_id"),
            "branch_name": staff.get("branch_name"),
            "updated_at": datetime.now()
        }}
    )

    # 🔔 Socket Notification
    socketio.emit("new_assignment", {
        "message": f"New parcel assigned: {parcel['tracking_id']}",
        "tracking_id": parcel["tracking_id"]
    }, room=str(staff["_id"]))

    # 🔔 DB Notification
    mongo.db.notifications.insert_one({
        "user_id": staff["_id"],
        "title": "New Parcel Assigned",
        "message": f"Parcel #{tracking_id} has been assigned to you.",
        "read": False,
        "created_at": datetime.now()
    })

    flash(f"Parcel {tracking_id} assigned to {staff['name']}", "success")
    return redirect(url_for('admin_staff'))


@app.route('/admin/assign_staff/<tracking_id>', methods=['GET', 'POST'])
@admin_required
def assign_staff(tracking_id):
    parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
    if not parcel:
        flash('Parcel not found', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
        staff = mongo.db.users.find_one({"_id": ObjectId(staff_id), "role": "staff"})
        
        if staff:
            # mongo.db.parcels.update_one(
            #     {"tracking_id": tracking_id},
            #     {"$set": {
            #         "staff_id": staff["_id"],
            #         "staff_name": staff["name"],
            #         "assigned_branch_id": staff.get("branch_id"),
            #         "assigned_branch_name": staff.get("branch_name"),
            #         "updated_at": datetime.now()
            #     }}
            # )
            mongo.db.parcels.update_one(
                {"_id": parcel["_id"]},
                {"$set": {
                    "staff_id": staff["_id"],
                    "staff_name": staff["name"],
                    "branch_id": staff.get("branch_id"),
                    "branch_name": staff.get("branch_name"),
                    "updated_at": datetime.now()
           }}
       )

            # 🔔 Auto Notification
            mongo.db.notifications.insert_one({
                "user_id": staff["_id"],
                "title": "New Parcel Assigned",
                "message": f"Parcel #{tracking_id} has been assigned to you.",
                "read": False,
                "created_at": datetime.now()
            })

            flash(f'Parcel #{tracking_id} assigned to {staff["name"]}! ✅', 'success')
        else:
            flash('Invalid staff selection', 'danger')
        
        return redirect(url_for('admin_dashboard'))
    
    staffs = list(mongo.db.users.find({"role": "staff"}))
    return render_template('admin/assign_staff.html', parcel=parcel, staffs=staffs)


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
    current_status = parcel["status"]
    allowed_next = STATUS_FLOW.get(current_status, [])

    if new_status not in allowed_next and new_status != STATUS_CANCELLED:
     flash("Invalid status transition", "danger")
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
@admin_required
def admin_mark_paid(tracking_id):
    mongo.db.parcels.update_one(
        {"tracking_id": tracking_id},
        {"$set": {
            "payment_status": "paid",
            "payment_collected_at": datetime.now()
        }}
    )
    flash('Payment marked as collected!', 'success')
    return redirect(url_for('admin_parcels'))

# @app.route('/admin/mark_paid/<tracking_id>', methods=['POST'])
# def admin_mark_paid(tracking_id):
#     if 'user_id' not in session or session.get('role') not in ['admin', 'staff']:
#         return redirect(url_for('login'))
    
#     mongo.db.parcels.update_one(
#     {"tracking_id": tracking_id},
#     {"$set": {
#         "payment_status": "paid",   # ✅ CORRECT
#         "payment_mode": "cod", 
#         "payment_collected_at": datetime.now()
#     }}
# )
#     flash('Payment marked as collected!')
#     return redirect(url_for('admin_parcels'))
@app.route('/admin/parcels/add', methods=['GET', 'POST'])
@admin_required
def admin_add_parcel():
    # Admin chooses existing customer
    customers = list(
        mongo.db.users.find({"role": "customer"}).sort("name", 1)
    )

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

        # ✅ ASSIGN BRANCH (INSIDE POST)
        branch = mongo.db.branches.find_one({"status": "active"})
        if not branch:
            flash("No active branch available. Please add a branch first.", "danger")
            return redirect(url_for('admin_add_parcel'))

        parcel_data = {
            "tracking_id": generate_tracking_id(),
            "customer_id": customer["_id"],
            "customer_name": customer["name"],
            "customer_email": customer["email"],

            # ✅ BRANCH INFO
            "branch_id": branch["_id"],
            "branch_name": branch["name"],
            "branch_city": branch.get("city"),
            "branch_address": branch.get("address"),
            "branch_phone": branch.get("phone"),

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
                "note": f"Parcel booked by admin at {branch['name']}"
            }],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "staff_id": None,
            "staff_name": None,
            "delivered_at": None
        }

        mongo.db.parcels.insert_one(parcel_data)

        flash(
            f"Parcel booked for {customer['name']} "
            f"(TRK: {parcel_data['tracking_id']})",
            'success'
        )
        return redirect(url_for('admin_parcels'))

    # ✅ GET request
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

    kpi = get_kpi_stats()

    total_revenue_all = 0
    total_expense_all = 0

    for p in mongo.db.parcels.find({
        "status": "delivered",
        "payment_status": "paid"
    }):
        cost = float(p.get("cost", 0))
        weight = p.get("weight", 0)
        delivery_type = p.get("delivery_type", "standard")

        total_revenue_all += cost
        total_expense_all += calculate_real_expense(weight, delivery_type)

    total_profit_all = total_revenue_all - total_expense_all

    loss = abs(total_profit_all) if total_profit_all < 0 else 0


    # ======================
    # STAFF PERFORMANCE
    # ======================
    staff_data = defaultdict(int)

    all_staff = list(mongo.db.users.find({"role": "staff"}))

    for s in all_staff:
        staff_data[s.get("name", "Unknown")] = 0

    for p in mongo.db.parcels.find({"status": "delivered"}):
        staff = p.get("staff_name", "Unknown")
        staff_data[staff] += 1

    staff_labels = list(staff_data.keys())
    staff_values = list(staff_data.values())

    top_staff = max(staff_data, key=staff_data.get) if staff_data else "N/A"


    # ======================
    # BRANCH PERFORMANCE
    # ======================
    branch_data = defaultdict(int)

    for p in mongo.db.parcels.find({"status": "delivered"}):
        branch = p.get("branch_name", "Unknown")
        branch_data[branch] += 1

    branch_labels = list(branch_data.keys())
    branch_values = list(branch_data.values())

    best_branch = max(branch_data, key=branch_data.get) if branch_data else "N/A"
    worst_branch = min(branch_data, key=branch_data.get) if branch_data else "N/A"


    # ======================
    # CUSTOMER ANALYSIS
    # ======================
    customer_data = defaultdict(int)

    for p in mongo.db.parcels.find():
        customer = p.get("customer_name", "Unknown")
        customer_data[customer] += 1

    sorted_customers = sorted(customer_data.items(), key=lambda x: x[1], reverse=True)[:5]

    customer_labels = [c[0] for c in sorted_customers]
    customer_values = [c[1] for c in sorted_customers]

    top_customer = customer_labels[0] if customer_labels else "N/A"


    # ======================
    # MONTHLY ANALYTICS (REAL DATA ONLY ✅)
    # ======================
    monthly_data = defaultdict(lambda: {
    "revenue": 0,
    "expense": 0,
    "profit": 0
})
     
    for p in mongo.db.parcels.find({
    "status": "delivered",
    "payment_status": "paid"
}):

        delivery_date = None

        for h in p.get("status_history", []):
            if h.get("status") == "delivered":
                delivery_date = h.get("timestamp")
                break

        if not delivery_date:
            continue

    # ✅ FIX HERE
        delivery_date = delivery_date.replace(tzinfo=None)

        month_key = delivery_date.strftime("%b %Y")

        cost = float(p.get("cost", 0))
        weight = p.get("weight", 0)
        delivery_type = p.get("delivery_type", "standard")

        expense = calculate_real_expense(weight, delivery_type)
        profit = cost - expense

        monthly_data[month_key]["revenue"] += cost
        monthly_data[month_key]["expense"] += expense
        monthly_data[month_key]["profit"] += profit

    sorted_months = sorted(
    monthly_data.keys(),
    key=lambda x: datetime.strptime(x, "%b %Y")
)

    months = []
    revenues = []
    expenses = []
    profits = []

    for month in sorted_months:
        months.append(month)
        revenues.append(round(monthly_data[month]["revenue"], 2))
        expenses.append(round(monthly_data[month]["expense"], 2))
        profits.append(round(monthly_data[month]["profit"], 2))


    # Convert to list (ONLY real months)
    # months = []
    # revenues = []
    # expenses = []
    # profits = []

    # for month in sorted(monthly_data.keys()):
    #     months.append(month)
    #     revenues.append(round(monthly_data[month]["revenue"], 2))
    #     expenses.append(round(monthly_data[month]["expense"], 2))
    #     profits.append(round(monthly_data[month]["profit"], 2))

    
    ratings = []

    for f in mongo.db.feedback.find():
        if f.get("rating"):
            ratings.append(int(f.get("rating")))

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0

    return render_template(
        "admin/reports.html",

        total_parcels=kpi["total_parcels"],
        delivered=kpi["delivered"],
        pending=kpi["pending"],
        cancelled=kpi["cancelled"],
        revenue=kpi["revenue"],
        profit=kpi["profit"],

        total_revenue_all=round(total_revenue_all, 2),
        total_expense_all=round(total_expense_all, 2),
        total_profit_all=round(total_profit_all, 2),
        loss=round(loss, 2),

        top_staff=top_staff,
        best_branch=best_branch,
        worst_branch=worst_branch,

        staff_labels=staff_labels,
        staff_values=staff_values,
        branch_labels=branch_labels,
        branch_values=branch_values,

        customer_labels=customer_labels,
        customer_values=customer_values,
        top_customer=top_customer,

        months=months,
        revenues=revenues,
        expenses=expenses,
        profits=profits,
       avg_rating=avg_rating
    )

@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    feedback_list = list(mongo.db.feedback.find()
                        .sort("created_at", -1)
                        .limit(100))
    
    # Only customer_id for display (template handles rest)
    for feedback in feedback_list:
        if 'customer_id' in feedback and feedback['customer_id']:
            feedback['customer_id_str'] = str(feedback['customer_id'])
        else:
            feedback['customer_id_str'] = None
    
    total_feedback = len(feedback_list)
    ratings = [int(f.get('rating', 0)) for f in feedback_list]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for feedback in feedback_list:
        rating = int(feedback.get('rating', 0))
        if rating in rating_dist:
            rating_dist[rating] += 1
    
    return render_template('admin/feedback.html',
                         feedback_list=feedback_list,
                         total_feedback=total_feedback,
                         avg_rating=avg_rating,
                         rating_dist=rating_dist)

@app.route('/staff/dashboard')
@staff_required
def staff_dashboard():
    staff = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})

    # parcels = list(mongo.db.parcels.find({
    #     "staff_id": staff["_id"]   # only assigned parcels
    # }).sort("updated_at", -1))
    parcels = list(mongo.db.parcels.find({
        "staff_id": staff["_id"],
        "branch_id": staff.get("branch_id")
        }).sort("updated_at", -1)) 
    total_assigned = len(parcels)

    pending_count = mongo.db.parcels.count_documents({
        "staff_id": staff["_id"],
        "status": {"$ne": "delivered"}
    })

    today = datetime.now().date()

    delivered_today = mongo.db.parcels.count_documents({
        "staff_id": staff["_id"],
        "status": "delivered",
        "updated_at": {
            "$gte": datetime(today.year, today.month, today.day),
            "$lt": datetime(today.year, today.month, today.day, 23, 59, 59)
        }
    })
    notification_count = mongo.db.notifications.count_documents({
        "user_id": staff["_id"],
        "read": False
    })
    return render_template(
        "staff/dashboard.html",
        staff=staff,
        parcels=parcels,
        total_assigned=total_assigned,
        pending_count=pending_count,
        delivered_today=delivered_today,
    notification_count=notification_count
    )

@app.route('/staff/notifications/read/<notification_id>', methods=['POST'])
@staff_required
def mark_notification_read(notification_id):
    mongo.db.notifications.update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"read": True}}
    )
    return jsonify({"success": True})
@app.route('/staff/notifications')
@staff_required
def staff_notifications():
    staff_id = session['user_id']

    notifications = list(
        mongo.db.notifications.find({
            "user_id": ObjectId(staff_id)
        }).sort("created_at", -1)
    )

    # Mark as read
    mongo.db.notifications.update_many(
        {"user_id": ObjectId(staff_id), "read": False},
        {"$set": {"read": True}}
    )

    return render_template('staff/notifications.html', notifications=notifications)

@app.route('/staff/parcel/<tracking_id>')
@staff_required
def staff_parcel_details(tracking_id):
    staff_id = ObjectId(session['user_id'])
    staff = mongo.db.users.find_one({"_id": staff_id})

    parcel = mongo.db.parcels.find_one({
        "tracking_id": tracking_id,
        "staff_id": staff_id,
        "branch_id": staff["branch_id"]
    })

    if not parcel:
        flash("Parcel not assigned to you", "danger")
        return redirect(url_for("staff_dashboard"))

    return render_template(
        "staff/parcel_details.html",
        parcel=parcel
    )

@app.route('/staff/parcel/update/<tracking_id>', methods=['POST'])
@staff_required
def staff_update_parcel(tracking_id):
    staff_id = ObjectId(session['user_id'])
    new_status = request.form.get("status")

    staff = mongo.db.users.find_one({"_id": staff_id})

    parcel = mongo.db.parcels.find_one({
        "tracking_id": tracking_id,
        "staff_id": staff_id,
        "branch_id": staff["branch_id"]
    })

    if not parcel:
        flash("Parcel not assigned to you", "danger")
        return redirect(url_for("staff_dashboard"))

    if parcel["status"] == STATUS_DELIVERED:
        flash("Parcel already delivered. Status cannot be changed.", "info")
        return redirect(url_for("staff_dashboard"))

    allowed_next = STATUS_FLOW.get(parcel["status"], [])

    if new_status not in allowed_next:
        flash("Invalid status transition", "danger")
        return redirect(url_for("staff_parcel_details", tracking_id=tracking_id))

    mongo.db.parcels.update_one(
        {"_id": parcel["_id"]},
        {
            "$set": {
                "status": new_status,
                "updated_at": datetime.now(),
                "delivered_at": datetime.now() if new_status == STATUS_DELIVERED else None
            },
            "$push": {
                "status_history": {
                    "status": new_status,
                    "timestamp": datetime.now(),
                    "updated_by": staff["name"]
                }
            }
        }
    )

    create_notification(
        parcel["customer_id"],
        "Parcel Status Updated",
        f"Your parcel {tracking_id} is now {new_status.replace('_',' ').title()}",
        "status_update"
    )

    flash("Status updated successfully", "success")
    return redirect(url_for("staff_dashboard"))


@app.route('/staff/mark_paid/<tracking_id>', methods=['POST'])
@staff_required
def staff_mark_paid(tracking_id):
    staff_id = ObjectId(session['user_id'])

    parcel = mongo.db.parcels.find_one({
        "tracking_id": tracking_id,
        "staff_id": staff_id
    })

    if not parcel:
        flash("Parcel not found or not assigned to you", "danger")
        return redirect(url_for('staff_dashboard'))

    if parcel["status"] != "delivered":
        flash("Payment can be marked only after delivery.", "danger")
        return redirect(url_for('staff_parcel_details', tracking_id=tracking_id))

    if parcel.get("payment_status") == "paid":
        flash("Payment already collected.", "info")
        return redirect(url_for('staff_parcel_details', tracking_id=tracking_id))

    mongo.db.parcels.update_one(
        {"_id": parcel["_id"]},
        {"$set": {
            "payment_status": "paid",
            "payment_collected_at": datetime.now()
        }}
    )

    flash("💰 Payment marked as collected successfully!", "success")
    return redirect(url_for('staff_parcel_details', tracking_id=tracking_id))

@app.route('/staff/qr/<tracking_id>')
@staff_required
def staff_generate_qr(tracking_id):
    qr_data = url_for(
        'staff_parcel_details',
        tracking_id=tracking_id,
        _external=True
    )

    qr = qrcode.make(qr_data)
    buf = BytesIO()
    qr.save(buf)
    buf.seek(0)

    return send_file(buf, mimetype='image/png')

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
def ensure_default_branches():
    default_branches = [
     {  "name": "Mumbai Hub",
        "city": "Mumbai",
        "address": "Mumbai Central Warehouse",
        "phone": "9123456780"
    },
    {
        "name": "Chennai Hub",
        "city": "Chennai",
        "address": "Chennai Logistics Hub",
        "phone": "9876543210"
    }

    ]

    for branch in default_branches:
        existing = mongo.db.branches.find_one({"name": branch["name"]})
        if not existing:
            mongo.db.branches.insert_one({
                "name": branch["name"],
                "city": branch["city"],
                "address": branch["address"],
                "status": "active",
                "created_at": datetime.now()
            })
            print(f"✅ Branch created: {branch['name']}")

# ========== MAIN EXECUTION ==========


if __name__ == '__main__':
     with app.app_context():
         init_db()
         ensure_default_branches()

        # Optional indexes (recommended)
         mongo.db.notifications.create_index([("user_id", 1), ("read", 1)])
         mongo.db.parcels.create_index([("tracking_id", 1)], unique=True)
         mongo.db.users.create_index([("email", 1)], unique=True)
         mongo.db.parcels.create_index([("status", 1)])

         print("✅ Database initialized")

print("🚀 Real-time SocketIO server running on http://localhost:5000")
socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)




