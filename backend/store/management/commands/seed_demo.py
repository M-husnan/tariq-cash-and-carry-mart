from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from store.models import Branch, BranchStock, Category, PriceTier, Product

class Command(BaseCommand):
    help = "Create a small clearly-demonstration catalog for local development."
    def handle(self, *args, **options):
        branch, _ = Branch.objects.get_or_create(code="karachi-central", defaults={
            "name": "Tariq Cash and Carry Mart — Karachi Central", "address": "Demo Market Road", "city": "Karachi",
            "delivery_fee": Decimal("180.00"), "free_delivery_threshold": Decimal("5000.00"),
            "minimum_order": Decimal("500.00"),
        })
        examples = [
            ("fresh-produce", "Fresh Produce", [("Sindh Mangoes", "BB-FR-001", "Fresh", "kg", "1 kg", "650.00", "520.00", 6), ("Red Tomatoes", "BB-FR-002", "Fresh", "kg", "1 kg", "180.00", "145.00", 10)]),
            ("grocery-pantry", "Grocery & Pantry", [("Basmati Rice", "BB-GR-001", "Premium Harvest", "kg", "5 kg bag", "2100.00", "1850.00", 8), ("Sunflower Cooking Oil", "BB-GR-002", "Daily Gold", "litre", "5 L can", "2850.00", "2550.00", 8)]),
            ("household", "Cleaning & Household", [("Dishwashing Liquid", "BB-HH-001", "Sparkle", "piece", "750 ml", "420.00", "360.00", 12)]),
            ("dairy-bakery", "Dairy & Bakery", [("UHT Milk", "BB-DB-001", "Farm Fresh", "piece", "1 L carton", "330.00", "290.00", 12)]),
        ]
        count = 0
        for slug, name, products in examples:
            category, _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})
            for product_name, sku, brand, unit, pack, retail, wholesale, stock_qty in products:
                product, created = Product.objects.get_or_create(slug=sku.lower(), defaults={
                    "name": product_name, "sku": sku, "brand": brand, "category": category,
                    "description": f"{product_name} — sample catalog item for development only.",
                    "unit": unit, "pack_size": pack, "retail_price": Decimal(retail),
                    "wholesale_price": Decimal(wholesale), "wholesale_min_quantity": 4,
                    "is_featured": count < 3,
                })
                BranchStock.objects.update_or_create(branch=branch, product=product, defaults={"quantity": stock_qty})
                PriceTier.objects.get_or_create(product=product, customer_type=PriceTier.CustomerType.ALL, min_quantity=12, defaults={"unit_price": Decimal(wholesale)})
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Demo catalog ready: {count} sample products at {branch.name}. Demo prices are not live prices."))

