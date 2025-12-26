# from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
# from flask_pymongo import PyMongo
# from bson.objectid import ObjectId
# from datetime import datetime, timedelta
# import bcrypt
# import os
# from dotenv import load_dotenv
# import re

# load_dotenv()

# app = Flask(__name__)
# app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
# app.config["MONGO_URI"] = os.getenv("MONGO_URI")
# app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)  # Remember me functionality

# mongo = PyMongo(app)

# # ========== HELPER FUNCTIONS ==========

# # Initialize database with default admin
# def init_db():
#     if not mongo.db.users.find_one({"email": "admin@parcel.com"}):
#         hashed_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
#         mongo.db.users.insert_one({
#             "name": "Admin",
#             "email": "admin@parcel.com",
#             "password": hashed_password,
#             "phone": "0000000000",
#             "role": "admin",
#             "created_at": datetime.now(),
#             "status": "active"
#         })
#         print("Default admin created: admin@parcel.com / admin123")

# # Generate tracking ID
# def generate_tracking_id():
#     import random
#     import string
#     return 'TRK' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

# # Calculate delivery cost
# def calculate_cost(weight, parcel_type, delivery_type):
#     base_cost = 50
#     weight_cost = float(weight) * 10
    
#     type_multiplier = {
#         'document': 1.0,
#         'box': 1.2,
#         'fragile': 1.5,
#         'electronics': 1.3
#     }
    
#     delivery_multiplier = {
#         'standard': 1.0,
#         'express': 1.5
#     }
    
#     cost = base_cost + weight_cost
#     cost *= type_multiplier.get(parcel_type.lower(), 1.0)
#     cost *= delivery_multiplier.get(delivery_type.lower(), 1.0)
    
#     return round(cost, 2)

# # Helper function to create notifications
# def create_notification(user_id, title, message, notification_type):
#     """
#     Create a notification for a user
#     """
#     try:
#         # Ensure user_id is string
#         if isinstance(user_id, ObjectId):
#             user_id = str(user_id)
        
#         notification_data = {
#             "user_id": ObjectId(user_id),
#             "title": title,
#             "message": message,
#             "type": notification_type,
#             "read": False,
#             "created_at": datetime.now()
#         }
#         return mongo.db.notifications.insert_one(notification_data)
#     except Exception as e:
#         print(f"Error creating notification: {e}")
#         return None

# # Helper function to get next status
# def get_next_status(current_status):
#     """
#     Get the next logical status in the parcel flow
#     """
#     status_flow = ['booked', 'picked', 'in transit', 'out for delivery', 'delivered']
#     try:
#         current_index = status_flow.index(current_status)
#         if current_index < len(status_flow) - 1:
#             return status_flow[current_index + 1]
#     except ValueError:
#         pass
#     return None

# # ========== ROUTES ==========

# @app.route('/')
# def index():
#     return render_template('index.html')

# @app.route('/about')
# def about():
#     return render_template('about.html')

# @app.route('/track', methods=['GET', 'POST'])
# def track():
#     if request.method == 'POST':
#         tracking_id = request.form.get('tracking_id')
#         parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
#         if parcel:
#             return render_template('track.html', parcel=parcel, found=True)
#         else:
#             flash('Tracking ID not found', 'danger')
#     return render_template('track.html', found=False)

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if 'user_id' in session:
#         role = session.get('role')
#         if role == 'admin':
#             return redirect(url_for('admin_dashboard'))
#         elif role == 'staff':
#             return redirect(url_for('staff_dashboard'))
#         elif role == 'customer':
#             return redirect(url_for('customer_dashboard'))
    
#     if request.method == 'POST':
#         email = request.form.get('email')
#         password = request.form.get('password')
#         remember = request.form.get('remember')
        
#         user = mongo.db.users.find_one({"email": email})
        
#         if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
#             session['user_id'] = str(user['_id'])
#             session['email'] = user['email']
#             session['name'] = user['name']
#             session['role'] = user['role']
            
#             if remember:
#                 session.permanent = True
            
#             if user['role'] == 'admin':
#                 return redirect(url_for('admin_dashboard'))
#             elif user['role'] == 'staff':
#                 return redirect(url_for('staff_dashboard'))
#             elif user['role'] == 'customer':
#                 return redirect(url_for('customer_dashboard'))
#         else:
#             flash('Invalid email or password', 'danger')
    
#     return render_template('login.html')

