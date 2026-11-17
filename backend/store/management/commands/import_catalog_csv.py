import csv
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from store.models import Branch, BranchStock, Category, Product

class Command(BaseCommand):
    help = "Import/update products from CSV columns: name,sku,category_slug,retail_price; optional brand,unit,pack_size,wholesale_price,stock,branch_code."
    def add_arguments(self, parser): parser.add_argument("csv_file")
    def handle(self, *args, **options):
        try:
            stream = open(options["csv_file"], newline="", encoding="utf-8-sig")
        except OSError as exc: raise CommandError(str(exc)) from exc
        created = updated = 0
        with stream:
            reader = csv.DictReader(stream)
            required = {"name", "sku", "category_slug", "retail_price"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise CommandError("CSV must include: name,sku,category_slug,retail_price")
            for line, row in enumerate(reader, start=2):
                try:
                    category = Category.objects.get(slug=row["category_slug"].strip(), is_active=True)
                    sku = row["sku"].strip()
                    defaults = {
                        "name": row["name"].strip(), "slug": slugify(row["name"])[:50] + "-" + slugify(sku)[:20],
                        "category": category, "brand": row.get("brand", "").strip(),
                        "unit": row.get("unit", "piece").strip() or "piece", "pack_size": row.get("pack_size", "").strip(),
                        "retail_price": Decimal(row["retail_price"]),
                        "wholesale_price": Decimal(row["wholesale_price"]) if row.get("wholesale_price", "").strip() else None,
                    }
                    product, was_created = Product.objects.update_or_create(sku=sku, defaults=defaults)
                    created += int(was_created); updated += int(not was_created)
                    if row.get("branch_code", "").strip() and row.get("stock", "").strip():
                        branch = Branch.objects.get(code=row["branch_code"].strip())
                        BranchStock.objects.update_or_create(branch=branch, product=product, defaults={"quantity": int(row["stock"])})
                except Exception as exc:
                    raise CommandError(f"CSV line {line}: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Import complete: {created} created, {updated} updated."))
