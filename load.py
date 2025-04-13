import json
from pymongo import MongoClient

# Kết nối MongoDB (bỏ kiểm tra chứng chỉ - chỉ dùng khi test/debug)
MONGO_URI = "mongodb+srv://phanxuanhaianh:haianh1919@tmdt.wouuo96.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)

db = client["product"]
collection = db["product"]

# Đọc file JSON dòng (mỗi dòng 1 object)
json_path = r"C:\HOC_DAI_HOC\KY_VI\cloud\products.json"
with open(json_path, "r", encoding="utf-8") as f:
    data = [json.loads(line) for line in f if line.strip()]

# Xoá trường _id nếu có
for item in data:
    item.pop("_id", None)

# Insert vào MongoDB
collection.insert_many(data)

print(f"✅ Đã import {len(data)} sản phẩm vào MongoDB!")