# @app.route('/signup', methods=['GET', 'POST'])
# def signup():
#     if request.method == 'POST':
#         name = request.form.get('name')
#         email = request.form.get('email')
#         phone = request.form.get('phone')
#         password = request.form.get('password')
        
#         # Check if user exists
#         if mongo.db.users.find_one({"email": email}):
#             flash('Email already registered', 'danger')
#             return redirect(url_for('signup'))
        
#         # Validate password
#         if len(password) < 6:
#             flash('Password must be at least 6 characters', 'danger')
#             return redirect(url_for('signup'))
        
#         # Hash password
#         hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
#         # Create user
#         user_data = {
#             "name": name,
#             "email": email,
#             "phone": phone,
#             "password": hashed_password,
#             "role": "customer",
#             "created_at": datetime.now(),
#             "status": "active",
#             "address": ""
#         }
        
#         mongo.db.users.insert_one(user_data)
#         flash('Registration successful! Please login.', 'success')
#         return redirect(url_for('login'))
    
#     return render_template('signup.html')

# @app.route('/logout')
# def logout():
#     session.clear()
#     flash('Logged out successfully', 'success')
#     return redirect(url_for('index'))

# # ========== CUSTOMER ROUTES ==========

# @app.route('/customer/dashboard')
# def customer_dashboard():
#     if 'user_id' not in session or session.get('role') != 'customer':
#         return redirect(url_for('login'))
    
#     customer_id = session['user_id']
#     parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)}).sort("created_at", -1))
    
#     # Count notifications
#     notification_count = mongo.db.notifications.count_documents({
#         "user_id": ObjectId(customer_id),
#         "read": False
#     })
    
#     return render_template('customer/dashboard.html', 
#                          parcels=parcels[:5], 
#                          notification_count=notification_count)

# @app.route('/customer/book', methods=['GET', 'POST'])
# def book_parcel():
#     if 'user_id' not in session or session.get('role') != 'customer':
#         return redirect(url_for('login'))
    
#     customer_id = session['user_id']
#     customer = mongo.db.users.find_one({"_id": ObjectId(customer_id)})
    
#     if request.method == 'POST':
#         # Get form data
#         sender_name = request.form.get('sender_name')
#         sender_phone = request.form.get('sender_phone')
#         sender_address = request.form.get('sender_address')
#         sender_pincode = request.form.get('sender_pincode')
        
#         receiver_name = request.form.get('receiver_name')
#         receiver_phone = request.form.get('receiver_phone')
#         receiver_address = request.form.get('receiver_address')
#         receiver_pincode = request.form.get('receiver_pincode')
        
#         weight = request.form.get('weight')
#         parcel_type = request.form.get('parcel_type')
#         description = request.form.get('description')
#         delivery_type = request.form.get('delivery_type')
#         pickup_date = request.form.get('pickup_date')
        
#         # Calculate cost
#         cost = calculate_cost(weight, parcel_type, delivery_type)
        
#         # Create parcel
#         parcel_data = {
#             "tracking_id": generate_tracking_id(),
#             "customer_id": ObjectId(customer_id),
#             "customer_name": customer['name'],
#             "customer_email": customer['email'],
#             "customer_phone": sender_phone,  # Use form phone
#             "pickup_address": sender_address,
#             "pickup_pincode": sender_pincode,
#             "sender_name": sender_name,
#             "sender_phone": sender_phone,
#             "sender_address": sender_address,
#             "sender_pincode": sender_pincode,
#             "receiver_name": receiver_name,
#             "receiver_phone": receiver_phone,
#             "receiver_address": receiver_address,
#             "receiver_pincode": receiver_pincode,
#             "weight": float(weight),
#             "parcel_type": parcel_type,
#             "description": description,
#             "delivery_type": delivery_type,
#             "pickup_date": datetime.strptime(pickup_date, '%Y-%m-%d'),
#             "cost": cost,
#             "payment_mode": "cod",
#             "payment_status": "pending",
#             "status": "booked",
#             "status_history": [{
#                 "status": "booked",
#                 "timestamp": datetime.now(),
#                 "note": "Parcel booked successfully"
#             }],
#             "created_at": datetime.now(),
#             "updated_at": datetime.now(),
#             "staff_id": None,
#             "staff_name": None,
#             "delivered_at": None
#         }
        
#         mongo.db.parcels.insert_one(parcel_data)
        
#         # Create notification
#         create_notification(
#             customer_id,
#             "Parcel Booked Successfully",
#             f"Your parcel has been booked. Tracking ID: {parcel_data['tracking_id']}. Cost: ₹{cost}",
#             "booking"
#         )
        
