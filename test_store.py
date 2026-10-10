"""Meaningful API smoke tests for account access, item management, and order totals."""

import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

import server


class StoreFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=server.ROOT)
        server.DATABASE = Path(cls.temp.name) / "test.db"
        os.environ["MORROW_ADMIN_EMAIL"] = "admin@example.test"
        os.environ["MORROW_ADMIN_PASSWORD"] = "test-password-1234"
        server.init_db()
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StoreHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=2)
        cls.httpd.server_close()
        if not Path(cls.temp.name).resolve().is_relative_to(server.ROOT.resolve()):
            raise RuntimeError("Refusing to clean up a directory outside this project")
        cls.temp.cleanup()
        del os.environ["MORROW_ADMIN_EMAIL"]
        del os.environ["MORROW_ADMIN_PASSWORD"]

    def request(self, method, path, body=None, cookie=""):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = conn.getresponse()
        status = response.status
        session = response.getheader("Set-Cookie", "").split(";", 1)[0]
        data = json.loads(response.read())
        conn.close()
        return status, data, session

    def test_existing_customer_cannot_become_admin_from_environment(self):
        status, _, _ = self.request("POST", "/api/register", {
            "name": "Regular Customer",
            "email": "regular@example.test",
            "password": "safe-password-123",
        })
        self.assertEqual(status, 200)
        os.environ["MORROW_ADMIN_EMAIL"] = "regular@example.test"
        try:
            with self.assertRaisesRegex(ValueError, "already belongs to a customer"):
                server.init_db()
        finally:
            os.environ["MORROW_ADMIN_EMAIL"] = "admin@example.test"

    def test_shopping_flow_and_admin_permissions(self):
        status, data, _ = self.request("GET", "/api/products")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["products"]), 8)
        status, _, _ = self.request("POST", "/api/orders", {"items": [{"product_id": 5, "quantity": 1}]})
        self.assertEqual(status, 401)

        status, data, user_cookie = self.request("POST", "/api/register", {"name": "Sample Shopper", "email": "shopper@example.test", "password": "safe-password-123"})
        self.assertEqual(status, 200)
        self.assertFalse(data["user"]["is_admin"])
        status, _, _ = self.request("POST", "/api/admin/products", {"name": "Unauthorized"}, user_cookie)
        self.assertEqual(status, 403)
        status, data, _ = self.request("POST", "/api/orders", {"items": [{"product_id": 5, "quantity": 1}]}, user_cookie)
        self.assertEqual(status, 201)
        self.assertEqual(data["total"], 199920)
        order_id = data["order_id"]
        status, data, _ = self.request("GET", "/api/orders", cookie=user_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["orders"][0]["items"][0]["name"], "The City Tote")
        status, data, _ = self.request("GET", "/api/products")
        self.assertEqual(next(p for p in data["products"] if p["id"] == 5)["stock"], 15)
        status, _, other_cookie = self.request("POST", "/api/register", {"name": "Other Shopper", "email": "other@example.test", "password": "safe-password-123"})
        self.assertEqual(status, 200)
        status, _, _ = self.request("DELETE", f"/api/orders/{order_id}", cookie=other_cookie)
        self.assertEqual(status, 404)
        status, _, _ = self.request("DELETE", f"/api/orders/{order_id}", cookie=user_cookie)
        self.assertEqual(status, 200)
        status, data, _ = self.request("GET", "/api/orders", cookie=user_cookie)
        self.assertEqual(data["orders"], [])
        status, data, _ = self.request("GET", "/api/products")
        self.assertEqual(next(p for p in data["products"] if p["id"] == 5)["stock"], 16)

        status, data, admin_cookie = self.request("POST", "/api/login", {"email": "admin@example.test", "password": "test-password-1234"})
        self.assertEqual(status, 200)
        self.assertTrue(data["user"]["is_admin"])
        item = {"name": "New Carry Bag", "category": "bags", "price": 150000, "discount": 10, "image": "", "description": "A practical bag.", "stock": 5, "featured": True, "active": True}
        status, data, _ = self.request("POST", "/api/admin/products", item, admin_cookie)
        self.assertEqual(status, 200)
        new_id = data["id"]
        item["active"] = False
        status, _, _ = self.request("PUT", f"/api/admin/products/{new_id}", item, admin_cookie)
        self.assertEqual(status, 200)
        status, data, _ = self.request("GET", "/api/products")
        self.assertNotIn(new_id, [p["id"] for p in data["products"]])
        status, data, _ = self.request("GET", "/api/products?all=1", cookie=admin_cookie)
        self.assertIn(new_id, [p["id"] for p in data["products"]])


if __name__ == "__main__":
    unittest.main()
