import uuid
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        BUSINESS = "business", "Business buyer"
        STAFF = "staff", "Store staff"
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone_number = models.CharField(max_length=24, blank=True)
    preferred_language = models.CharField(max_length=5, choices=[("en", "English"), ("ur", "Urdu")], default="en")
    business_name = models.CharField(max_length=160, blank=True)
    business_approved = models.BooleanField(default=False)
    membership_number = models.CharField(max_length=40, blank=True, unique=True, null=True)


class Branch(models.Model):
    name = models.CharField(max_length=120)
    code = models.SlugField(unique=True)
    address = models.TextField()
    city = models.CharField(max_length=80)
    phone = models.CharField(max_length=24, blank=True)
    is_active = models.BooleanField(default=True)
    delivery_enabled = models.BooleanField(default=True)
    pickup_enabled = models.BooleanField(default=True)
    delivery_fee = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    free_delivery_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    opening_hours = models.JSONField(default=dict, blank=True)
    def __str__(self): return f"{self.name} ({self.city})"


class Category(models.Model):
    name = models.CharField(max_length=100)
    name_ur = models.CharField(max_length=100, blank=True)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    image = models.ImageField(upload_to="categories/", blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.name


class Product(models.Model):
    name = models.CharField(max_length=180)
    name_ur = models.CharField(max_length=180, blank=True)
    slug = models.SlugField(unique=True)
    sku = models.CharField(max_length=60, unique=True)
    barcode = models.CharField(max_length=80, blank=True, db_index=True)
    brand = models.CharField(max_length=100, blank=True, db_index=True)
    external_image_url = models.URLField(max_length=1000, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50, default="piece")
    pack_size = models.CharField(max_length=80, blank=True)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    wholesale_min_quantity = models.PositiveIntegerField(default=1)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    sale_starts_at = models.DateTimeField(null=True, blank=True)
    sale_ends_at = models.DateTimeField(null=True, blank=True)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    ingredients = models.TextField(blank=True)
    allergens = models.CharField(max_length=255, blank=True)
    storage_instructions = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    def current_price(self, user=None, quantity=1):
        now = timezone.now()
        if self.sale_price is not None and (not self.sale_starts_at or self.sale_starts_at <= now) and (not self.sale_ends_at or self.sale_ends_at >= now):
            return self.sale_price
        authenticated = bool(user and getattr(user, "is_authenticated", False))
        is_business = authenticated and user.role == User.Role.BUSINESS and user.business_approved
        tiers = self.price_tiers.filter(is_active=True, min_quantity__lte=quantity)
        if is_business:
            tiers = tiers.filter(customer_type__in=[PriceTier.CustomerType.ALL, PriceTier.CustomerType.BUSINESS])
        else:
            tiers = tiers.filter(customer_type__in=[PriceTier.CustomerType.ALL, PriceTier.CustomerType.RETAIL])
        tier = tiers.order_by("-min_quantity").first()
        if tier: return tier.unit_price
        if is_business and self.wholesale_price is not None and quantity >= self.wholesale_min_quantity:
            return self.wholesale_price
        return self.retail_price
    def __str__(self): return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=180, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)


class PriceTier(models.Model):
    class CustomerType(models.TextChoices):
        ALL = "all", "All customers"
        RETAIL = "retail", "Retail customers"
        BUSINESS = "business", "Business buyers"
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_tiers")
    customer_type = models.CharField(max_length=12, choices=CustomerType.choices, default=CustomerType.ALL)
    min_quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["min_quantity"]
        constraints = [models.UniqueConstraint(fields=["product", "customer_type", "min_quantity"], name="unique_product_price_tier")]


class BranchStock(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="stock")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="branch_stock")
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["branch", "product"], name="unique_branch_product_stock")]


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=40, default="Home")
    recipient_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=24)
    address_line = models.TextField()
    city = models.CharField(max_length=80)
    area = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)
    def __str__(self): return f"{self.label}: {self.address_line[:40]}"


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart_items")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "branch", "product"], name="unique_cart_line")]


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_user_favorite")]


class Promotion(models.Model):
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="promotions/", blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.title


class DiscountCode(models.Model):
    code = models.CharField(max_length=40, unique=True)
    percent_off = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    amount_off = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        PICKING = "picking", "Picking and packing"
        READY = "ready", "Ready for pickup"
        OUT = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
    class Fulfillment(models.TextChoices):
        DELIVERY = "delivery", "Delivery"
        PICKUP = "pickup", "Store pickup"
    class PaymentMethod(models.TextChoices):
        COD = "cod", "Cash to delivery rider"
        STORE = "pay_at_store", "Cash at store after showing invoice"
    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    address = models.ForeignKey(Address, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    fulfillment = models.CharField(max_length=12, choices=Fulfillment.choices)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    discount_code = models.CharField(max_length=40, blank=True)
    delivery_instructions = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=80, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["-created_at"]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=180)
    sku = models.CharField(max_length=60)
    unit = models.CharField(max_length=50)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)


class OrderStatusEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=24, choices=Order.Status.choices)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["created_at"]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=140)
    body = models.TextField(blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