#         flash('Parcel booked successfully!', 'success')
#         return redirect(url_for('customer_parcels'))
    
#     return render_template('customer/book_parcel.html', customer=customer)

# @app.route('/customer/parcels')
# def customer_parcels():
#     if 'user_id' not in session or session.get('role') != 'customer':
#         return redirect(url_for('login'))
    
#     customer_id = session['user_id']
#     parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)}).sort("created_at", -1))
    
#     return render_template('customer/my_parcels.html', parcels=parcels)

# # @app.route('/customer/track')
# # def customer_track():
# #     if 'user_id' not in session or session.get('role') != 'customer':
# #         return redirect(url_for('login'))
    
# #     customer_id = session['user_id']
# #     parcels = list(mongo.db.parcels.find({"customer_id": ObjectId(customer_id)},
# #                                         {"tracking_id": 1, "status": 1, "created_at": 1, "updated_at": 1, "receiver_name": 1})
# #                   .sort("created_at", -1))
    
# #     return render_template('customer/track.html', parcels=parcels)
# @app.route('/customer/track')
# def customer_track():
#     if 'user_id' not in session or session.get('role') != 'customer':
#         return redirect(url_for('login'))
    
#     customer_id = session['user_id']
#     # Fetch all necessary fields including created_at
#     parcels = list(mongo.db.parcels.find(
#         {"customer_id": ObjectId(customer_id)},
#         {
#             "tracking_id": 1,
#             "status": 1,
#             "created_at": 1,
#             "updated_at": 1,
#             "receiver_name": 1,
#             "receiver_address": 1
#         }
#     ).sort("created_at", -1))
    
#     return render_template('customer/track.html', parcels=parcels)

# # @app.route('/customer/notifications')
# # def customer_notifications():
# #     if 'user_id' not in session or session.get('role') != 'customer':
# #         return redirect(url_for('login'))
    
# #     customer_id = session['user_id']
# #     notifications = list(mongo.db.notifications.find({"user_id": ObjectId(customer_id)})
# #                         .sort("created_at", -1))
    
# #     # Mark as read
# #     mongo.db.notifications.update_many(
# #         {"user_id": ObjectId(customer_id), "read": False},
# #         {"$set": {"read": True}}
# #     )
    
# #     return render_template('customer/notifications.html', notifications=notifications)

# @app.route('/customer/profile', methods=['GET', 'POST'])
# def customer_profile():
#     if 'user_id' not in session or session.get('role') != 'customer':
#         return redirect(url_for('login'))
    
#     customer_id = session['user_id']
#     customer = mongo.db.users.find_one({"_id": ObjectId(customer_id)})
    
#     if request.method == 'POST':
#         name = request.form.get('name')
#         phone = request.form.get('phone')
#         address = request.form.get('address')
        
#         mongo.db.users.update_one(
#             {"_id": ObjectId(customer_id)},
#             {"$set": {
#                 "name": name,
#                 "phone": phone,
#                 "address": address,
#                 "updated_at": datetime.now()
#             }}
#         )
        
#         session['name'] = name
#         flash('Profile updated successfully', 'success')
#         return redirect(url_for('customer_profile'))
    
#     return render_template('customer/profile.html', customer=customer)

# @app.route('/cancel_parcel/<tracking_id>')
# def cancel_parcel(tracking_id):
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
    
#     parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
    
#     if not parcel:
#         flash('Parcel not found', 'danger')
#         return redirect(url_for('customer_parcels'))
    
#     # Check if parcel is still in booked status
#     if parcel['status'] != 'booked':
#         flash('Cannot cancel parcel after it has been picked up', 'danger')
#         return redirect(url_for('customer_parcels'))
    
#     # Update status
#     mongo.db.parcels.update_one(
#         {"tracking_id": tracking_id},
#         {"$set": {
#             "status": "cancelled",
#             "updated_at": datetime.now()
#         }}
#     )
    
#     flash('Parcel cancelled successfully', 'success')
#     return redirect(url_for('customer_parcels'))

# # ========== ADMIN ROUTES ==========

# @app.route('/admin/dashboard')
# def admin_dashboard():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     # Get counts
#     total_customers = mongo.db.users.count_documents({"role": "customer", "status": "active"})
#     total_staff = mongo.db.users.count_documents({"role": "staff", "status": "active"})
#     total_parcels = mongo.db.parcels.count_documents({})
    
