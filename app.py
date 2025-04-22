# app.py - Phiên bản nâng cấp UI/UX phù hợp giao diện mới
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

client = MongoClient("mongodb+srv://phanxuanhaianh:haianh1919@tmdt.wouuo96.mongodb.net/?retryWrites=true&w=majority")
db = client["product"]
collection = db["product"]
user_db = client["auth"]
users_collection = user_db["users"]

def get_product_by_id(product_id):
    try:
        return collection.find_one({"_id": ObjectId(product_id)})
    except:
        return None

@app.context_processor
def inject_cart_count():
    if "user" in session:
        user = users_collection.find_one({"email": session["user"]["email"]})
        cart = user.get("cart", {})
        return {"cart_count": sum(item.get("quantity", 0) for item in cart.values())}
    return {"cart_count": 0}

@app.route("/")
def index():
    page = int(request.args.get("page", 1))
    per_page = 12
    skip = (page - 1) * per_page

    category = request.args.get("category")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    keyword = request.args.get("q", "").strip()
    min_rating = request.args.get("min_rating", type=float)
    sort_by = request.args.get("sort")

    query = {}
    if category:
        query["category"] = category
    if keyword:
        query["productName"] = {"$regex": keyword, "$options": "i"}
    if min_price is not None or max_price is not None:
        query["price.sale"] = {}
        if min_price is not None:
            query["price.sale"]["$gte"] = min_price
        if max_price is not None:
            query["price.sale"]["$lte"] = max_price
    if min_rating is not None:
        query["reviews.averageReviewScore"] = {"$gte": min_rating}

    sort_criteria = None
    if sort_by == "price_asc":
        sort_criteria = [("price.sale", 1)]
    elif sort_by == "price_desc":
        sort_criteria = [("price.sale", -1)]
    elif sort_by == "rating_desc":
        sort_criteria = [("reviews.averageReviewScore", -1)]

    total_products = collection.count_documents(query)
    total_pages = (total_products + per_page - 1) // per_page
    products = list(collection.find(query).sort(sort_criteria).skip(skip).limit(per_page)) if sort_criteria else list(collection.find(query).skip(skip).limit(per_page))
    for product in products:
        product["image_url"] = product.get("productImages", [None])[0]

    categories = sorted({c for c in collection.distinct("category") if c and c.strip()})

    return render_template("index.html", products=products, page=page, total_pages=total_pages,
                           category=category, min_price=min_price, max_price=max_price,
                           categories=categories, keyword=keyword, min_rating=min_rating,
                           sort_by=sort_by, max=max, min=min)

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    if "user" not in session:
        return jsonify(success=False, message="Bạn cần đăng nhập để thêm sản phẩm vào giỏ hàng."), 401

    product_id = request.form["product_id"]
    user_email = session["user"]["email"]
    user = users_collection.find_one({"email": user_email})
    cart = user.get("cart", {})

    if product_id in cart:
        cart[product_id]["quantity"] += 1
    else:
        product = get_product_by_id(product_id)
        if product:
            cart[product_id] = {
                "name": product["productName"],
                "description": product.get("description", ""),
                "price": {"sale": float(product["price"]["sale"])},
                "image_url": product.get("productImages", [None])[0],
                "quantity": 1
            }

    users_collection.update_one({"email": user_email}, {"$set": {"cart": cart}})
    cart_count = sum(item["quantity"] for item in cart.values())
    return jsonify(success=True, cart_count=cart_count)

@app.route("/cart")
def view_cart():
    if "user" not in session:
        flash("Bạn cần đăng nhập để xem giỏ hàng", "warning")
        return redirect(url_for("login"))

    user_email = session["user"]["email"]
    user = users_collection.find_one({"email": user_email})
    cart = user.get("cart", {})

    cart_items = []
    total_price = 0
    for product_id, item in cart.items():
        quantity = item["quantity"]
        sale_price = float(item["price"]["sale"])
        total = sale_price * quantity
        total_price += total
        cart_items.append({"_id": product_id, "name": item["name"], "description": item.get("description", ""),
                           "price": item["price"], "image_url": item.get("image_url"), "quantity": quantity, "total": total})

    message = request.args.get("message")
    return render_template("cart.html", cart_items=cart_items, total_price=round(total_price, 2), message=message)

@app.route("/update_quantity_ajax", methods=["POST"])
def update_quantity_ajax():
    if "user" not in session:
        return jsonify(success=False, message="Bạn cần đăng nhập"), 401

    product_id = request.form.get("product_id")
    delta = int(request.form.get("delta", 0))
    user_email = session["user"]["email"]
    user = users_collection.find_one({"email": user_email})
    cart = user.get("cart", {})

    if product_id in cart:
        cart[product_id]["quantity"] = max(1, cart[product_id]["quantity"] + delta)
        users_collection.update_one({"email": user_email}, {"$set": {"cart": cart}})
        return jsonify(success=True, new_quantity=cart[product_id]["quantity"])

    return jsonify(success=False), 400

@app.route("/remove_from_cart", methods=["POST"])
def remove_from_cart():
    if "user" not in session:
        flash("Bạn cần đăng nhập để cập nhật giỏ hàng", "warning")
        return redirect(url_for("login"))

    product_id = request.form["product_id"]
    user_email = session["user"]["email"]
    user = users_collection.find_one({"email": user_email})
    cart = user.get("cart", {})

    if product_id in cart:
        del cart[product_id]
        users_collection.update_one({"email": user_email}, {"$set": {"cart": cart}})

    return redirect(url_for("view_cart"))

@app.route("/clear_cart", methods=["POST"])
def clear_cart():
    if "user" not in session:
        flash("Bạn cần đăng nhập để thực hiện chức năng này", "warning")
        return redirect(url_for("login"))

    user_email = session["user"]["email"]
    users_collection.update_one({"email": user_email}, {"$set": {"cart": {}}})
    flash("Đã xóa toàn bộ giỏ hàng", "info")
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["POST"])
def checkout():
    if "user" not in session:
        flash("Bạn cần đăng nhập để thanh toán", "warning")
        return redirect(url_for("login"))

    selected_ids = request.form.getlist("checkout_ids")
    user_email = session["user"]["email"]
    user = users_collection.find_one({"email": user_email})
    cart = user.get("cart", {})
    for product_id in selected_ids:
        if product_id in cart:
            del cart[product_id]
    users_collection.update_one({"email": user_email}, {"$set": {"cart": cart}})
    flash("Thanh toán thành công cho các sản phẩm đã chọn!", "success")
    return redirect(url_for("view_cart"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        existing_user = users_collection.find_one({"email": email})
        if existing_user:
            flash("Email đã được sử dụng", "danger")
            return render_template("register.html")
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({"email": email, "password": hashed_password})
        flash("Đăng ký thành công, vui lòng đăng nhập", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = users_collection.find_one({"email": email})
        if not user or not check_password_hash(user["password"], password):
            flash("Email hoặc mật khẩu không đúng", "danger")
            return redirect(url_for("login"))
        session["user"] = {"email": user["email"]}
        if "cart" not in user:
            users_collection.update_one({"email": email}, {"$set": {"cart": {}}})
        flash("Đăng nhập thành công!", "success")
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Đã đăng xuất", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)