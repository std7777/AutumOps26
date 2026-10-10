# Morrow Edit

A small, minimal shopping store for clothing, accessories, bags, and luggage. The old fantasy page has been removed. This version uses a white editorial layout, yellow/pale pink/orange accents, subtle glass on the campaign label, and restrained animations.

## Run locally

1. Open a terminal in this `storefront` folder.
2. Run `python server.py`.
3. Open `http://127.0.0.1:8000` in a browser.

Python 3.10+ is required. No package installation is needed. The app creates `data/store.db` on first run and fills it with eight sample items and their photos.

## What works

- Home offer section, category pages, product search and sorting.
- Product details, shopping bag, quantity changes, and order placement.
- Account registration and login. Passwords are hashed; sessions use an HTTP-only cookie.
- Order history with the exact item prices at purchase time. Customers can remove their own demo orders; removing one returns its items to stock.
- Admin page to add, edit, hide, or delete items, set discounts, stock, and photos.

There is no payment processing. Placing an order records a **demo order**; it does not charge anyone or collect an address. The subtotal is the total shown, with no delivery or extra charges.

## Set up an admin login

In PowerShell, run these commands in the `storefront` folder, replacing the example values with your own:

```powershell
$env:MORROW_ADMIN_EMAIL = "you@example.com"
$env:MORROW_ADMIN_PASSWORD = "choose-a-long-private-password"
python server.py
```

Log in at `http://127.0.0.1:8000/#account`, then open **Manage shop**. The server creates this admin account at startup if it does not exist. If the email already belongs to a regular account, startup grants it admin access. The account's existing password remains in place.

Do not commit or share real passwords. The `data` folder is local store data and should not be published.

## Add photos

Read [PHOTO_GUIDE.md](PHOTO_GUIDE.md) for the current photos. To add or replace one, put it in `static/images`, then enter its filename in the admin page, for example `city-tote.jpg`. The server checks that the file exists before saving.

## Project scope

This is a local application for reviewing the design and interactions. It currently uses SQLite in one local server. The AWS assignment's final three-tier deployment still requires moving the application API to the private application EC2, connecting it to the private RDS database, and serving the frontend through the public web EC2. Nothing here launches an AWS resource.
