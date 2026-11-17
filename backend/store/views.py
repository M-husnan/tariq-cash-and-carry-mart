from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Q, F, Sum, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from .models import (Address, Branch, BranchStock, CartItem, Category, DiscountCode, Favorite,
                    Notification, Order, OrderItem, OrderStatusEvent, Product,
                    Promotion, User)
from .serializers import (AddressSerializer, BranchSerializer, CartItemSerializer,
                          CategorySerializer, NotificationSerializer, OrderSerializer,
                          ProductSerializer, PromotionSerializer, RegisterSerializer,
                          UserSerializer)


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request): return Response({"user": UserSerializer(request.user).data})
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"user": serializer.data})


class BranchListView(generics.ListAPIView):
    serializer_class = BranchSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Branch.objects.filter(is_active=True).order_by("city", "name")


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    queryset = Category.objects.filter(is_active=True).order_by("sort_order", "name")


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).select_related("category").prefetch_related("images", "price_tiers")
        params = self.request.query_params
        if params.get("category"): qs = qs.filter(category__slug=params["category"])
        if params.get("brand"): qs = qs.filter(brand__iexact=params["brand"])
        if params.get("q"):
            q = params["q"].strip()
            qs = qs.filter(Q(name__icontains=q) | Q(name_ur__icontains=q) | Q(brand__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q))
        if params.get("min_price"): qs = qs.filter(retail_price__gte=params["min_price"])
        if params.get("max_price"): qs = qs.filter(retail_price__lte=params["max_price"])
        if params.get("featured") == "true": qs = qs.filter(is_featured=True)
        branch = params.get("branch")
        if branch: qs = qs.filter(branch_stock__branch_id=branch, branch_stock__quantity__gt=0).distinct()
        ordering = params.get("sort", "name")
        allowed = {"name": "name", "price_low": "retail_price", "price_high": "-retail_price", "newest": "-created_at"}
        return qs.order_by(allowed.get(ordering, "name"))
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["branch_id"] = self.request.query_params.get("branch")
        try: context["quantity"] = max(1, min(999, int(self.request.query_params.get("quantity", "1"))))
        except (ValueError, TypeError): context["quantity"] = 1
        return context


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Product.objects.filter(is_active=True).select_related("category").prefetch_related("images", "price_tiers")
    lookup_field = "slug"
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["branch_id"] = self.request.query_params.get("branch")
        return context


class AddressListCreateView(generics.ListCreateAPIView):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Address.objects.filter(user=self.request.user).order_by("-is_default", "id")
    def perform_create(self, serializer): serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Address.objects.filter(user=self.request.user)


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        items = CartItem.objects.filter(user=request.user).select_related("product", "product__category", "branch").prefetch_related("product__images", "product__price_tiers")
        data = CartItemSerializer(items, many=True, context={"request": request}).data
        subtotal = sum((Decimal(row["line_total"]) for row in data), Decimal("0.00"))
        return Response({"items": data, "subtotal": str(money(subtotal)), "count": sum(x.quantity for x in items)})
    def post(self, request):
        product = get_object_or_404(Product, id=request.data.get("product_id"), is_active=True)
        branch = get_object_or_404(Branch, id=request.data.get("branch_id"), is_active=True)
        try: quantity = int(request.data.get("quantity", 1))
        except (ValueError, TypeError): return Response({"detail": "Quantity must be a whole number."}, status=400)
        if quantity < 1 or quantity > 999: return Response({"detail": "Quantity must be from 1 to 999."}, status=400)
        stock = BranchStock.objects.filter(product=product, branch=branch).first()
        if not stock or quantity > stock.quantity: return Response({"detail": "Requested quantity is not available at this branch."}, status=400)
        other_branch = CartItem.objects.filter(user=request.user).exclude(branch=branch).exists()
        if other_branch: return Response({"detail": "Your cart contains another branch. Clear it before changing branches."}, status=400)
        item, _ = CartItem.objects.update_or_create(user=request.user, branch=branch, product=product, defaults={"quantity": quantity})
        return Response(CartItemSerializer(item, context={"request": request}).data, status=status.HTTP_200_OK)


class CartItemDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def patch(self, request, pk):
        item = get_object_or_404(CartItem, pk=pk, user=request.user)
        try: quantity = int(request.data.get("quantity", item.quantity))
        except (ValueError, TypeError): return Response({"detail": "Quantity must be a whole number."}, status=400)
        stock = BranchStock.objects.filter(product=item.product, branch=item.branch).first()
        if quantity < 1 or quantity > 999: return Response({"detail": "Quantity must be from 1 to 999."}, status=400)
        if not stock or quantity > stock.quantity: return Response({"detail": "Requested quantity is not available."}, status=400)
        item.quantity = quantity; item.save(update_fields=["quantity", "updated_at"])
        return Response(CartItemSerializer(item, context={"request": request}).data)
    def delete(self, request, pk):
        get_object_or_404(CartItem, pk=pk, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WishlistView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        products = Product.objects.filter(favorited_by__user=request.user, is_active=True).select_related("category").prefetch_related("images", "price_tiers")
        return Response(ProductSerializer(products, many=True, context={"request": request}).data)
    def post(self, request):
        product = get_object_or_404(Product, id=request.data.get("product_id"), is_active=True)
        favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
        if not created:
            favorite.delete()
        return Response({"product_id": product.id, "favorited": created})


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    @transaction.atomic
    def post(self, request):
        key = str(request.data.get("idempotency_key", "")).strip()[:80]
        if key:
            existing = Order.objects.filter(idempotency_key=key, user=request.user).first()
            if existing: return Response(OrderSerializer(existing).data)
        items = list(CartItem.objects.filter(user=request.user).select_related("product", "branch", "product__category"))
        if not items: return Response({"detail": "Your cart is empty."}, status=400)
        branch_id = request.data.get("branch_id")
        branch = get_object_or_404(Branch.objects.select_for_update(), id=branch_id, is_active=True)
        if any(item.branch_id != branch.id for item in items): return Response({"detail": "All cart items must be from the selected branch."}, status=400)
        fulfillment = request.data.get("fulfillment", Order.Fulfillment.DELIVERY)
        payment = request.data.get("payment_method", Order.PaymentMethod.COD)
        if fulfillment not in Order.Fulfillment.values: return Response({"detail": "Choose delivery or pickup."}, status=400)
        if payment not in [Order.PaymentMethod.COD, Order.PaymentMethod.STORE]:
            return Response({"detail": "Only cash to the delivery rider or cash at store pickup is available."}, status=400)
        if (fulfillment == Order.Fulfillment.DELIVERY and payment != Order.PaymentMethod.COD) or (fulfillment == Order.Fulfillment.PICKUP and payment != Order.PaymentMethod.STORE):
            return Response({"detail": "Choose rider cash payment for delivery or store cash payment for pickup."}, status=400)
        if fulfillment == Order.Fulfillment.DELIVERY and not branch.delivery_enabled: return Response({"detail": "Delivery is not available from this branch."}, status=400)
        if fulfillment == Order.Fulfillment.PICKUP and not branch.pickup_enabled: return Response({"detail": "Pickup is not available from this branch."}, status=400)
        address = None
        if fulfillment == Order.Fulfillment.DELIVERY:
            address = get_object_or_404(Address, id=request.data.get("address_id"), user=request.user)
        prepared, subtotal, tax_total = [], Decimal("0.00"), Decimal("0.00")
        for item in items:
            product = Product.objects.select_for_update().get(pk=item.product_id, is_active=True)
            stock = BranchStock.objects.select_for_update().filter(branch=branch, product=product).first()
            if not stock or stock.quantity < item.quantity:
                return Response({"detail": f"Not enough stock for {product.name}. Please update your cart."}, status=400)
            unit_price = money(product.current_price(request.user, item.quantity))
            line_subtotal = money(unit_price * item.quantity)
            line_tax = money(line_subtotal * product.tax_percent / Decimal("100"))
            prepared.append((item, product, stock, unit_price, line_subtotal, line_tax))
            subtotal += line_subtotal; tax_total += line_tax
        subtotal, tax_total = money(subtotal), money(tax_total)
        if subtotal < branch.minimum_order: return Response({"detail": f"Minimum order for this branch is PKR {branch.minimum_order}."}, status=400)
        discount = Decimal("0.00")
        code_text = str(request.data.get("discount_code", "")).strip().upper()
        code = None
        if code_text:
            code = DiscountCode.objects.select_for_update().filter(code__iexact=code_text, is_active=True).first()
            now = timezone.now()
            if not code or (code.starts_at and code.starts_at > now) or (code.ends_at and code.ends_at < now) or (code.usage_limit is not None and code.uses >= code.usage_limit) or subtotal < code.minimum_order:
                return Response({"detail": "This discount code is invalid or does not apply to this order."}, status=400)
            if code.percent_off is not None: discount = money(subtotal * min(code.percent_off, Decimal("100")) / Decimal("100"))
            elif code.amount_off is not None: discount = min(subtotal, money(code.amount_off))
        delivery_fee = Decimal("0.00")
        if fulfillment == Order.Fulfillment.DELIVERY and (branch.free_delivery_threshold <= 0 or subtotal < branch.free_delivery_threshold):
            delivery_fee = money(branch.delivery_fee)
        total = max(Decimal("0.00"), money(subtotal + tax_total - discount + delivery_fee))
        order = Order.objects.create(user=request.user, branch=branch, address=address, fulfillment=fulfillment,
            payment_method=payment, subtotal=subtotal, tax_total=tax_total, discount_total=discount,
            delivery_fee=delivery_fee, total=total, discount_code=code_text,
            delivery_instructions=str(request.data.get("delivery_instructions", ""))[:2000],
            idempotency_key=key or None)
        for item, product, stock, unit_price, line_subtotal, line_tax in prepared:
            OrderItem.objects.create(order=order, product=product, product_name=product.name, sku=product.sku,
                unit=product.pack_size or product.unit, quantity=item.quantity, unit_price=unit_price,
                tax_percent=product.tax_percent, line_total=money(line_subtotal + line_tax))
            stock.quantity -= item.quantity
            stock.save(update_fields=["quantity", "updated_at"])
        if code:
            DiscountCode.objects.filter(pk=code.pk).update(uses=F("uses") + 1)
        OrderStatusEvent.objects.create(order=order, status=order.status, note="Order placed")
        Notification.objects.create(user=request.user, title="Order received", body=f"Your order {str(order.id)[:8]} was received.")
        CartItem.objects.filter(user=request.user).delete()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Order.objects.filter(user=self.request.user).select_related("branch", "address").prefetch_related("items", "events")


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"
    def get_queryset(self): return Order.objects.filter(user=self.request.user).select_related("branch", "address").prefetch_related("items", "events")


class CancelOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    @transaction.atomic
    def post(self, request, order_id):
        order = get_object_or_404(Order.objects.select_for_update(), id=order_id, user=request.user)
        if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
            return Response({"detail": "This order can no longer be cancelled in the app."}, status=400)
        for line in order.items.select_related("product"):
            if line.product_id:
                stock = BranchStock.objects.select_for_update().filter(branch=order.branch, product=line.product).first()
                if stock:
                    stock.quantity += line.quantity; stock.save(update_fields=["quantity", "updated_at"])
        order.status = Order.Status.CANCELLED; order.save(update_fields=["status", "updated_at"])
        OrderStatusEvent.objects.create(order=order, status=order.status, note="Cancelled by customer", changed_by=request.user)
        return Response(OrderSerializer(order).data)


class StaffOrderStatusView(APIView):
    permission_classes = [permissions.IsAdminUser]
    @transaction.atomic
    def patch(self, request, order_id):
        order = get_object_or_404(Order.objects.select_for_update(), id=order_id)
        next_status = request.data.get("status")
        if next_status not in Order.Status.values: return Response({"detail": "Unknown order status."}, status=400)
        order.status = next_status; order.save(update_fields=["status", "updated_at"])
        note = str(request.data.get("note", ""))[:255]
        OrderStatusEvent.objects.create(order=order, status=next_status, note=note, changed_by=request.user)
        Notification.objects.create(user=order.user, title="Order update", body=f"Order {str(order.id)[:8]}: {order.get_status_display()}.")
        return Response(OrderSerializer(order).data)


class InvoiceView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, order_id):
        order = get_object_or_404(Order.objects.select_related("branch", "address", "user").prefetch_related("items"), id=order_id)
        if order.user_id != request.user.id and not request.user.is_staff: return Response({"detail": "Not found."}, status=404)
        buffer = BytesIO(); pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4; y = height - 48
        pdf.setTitle(f"Tariq Cash and Carry Mart invoice {str(order.id)[:8]}")
        pdf.setFont("Helvetica-Bold", 18); pdf.drawString(42, y, "Tariq Cash and Carry Mart")
        y -= 28; pdf.setFont("Helvetica", 10)
        pdf.drawString(42, y, f"Invoice / order: {order.id}"); y -= 16
        pdf.drawString(42, y, f"Date: {timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M')} PKT"); y -= 16
        pdf.drawString(42, y, f"Branch: {order.branch.name} — {order.branch.city}"); y -= 16
        pdf.drawString(42, y, f"Customer: {order.user.get_full_name() or order.user.username}"); y -= 28
        pdf.setFont("Helvetica-Bold", 10); pdf.drawString(42, y, "Item")
        pdf.drawString(300, y, "Qty"); pdf.drawString(350, y, "Unit price"); pdf.drawString(455, y, "Line total")
        y -= 8; pdf.line(42, y, width - 42, y); y -= 18; pdf.setFont("Helvetica", 9)
        for line in order.items.all():
            if y < 95: pdf.showPage(); y = height - 48; pdf.setFont("Helvetica", 9)
            pdf.drawString(42, y, f"{line.product_name[:38]} ({line.unit})")
            pdf.drawRightString(325, y, str(line.quantity)); pdf.drawRightString(425, y, f"PKR {line.unit_price}")
            pdf.drawRightString(width - 42, y, f"PKR {line.line_total}"); y -= 17
        y -= 8; pdf.line(42, y, width - 42, y); y -= 20
        for label, value in [("Subtotal", order.subtotal), ("Tax", order.tax_total), ("Discount", -order.discount_total), ("Delivery", order.delivery_fee), ("Total (PKR)", order.total)]:
            pdf.drawRightString(width - 150, y, label); pdf.drawRightString(width - 42, y, f"{value:.2f}"); y -= 16
        pdf.setFont("Helvetica", 9); pdf.drawString(42, 42, f"Payment: {order.get_payment_method_display()}   Status: {order.get_status_display()}")
        pdf.save(); response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="tariq-mart-invoice-{str(order.id)[:8]}.pdf"'
        return response


