# app.py sau khi tích hợp lọc theo đánh giá, sắp xếp và nút reset
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = "supersecretkey"

client = MongoClient("mongodb+srv://phanxuanhaianh:haianh1919@tmdt.wouuo96.mongodb.net/?retryWrites=true&w=majority")
db = client["product"]
collection = db["product"]

def get_product_by_id(product_id):
    try:
        return collection.find_one({"_id": ObjectId(product_id)})
    except:
        return None

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
    if sort_criteria:
        products = list(collection.find(query).sort(sort_criteria).skip(skip).limit(per_page))
    else:
        products = list(collection.find(query).skip(skip).limit(per_page))

    for product in products:
        product["image_url"] = product.get("productImages", [None])[0]

    categories = sorted({c for c in collection.distinct("category") if c and c.strip()})

    return render_template(
        "index.html",
        products=products,
        page=page,
        total_pages=total_pages,
        category=category,
        min_price=min_price,
        max_price=max_price,
        categories=categories,
        keyword=keyword,
        min_rating=min_rating,
        sort_by=sort_by,
        max=max,
        min=min
    )

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    product_id = request.form["product_id"]
    cart = session.get("cart", {})

    if product_id in cart and isinstance(cart[product_id], dict):
        cart[product_id]["quantity"] += 1
    else:
        product = get_product_by_id(product_id)
        if product:
            cart[product_id] = {
                "name": product["productName"],
                "description": product.get("description", ""),
                "price": {
                    "sale": float(product["price"]["sale"])
                },
                "image_url": product.get("productImages", [None])[0],
                "quantity": 1
            }

    session["cart"] = cart
    session.modified = True
    return jsonify(success=True)

@app.route("/cart")
def view_cart():
    cart = session.get("cart", {})
    cart_items = []
    total_price = 0

    for product_id, item in cart.items():
        if isinstance(item, int):
            product = get_product_by_id(product_id)
            if product:
                item = {
                    "name": product["productName"],
                    "description": product.get("description", ""),
                    "price": {
                        "sale": float(product["price"]["sale"])
                    },
                    "image_url": product.get("productImages", [None])[0],
                    "quantity": item
                }
                cart[product_id] = item
                session["cart"] = cart

        quantity = item["quantity"]
        sale_price = float(item["price"]["sale"])
        total = sale_price * quantity
        total_price += total
        cart_items.append({
            "_id": product_id,
            "name": item["name"],
            "description": item.get("description", ""),
            "price": item["price"],
            "image_url": item.get("image_url"),
            "quantity": quantity,
            "total": total
        })

    message = request.args.get("message")
    return render_template("cart.html", cart_items=cart_items, total_price=round(total_price, 2), message=message)

@app.route("/update_quantity", methods=["POST"])
def update_quantity():
    product_id = request.form.get("product_id")
    action = request.form.get("action")

    cart = session.get("cart", {})

    if product_id in cart and isinstance(cart[product_id], dict):
        if action == "increase":
            cart[product_id]["quantity"] += 1
        elif action == "decrease" and cart[product_id]["quantity"] > 1:
            cart[product_id]["quantity"] -= 1

    session["cart"] = cart
    session.modified = True
    return redirect(url_for("view_cart"))

@app.route("/remove_from_cart", methods=["POST"])
def remove_from_cart():
    product_id = request.form["product_id"]
    cart = session.get("cart", {})
    if product_id in cart:
        del cart[product_id]
    session["cart"] = cart
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["POST"])
def checkout():
    selected_ids = request.form.getlist("checkout_ids")
    cart = session.get("cart", {})

    for product_id in selected_ids:
        if product_id in cart:
            del cart[product_id]

    session["cart"] = cart
    session.modified = True

    message = "Thanh toán thành công cho các sản phẩm đã chọn!"
    return redirect(url_for("view_cart", message=message))

@app.route("/update_quantity_ajax", methods=["POST"])
def update_quantity_ajax():
    product_id = request.form.get("product_id")
    delta = int(request.form.get("delta", 0))
    cart = session.get("cart", {})

    if product_id in cart and isinstance(cart[product_id], dict):
        cart[product_id]["quantity"] = max(1, cart[product_id]["quantity"] + delta)
        session["cart"] = cart
        session.modified = True
        return jsonify(success=True, new_quantity=cart[product_id]["quantity"])

    return jsonify(success=False), 400

if __name__ == "__main__":
    app.run(debug=True)
