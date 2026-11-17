# Tariq Cash and Carry Mart API (v1)

Base path: `/api/v1/`. JSON endpoints use `Authorization: Token <token>` where authentication is required. Monetary values are PKR decimal strings. Paginated list responses use `{ "count", "next", "previous", "results" }`.

## Public catalog

- `GET /health/` — health status.
- `GET /branches/` — active branches and delivery/pickup settings.
- `GET /categories/` — active categories.
- `GET /products/?q=rice&category=grocery-pantry&branch=1&sort=price_low` — search/filter. `sort`: `name`, `price_low`, `price_high`, `newest`; optional `brand`, `min_price`, `max_price`, `featured=true`, `quantity`.
- `GET /products/<slug>/` — product detail.
- `GET /promotions/` — currently active promotions.

## Authentication and profile

- `POST /auth/register/` — `{username,email,password,phone_number,role,business_name}`; `role` is `customer` or `business`.
- `POST /auth/login/` — `{username,password}`; returns `{token,user}`.
- `GET/PATCH /auth/me/` — current account; private fields are scoped to the signed-in user.

## Addresses and cart

- `GET/POST /addresses/`; `GET/PATCH/DELETE /addresses/<id>/`.
- `GET /cart/` — cart lines and subtotal.
- `POST /cart/` — `{product_id,branch_id,quantity}`; adds or replaces that product line.
- `PATCH /cart/items/<id>/` — `{quantity}`; `DELETE` removes a line.
- `GET /wishlist/` — signed-in customer's saved products. `POST /wishlist/` with `{product_id}` toggles a favorite.

## Checkout and orders

- `POST /checkout/` — `{branch_id,address_id,fulfillment,payment_method,discount_code,delivery_instructions,idempotency_key}`. `fulfillment` is `delivery` or `pickup`; the only valid pairings are `delivery` + `cod` (cash to rider) or `pickup` + `pay_at_store` (show invoice and pay cash at store). Card, online, and bank-transfer payments are rejected. The server recalculates prices, tax, discounts, delivery charges, and stock in a transaction.
- `GET /orders/`; `GET /orders/<uuid>/` — signed-in user's own orders.
- `POST /orders/<uuid>/cancel/` — cancel while status allows and restore reserved stock.
- `GET /orders/<uuid>/invoice/` — downloadable PDF invoice for the owner or staff.
- `PATCH /orders/<uuid>/status/` — staff/admin only; `{status,note}`.
- `GET /notifications/`; `POST /notifications/<id>/read/`.
- `GET /staff/reports/summary/` — staff/admin only; paid revenue, order status counts, top products, and low stock.

## Error behavior

Errors use a useful `detail` message when possible. Checkout rejects unavailable stock, invalid delivery mode, invalid address ownership, unconfigured payment methods, and ineligible promo codes. Never treat a client-provided price as authoritative.
