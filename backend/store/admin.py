import csv
import io
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.text import slugify
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import (Address, Branch, BranchStock, CartItem, Category,
                     DiscountCode, Favorite, Notification, Order, OrderItem,
                     OrderStatusEvent, PriceTier, Product, ProductImage,
                     Promotion, User)

class PriceTierInline(admin.TabularInline):
    model = PriceTier
    extra = 0

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0

class BranchStockInline(admin.TabularInline):
    model = BranchStock
    extra = 0

@admin.action(description="Export selected products and branch stock as CSV")
def export_products_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="tariq-mart-products.csv"'
    writer = csv.writer(response)
    writer.writerow(["name", "sku", "category_slug", "brand", "unit", "pack_size", "retail_price", "wholesale_price", "branch_code", "stock"])
    for product in queryset.select_related("category").prefetch_related("branch_stock__branch"):
        stock_rows = list(product.branch_stock.all()) or [None]
        for row in stock_rows:
            writer.writerow([product.name, product.sku, product.category.slug, product.brand, product.unit, product.pack_size, product.retail_price, product.wholesale_price or "", row.branch.code if row else "", row.quantity if row else ""])
    return response

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "retail_price", "wholesale_price", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "category", "brand")
    search_fields = ("name", "name_ur", "sku", "barcode", "brand")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, PriceTierInline, BranchStockInline]
    actions = [export_products_csv]
    change_list_template = "admin/store/product/change_list.html"

    def get_urls(self):
        custom = [
            path("daily-inventory-import/", self.admin_site.admin_view(self.import_daily_inventory), name="store_product_daily_inventory_import"),
            path("daily-inventory-template.csv", self.admin_site.admin_view(self.download_inventory_template), name="store_product_daily_inventory_template"),
        ]
        return custom + super().get_urls()

    def download_inventory_template(self, request):
        if not request.user.has_perm("store.change_product"):
            return HttpResponseForbidden("You do not have permission to download the inventory template.")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="tariq-mart-inventory-template.csv"'
        csv.writer(response).writerow(["ITEMCODE", "ITEMNAME", "QTY", "RATE", "PSIZE", "MNF", "CATAGRY", "BARCODE"])
        return response

    def import_daily_inventory(self, request):
        if not request.user.has_perm("store.change_product"):
            return HttpResponseForbidden("You do not have permission to import inventory.")
        if request.method == "POST":
            upload = request.FILES.get("inventory_file")
            branch_id = request.POST.get("branch")
            full_snapshot = request.POST.get("full_snapshot") == "on"
            if not upload:
                messages.error(request, "Choose a CSV inventory export first.")
            elif upload.name.lower().endswith(".dmp"):
                messages.error(request, "This is an Oracle .DMP backup. Export the STOCK table as CSV first; Django cannot import this binary Oracle export directly.")
            elif not upload.name.lower().endswith(".csv"):
                messages.error(request, "Upload a UTF-8 CSV file exported from the store software.")
            elif upload.size > 30 * 1024 * 1024:
                messages.error(request, "CSV files must be 30 MB or smaller.")
            else:
                try:
                    branch = Branch.objects.get(pk=branch_id, is_active=True)
                    text = io.TextIOWrapper(upload.file, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text)
                    if not reader.fieldnames:
                        raise ValueError("The CSV has no header row.")
                    rows = []
                    seen_skus = set()
                    for line_number, source in enumerate(reader, start=2):
                        row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in source.items()}
                        def pick(*keys):
                            for key in keys:
                                if row.get(key): return row[key]
                            return ""
                        sku = pick("sku", "itemcode", "item_code", "barcode")[:60]
                        name = pick("name", "itemname", "item_name", "product_name")
                        raw_price = pick("retail_price", "rate", "sale_rate", "price")
                        raw_qty = pick("quantity", "qty", "stock", "on_hand")
                        if not sku or not name or not raw_price or not raw_qty:
                            raise ValueError(f"CSV row {line_number} needs item code, item name, retail price, and quantity.")
                        if sku in seen_skus:
                            raise ValueError(f"CSV row {line_number} repeats item code {sku}.")
                        seen_skus.add(sku)
                        try:
                            price = Decimal(raw_price.replace(",", ""))
                            quantity_decimal = Decimal(raw_qty.replace(",", ""))
                            quantity = int(quantity_decimal)
                            if quantity_decimal != quantity:
                                raise ValueError("quantity must be a whole number")
                            wholesale_raw = pick("wholesale_price", "wholesale", "business_price")
                            wholesale = Decimal(wholesale_raw.replace(",", "")) if wholesale_raw else None
                        except (InvalidOperation, ValueError) as exc:
                            raise ValueError(f"CSV row {line_number} has an invalid price or quantity.") from exc
                        if price < 0 or quantity < 0 or (wholesale is not None and wholesale < 0):
                            raise ValueError(f"CSV row {line_number} has a negative price or quantity.")
                        category_name = pick("category", "catagry", "category_name") or "Uncategorized"
                        category_slug = slugify(category_name) or "category-" + sha1(category_name.encode("utf-8")).hexdigest()[:10]
                        image_url = pick("image_url", "primary_image", "photo_url")
                        if image_url and (not image_url.startswith("https://") or len(image_url) > 1000):
                            raise ValueError(f"CSV row {line_number} has an invalid image URL; use an HTTPS image URL under 1,000 characters.")
                        rows.append({
                            "sku": sku[:60], "name": name[:180], "price": price, "quantity": quantity,
                            "category_name": category_name[:100], "category_slug": category_slug[:50],
                            "brand": pick("brand", "mnf", "manufacturer")[:100],
                            "pack_size": pick("pack_size", "psize", "pack")[:80],
                            "unit": (pick("unit") or "piece")[:50], "barcode": pick("barcode")[:80],
                            "wholesale_price": wholesale, "image_url": image_url,
                        })
                        if len(rows) > 50000:
                            raise ValueError("CSV contains more than 50,000 inventory rows.")
                    if not rows:
                        raise ValueError("The CSV contains no inventory rows.")
                    with transaction.atomic():
                        imported_ids = []
                        for row in rows:
                            category, _ = Category.objects.get_or_create(slug=row["category_slug"], defaults={"name": row["category_name"]})
                            product_slug = f"{slugify(row['name'])[:38]}-{slugify(row['sku'])[:20]}".strip("-")
                            if not product_slug: product_slug = "item-" + sha1(row["sku"].encode()).hexdigest()[:12]
                            defaults = {"name": row["name"], "slug": product_slug, "category": category,
                                        "brand": row["brand"], "pack_size": row["pack_size"], "unit": row["unit"],
                                        "barcode": row["barcode"], "retail_price": row["price"]}
                            if row["image_url"]: defaults["external_image_url"] = row["image_url"]
                            if row["wholesale_price"] is not None: defaults["wholesale_price"] = row["wholesale_price"]
                            product, _ = Product.objects.update_or_create(sku=row["sku"], defaults=defaults)
                            BranchStock.objects.update_or_create(branch=branch, product=product, defaults={"quantity": row["quantity"]})
                            imported_ids.append(product.pk)
                        if full_snapshot:
                            BranchStock.objects.filter(branch=branch).exclude(product_id__in=imported_ids).update(quantity=0)
                    messages.success(request, f"Inventory imported: {len(rows)} products updated for {branch.name}. Existing product photos were kept. " + ("Products missing from this full snapshot now have zero stock at this branch." if full_snapshot else "Products omitted from the file were left unchanged."))
                    return redirect("admin:store_product_changelist")
                except (Branch.DoesNotExist, csv.Error, UnicodeDecodeError, ValueError) as exc:
                    messages.error(request, str(exc))
        context = {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": "Import daily inventory CSV", "branches": Branch.objects.filter(is_active=True).order_by("city", "name"),
        }
        return TemplateResponse(request, "admin/store/product/import_daily_inventory.html", context)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "branch", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "payment_status", "payment_method", "fulfillment", "branch")
    search_fields = ("id", "user__username", "user__email")
    readonly_fields = ("id", "subtotal", "tax_total", "discount_total", "delivery_fee", "total", "created_at", "updated_at")
    inlines = []
    def save_model(self, request, obj, form, change):
        old_status = None
        if change:
            old_status = Order.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
        super().save_model(request, obj, form, change)
        if old_status != obj.status:
            OrderStatusEvent.objects.create(order=obj, status=obj.status, note="Updated in admin", changed_by=request.user)
            Notification.objects.create(user=obj.user, title="Order update", body=f"Order {str(obj.id)[:8]}: {obj.get_status_display()}.")

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Store account", {"fields": ("role", "phone_number", "preferred_language", "business_name", "business_approved", "membership_number")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (("Store account", {"fields": ("role", "phone_number", "business_name")}),)
    list_display = ("username", "email", "role", "business_approved", "is_staff")
    list_filter = ("role", "business_approved", "is_staff")

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "city", "is_active", "delivery_enabled", "pickup_enabled")
    search_fields = ("name", "code", "city")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(BranchStock)
class BranchStockAdmin(admin.ModelAdmin):
    list_display = ("branch", "product", "quantity", "low_stock_threshold", "updated_at")
    list_filter = ("branch",)
    search_fields = ("product__name", "product__sku", "branch__name")

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "product_name", "sku", "unit", "quantity", "unit_price", "tax_percent", "line_total")

class OrderStatusInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    can_delete = False
    readonly_fields = ("status", "note", "changed_by", "created_at")

OrderAdmin.inlines = [OrderItemInline, OrderStatusInline]

admin.site.register(Address)
admin.site.register(CartItem)
admin.site.register(DiscountCode)
admin.site.register(Promotion)
admin.site.register(Notification)
admin.site.register(Favorite)
admin.site.site_header = "Tariq Cash and Carry Mart — Store Operations"
admin.site.site_title = "Tariq Cash and Carry Mart Admin"
admin.site.index_title = "Catalog, inventory, and orders"
