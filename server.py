"""Small shopping store server. SQLite locally or MySQL on AWS."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
DATABASE = DATA / "store.db"
DB_BACKEND = os.getenv("MORROW_DB_BACKEND", "sqlite").strip().lower()
if DB_BACKEND not in {"sqlite", "mysql"}:
    raise ValueError("MORROW_DB_BACKEND must be sqlite or mysql")
if DB_BACKEND == "mysql":
    try:
        import pymysql
        from pymysql.constants import CLIENT
    except ImportError as exc:
        raise RuntimeError("MySQL mode needs PyMySQL. Install requirements-aws.txt on the app EC2.") from exc

INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + ((pymysql.IntegrityError,) if DB_BACKEND == "mysql" else ())
HOST = os.getenv("MORROW_HOST", "127.0.0.1")
PORT = int(os.getenv("MORROW_PORT", "8000"))
SESSION_DAYS = 7
CATEGORIES = {"clothing", "accessories", "bags", "luggage"}
IMAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:jpe?g|png|webp)$", re.I)

SEED_PRODUCTS = [
    ("The Everyday Shirt", "clothing", 189900, 0, "/images/everyday-shirt.jpg", "A relaxed layer made for wherever the day leads.", 24, 1, 1),
    ("Easy Sunday Tee", "clothing", 99900, 0, "/images/sunday-tee.jpg", "An everyday staple with a soft, easy shape.", 30, 0, 1),
    ("The Little Scarf", "accessories", 79900, 20, "/images/little-scarf.jpg", "A bright detail for your bag, neck, or hair.", 20, 1, 1),
    ("Everyday Sunglasses", "accessories", 129900, 20, "/images/sunglasses.jpg", "A clean shape that goes with almost anything.", 18, 0, 1),
    ("The City Tote", "bags", 249900, 20, "/images/city-tote.jpg", "Room for the whole day without the extra fuss.", 16, 1, 1),
    ("Star Mini Crossbody", "bags", 199900, 20, "/images/crossbody.jpg", "A playful little bag for your everyday essentials.", 17, 1, 1),
    ("Carry-On Case", "luggage", 649900, 0, "/images/carry-on.jpg", "Your essentials, neatly packed and ready to go.", 12, 0, 1),
    ("Sunshine Travel Set", "luggage", 389900, 0, "/images/travel-set.jpg", "A coordinated luggage set for your next escape.", 14, 0, 1),
]

MYSQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(80) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE,
  password_hash VARCHAR(128) NOT NULL, is_admin TINYINT(1) NOT NULL DEFAULT 0,
  created_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS sessions (
  token_hash CHAR(64) NOT NULL PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  expires_at VARCHAR(40) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS products (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL, category VARCHAR(32) NOT NULL,
  price BIGINT NOT NULL, discount INT NOT NULL DEFAULT 0,
  image VARCHAR(255) NOT NULL DEFAULT '', description VARCHAR(500) NOT NULL DEFAULT '',
  stock INT NOT NULL DEFAULT 0, featured TINYINT(1) NOT NULL DEFAULT 0,
  active TINYINT(1) NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL, total BIGINT NOT NULL,
  created_at VARCHAR(40) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL, product_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL, quantity INT NOT NULL, unit_price BIGINT NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MySQLConnection:
    """Expose the small execute interface used by the SQLite code."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement: str, parameters=()):
        cursor = self.connection.cursor()
        cursor.execute(statement.replace("?", "%s"), parameters)
        return cursor

    def executemany(self, statement: str, rows):
        cursor = self.connection.cursor()
        cursor.executemany(statement.replace("?", "%s"), rows)
        return cursor

    def executescript(self, script: str):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


