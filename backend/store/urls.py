from django.urls import path
from .views import (
    AddressDetailView, AddressListCreateView, BranchListView, CancelOrderView,
    CartItemDetailView, CartView, CategoryListView, CheckoutView, InvoiceView,
    LoginView, MeView, NotificationListView, NotificationReadView, OrderDetailView,
    OrderListView, ProductDetailView, ProductListView, PromotionListView,
    RegisterView, StaffOrderStatusView, StaffReportView, WishlistView, health,
)

urlpatterns = [
    path("health/", health, name="api-health"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("branches/", BranchListView.as_view(), name="branches"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("products/", ProductListView.as_view(), name="products"),
    path("products/<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
    path("addresses/", AddressListCreateView.as_view(), name="addresses"),
    path("addresses/<int:pk>/", AddressDetailView.as_view(), name="address-detail"),
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item"),
    path("wishlist/", WishlistView.as_view(), name="wishlist"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/", OrderListView.as_view(), name="orders"),
    path("orders/<uuid:id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:order_id>/cancel/", CancelOrderView.as_view(), name="order-cancel"),
    path("orders/<uuid:order_id>/status/", StaffOrderStatusView.as_view(), name="order-status"),
    path("orders/<uuid:order_id>/invoice/", InvoiceView.as_view(), name="order-invoice"),
    path("promotions/", PromotionListView.as_view(), name="promotions"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/<int:notification_id>/read/", NotificationReadView.as_view(), name="notification-read"),
    path("staff/reports/summary/", StaffReportView.as_view(), name="staff-report-summary"),
]
