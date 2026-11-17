from rest_framework import serializers
from .models import (Address, Branch, BranchStock, CartItem, Category, Notification,
                     Order, OrderItem, OrderStatusEvent, PriceTier, Product,
                     ProductImage, Promotion, User)


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "code", "address", "city", "phone", "delivery_enabled", "pickup_enabled", "delivery_fee", "free_delivery_threshold", "minimum_order", "opening_hours"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "name_ur", "slug", "parent", "image", "sort_order"]

class PriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceTier
        fields = ["customer_type", "min_quantity", "unit_price"]

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    price_tiers = PriceTierSerializer(many=True, read_only=True)
    class Meta:
        model = Product
        fields = ["id", "name", "name_ur", "slug", "sku", "barcode", "brand", "category", "category_name", "description", "unit", "pack_size", "retail_price", "wholesale_price", "wholesale_min_quantity", "sale_price", "tax_percent", "ingredients", "allergens", "storage_instructions", "is_featured", "primary_image", "images", "price", "stock", "price_tiers"]
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = request.user if request else None
        is_business = bool(user and getattr(user, "is_authenticated", False) and user.role == User.Role.BUSINESS and user.business_approved)
        if is_business:
            data["price_tiers"] = [tier for tier in data["price_tiers"] if tier["customer_type"] in [PriceTier.CustomerType.ALL, PriceTier.CustomerType.BUSINESS]]
        else:
            data.pop("wholesale_price", None)
            data.pop("wholesale_min_quantity", None)
            data["price_tiers"] = [tier for tier in data["price_tiers"] if tier["customer_type"] in [PriceTier.CustomerType.ALL, PriceTier.CustomerType.RETAIL]]
        return data
    def get_primary_image(self, obj):
        image = obj.images.filter(is_primary=True).first() or obj.images.order_by("sort_order", "id").first()
        request = self.context.get("request")
        if image and image.image:
            return request.build_absolute_uri(image.image.url) if request else image.image.url
        return obj.external_image_url or None
    def get_images(self, obj):
        request = self.context.get("request")
        result = []
        for item in obj.images.order_by("sort_order", "id"):
            if item.image:
                result.append(request.build_absolute_uri(item.image.url) if request else item.image.url)
        if not result and obj.external_image_url:
            result.append(obj.external_image_url)
        return result
    def get_price(self, obj):
        user = self.context.get("request").user if self.context.get("request") else None
        quantity = int(self.context.get("quantity", 1))
        return str(obj.current_price(user, quantity))
    def get_stock(self, obj):
        branch_id = self.context.get("branch_id")
        if not branch_id: return None
        row = obj.branch_stock.filter(branch_id=branch_id).first()
        return row.quantity if row else 0

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        fields = ["username", "email", "password", "phone_number", "role", "business_name"]
    def validate_role(self, value):
        if value not in [User.Role.CUSTOMER, User.Role.BUSINESS]:
            raise serializers.ValidationError("Only customer or business accounts can self-register.")
        return value
    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone_number", "role", "preferred_language", "business_name", "business_approved", "membership_number"]
        read_only_fields = ["id", "role", "business_approved", "membership_number"]

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        exclude = ["user"]
        read_only_fields = ["id"]

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    class Meta:
        model = CartItem
        fields = ["id", "branch", "product", "quantity", "unit_price", "line_total", "updated_at"]
    def get_unit_price(self, obj): return str(obj.product.current_price(obj.user, obj.quantity))
    def get_line_total(self, obj): return str(obj.product.current_price(obj.user, obj.quantity) * obj.quantity)

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["product_name", "sku", "unit", "quantity", "unit_price", "tax_percent", "line_total"]

class OrderEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusEvent
        fields = ["status", "note", "created_at"]

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    class Meta:
        model = Order
        fields = ["id", "branch", "branch_name", "address", "status", "fulfillment", "payment_method", "payment_status", "subtotal", "tax_total", "discount_total", "delivery_fee", "total", "discount_code", "delivery_instructions", "items", "events", "created_at", "updated_at"]

class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = ["id", "title", "description", "image", "starts_at", "ends_at"]

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "body", "read_at", "created_at"]
