const CATEGORIES = ["clothing", "accessories", "bags", "luggage"];
const CATEGORY_NOTES = {
  clothing: "Pieces to wear on repeat.",
  accessories: "The smallest details matter.",
  bags: "Room for every kind of day.",
  luggage: "Ready when you are."
};
const state = {
  products: [], me: null, cart: readCart(), query: "", sort: "featured",
  heroImage: false, authTab: "login", editing: null, orders: [], toastTimer: null
};
const app = document.getElementById("app");
const money = value => new Intl.NumberFormat("en-IN", {style:"currency", currency:"INR", maximumFractionDigits:2}).format(value / 100);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[char]);

function readCart() { try { return JSON.parse(localStorage.getItem("morrow-cart") || "{}"); } catch { return {}; } }
function saveCart() { localStorage.setItem("morrow-cart", JSON.stringify(state.cart)); updateCartCount(); renderCart(); }
function toast(message) {
  const el = document.getElementById("toast"); el.textContent = message; el.classList.add("show");
  clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => el.classList.remove("show"), 3300);
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {credentials:"same-origin", headers:{"Content-Type":"application/json", ...(options.headers || {})}, ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "Something went wrong. Please try again.");
  return body;
}
async function loadData() {
  const [products, me, config] = await Promise.all([api("/products"), api("/me"), api("/config")]);
  state.products = products.products; state.me = me.user; state.heroImage = config.hero_image;
  syncPromo(); route(); updateCartCount();
}
function productById(id) { return state.products.find(item => item.id === Number(id)); }
function activeProducts() { return state.products.filter(item => item.active); }
function salePrice(product) { return Math.round(product.price * (100 - product.discount) / 100); }
function offerSummary() {
  const items = activeProducts().filter(item => item.discount > 0);
  const percent = Math.max(0, ...items.map(item => item.discount));
  const categories = [...new Set(items.map(item => item.category))];
  const label = items.every(item => item.discount === percent)
    ? `${percent}% off selected ${categories.join(" & ")}`
    : `Up to ${percent}% off selected pieces`;
  return {items, percent, label};
}
function syncPromo() {
  const offer = offerSummary();
  document.querySelector(".announcement").hidden = !offer.items.length;
  document.getElementById("announcement-copy").textContent = offer.label;
}
function art(label, image, classes = "", extra = "") {
  return image ? `<div class="${classes}"><img src="${escapeHtml(image)}" alt="${escapeHtml(label)}" loading="lazy" ${extra}></div>` : `<div class="${classes} placeholder" data-label="${escapeHtml(label)}" aria-label="Photo placeholder for ${escapeHtml(label)}"></div>`;
}
function productCard(p) {
  return `<article class="product-card" data-category="${escapeHtml(p.category)}">
    <div class="product-image" data-product="${p.id}" role="button" tabindex="0" aria-label="View ${escapeHtml(p.name)}">
      ${p.discount ? `<span class="product-label">${p.discount}% off</span>` : (p.featured ? `<span class="product-label">The edit</span>` : "")}
      ${art(p.category, p.image, "product-art")}
      <button class="quick-add" type="button" data-add="${p.id}" aria-label="Add ${escapeHtml(p.name)} to bag">+</button>
    </div><div class="product-info"><div><div class="product-name">${escapeHtml(p.name)}</div><div class="product-category">${escapeHtml(p.category)}</div></div><div class="product-price">${p.discount ? `<span class="old-price">${money(p.price)}</span>` : ""}${money(salePrice(p))}</div></div>
  </article>`;
}
function productGrid(products) { return products.length ? `<div class="product-grid">${products.map(productCard).join("")}</div>` : `<div class="empty-state"><h3>Nothing in this edit yet.</h3><p>Try another category or search term.</p><a href="#shop">Shop everything ↗</a></div>`; }
function renderHome() {
  const picks = activeProducts().filter(p => p.featured).slice(0, 4);
  const selection = picks.length ? picks : activeProducts().slice(0, 4);
  const offer = offerSummary();
  app.innerHTML = `<section class="hero"><div class="hero-copy"><span class="eyebrow">THE EVERYDAY COLLECTION · 01/04</span><h1>Good things<br>for <em>going<br>places.</em></h1><p>Easy pieces, good details, and room for a little spontaneity. Meet the things you will reach for again and again.</p><a class="button button-dark" href="#shop">Explore the collection <span>↗</span></a><div class="hero-index">MORROW EDIT / 2026</div></div><div class="hero-art"><div class="hero-placeholder" ${state.heroImage ? "hidden" : ""}><div class="hero-placeholder-inner"><span>YOUR CAMPAIGN PHOTO</span></div></div>${state.heroImage ? `<div class="hero-image"><img src="/images/hero.jpg" alt="Morrow Edit campaign"></div>` : ""}<div class="hero-mark">✳</div><div class="hero-floating"><small>THE CURRENT EDIT</small><strong>Wear it your way. ↗</strong></div></div></section>
    <section class="section shell"><div class="section-header"><div><span class="eyebrow">FIND YOUR WAY IN</span><h2>Shop by category</h2></div><a class="subtle-link" href="#shop">View everything ↗</a></div><div class="category-grid">${CATEGORIES.map((category,i) => { const img = activeProducts().find(p => p.category === category && p.image)?.image || ""; return `<a class="category-card" href="#category/${category}">${art(category, img, "category-image", "") }<div class="category-name"><span>${category[0].toUpperCase()+category.slice(1)}</span><span>↗</span></div></a>`; }).join("")}</div></section>
    ${offer.items.length ? `<section class="offer-band"><div class="shell offer-layout"><div class="offer-copy"><span class="eyebrow">A LITTLE SOMETHING EXTRA</span><h2>The current<br>edit is on.</h2><p>${escapeHtml(offer.label)}. Savings are already reflected in the price. No code needed.</p><a class="button button-light" href="#offers">Shop the offer <span>↗</span></a></div><div class="offer-visual" data-offer="${offer.percent}%"><span>SELECTED PIECES ONLY ↗</span></div></div></section>` : ""}
    <section class="section shell"><div class="section-header"><div><span class="eyebrow">A FEW FAVOURITES</span><h2>Made for your everyday</h2></div><a class="subtle-link" href="#shop">Shop all pieces ↗</a></div>${productGrid(selection)}<div class="editorial-note"><p>Simple pieces. Interesting days.<br>Take the good stuff with you.</p><span>THE MORROW POINT OF VIEW ↗</span></div></section>`;
}
function currentRoute() { return decodeURIComponent(location.hash.replace(/^#/, "") || "home"); }
function shopProducts(category, offers) {
  let list = activeProducts();
  if (category) list = list.filter(p => p.category === category);
  if (offers) list = list.filter(p => p.discount > 0);
  if (state.query) { const q = state.query.toLowerCase(); list = list.filter(p => `${p.name} ${p.category} ${p.description}`.toLowerCase().includes(q)); }
  if (state.sort === "price-low") list.sort((a,b) => salePrice(a)-salePrice(b));
  else if (state.sort === "price-high") list.sort((a,b) => salePrice(b)-salePrice(a));
  else if (state.sort === "new") list.sort((a,b) => b.id-a.id);
  else list.sort((a,b) => Number(b.featured)-Number(a.featured) || a.id-b.id);
  return list;
}
function renderShop(category = "", offers = false) {
  const title = state.query ? `Results for “${state.query}”` : offers ? "The current offer" : category ? category[0].toUpperCase()+category.slice(1) : "The full edit";
  const description = offers ? "A little extra on selected bags and accessories. Prices shown already include the discount." : category ? CATEGORY_NOTES[category] : "Clothing, accessories, bags and luggage for whatever the day brings.";
  app.innerHTML = `<div class="page shell"><div class="page-heading"><div><span class="eyebrow">SHOP / ${offers ? "OFFER" : category ? category.toUpperCase() : "ALL"}</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}${state.query ? ` <button class="clear-search" id="clear-search">Clear search ↗</button>` : ""}</p></div><span class="eyebrow">${shopProducts(category, offers).length} PIECES</span></div><div class="filter-row"><a class="filter-chip ${!category && !offers ? "active" : ""}" href="#shop">All</a>${CATEGORIES.map(c => `<a class="filter-chip ${category===c ? "active" : ""}" href="#category/${c}">${c[0].toUpperCase()+c.slice(1)}</a>`).join("")}<a class="filter-chip ${offers ? "active" : ""}" href="#offers">Offers</a><select class="sort-select" id="sort-select" aria-label="Sort products"><option value="featured">Featured</option><option value="new">Newest</option><option value="price-low">Price: low to high</option><option value="price-high">Price: high to low</option></select></div>${productGrid(shopProducts(category, offers))}</div>`;
  document.getElementById("sort-select").value = state.sort;
}
function renderAccount() {
  if (state.me) {
    app.innerHTML = `<div class="page shell account-layout"><div class="account-aside"><span class="eyebrow">YOUR SPACE</span><h1>Welcome back,<br>${escapeHtml(state.me.name.split(" ")[0])}.</h1><p>Your orders and account live here. Keep the good things close.</p></div><div class="account-card"><span class="eyebrow">ACCOUNT</span><h2>Your details</h2><p>${escapeHtml(state.me.name)}<br>${escapeHtml(state.me.email)}</p><div class="account-links"><a href="#orders">View your orders ↗</a>${state.me.is_admin ? `<a href="#admin">Manage shop ↗</a>` : ""}</div><button class="button button-light" type="button" id="logout-button" style="margin-top:35px">Log out <span>↗</span></button></div></div>`;
    return;
  }
  const register = state.authTab === "register";
  app.innerHTML = `<div class="page shell account-layout"><div class="account-aside"><span class="eyebrow">A PLACE FOR YOUR PICKS</span><h1>Nice to see<br>you here.</h1><p>Sign in to save your orders. New around here? Your account takes just a moment.</p></div><div class="account-card"><div class="tabs"><button class="tab ${!register ? "active" : ""}" type="button" data-auth-tab="login">Log in</button><button class="tab ${register ? "active" : ""}" type="button" data-auth-tab="register">Create account</button></div><h2>${register ? "Create your account" : "Welcome back"}</h2><p>${register ? "A few details, then you are in." : "Enter your details to continue."}</p><form id="auth-form">${register ? `<label class="field"><span>Name</span><input name="name" required maxlength="80" autocomplete="name" placeholder="Your name"></label>` : ""}<label class="field"><span>Email</span><input type="email" name="email" required autocomplete="email" placeholder="you@example.com"></label><label class="field"><span>Password</span><input type="password" name="password" required minlength="8" autocomplete="${register ? "new-password" : "current-password"}" placeholder="At least 8 characters"></label><button class="button button-dark full" type="submit">${register ? "Create account" : "Log in"} <span>↗</span></button><div class="form-message" id="auth-message" role="status"></div></form></div></div>`;
}
async function renderOrders() {
  if (!state.me) { location.hash = "#account"; toast("Log in to view your orders."); return; }
  try { state.orders = (await api("/orders")).orders; } catch (e) { toast(e.message); }
  app.innerHTML = `<div class="page shell"><div class="page-heading"><div><span class="eyebrow">YOUR ACCOUNT</span><h1>Your orders</h1><p>A record of the pieces you picked.</p></div><a class="subtle-link" href="#account">Back to account ↗</a></div>${state.orders.length ? state.orders.map(o => `<div class="order-card"><div><strong>Order #${o.id}</strong><br><span>${new Date(o.created_at).toLocaleDateString("en-IN",{day:"numeric",month:"long",year:"numeric"})}</span><br><span>${o.items.map(i => `${i.quantity} × ${escapeHtml(i.name)}`).join(", ")}</span></div><div class="order-actions"><strong>${money(o.total)}</strong><button type="button" class="remove-order" data-remove-order="${o.id}" aria-label="Remove order number ${o.id}">Remove order</button></div></div>`).join("") : `<div class="empty-state"><h3>No orders yet.</h3><p>Good things are waiting.</p><a href="#shop">Browse the collection ↗</a></div>`}</div>`;
}
function adminForm(product = null) {
  return `<div class="admin-form-wrap" id="admin-form-wrap"><h2>${product ? "Edit item" : "Add a new item"}</h2><form class="admin-form" id="admin-form"><input type="hidden" name="id" value="${product?.id || ""}"><label class="field"><span>Item name</span><input name="name" required maxlength="100" value="${escapeHtml(product?.name || "")}" placeholder="e.g. The Everyday Tote"></label><label class="field"><span>Category</span><select name="category" required>${CATEGORIES.map(c => `<option value="${c}" ${product?.category===c ? "selected" : ""}>${c[0].toUpperCase()+c.slice(1)}</option>`).join("")}</select></label><label class="field"><span>Price (₹)</span><input name="price" type="number" min="1" step="1" required value="${product ? product.price/100 : ""}"></label><label class="field"><span>Offer discount (%)</span><input name="discount" type="number" min="0" max="90" step="1" value="${product?.discount || 0}"></label><label class="field wide"><span>Photo filename</span><input name="image" value="${escapeHtml(product?.image?.replace(/^\/images\//, "") || "")}" placeholder="everyday-tote.webp"><div class="admin-help">Place the photo in static/images, then enter its filename here.</div></label><label class="field wide"><span>Short description</span><textarea name="description" maxlength="500" placeholder="A sentence or two about this piece.">${escapeHtml(product?.description || "")}</textarea></label><label class="field"><span>Stock available</span><input name="stock" type="number" min="0" step="1" required value="${product?.stock ?? 20}"></label><label class="field"><span>Visibility</span><select name="active"><option value="1" ${product?.active!==false ? "selected" : ""}>Visible</option><option value="0" ${product?.active===false ? "selected" : ""}>Hidden</option></select></label><label class="field"><span>Featured on home</span><select name="featured"><option value="0" ${!product?.featured ? "selected" : ""}>No</option><option value="1" ${product?.featured ? "selected" : ""}>Yes</option></select></label><div class="form-actions"><button type="button" class="button button-light" id="cancel-admin">Cancel</button><button type="submit" class="button button-dark">Save item ↗</button></div><div class="form-message wide" id="admin-message" role="status"></div></form></div>`;
}
function renderAdmin() {
  if (!state.me?.is_admin) { location.hash = "#account"; toast("Log in with an admin account to manage items."); return; }
  app.innerHTML = `<div class="page shell"><div class="page-heading"><div><span class="eyebrow">SHOP CONTROL</span><h1>Manage items</h1><p>Add pieces, update prices and photos, or hide anything that is not ready.</p></div><a class="subtle-link" href="#shop">View shop ↗</a></div><div class="admin-toolbar"><span class="eyebrow">${state.products.length} TOTAL ITEMS</span><button class="button button-dark" id="new-item">+ Add item</button></div><div id="admin-form-slot">${state.editing === "new" ? adminForm() : state.editing ? adminForm(productById(state.editing)) : ""}</div><div class="admin-list">${state.products.map(p => `<div class="admin-row"><div class="admin-thumb">${p.image ? `<img src="${escapeHtml(p.image)}" alt="">` : ""}</div><div><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(p.category)} · ${p.active ? "Visible" : "Hidden"} · ${p.stock} in stock${p.discount ? ` · ${p.discount}% off` : ""}</small></div><span class="admin-price">${money(salePrice(p))}</span><div class="admin-actions"><button class="small-btn" data-edit="${p.id}">Edit</button><button class="small-btn" data-delete="${p.id}">Delete</button></div></div>`).join("")}</div></div>`;
  if (state.editing) document.getElementById("admin-form-wrap")?.scrollIntoView({block:"center",behavior:"smooth"});
}
function route() {
  closeCart(); closeProduct(); closeMobile();
  const path = currentRoute();
  if (path === "home" || path === "") renderHome();
  else if (path === "shop") renderShop();
  else if (path === "offers") renderShop("", true);
  else if (path.startsWith("category/") && CATEGORIES.includes(path.split("/")[1])) renderShop(path.split("/")[1]);
  else if (path === "account") renderAccount();
  else if (path === "orders") { renderOrders(); }
  else if (path === "admin") renderAdmin();
  else renderShop();
  window.scrollTo({top:0,behavior:"instant"});
}
function updateCartCount() {
  const count = Object.values(state.cart).reduce((a,b) => a + b, 0);
  document.getElementById("cart-count").textContent = count;
  document.getElementById("drawer-count").textContent = `(${count})`;
}
function cartEntries() { return Object.entries(state.cart).map(([id,quantity]) => ({product:productById(id),quantity})).filter(x => x.product && x.quantity > 0); }
function renderCart() {
  const items = cartEntries(), sum = items.reduce((total,{product,quantity}) => total + salePrice(product)*quantity,0);
  document.getElementById("drawer-total").textContent = money(sum);
  document.getElementById("drawer-items").innerHTML = items.length ? items.map(({product:p,quantity}) => `<div class="cart-row"><div class="cart-thumb">${p.image ? `<img src="${escapeHtml(p.image)}" alt="">` : ""}</div><div><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(p.category)}</small><div class="qty"><button data-qty="${p.id}" data-delta="-1" aria-label="Remove one ${escapeHtml(p.name)}">−</button><span>${quantity}</span><button data-qty="${p.id}" data-delta="1" aria-label="Add one ${escapeHtml(p.name)}">+</button></div></div><span>${money(salePrice(p)*quantity)}</span></div>`).join("") : `<div class="empty-state"><h3>Your bag is empty.</h3><p>Find something you love.</p><a href="#shop" id="bag-shop-link">Browse the collection ↗</a></div>`;
  document.getElementById("place-order").disabled = !items.length;
}
function openCart() { renderCart(); document.getElementById("scrim").hidden=false; document.getElementById("cart-drawer").hidden=false; document.body.style.overflow="hidden"; document.getElementById("close-cart").focus(); }
function closeCart() { document.getElementById("scrim").hidden=true; document.getElementById("cart-drawer").hidden=true; document.body.style.overflow=""; }
function addToCart(id) { const p=productById(id); if (!p || !p.active) return; if ((state.cart[id]||0) >= p.stock) { toast("No more stock is available for this item."); return; } state.cart[id]=(state.cart[id]||0)+1; saveCart(); toast(`${p.name} added to your bag.`); }
function openProduct(id) {
  const p=productById(id); if (!p) return;
  document.getElementById("dialog-content").innerHTML=`<div class="dialog-layout">${art(p.category,p.image,"dialog-art")}<div class="dialog-copy"><span class="eyebrow">${escapeHtml(p.category)} / MORROW EDIT</span><h2>${escapeHtml(p.name)}</h2><div class="dialog-price">${p.discount ? `<span class="old-price">${money(p.price)}</span>` : ""}${money(salePrice(p))}</div><p>${escapeHtml(p.description || "An easy piece for everyday moments.")}</p><button class="button button-dark full" data-add="${p.id}" ${p.stock<1 ? "disabled" : ""}>${p.stock<1 ? "Sold out" : "Add to bag"} <span>↗</span></button></div></div>`;
  document.getElementById("product-dialog").showModal();
}
function closeProduct() { const d=document.getElementById("product-dialog"); if (d.open) d.close(); }
function closeMobile() { const m=document.getElementById("mobile-nav"); m.hidden=true; document.querySelector(".menu-toggle").setAttribute("aria-expanded","false"); }
async function submitAuth(form) {
  const data=Object.fromEntries(new FormData(form)); const msg=document.getElementById("auth-message"); msg.textContent="";
  try { const result=await api(state.authTab==="register" ? "/register" : "/login",{method:"POST",body:JSON.stringify(data)}); state.me=result.user; if (state.me.is_admin) state.products=(await api("/products?all=1")).products; toast(`Welcome, ${state.me.name.split(" ")[0]}.`); location.hash="#account"; route(); }
  catch(e) { msg.textContent=e.message; }
}
async function submitAdmin(form) {
  const fields=Object.fromEntries(new FormData(form)); const id=fields.id; const msg=document.getElementById("admin-message");
  const data={name:fields.name,category:fields.category,price:Math.round(Number(fields.price)*100),discount:Number(fields.discount),image:fields.image.trim() ? `/images/${fields.image.trim()}` : "",description:fields.description,stock:Number(fields.stock),active:fields.active==="1",featured:fields.featured==="1"};
  try { await api(id ? `/admin/products/${id}` : "/admin/products",{method:id ? "PUT" : "POST",body:JSON.stringify(data)}); state.products=(await api("/products?all=1")).products; syncPromo(); state.editing=null; renderAdmin(); toast("Item saved."); }
  catch(e) { msg.textContent=e.message; }
}
async function placeOrder() {
  if (!state.me) { closeCart(); location.hash="#account"; toast("Log in to place an order."); return; }
  const items=cartEntries().map(({product,quantity}) => ({product_id:product.id,quantity}));
  if (!items.length) return;
  const button=document.getElementById("place-order"); button.disabled=true; button.textContent="Placing order…";
  try { const order=await api("/orders",{method:"POST",body:JSON.stringify({items})}); state.cart={}; saveCart(); closeCart(); state.products=(await api(state.me?.is_admin ? "/products?all=1" : "/products")).products; location.hash="#orders"; route(); toast(`Order #${order.order_id} placed. No payment was collected.`); }
  catch(e) { toast(e.message); button.disabled=false; button.innerHTML="Place order <span>↗</span>"; }
}
document.addEventListener("click", async event => {
  const add=event.target.closest("[data-add]"); if (add) { event.stopPropagation(); addToCart(add.dataset.add); return; }
  const product=event.target.closest("[data-product]"); if (product) { openProduct(product.dataset.product); return; }
  if (event.target.closest(".cart-toggle")) { openCart(); return; }
  if (event.target.closest("#close-cart") || event.target.closest("#scrim") || event.target.closest("#bag-shop-link")) { closeCart(); return; }
  if (event.target.closest("#close-product")) { closeProduct(); return; }
  if (event.target.closest("#clear-search")) { state.query=""; document.getElementById("search-input").value=""; route(); return; }
  const qty=event.target.closest("[data-qty]"); if (qty) { const id=qty.dataset.qty; state.cart[id]=Math.max(0,Math.min(productById(id)?.stock ?? 0,(state.cart[id]||0)+Number(qty.dataset.delta))); if (!state.cart[id]) delete state.cart[id]; saveCart(); return; }
  if (event.target.closest("#place-order")) { placeOrder(); return; }
  if (event.target.closest(".search-toggle")) { const panel=document.getElementById("search-panel"); panel.hidden=!panel.hidden; if (!panel.hidden) document.getElementById("search-input").focus(); return; }
  if (event.target.closest(".menu-toggle")) { const m=document.getElementById("mobile-nav"); m.hidden=!m.hidden; document.querySelector(".menu-toggle").setAttribute("aria-expanded",String(!m.hidden)); return; }
  if (event.target.closest(".mobile-nav a")) { closeMobile(); return; }
  const tab=event.target.closest("[data-auth-tab]"); if (tab) { state.authTab=tab.dataset.authTab; renderAccount(); return; }
  if (event.target.closest("#logout-button")) { try { await api("/logout",{method:"POST",body:"{}"}); state.me=null; route(); toast("Logged out."); } catch(e) { toast(e.message); } return; }
  const removeOrder=event.target.closest("[data-remove-order]"); if (removeOrder) { const id=Number(removeOrder.dataset.removeOrder); if (!confirm(`Remove order #${id}? Its items will be returned to stock.`)) return; removeOrder.disabled=true; try { await api(`/orders/${id}`,{method:"DELETE"}); state.products=(await api(state.me?.is_admin ? "/products?all=1" : "/products")).products; await renderOrders(); toast(`Order #${id} removed.`); } catch(e) { removeOrder.disabled=false; toast(e.message); } return; }
  if (event.target.closest("#new-item")) { state.editing="new"; renderAdmin(); return; }
  const edit=event.target.closest("[data-edit]"); if (edit) { state.editing=Number(edit.dataset.edit); renderAdmin(); return; }
  if (event.target.closest("#cancel-admin")) { state.editing=null; renderAdmin(); return; }
  const del=event.target.closest("[data-delete]"); if (del) { const p=productById(del.dataset.delete); if (!confirm(`Delete ${p.name}?`)) return; try { await api(`/admin/products/${p.id}`,{method:"DELETE",body:"{}"}); state.products=(await api("/products?all=1")).products; syncPromo(); renderAdmin(); toast("Item deleted."); } catch(e) { toast(e.message); } }
});
document.addEventListener("submit", event => { if (event.target.id==="auth-form") { event.preventDefault(); submitAuth(event.target); } if (event.target.id==="admin-form") { event.preventDefault(); submitAdmin(event.target); } });
document.addEventListener("change", event => { if (event.target.id==="sort-select") { state.sort=event.target.value; route(); } });
document.addEventListener("input", event => { if (event.target.id==="search-input") { state.query=event.target.value.trim(); if (currentRoute()!=="shop") location.hash="#shop"; else renderShop(); } });
document.addEventListener("keydown", event => { if (event.key==="Escape") closeCart(); if ((event.key==="Enter" || event.key===" ") && event.target.matches("[data-product]")) { event.preventDefault(); openProduct(event.target.dataset.product); } });
window.addEventListener("hashchange", route);
loadData().catch(error => { app.innerHTML=`<div class="page shell empty-state"><h3>Store unavailable</h3><p>${escapeHtml(error.message)}</p><p>Start the local server, then refresh this page.</p></div>`; });