#     # Get status counts
#     status_counts = {}
#     statuses = ['booked', 'picked', 'in transit', 'out for delivery', 'delivered', 'cancelled']
#     for status in statuses:
#         status_counts[status] = mongo.db.parcels.count_documents({"status": status})
    
#     # Calculate revenue
#     delivered_parcels = mongo.db.parcels.find({"status": "delivered"})
#     total_revenue = sum(parcel['cost'] for parcel in delivered_parcels)
    
#     # Get recent parcels
#     recent_parcels = list(mongo.db.parcels.find().sort("created_at", -1).limit(10))
    
#     # Get staff for assignment
#     staff_list = list(mongo.db.users.find({"role": "staff", "status": "active"}))
    
#     return render_template('admin/dashboard.html',
#                          total_customers=total_customers,
#                          total_staff=total_staff,
#                          total_parcels=total_parcels,
#                          status_counts=status_counts,
#                          total_revenue=total_revenue,
#                          recent_parcels=recent_parcels,
#                          staff_list=staff_list)

# @app.route('/admin/staff', methods=['GET', 'POST'])
# def admin_staff():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     if request.method == 'POST':
#         name = request.form.get('name')
#         email = request.form.get('email')
#         phone = request.form.get('phone')
#         password = request.form.get('password')
        
#         # Check if staff exists
#         if mongo.db.users.find_one({"email": email}):
#             flash('Staff with this email already exists', 'danger')
#             return redirect(url_for('admin_staff'))
        
#         # Validate password
#         if len(password) < 6:
#             flash('Password must be at least 6 characters', 'danger')
#             return redirect(url_for('admin_staff'))
        
#         # Hash password
#         hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
#         # Create staff
#         staff_data = {
#             "name": name,
#             "email": email,
#             "phone": phone,
#             "password": hashed_password,
#             "role": "staff",
#             "created_at": datetime.now(),
#             "status": "active"
#         }
        
#         mongo.db.users.insert_one(staff_data)
#         flash('Staff added successfully', 'success')
#         return redirect(url_for('admin_staff'))
    
#     # Get all staff
#     staff_list = list(mongo.db.users.find({"role": "staff"}))
#     return render_template('admin/staff.html', staff_list=staff_list)