@contextmanager
def db():
    if DB_BACKEND == "mysql":
        names = ("MORROW_DB_HOST", "MORROW_DB_USER", "MORROW_DB_PASSWORD", "MORROW_DB_NAME")
        missing = [name for name in names if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing MySQL settings: {', '.join(missing)}")
        options = {}
        if os.getenv("MORROW_DB_SSL_CA"):
            options["ssl_ca"] = os.environ["MORROW_DB_SSL_CA"]
            options["ssl_verify_cert"] = True
            options["ssl_verify_identity"] = True
        raw = pymysql.connect(
            host=os.environ["MORROW_DB_HOST"],
            port=int(os.getenv("MORROW_DB_PORT", "3306")),
            user=os.environ["MORROW_DB_USER"],
            password=os.environ["MORROW_DB_PASSWORD"],
            database=os.environ["MORROW_DB_NAME"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            client_flag=CLIENT.FOUND_ROWS,
            autocommit=False,
            connect_timeout=10,
            **options,
        )
        try:
            yield MySQLConnection(raw)
            raw.commit()
        except BaseException:
            raw.rollback()
            raise
        finally:
            raw.close()
    else:
        connection = sqlite3.connect(DATABASE, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def begin_write(connection) -> None:
    # SQLite locks writers up front; MySQL locks the selected rows below.
    if DB_BACKEND == "sqlite":
        connection.execute("BEGIN IMMEDIATE")


def for_update(statement: str) -> str:
    return statement + (" FOR UPDATE" if DB_BACKEND == "mysql" else "")


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260_000)
    return f"{salt}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def init_db() -> None:
    if DB_BACKEND == "sqlite":
        DATA.mkdir(exist_ok=True)
    (STATIC / "images").mkdir(exist_ok=True)
    with db() as connection:
        connection.executescript(
            MYSQL_SCHEMA if DB_BACKEND == "mysql" else """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
              price INTEGER NOT NULL, discount INTEGER NOT NULL DEFAULT 0,
              image TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
              stock INTEGER NOT NULL DEFAULT 0, featured INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
              id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
              total INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
              id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
              product_id INTEGER NOT NULL, name TEXT NOT NULL,
              quantity INTEGER NOT NULL, unit_price INTEGER NOT NULL
            );
            """
        )
        if connection.execute("SELECT COUNT(*) AS item_count FROM products").fetchone()["item_count"] == 0:
            connection.executemany(
                "INSERT INTO products (name,category,price,discount,image,description,stock,featured,active,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(*row, now()) for row in SEED_PRODUCTS],
            )
        admin_email = os.getenv("MORROW_ADMIN_EMAIL", "").strip().lower()
        admin_password = os.getenv("MORROW_ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            if len(admin_password) < 12:
                raise ValueError("MORROW_ADMIN_PASSWORD must be at least 12 characters")
            existing = connection.execute("SELECT id,is_admin FROM users WHERE email=?", (admin_email,)).fetchone()
            if existing:
                if not existing["is_admin"]:
                    raise ValueError("Admin email already belongs to a customer. Choose a different admin email.")
            else:
                connection.execute(
                    "INSERT INTO users (name,email,password_hash,is_admin,created_at) VALUES (?,?,?,?,?)",
                    ("Shop Admin", admin_email, password_hash(admin_password), 1, now()),
                )


def product_dict(row) -> dict:
    item = dict(row)
    item["active"] = bool(item["active"])
    item["featured"] = bool(item["featured"])
    return item


class StoreHandler(BaseHTTPRequestHandler):
    server_version = "MorrowStore/1.0"

    def json_response(self, status: int, data: dict, cookie: str | None = None) -> None:
        payload = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def error(self, status: int, message: str) -> None:
        self.json_response(status, {"error": message})

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 64_000:
            raise ValueError("Invalid request size")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        return body

    def current_user(self) -> dict | None:
        raw_cookie = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
            token = cookie["morrow_session"].value if "morrow_session" in cookie else ""
        except Exception:
            token = ""
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with db() as connection:
            row = connection.execute(
                "SELECT u.id,u.name,u.email,u.is_admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                (token_hash, now()),
            ).fetchone()
        return dict(row) if row else None

    def require_user(self, admin: bool = False) -> dict | None:
        user = self.current_user()
        if not user:
            self.error(HTTPStatus.UNAUTHORIZED, "Please log in first.")
            return None
        if admin and not user["is_admin"]:
            self.error(HTTPStatus.FORBIDDEN, "Admin access is required.")
            return None
        return user

    def check_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        if origin and origin not in {f"http://{self.headers.get('Host')}", f"https://{self.headers.get('Host')}"}:
            self.error(HTTPStatus.FORBIDDEN, "Invalid request origin.")
            return False
        return True

    def cookie_header(self, token: str, max_age: int) -> str:
        secure = "; Secure" if os.getenv("MORROW_HTTPS") == "1" else ""
        return f"morrow_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            self.get_api(path, parse_qs(parsed.query))
            return
        if path == "/":
            path = "/index.html"
        candidate = (STATIC / path.lstrip("/")).resolve()
        try:
            candidate.relative_to(STATIC.resolve())
        except ValueError:
            self.error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if not candidate.is_file():
            self.error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content = candidate.read_bytes()
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def get_api(self, path: str, query: dict) -> None:
        if path == "/api/config":
            self.json_response(200, {"hero_image": (STATIC / "images" / "hero.jpg").is_file()})
        elif path == "/api/me":
            self.json_response(200, {"user": self.current_user()})
        elif path == "/api/products":
            show_all = query.get("all") == ["1"]
            if show_all and not self.require_user(admin=True):
                return
            with db() as connection:
                rows = connection.execute("SELECT * FROM products" + ("" if show_all else " WHERE active=1") + " ORDER BY id").fetchall()
            self.json_response(200, {"products": [product_dict(row) for row in rows]})
        elif path == "/api/orders":
            user = self.require_user()
            if not user:
                return
            with db() as connection:
                rows = connection.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
                orders = []
                for row in rows:
                    order = dict(row)
                    order["items"] = [dict(item) for item in connection.execute("SELECT product_id,name,quantity,unit_price FROM order_items WHERE order_id=?", (row["id"],)).fetchall()]
                    orders.append(order)
            self.json_response(200, {"orders": orders})
        else:
            self.error(404, "Not found")

    def do_POST(self) -> None:
        if not self.check_origin():
            return
        path = urlsplit(self.path).path
        try:
            data = self.read_json()
            if path == "/api/register":
                self.register(data)
            elif path == "/api/login":
                self.login(data)
            elif path == "/api/logout":
                self.logout()
            elif path == "/api/orders":
                self.place_order(data)
            elif path == "/api/admin/products":
                self.save_product(data)
            else:
                self.error(404, "Not found")
        except (ValueError, json.JSONDecodeError) as exc:
            self.error(400, str(exc))
        except INTEGRITY_ERRORS:
            self.error(409, "This item could not be saved because it is already in use.")

    def do_PUT(self) -> None:
        if not self.check_origin():
            return
        match = re.fullmatch(r"/api/admin/products/(\d+)", urlsplit(self.path).path)
        if not match:
            self.error(404, "Not found")
            return
        try:
            self.save_product(self.read_json(), int(match.group(1)))
        except (ValueError, json.JSONDecodeError) as exc:
            self.error(400, str(exc))

    def do_DELETE(self) -> None:
        if not self.check_origin():
            return
        path = urlsplit(self.path).path
        order_match = re.fullmatch(r"/api/orders/(\d+)", path)
        if order_match:
            self.remove_order(int(order_match.group(1)))
            return
        match = re.fullmatch(r"/api/admin/products/(\d+)", path)
        if not match:
            self.error(404, "Not found")
            return
        if not self.require_user(admin=True):
            return
        with db() as connection:
            begin_write(connection)
            product_id = int(match.group(1))
            product = connection.execute(for_update("SELECT id FROM products WHERE id=?"), (product_id,)).fetchone()
            if not product:
                self.error(404, "Item not found.")
                return
            # Preserve an ordered product's record so existing orders stay readable.
            in_order = connection.execute("SELECT 1 FROM order_items WHERE product_id=? LIMIT 1", (product_id,)).fetchone()
            if in_order:
                connection.execute("UPDATE products SET active=0,stock=0 WHERE id=?", (product_id,))
            else:
                connection.execute("DELETE FROM products WHERE id=?", (product_id,))
        self.json_response(200, {"ok": True})

    def register(self, data: dict) -> None:
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not 1 <= len(name) <= 80 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not 8 <= len(password) <= 128:
            raise ValueError("Enter a name, valid email, and password of at least 8 characters.")
        try:
            with db() as connection:
                cursor = connection.execute("INSERT INTO users (name,email,password_hash,created_at) VALUES (?,?,?,?)", (name, email, password_hash(password), now()))
                user_id = cursor.lastrowid
        except INTEGRITY_ERRORS:
            self.error(409, "An account with this email already exists.")
            return
        self.create_session({"id": user_id, "name": name, "email": email, "is_admin": 0})

    def login(self, data: dict) -> None:
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        with db() as connection:
            row = connection.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not password_matches(password, row["password_hash"]):
            self.error(401, "Email or password is incorrect.")
            return
        self.create_session({key: row[key] for key in ("id", "name", "email", "is_admin")})

    def create_session(self, user: dict) -> None:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
        with db() as connection:
            connection.execute("INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)", (token_hash, user["id"], expires))
        user["is_admin"] = bool(user["is_admin"])
        self.json_response(200, {"user": user}, self.cookie_header(token, SESSION_DAYS * 86400))

    def logout(self) -> None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        if "morrow_session" in cookie:
            token_hash = hashlib.sha256(cookie["morrow_session"].value.encode()).hexdigest()
            with db() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        self.json_response(200, {"ok": True}, self.cookie_header("", 0))

    def place_order(self, data: dict) -> None:
        user = self.require_user()
        if not user:
            return
        items = data.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 30:
            raise ValueError("Add items to your bag before placing an order.")
        normalized = {}
        for item in items:
            if not isinstance(item, dict) or type(item.get("product_id")) is not int or type(item.get("quantity")) is not int:
                raise ValueError("Invalid item in order.")
            product_id, quantity = item["product_id"], item["quantity"]
            if product_id < 1 or not 1 <= quantity <= 99 or product_id in normalized:
                raise ValueError("Invalid item quantity.")
            normalized[product_id] = quantity
        with db() as connection:
            begin_write(connection)
            entries, total = [], 0
            for product_id in sorted(normalized):
                quantity = normalized[product_id]
                row = connection.execute(for_update("SELECT * FROM products WHERE id=? AND active=1"), (product_id,)).fetchone()
                if not row or row["stock"] < quantity:
                    raise ValueError("An item in your bag is no longer available in that quantity.")
                unit = (row["price"] * (100 - row["discount"]) + 50) // 100
                total += unit * quantity
                entries.append((product_id, row["name"], quantity, unit))
                connection.execute("UPDATE products SET stock=stock-? WHERE id=?", (quantity, product_id))
            cursor = connection.execute("INSERT INTO orders (user_id,total,created_at) VALUES (?,?,?)", (user["id"], total, now()))
            connection.executemany("INSERT INTO order_items (order_id,product_id,name,quantity,unit_price) VALUES (?,?,?,?,?)", [(cursor.lastrowid, *entry) for entry in entries])
            order_id = cursor.lastrowid
        self.json_response(201, {"order_id": order_id, "total": total})

    def remove_order(self, order_id: int) -> None:
        user = self.require_user()
        if not user:
            return
        with db() as connection:
            begin_write(connection)
            order = connection.execute(
                for_update("SELECT id FROM orders WHERE id=? AND user_id=?"), (order_id, user["id"])
            ).fetchone()
            if not order:
                self.error(404, "Order not found.")
                return
            items = connection.execute(
                "SELECT product_id,quantity FROM order_items WHERE order_id=? ORDER BY product_id", (order_id,)
            ).fetchall()
            for item in items:
                connection.execute(
                    "UPDATE products SET stock=stock+? WHERE id=?",
                    (item["quantity"], item["product_id"]),
                )
            connection.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
            connection.execute("DELETE FROM orders WHERE id=?", (order_id,))
        self.json_response(200, {"ok": True})

    def save_product(self, data: dict, product_id: int | None = None) -> None:
        if not self.require_user(admin=True):
            return
        name = str(data.get("name", "")).strip()
        category = str(data.get("category", ""))
        description = str(data.get("description", "")).strip()
        image = str(data.get("image", "")).strip()
        price, discount, stock = data.get("price"), data.get("discount"), data.get("stock")
        if not 1 <= len(name) <= 100 or category not in CATEGORIES or len(description) > 500:
            raise ValueError("Check the item name, category, and description.")
        if type(price) is not int or not 1 <= price <= 10_000_000 or type(discount) is not int or not 0 <= discount <= 90 or type(stock) is not int or not 0 <= stock <= 10_000:
            raise ValueError("Check the price, discount, and stock values.")
        if image:
            if not image.startswith("/images/") or not IMAGE_NAME.fullmatch(image.removeprefix("/images/")):
                raise ValueError("Use a JPG, PNG, or WebP filename from static/images.")
            if not (STATIC / image.lstrip("/")).is_file():
                raise ValueError("That photo is not in static/images yet.")
        active, featured = int(data.get("active") is True), int(data.get("featured") is True)
        with db() as connection:
            if product_id is None:
                cursor = connection.execute("INSERT INTO products (name,category,price,discount,image,description,stock,featured,active,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (name,category,price,discount,image,description,stock,featured,active,now()))
                product_id = cursor.lastrowid
            else:
                cursor = connection.execute("UPDATE products SET name=?,category=?,price=?,discount=?,image=?,description=?,stock=?,featured=?,active=? WHERE id=?", (name,category,price,discount,image,description,stock,featured,active,product_id))
                if cursor.rowcount == 0:
                    self.error(404, "Item not found.")
                    return
        self.json_response(200, {"id": product_id})


if __name__ == "__main__":
    init_db()
    print(f"Morrow Edit is running at http://{HOST}:{PORT}")
    if not os.getenv("MORROW_ADMIN_EMAIL"):
        print("Admin login is disabled until MORROW_ADMIN_EMAIL and MORROW_ADMIN_PASSWORD are set.")
    ThreadingHTTPServer((HOST, PORT), StoreHandler).serve_forever()
