from app import app, mongo

with app.app_context():
    mongo.db.notifications.create_index([("user_id", 1), ("read", 1)])
    mongo.db.parcels.create_index([("tracking_id", 1)], unique=True)
    mongo.db.users.create_index([("email", 1)], unique=True)
    mongo.db.parcels.create_index([("status", 1)])

print("✅ Indexes created successfully")