# @app.route('/admin/deactivate_staff/<staff_id>')
# def deactivate_staff(staff_id):
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     mongo.db.users.update_one(
#         {"_id": ObjectId(staff_id)},
#         {"$set": {"status": "inactive"}}
#     )
#     flash('Staff deactivated', 'success')
#     return redirect(url_for('admin_staff'))

# @app.route('/admin/activate_staff/<staff_id>')
# def activate_staff(staff_id):
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     mongo.db.users.update_one(
#         {"_id": ObjectId(staff_id)},
#         {"$set": {"status": "active"}}
#     )
#     flash('Staff activated', 'success')
#     return redirect(url_for('admin_staff'))

# @app.route('/admin/customers')
# def admin_customers():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     customers = list(mongo.db.users.find({"role": "customer"}).sort("created_at", -1))
#     return render_template('admin/customers.html', customers=customers)

# @app.route('/admin/parcels')
# def admin_parcels():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     parcels = list(mongo.db.parcels.find().sort("created_at", -1))
#     staff_list = list(mongo.db.users.find({"role": "staff", "status": "active"}))
#     return render_template('admin/parcels.html', parcels=parcels, staff_list=staff_list)

# @app.route('/admin/assign_parcel', methods=['POST'])
# def assign_parcel():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     tracking_id = request.form.get('tracking_id')
#     staff_id = request.form.get('staff_id')
    
#     parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
#     staff = mongo.db.users.find_one({"_id": ObjectId(staff_id)})
    
#     if not parcel or not staff:
#         flash('Invalid parcel or staff selection', 'danger')
#         return redirect(url_for('admin_parcels'))
    
#     # Update parcel
#     mongo.db.parcels.update_one(
#         {"tracking_id": tracking_id},
#         {
#             "$set": {
#                 "staff_id": ObjectId(staff_id),
#                 "staff_name": staff['name'],
#                 "updated_at": datetime.now()
#             }
#         }
#     )
    
#     # Create notification for staff
#     create_notification(
#         staff_id,
#         "New Parcel Assigned",
#         f"Parcel {tracking_id} has been assigned to you. Customer: {parcel['customer_name']}",
#         "assignment"
#     )
    
#     # Create notification for customer
#     create_notification(
#         str(parcel['customer_id']),
#         "Parcel Assigned to Rider",
#         f"Your parcel {tracking_id} has been assigned to delivery rider {staff['name']}",
#         "assignment"
#     )
    
#     flash(f'Parcel assigned to {staff["name"]}', 'success')
#     return redirect(url_for('admin_parcels'))

# @app.route('/admin/reports')
# def admin_reports():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     # Monthly statistics
#     current_month = datetime.now().month
#     current_year = datetime.now().year
    
#     # Parcels this month
#     parcels_this_month = mongo.db.parcels.count_documents({
#         "created_at": {
#             "$gte": datetime(current_year, current_month, 1),
#             "$lt": datetime(current_year, current_month + 1, 1) if current_month < 12 else datetime(current_year + 1, 1, 1)
#         }
#     })
    
#     # Delivered parcels
#     delivered_parcels = mongo.db.parcels.count_documents({"status": "delivered"})
    
#     # Pending parcels
#     pending_parcels = mongo.db.parcels.count_documents({
#         "status": {"$in": ["booked", "picked", "in transit", "out for delivery"]}
#     })
    
#     # Cancelled parcels
#     cancelled_parcels = mongo.db.parcels.count_documents({"status": "cancelled"})
    
#     # Cash collected
#     delivered_cod_parcels = mongo.db.parcels.find({
#         "status": "delivered",
#         "payment_mode": "cod",
#         "payment_status": "paid"
#     })
#     cash_collected = sum(parcel['cost'] for parcel in delivered_cod_parcels)
    
#     return render_template('admin/reports.html',
#                          parcels_this_month=parcels_this_month,
#                          delivered_parcels=delivered_parcels,
#                          pending_parcels=pending_parcels,
#                          cancelled_parcels=cancelled_parcels,
#                          cash_collected=cash_collected)

# @app.route('/admin/track')
# def admin_track():
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
    
#     return render_template('admin/track_parcel.html')

# # ========== STAFF ROUTES ==========

# @app.route('/staff/dashboard')
# def staff_dashboard():
#     if 'user_id' not in session or session.get('role') != 'staff':
#         return redirect(url_for('login'))
    
#     staff_id = session['user_id']
    
#     # Get assigned parcels
#     assigned_parcels = list(mongo.db.parcels.find({"staff_id": ObjectId(staff_id)}).sort("created_at", -1))
    
#     # Get counts
#     total_assigned = len(assigned_parcels)
#     pending_delivery = len([p for p in assigned_parcels if p['status'] != 'delivered'])
#     delivered = len([p for p in assigned_parcels if p['status'] == 'delivered'])
    
#     # Calculate cash collected
#     cash_collected = sum(p['cost'] for p in assigned_parcels 
#                         if p['status'] == 'delivered' and p['payment_mode'] == 'cod' and p['payment_status'] == 'paid')
    
#     return render_template('staff/dashboard.html',
#                          assigned_parcels=assigned_parcels[:5],
#                          total_assigned=total_assigned,
#                          pending_delivery=pending_delivery,
#                          delivered=delivered,
#                          cash_collected=cash_collected)

# @app.route('/staff/orders')
# def staff_orders():
#     if 'user_id' not in session or session.get('role') != 'staff':
#         return redirect(url_for('login'))
    
#     staff_id = session['user_id']
#     parcels = list(mongo.db.parcels.find({"staff_id": ObjectId(staff_id)}).sort("created_at", -1))
    
#     return render_template('staff/orders.html', parcels=parcels)

# @app.route('/update_parcel_status/<tracking_id>/<new_status>')
# def update_parcel_status(tracking_id, new_status):
#     if 'user_id' not in session or session.get('role') != 'staff':
#         flash('Unauthorized access', 'danger')
#         return redirect(url_for('login'))
    
#     # Validate status
#     valid_statuses = ['picked', 'in transit', 'out for delivery', 'delivered']
#     if new_status not in valid_statuses:
#         flash('Invalid status', 'danger')
#         return redirect(url_for('staff_orders'))
    
#     parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
#     if not parcel:
#         flash('Parcel not found', 'danger')
#         return redirect(url_for('staff_orders'))
    
#     # Update parcel status
#     status_update = {
#         "status": new_status,
#         "updated_at": datetime.now()
#     }
    
#     if new_status == 'delivered':
#         status_update['delivered_at'] = datetime.now()
    
#     # Add to status history
#     status_history_entry = {
#         "status": new_status,
#         "timestamp": datetime.now(),
#         "updated_by": session['name']
#     }
    
#     mongo.db.parcels.update_one(
#         {"tracking_id": tracking_id},
#         {
#             "$set": status_update,
#             "$push": {"status_history": status_history_entry}
#         }
#     )
    
#     # Create notification for customer
#     status_messages = {
#         "picked": "Your parcel has been picked up by our rider",
#         "in transit": "Your parcel is in transit to the destination",
#         "out for delivery": "Your parcel is out for delivery",
#         "delivered": "Your parcel has been delivered successfully"
#     }
    
#     if new_status in status_messages:
#         create_notification(
#             str(parcel['customer_id']),
#             f"Parcel Status Updated - {tracking_id}",
#             status_messages[new_status],
#             "status_update"
#         )
    
#     flash(f'Parcel status updated to {new_status}', 'success')
#     return redirect(url_for('staff_orders'))

# @app.route('/staff/parcel_details/<tracking_id>')
# def staff_parcel_details(tracking_id):
#     if 'user_id' not in session or session.get('role') != 'staff':
#         return redirect(url_for('login'))
    
#     parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
#     if not parcel:
#         flash('Parcel not found', 'danger')
#         return redirect(url_for('staff_orders'))
    
#     return render_template('staff/parcel_details.html', parcel=parcel)

# @app.route('/staff/update_payment')
# def staff_update_payment():
#     if 'user_id' not in session or session.get('role') != 'staff':
#         return redirect(url_for('login'))
    
#     staff_id = session['user_id']
    
#     # Get parcels that need payment update
#     parcels = list(mongo.db.parcels.find({
#         "staff_id": ObjectId(staff_id),
#         "status": "delivered",
#         "payment_mode": "cod",
#         "payment_status": "pending"
#     }).sort("created_at", -1))
    
#     return render_template('staff/update_payment.html', parcels=parcels)

# @app.route('/update_payment/<tracking_id>')
# def update_payment(tracking_id):
#     if 'user_id' not in session or session.get('role') != 'staff':
#         flash('Unauthorized access', 'danger')
#         return redirect(url_for('login'))
    
#     parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
#     if not parcel:
#         flash('Parcel not found', 'danger')
#         return redirect(url_for('staff_orders'))
    
#     # Update payment status
#     mongo.db.parcels.update_one(
#         {"tracking_id": tracking_id},
#         {"$set": {
#             "payment_status": "paid",
#             "updated_at": datetime.now()
#         }}
#     )
    
#     # Create notification for customer
#     create_notification(
#         str(parcel['customer_id']),
#         "Payment Received",
#         f"Cash on Delivery payment received for parcel {tracking_id}",
#         "payment"
#     )
    
#     # Create notification for admin
#     admin = mongo.db.users.find_one({"role": "admin"})
#     if admin:
#         create_notification(
#             str(admin['_id']),
#             "Payment Collected",
#             f"COD payment of ₹{parcel['cost']} collected for parcel {tracking_id}",
#             "payment"
#         )
    
#     flash('Payment marked as received', 'success')
#     return redirect(url_for('staff_orders'))

# # ========== API ENDPOINTS ==========

# @app.route('/api/track/<tracking_id>')
# def api_track(tracking_id):
#     parcel = mongo.db.parcels.find_one({"tracking_id": tracking_id})
#     if parcel:
#         # Convert ObjectId to string for JSON serialization
#         parcel['_id'] = str(parcel['_id'])
#         if 'customer_id' in parcel:
#             parcel['customer_id'] = str(parcel['customer_id'])
#         if 'staff_id' in parcel and parcel['staff_id']:
#             parcel['staff_id'] = str(parcel['staff_id'])
#         return jsonify(parcel)
#     else:
#         return jsonify({"error": "Tracking ID not found"}), 404

# # ========== CONTEXT PROCESSORS & ERROR HANDLERS ==========

# @app.context_processor
# def utility_processor():
#     def format_date(date_obj):
#         if date_obj:
#             return date_obj.strftime('%Y-%m-%d %H:%M')
#         return ''
#     return dict(format_date=format_date, now=datetime.now)

# # Simple error handlers that redirect to home
# @app.errorhandler(404)
# def not_found_error(error):
#     flash('Page not found', 'warning')
#     return redirect(url_for('index'))

# @app.errorhandler(500)
# def internal_error(error):
#     flash('Server error occurred', 'danger')
#     return redirect(url_for('index'))

# # ========== MAIN EXECUTION ==========

# if __name__ == '__main__':
#     with app.app_context():
#         init_db()
#         # Create database indexes
#         mongo.db.notifications.create_index([("user_id", 1), ("read", 1)])
#         mongo.db.parcels.create_index([("tracking_id", 1)], unique=True)
#         mongo.db.users.create_index([("email", 1)], unique=True)
#         mongo.db.parcels.create_index([("status", 1)])
#         mongo.db.parcels.create_index([("staff_id", 1)])
#         print("Database initialized and indexes created")
    
#     app.run(debug=True, port=5000, host='0.0.0.0')



# <!DOCTYPE html>
# <html lang="en">
# <head>
#     <meta charset="UTF-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <title>{% block title %}Courier Management System{% endblock %}</title>
#     <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
#     <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
# </head>
# <body>
#     <!-- Flash Messages -->
#     {% with messages = get_flashed_messages(with_categories=true) %}
#         {% if messages %}
#             <div class="container">
#                 {% for category, message in messages %}
#                     <div class="alert alert-{{ category }}">{{ message }}</div>
#                 {% endfor %}
#             </div>
#         {% endif %}
#     {% endwith %}

#     {% block content %}{% endblock %}

#     <script src="{{ url_for('static', filename='js/main.js') }}"></script>
#     {% block scripts %}{% endblock %}
# </body>
# </html>

# dashboard.html
# {% extends "layout.html" %}

# {% block title %}Customer Dashboard{% endblock %}

# {% block content %}
# <div class="dashboard">
#     <!-- Sidebar -->
#     <aside class="sidebar">
#         <div class="sidebar-header">
#             <h2>Customer Panel</h2>
#             <p>Welcome, {{ session.name }}</p>
#         </div>
#         <nav class="sidebar-nav">
#             <ul>
#                 <li><a href="{{ url_for('customer_dashboard') }}" class="active">Dashboard</a></li>
#                 <li><a href="{{ url_for('book_parcel') }}">Book New Parcel</a></li>
#                 <li><a href="{{ url_for('customer_parcels') }}">My Parcels</a></li>
#                 <li><a href="{{ url_for('customer_track') }}">Track Parcel</a></li>
#                 <li>
#                     <a href="{{ url_for('customer_notifications') }}">
#                         Notifications 
#                         {% if notification_count > 0 %}
#                         <span style="background: red; color: white; padding: 2px 6px; border-radius: 50%; font-size: 0.8rem;">
#                             {{ notification_count }}
#                         </span>
#                         {% endif %}
#                     </a>
#                 </li>
#                 <li><a href="{{ url_for('customer_profile') }}">Profile</a></li>
#                 <li><a href="{{ url_for('logout') }}">Logout</a></li>
#             </ul>
#         </nav>
#     </aside>

#     <!-- Main Content -->
#     <main class="main-content">
#         <h1>Dashboard</h1>
        
#         <!-- Stats Cards -->
#         <div class="stats-cards">
#             <div class="stat-card">
#                 <h3>Total Parcels</h3>
#                 <div class="number">{{ parcels|length }}</div>
#             </div>
#             <div class="stat-card">
#                 <h3>Pending Delivery</h3>
#                 <div class="number">
#                     {{ parcels|selectattr('status', 'equalto', 'booked')|list|length + 
#                        parcels|selectattr('status', 'equalto', 'picked')|list|length + 
#                        parcels|selectattr('status', 'equalto', 'in transit')|list|length + 
#                        parcels|selectattr('status', 'equalto', 'out for delivery')|list|length }}
#                 </div>
#             </div>
#             <div class="stat-card">
#                 <h3>Delivered</h3>
#                 <div class="number">
#                     {{ parcels|selectattr('status', 'equalto', 'delivered')|list|length }}
#                 </div>
#             </div>
#             <div class="stat-card">
#                 <h3>Cancelled</h3>
#                 <div class="number">
#                     {{ parcels|selectattr('status', 'equalto', 'cancelled')|list|length }}
#                 </div>
#             </div>
#         </div>

#         <!-- Recent Parcels -->
#         <div style="margin-top: 2rem;">
#             <h2>Recent Parcels</h2>
#             {% if parcels %}
#             <div class="table-container">
#                 <table class="table">
#                     <thead>
#                         <tr>
#                             <th>Tracking ID</th>
#                             <th>Receiver</th>
#                             <th>Status</th>
#                             <th>Date</th>
#                             <th>Actions</th>
#                         </tr>
#                     </thead>
#                     <tbody>
#                         {% for parcel in parcels[:5] %}
#                         <tr>
#                             <td>{{ parcel.tracking_id }}</td>
#                             <td>{{ parcel.receiver_name }}</td>
#                             <td>
#                                 <span class="status-badge status-{{ parcel.status }}">
#                                     {{ parcel.status|upper }}
#                                 </span>
#                             </td>
#                             <td>{{ parcel.created_at.strftime('%Y-%m-%d') }}</td>
#                             <td>
#                                 <a href="/track?tracking_id={{ parcel.tracking_id }}" 
#                                    class="btn" style="padding: 0.3rem 0.8rem;">Track</a>
#                                 {% if parcel.status == 'booked' %}
#                                 <a href="/cancel_parcel/{{ parcel.tracking_id }}" 
#                                    class="btn btn-danger" style="padding: 0.3rem 0.8rem;"
#                                    onclick="return confirm('Are you sure you want to cancel this parcel?')">
#                                     Cancel
#                                 </a>
#                                 {% endif %}
#                             </td>
#                         </tr>
#                         {% endfor %}
#                     </tbody>
#                 </table>
#             </div>
#             {% else %}
#             <div style="text-align: center; padding: 2rem; background: white; border-radius: 10px;">
#                 <p>No parcels found. <a href="{{ url_for('book_parcel') }}">Book your first parcel!</a></p>
#             </div>
#             {% endif %}
#         </div>

#         <!-- Quick Actions -->
#         <div style="margin-top: 2rem;">
#             <h2>Quick Actions</h2>
#             <div style="display: flex; gap: 1rem; margin-top: 1rem;">
#                 <a href="{{ url_for('book_parcel') }}" class="btn btn-success">
#                     <i class="fas fa-plus"></i> Book New Parcel
#                 </a>
#                 <a href="{{ url_for('customer_track') }}" class="btn">
#                     <i class="fas fa-search"></i> Track Parcel
#                 </a>
#                 <a href="{{ url_for('customer_notifications') }}" class="btn">
#                     <i class="fas fa-bell"></i> View Notifications
#                 </a>
#             </div>
#         </div>
#     </main>
# </div>
# {% endblock %}

# notifuication Cus  

# {% extends "layout.html" %}

# {% block content %}

# <div class="d-flex align-items-start">

# <div class="flex-grow-1 ms-4">
#     <h2 class="fw-bold mb-4">Notifications</h2>

#     <div class="card shadow-sm p-3">

#         {% if notifications|length == 0 %}
#             <p class="text-muted text-center">No notifications available.</p>
#         {% else %}

#             <ul class="list-group">
#                 {% for note in notifications %}
#                 <li class="list-group-item mb-2 shadow-sm" style="border-radius: 10px;">
#                     <div class="d-flex justify-content-between">
#                         <div>
#                             <h6 class="fw-bold mb-1">{{ note.title }}</h6>
#                             <p class="mb-1">{{ note.message }}</p>
#                             <small class="text-muted">
#                                 {{ note.created_at.strftime("%d %b %Y, %I:%M %p") }}
#                             </small>
#                         </div>

#                         {% if not note.read %}
#                             <span class="badge bg-primary">New</span>
#                         {% endif %}
#                     </div>
#                 </li>
#                 {% endfor %}
#             </ul>

#         {% endif %}
#     </div>
# </div>
# ```

# </div>
# {% endblock %}
# class="active">Dashboard</a></li>
# <nav class="sidebar-nav">
#             <ul>
#                 <li><a href="{{ url_for('customer_dashboard') }}" 
#                 class="active">Dashboard</a></li>
#                 <li><a href="{{ url_for('book_parcel') }}">Book New Parcel</a></li>
#                 <li><a href="{{ url_for('customer_parcels') }}">My Parcels</a></li>
#                 <li><a href="{{ url_for('customer_track') }}">Track Parcel</a></li>
#                 <li>
#  <a href="{{ url_for('customer_notifications') }}">
#                         Notifications 
#                         {% if notification_count > 0 %}
#                         <span style="background: red; color: white; padding: 2px 6px; border-radius: 50%; font-size: 0.8rem;">
#                             {{ notification_count }}
#                         </span>
#                         {% endif %}
#                     </a>
#                 </li>
#                 <li><a href="{{ url_for('customer_profile') }}">Profile</a></li>
#                 <li><a href="{{ url_for('logout') }}">Logout</a></li>
#             </ul>
#         </nav>
#     </aside>