class PromotionListView(generics.ListAPIView):
    serializer_class = PromotionSerializer
    permission_classes = [permissions.AllowAny]
    def get_queryset(self):
        now = timezone.now()
        return Promotion.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).order_by("ends_at")


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, notification_id):
        item = get_object_or_404(Notification, id=notification_id, user=request.user)
        item.read_at = timezone.now(); item.save(update_fields=["read_at"])
        return Response(NotificationSerializer(item).data)


class StaffReportView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def get(self, request):
        orders = Order.objects.all()
        branch_id = request.query_params.get("branch")
        if branch_id: orders = orders.filter(branch_id=branch_id)
        totals = orders.aggregate(orders=Count("id"))
        paid_revenue = orders.filter(payment_status=Order.PaymentStatus.PAID).aggregate(total=Sum("total"))["total"] or 0
        status_counts = dict(orders.values_list("status").annotate(total=Count("id")))
        active_orders = orders.exclude(status=Order.Status.CANCELLED)
        top_products = list(OrderItem.objects.filter(order__in=active_orders).values("product_name", "sku").annotate(quantity=Sum("quantity"), revenue=Sum("line_total")).order_by("-quantity")[:10])
        low_stock = list(BranchStock.objects.filter(quantity__lte=F("low_stock_threshold")).select_related("branch", "product").values("branch__name", "product__name", "quantity")[:50])
        return Response({"paid_revenue": str(paid_revenue), "order_count": totals["orders"] or 0, "orders_by_status": status_counts, "top_products": top_products, "low_stock": low_stock})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(request): return Response({"status": "ok", "service": "Tariq Cash and Carry Mart API"})
