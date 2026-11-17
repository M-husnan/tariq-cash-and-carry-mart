# Tariq Cash and Carry Mart

An original retail and wholesale grocery app starter for Pakistan. It contains a Flutter customer app and a Django REST API/admin. It does not use Metro branding or assets. Demo catalog prices are sample data, not live store prices.

## Project layout

- `mobile/` — Flutter Android/iOS customer app.
- `backend/` — Django REST API and staff/admin console.
- `build.sh`, `render.yaml` — Render build/deploy configuration.
- `docs/API.md` — implemented API routes.

## Backend: local setup

Use Python 3.11.18 (or another Python version supported by the selected Django release). From the project root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python backend/manage.py makemigrations store
python backend/manage.py migrate
python backend/manage.py seed_demo
python backend/manage.py createsuperuser
python backend/manage.py runserver 0.0.0.0:8000
```

The default local database is SQLite for easy setup. Set `DATABASE_URL` to PostgreSQL for production. Set a unique `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=false` in production. Never commit `.env`.

Staff console: `http://127.0.0.1:8000/admin/`. Create a staff user in Django admin and grant the required permissions. The `seed_demo` command creates one branch and sample products only; change or remove those before taking real orders.

## Flutter: local setup and Android APK

Flutter and Android SDK must be installed on the build machine. If platform folders are not present, generate them once from `mobile/`:

```bash
cd mobile
flutter create . --platforms=android,ios
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
flutter build apk --release --dart-define=API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

The Android emulator reaches a local computer through `10.0.2.2`; a physical phone needs the computer's LAN IP. The APK is written to `mobile/build/app/outputs/flutter-apk/app-release.apk`.

## Render deployment

1. Push this project root to a new Git repository and create a Render Blueprint from `render.yaml`, or create a Python web service manually.
2. Provision PostgreSQL and set `DATABASE_URL` to the database's internal URL.
3. Set `DJANGO_ALLOWED_HOSTS` to the Render hostname (without `https://`). Set `CORS_ALLOWED_ORIGINS` to the Flutter web origin only if a web client is added. Set `CSRF_TRUSTED_ORIGINS` for any browser/admin origin.
4. Configure `CLOUDINARY_URL` for persistent product/category/promotion image storage. Without it, local development uses disk storage; Render instance disks are not a persistent media store.
5. Build command: `bash build.sh`. Start command: `cd backend && gunicorn config.wsgi:application --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`.
6. Set the resulting HTTPS API origin in the APK build command with `--dart-define=API_BASE_URL=https://YOUR-SERVICE.onrender.com`.

Do not deploy real orders on SQLite or temporary local media storage. Configure a persistent PostgreSQL database and media provider first. The Blueprint intentionally leaves `DATABASE_URL` and Cloudinary configuration for you to connect in Render; secret values are not in source.

## Implemented now

- Public branch/category/product catalog with search, category/brand/price filters, sorting, stock filtering, and pagination.
- Product favorites, image galleries, offers, in-app notifications, and a staff sales/low-stock summary API.
- Retail/business customer accounts, token login, profile endpoint, and account type display.
- Branch-specific stock and retail/wholesale price tiers.
- Authenticated cart, address book, server-side checkout totals, stock decrement, idempotency key, promo-code validation, order list/detail/cancel, staff status updates, and PDF invoices.
- Django admin for catalog, branch stock, price tiers, staff users, orders, promotions, discounts, and notifications.
- CSV product/stock export from the Product admin, command-line catalog import, and a Django Admin one-click daily inventory CSV importer. The importer accepts the converted Oracle STOCK CSV (SKU, name, quantity, retail_price, pack_size, brand, category, image_url), updates the selected branch immediately, and can zero stock for omitted items when the upload is confirmed as a complete snapshot. Existing product photos are preserved.
- Flutter catalog/search/categories, branch selection, sign-in/registration, cart editing, delivery/pickup checkout, order history, and shareable invoice PDF.

## Daily inventory refresh in Django Admin

Open **Admin → Products → Import daily inventory CSV**, choose a branch, upload the store software's complete stock CSV, and click **Update inventory**. The app reads the same database, so refreshed prices and quantities appear in the catalog after the import completes. Select **Full daily snapshot** only when the file contains every item for that branch; items missing from that snapshot are set to zero stock. Product photos already attached in Admin are kept.

Run `python -m pip install -r tools/requirements-dmp-converter.txt`, then convert each daily legacy Oracle backup with `python tools/convert_oracle_stock_dump.py daily-backup.DMP daily-inventory.csv`. The converter reads only grocery `STOCK`, uses `RATE` as the selling price, ignores `PRATE` and `RTLRATE`, and never reads medicine table `STOCK2`. It clamps negative quantities to zero and skips rows without a positive RATE so items cannot be sold at zero price. Upload its output in Admin. The supplied backup converted to 4,767 products; 100 rows without a positive RATE were left out. Product categories are inferred from item names when the source category is blank. The first converted catalog is included at `backend/data/initial_grocery_inventory.csv`; upload this once after creating the branch. A small verified image map is bundled in `tools/product_image_matches.csv` and is applied again on every daily conversion.

## External integrations and limits

- Checkout has exactly two cash-only choices: cash paid to the rider for home delivery, or cash paid at the store after showing the pickup invoice. Credit cards, debit cards, and online payments are not accepted.
- SMS OTP, push delivery, live delivery maps, and automated tax/legal compliance are not enabled. In-app order notifications are stored, but push requires Firebase setup.
- The account stores an English/Urdu preference, but translated Urdu strings and full right-to-left layout are not yet wired into the Flutter screens.
- Delivery time-slot capacity, customer-approved substitutions, loyalty-point accounting, and a return/refund workflow need a follow-up implementation before a real store launch.
- Product image uploads are managed in Django admin; production requires Cloudinary configuration. The customer app displays uploaded product images.
- CSV import: prepare `name,sku,category_slug,retail_price` columns (optional `brand,unit,pack_size,wholesale_price,stock,branch_code`) and run `python backend/manage.py import_catalog_csv path/to/catalog.csv`.
- The demo database seed is small. Import real inventory and tax rules only after confirming them with the store operator.
