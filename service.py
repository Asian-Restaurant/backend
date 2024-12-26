from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
import hashlib
from firebase_admin import auth
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

app = Flask(__name__)
CORS(app)

# Firebase setup
cred = credentials.Certificate("key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def hash_password(password):
    """Hashes the password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone")
    password = data.get("password")

    if not email or not phone or not password:
        return jsonify({"error": "Missing required fields"}), 400

    users_ref = db.collection("users").document(email)
    if users_ref.get().exists:
        return jsonify({"error": "User already exists"}), 400

    users_ref.set({
        "name": name,
        "email": email,
        "phone": phone,
        "password": hash_password(password)
    })
    return jsonify({"message": "User registered successfully"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing email or password"}), 400

    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    print(f"Login Attempt: email={email}, hashed_password={hashed_password}")

    try:
        # Query Firestore for the user by email
        users_query = db.collection("users").where(filter=FieldFilter("email", "==", email)).stream()
        user_doc = next(users_query, None)

        if not user_doc:
            print(f"User not found: email={email}")
            return jsonify({"error": "Invalid credentials"}), 401

        user_data = user_doc.to_dict()
        print(f"User Data Retrieved: {user_data}")

        if user_data.get("password") != hashed_password:
            print("Password mismatch")
            return jsonify({"error": "Invalid credentials"}), 401

        return jsonify({"message": "Login successful"}), 200
    except Exception as e:
        print(f"Error accessing Firestore: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/user', methods=['GET'])
def get_user():
    email = request.args.get('email')
    users_ref = db.collection("users").where(filter=FieldFilter("email", "==", email)).get()
    if not users_ref:
        return jsonify({"error": "User not found"}), 404

    user_data = users_ref[0].to_dict()
    return jsonify({"name": user_data["name"],"email": user_data["email"], "phone": user_data["phone"]}), 200

@app.route("/menu", methods=["GET"])
def menu():
    menu_ref = db.collection("menu").stream()
    menu_items = [item.to_dict() for item in menu_ref]
    return jsonify(menu_items), 200

@app.route('/dish', methods=['GET'])
def get_dish():
    dish_name = request.args.get('dish_name')
    dishes_ref = db.collection("dishes").where(filter=FieldFilter("dish_name", "==", dish_name)).get()

    if not dishes_ref:
        return jsonify({"error": "Dish not found"}), 404

    dish_data = dishes_ref[0].to_dict()
    return jsonify({
        "dish_name": dish_data["dish_name"],
        "description": dish_data["description"],
        "image_url": dish_data["image_url"],
        "price": dish_data["price"],
        "weight": dish_data["weight"]
    }), 200

# In-memory storage for carts
carts = {}

@app.route("/cart", methods=["POST"])
def add_to_cart():
    data = request.json
    name_dish = data.get("name_dish")
    price = data.get("price")
    quantity = data.get("quantity")
    comment = data.get("comment", "Want to bring home")

    cart_id = "generic_cart"

    if cart_id not in carts:
        carts[cart_id] = {}

    if name_dish in carts[cart_id]:
        carts[cart_id][name_dish]["quantity"] += quantity
        carts[cart_id][name_dish]["total_price"] += price * quantity
    else:
        total_price = price * quantity
        carts[cart_id][name_dish] = {
            "comment": comment,
            "price": price,
            "quantity": quantity,
            "total_price": total_price
        }

    return jsonify({"message": "Added to cart"}), 201


@app.route("/cart", methods=["GET"])
def get_cart():
    cart_id = "generic_cart"

    if cart_id not in carts or not carts[cart_id]:
        return jsonify({"error": "Cart is empty"}), 404

    formatted_items = []
    for item_name, item_data in carts[cart_id].items():
        formatted_items.append({
            "comment": item_data["comment"],
            "name_dish": item_name,
            "price": item_data["price"],
            "quantity": item_data["quantity"],
            "total_price": item_data["total_price"]
        })

    return jsonify(formatted_items), 200
@app.route("/save_cart", methods=["POST"])
def save_cart():
    data = request.json

    # Validate input data
    if not data or 'items' not in data:
        return jsonify({"error": "Invalid data"}), 400

    cart_id = "generic_cart"  # This could be a session ID or similar

    if cart_id not in carts:
        carts[cart_id] = {}

    # Process each item in the request
    for item in data['items']:
        name_dish = item.get("name_dish")
        price = item.get("price")
        quantity = item.get("quantity")
        comment = item.get("comment", "Want to bring home")  # Default comment

        if not (name_dish and price and quantity):
            return jsonify({"error": "Missing required fields"}), 400

        total_price = price * quantity

        # Save item in in-memory cart
        if name_dish in carts[cart_id]:
            carts[cart_id][name_dish]["quantity"] += quantity
            carts[cart_id][name_dish]["total_price"] += total_price
        else:
            carts[cart_id][name_dish] = {
                "comment": comment,
                "price": price,
                "quantity": quantity,
                "total_price": total_price
            }

        # Save to Firestore
        cart_item = {
            "comment": comment,
            "name_dish": name_dish,
            "price": price,
            "quantity": quantity,
            "total_price": total_price
        }
        
        db.collection("carts").add(cart_item)

    return jsonify({"message": "Cart saved successfully", "cart": carts[cart_id]}), 200

@app.route("/reviews", methods=["POST"])
def add_review():
    data = request.json
    email = data.get("email")
    comment = data.get("comment")

    if not email or not comment:
        return jsonify({"error": "Missing required fields"}), 400

    # Проверка пользователя в Firestore
    users_ref = db.collection("users").where(filter=FieldFilter("email", "==", email)).get()

    if len(users_ref) == 0:
        app.logger.error(f"User not found: {email}")
        return jsonify({"error": "User not authorized"}), 401

    # Добавление отзыва
    db.collection("reviews").add({
        "comment": comment,
        "name": users_ref[0].to_dict()["name"]
    })
    return jsonify({"message": "Review added"}), 201

@app.route("/reviews", methods=["GET"])
def get_reviews():
    reviews_ref = db.collection("reviews").stream()
    reviews = [review.to_dict() for review in reviews_ref]
    return jsonify(reviews), 200

@app.route("/delivery", methods=["POST"])
def delivery():
    data = request.json
    required_fields = ["street", "house", "floor", "apartment"]

    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing delivery details"}), 400

    db.collection("delivery").add(data)
    return jsonify({"message": "Delivery details saved"}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
