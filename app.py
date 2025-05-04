from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = "supersecretkey"

client = MongoClient("mongodb+srv://phanxuanhaianh:haianh1919@tmdt.wouuo96.mongodb.net/?retryWrites=true&w=majority")
db = client["product"]
collection = db["product"]
user_db = client["auth"]
users_collection = user_db["users"]
orders_collection = db["orders"]

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
    if "user" not in session or not session["user"].get("email"):
        flash("Bạn cần đăng nhập để thanh toán", "warning")
        return redirect(url_for("login"))

    selected_ids = request.form.getlist("checkout_ids")
    if not selected_ids:
        flash("Vui lòng chọn sản phẩm để thanh toán", "warning")
        return redirect(url_for("view_cart"))

    user_email = session["user"]["email"]
    user = users_collection.find_one({"email": user_email})
    cart = user.get("cart", {})

    purchased_items = []
    total_price = 0
    for product_id in selected_ids:
        item = cart.get(product_id)
        if not item:
            continue
        sale_price = float(item["price"].get("sale", 0))
        quantity = item.get("quantity", 1)
        purchased_items.append({
            "product_id": product_id,
            "name": item["name"],
            "price": item["price"],
            "quantity": quantity,
            "image_url": item.get("image_url", "")
        })
        total_price += sale_price * quantity
        cart.pop(product_id, None)

    users_collection.update_one({"email": user_email}, {"$set": {"cart": cart}})

    now = datetime.utcnow()
    order_data = {
        "order_id": str(ObjectId()),
        "user_email": user_email,
        "items": purchased_items,
        "total_price": round(total_price, 2),
        "status": "cho_xac_nhan",
        "status_timestamps": {
            "cho_xac_nhan": now,
            "cho_lay_hang": now + timedelta(hours=1),
            "cho_giao_hang": now + timedelta(days=1),
            "danh_gia": now + timedelta(days=3),
            "hoan_thanh": now + timedelta(days=5)
        },
        "countdown": (now + timedelta(hours=1)).isoformat(),
        "created_at": now
    }

    orders_collection.insert_one(order_data)
    flash("Thanh toán thành công!", "success")
    return redirect(url_for("orders"))

@app.route("/orders")
def orders():
    if "user" not in session:
        return redirect(url_for("login"))
    email = session["user"]["email"]
    orders = list(orders_collection.find({"user_email": email}))
    return render_template("orders.html", orders=orders)

@app.route("/review/<order_id>", methods=["GET", "POST"])
def review(order_id):
    if "user" not in session:
        return redirect(url_for("login"))

    order = orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order or order.get("status") != "danh_gia":
        flash("Không thể đánh giá đơn hàng này.", "warning")
        return redirect(url_for("orders"))

    if request.method == "POST":
        for item in order["items"]:
            product_id = item["product_id"]
            rating = int(request.form.get(f"rating_{product_id}", 0))
            comment = request.form.get(f"comment_{product_id}", "").strip()
            if rating > 0:
                collection.update_one({"_id": ObjectId(product_id)}, {
                    "$push": {
                        "reviews.data": {
                            "user": session["user"]["email"],
                            "rating": rating,
                            "comment": comment,
                            "created_at": datetime.utcnow()
                        }
                    }
                })
                reviews = collection.find_one({"_id": ObjectId(product_id)}).get("reviews", {}).get("data", [])
                if reviews:
                    avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 2)
                    collection.update_one({"_id": ObjectId(product_id)}, {
                        "$set": {"reviews.averageReviewScore": avg_rating}
                    })

        orders_collection.update_one({"_id": order["_id"]}, {"$set": {"status": "hoan_thanh"}})
        flash("Đánh giá thành công!", "success")
        return redirect(url_for("orders"))

    return render_template("review.html", order=order)

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

# Background Job: Update order statuses
def update_order_statuses():
    now = datetime.utcnow()
    for order in orders_collection.find({}):
        status = order.get("status", "cho_xac_nhan")
        timestamps = order.get("status_timestamps", {"cho_xac_nhan": order["created_at"]})
        updates = {}

        if status == "cho_xac_nhan" and now - timestamps["cho_xac_nhan"] > timedelta(hours=1):
            updates["status"] = "cho_lay_hang"
            updates["status_timestamps.cho_lay_hang"] = now
        elif status == "cho_lay_hang" and now - timestamps.get("cho_lay_hang", now) > timedelta(days=2):
            updates["status"] = "dang_giao"
            updates["status_timestamps.dang_giao"] = now
        elif status == "dang_giao" and now - timestamps.get("dang_giao", now) > timedelta(days=4):
            updates["status"] = "danh_gia"
            updates["status_timestamps.danh_gia"] = now

        if updates:
            orders_collection.update_one({"_id": order["_id"]}, {"$set": updates})

scheduler = BackgroundScheduler()
scheduler.add_job(update_order_statuses, "interval", minutes=10)
scheduler.start()

if __name__ == "__main__":
    app.run(debug=True)
