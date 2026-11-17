import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'api_client.dart';

void main() => runApp(const TariqMartApp());

class TariqMartApp extends StatefulWidget {
  const TariqMartApp({super.key});
  @override
  State<TariqMartApp> createState() => _TariqMartAppState();
}

class _TariqMartAppState extends State<TariqMartApp> {
  final api = ApiClient();
  bool ready = false;
  @override
  void initState() { super.initState(); api.restore().then((_) { if (mounted) setState(() => ready = true); }); }
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Tariq Cash and Carry Mart', debugShowCheckedModeBanner: false,
    theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff85898d), brightness: Brightness.light).copyWith(surface: Colors.white, surfaceContainerHighest: const Color(0xfff0f1f2)), useMaterial3: true, scaffoldBackgroundColor: const Color(0xfff3f4f5), appBarTheme: const AppBarTheme(backgroundColor: Colors.white, foregroundColor: Color(0xff292b2d), surfaceTintColor: Colors.white), navigationBarTheme: const NavigationBarThemeData(backgroundColor: Colors.white, indicatorColor: Color(0xffe3e5e7)), filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(backgroundColor: const Color(0xff55595d), foregroundColor: Colors.white)), inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: Colors.white, border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(12))))),
    home: !ready ? const Scaffold(body: Center(child: CircularProgressIndicator())) : StoreShell(api: api),
  );
}

List<Map<String, dynamic>> asRows(dynamic data) {
  if (data is List) return data.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  if (data is Map && data['results'] is List) return asRows(data['results']);
  return [];
}
String pkr(dynamic value) => 'PKR ${double.tryParse('$value')?.toStringAsFixed(2) ?? '0.00'}';
String paymentLabel(dynamic value) => value == 'cod' ? 'Cash to delivery rider' : value == 'pay_at_store' ? 'Cash at store after showing invoice' : 'Cash payment';
String readableError(Object e) => e is ApiFailure ? e.message : e.toString().replaceFirst('Exception: ', '');

class StoreShell extends StatefulWidget {
  const StoreShell({super.key, required this.api});
  final ApiClient api;
  @override
  State<StoreShell> createState() => _StoreShellState();
}

class _StoreShellState extends State<StoreShell> {
  int tab = 0, refresh = 0;
  Map<String, dynamic>? branch;
  bool branchBusy = true;
  @override
  void initState() { super.initState(); loadBranches(); }
  Future<void> loadBranches() async {
    try { final rows = asRows(await widget.api.get('/branches/')); if (rows.isNotEmpty && mounted) setState(() => branch = rows.first); }
    catch (_) {} finally { if (mounted) setState(() => branchBusy = false); }
  }
  Future<void> selectBranch() async {
    final rows = asRows(await widget.api.get('/branches/'));
    if (!mounted || rows.isEmpty) return;
    final selected = await showModalBottomSheet<Map<String, dynamic>>(context: context, builder: (ctx) => SafeArea(child: ListView(children: [const ListTile(title: Text('Choose your store branch', style: TextStyle(fontWeight: FontWeight.bold))), ...rows.map((b) => ListTile(leading: const Icon(Icons.storefront), title: Text(b['name'] ?? ''), subtitle: Text('${b['city'] ?? ''} · ${b['address'] ?? ''}'), onTap: () => Navigator.pop(ctx, b)))])));
    if (selected != null) setState(() { branch = selected; refresh++; });
  }
  void addedToCart() => setState(() => refresh++);
  @override
  Widget build(BuildContext context) {
    final branchId = branch?['id'];
    final pages = [
      CatalogPage(api: widget.api, branchId: branchId, refresh: refresh, onAdd: addedToCart, onLogin: () => setState(() => tab = 3)),
      CartPage(api: widget.api, refresh: refresh, onChanged: addedToCart),
      OrdersPage(api: widget.api, refresh: refresh),
      AccountPage(api: widget.api, onChanged: () => setState(() { refresh++; tab = 0; })),
    ];
    return Scaffold(
      appBar: tab == 0 ? AppBar(title: Row(mainAxisSize: MainAxisSize.min, children: [Image.asset('assets/tariq_mart_logo.png', width: 40, height: 40), const SizedBox(width: 7), const Flexible(child: Text('Tariq Cash and Carry Mart', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900)))]), actions: [TextButton.icon(onPressed: selectBranch, icon: const Icon(Icons.storefront), label: Text(branchBusy ? 'Loading' : (branch?['city'] ?? 'Choose store').toString())), const SizedBox(width: 8)]) : AppBar(title: Text(['Shop', 'Your cart', 'My orders', 'Account'][tab], style: const TextStyle(fontWeight: FontWeight.bold))),
      body: IndexedStack(index: tab, children: pages),
      bottomNavigationBar: NavigationBar(selectedIndex: tab, onDestinationSelected: (i) => setState(() => tab = i), destinations: const [NavigationDestination(icon: Icon(Icons.storefront_outlined), selectedIcon: Icon(Icons.storefront), label: 'Shop'), NavigationDestination(icon: Icon(Icons.shopping_cart_outlined), selectedIcon: Icon(Icons.shopping_cart), label: 'Cart'), NavigationDestination(icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long), label: 'Orders'), NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Account')]),
    );
  }
}

class CatalogPage extends StatefulWidget {
  const CatalogPage({super.key, required this.api, required this.branchId, required this.refresh, required this.onAdd, required this.onLogin});
  final ApiClient api; final dynamic branchId; final int refresh; final VoidCallback onAdd, onLogin;
  @override
  State<CatalogPage> createState() => _CatalogPageState();
}
class _CatalogPageState extends State<CatalogPage> {
  final search = TextEditingController();
  List<Map<String, dynamic>> products = [], categories = [];
  Set<int> favorites = {};
  String? category;
  String? brand, minPrice, maxPrice;
  String sort = 'name';
  bool loading = true; String? error;
  @override
  void initState() { super.initState(); load(); }
  @override
  void didUpdateWidget(covariant CatalogPage old) { super.didUpdateWidget(old); if (old.branchId != widget.branchId || old.refresh != widget.refresh) load(); }
  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final catData = await widget.api.get('/categories/');
      final productData = await widget.api.get('/products/', query: {if (search.text.trim().isNotEmpty) 'q': search.text.trim(), if (category != null) 'category': category!, if (widget.branchId != null) 'branch': '${widget.branchId}', if (brand?.isNotEmpty == true) 'brand': brand!, if (minPrice?.isNotEmpty == true) 'min_price': minPrice!, if (maxPrice?.isNotEmpty == true) 'max_price': maxPrice!, 'sort': sort});
      final favoriteData = widget.api.isSignedIn ? await widget.api.get('/wishlist/') : <dynamic>[];
      if (!mounted) return;
      setState(() { categories = asRows(catData); products = asRows(productData); favorites = asRows(favoriteData).map((p) => int.tryParse('${p['id']}')).whereType<int>().toSet(); });
    } catch (e) { if (mounted) setState(() => error = readableError(e)); }
    finally { if (mounted) setState(() => loading = false); }
  }
  Future<void> add(Map<String, dynamic> product, [int quantity = 1]) async {
    if (!widget.api.isSignedIn) { widget.onLogin(); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sign in before adding items to your cart.'))); return; }
    if (widget.branchId == null) { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Choose a store branch first.'))); return; }
    try { await widget.api.post('/cart/', {'product_id': product['id'], 'branch_id': widget.branchId, 'quantity': quantity}); widget.onAdd(); if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Added to cart'))); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  Future<void> toggleFavorite(Map<String, dynamic> product) async {
    if (!widget.api.isSignedIn) { widget.onLogin(); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sign in to save favorites.'))); return; }
    try { final result = await widget.api.post('/wishlist/', {'product_id': product['id']}); final id = int.tryParse('${product['id']}'); if (id != null && mounted) setState(() { if (result['favorited'] == true) { favorites.add(id); } else { favorites.remove(id); } }); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  Future<void> openFilters() async {
    final brandField = TextEditingController(text: brand ?? ''), minField = TextEditingController(text: minPrice ?? ''), maxField = TextEditingController(text: maxPrice ?? '');
    final filters = await showModalBottomSheet<Map<String, String>>(context: context, isScrollControlled: true, builder: (ctx) => Padding(padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(ctx).viewInsets.bottom + 20), child: Column(mainAxisSize: MainAxisSize.min, children: [Text('Filter products', style: Theme.of(ctx).textTheme.titleLarge), TextField(controller: brandField, decoration: const InputDecoration(labelText: 'Brand')), Row(children: [Expanded(child: TextField(controller: minField, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Minimum price'))), const SizedBox(width: 12), Expanded(child: TextField(controller: maxField, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Maximum price')))]), const SizedBox(height: 14), Row(children: [TextButton(onPressed: () => Navigator.pop(ctx, {'clear': 'true'}), child: const Text('Clear')), const Spacer(), FilledButton(onPressed: () => Navigator.pop(ctx, {'brand': brandField.text.trim(), 'min': minField.text.trim(), 'max': maxField.text.trim()}), child: const Text('Apply'))])]))) ;
    if (filters == null || !mounted) return;
    setState(() { brand = filters['clear'] == 'true' ? null : filters['brand']; minPrice = filters['clear'] == 'true' ? null : filters['min']; maxPrice = filters['clear'] == 'true' ? null : filters['max']; });
    load();
  }
  @override
  Widget build(BuildContext context) => RefreshIndicator(onRefresh: load, child: CustomScrollView(slivers: [
    SliverToBoxAdapter(child: Padding(padding: const EdgeInsets.fromLTRB(16, 12, 16, 8), child: TextField(controller: search, textInputAction: TextInputAction.search, onSubmitted: (_) => load(), decoration: InputDecoration(hintText: 'Search all groceries, brands, SKU…', prefixIcon: const Icon(Icons.search), suffixIcon: IconButton(icon: const Icon(Icons.search), onPressed: load), filled: true, fillColor: Colors.white, border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none))))),
    if (categories.isNotEmpty) SliverToBoxAdapter(child: SizedBox(height: 52, child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12), children: [Padding(padding: const EdgeInsets.symmetric(horizontal: 4), child: ChoiceChip(label: const Text('All'), selected: category == null, onSelected: (_) { setState(() => category = null); load(); })), ...categories.map((c) => Padding(padding: const EdgeInsets.symmetric(horizontal: 4), child: ChoiceChip(label: Text(c['name'] ?? ''), selected: category == c['slug'], onSelected: (_) { setState(() => category = c['slug']); load(); })))]))),
    SliverToBoxAdapter(child: Padding(padding: const EdgeInsets.fromLTRB(16, 8, 12, 8), child: Row(children: [Expanded(child: Text('Browse products', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800))), IconButton(tooltip: 'Filter', onPressed: openFilters, icon: Icon(Icons.tune, color: (brand?.isNotEmpty == true || minPrice?.isNotEmpty == true || maxPrice?.isNotEmpty == true) ? const Color(0xff666a6e) : null)), DropdownButton<String>(value: sort, underline: const SizedBox(), items: const [DropdownMenuItem(value: 'name', child: Text('Name')), DropdownMenuItem(value: 'price_low', child: Text('Price ↑')), DropdownMenuItem(value: 'price_high', child: Text('Price ↓')), DropdownMenuItem(value: 'newest', child: Text('Newest'))], onChanged: (v) { if (v != null) setState(() => sort = v); load(); })]))),
    if (loading) const SliverFillRemaining(child: Center(child: CircularProgressIndicator()))
    else if (error != null) SliverFillRemaining(child: _Message(message: error!, button: 'Retry', onPressed: load))
    else if (products.isEmpty) const SliverFillRemaining(child: _Message(message: 'No products found. Try another search or category.'))
    else SliverPadding(padding: const EdgeInsets.all(12), sliver: SliverGrid.builder(itemCount: products.length, gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 2, childAspectRatio: .67, crossAxisSpacing: 12, mainAxisSpacing: 12), itemBuilder: (context, i) => ProductCard(product: products[i], isFavorite: favorites.contains(int.tryParse('${products[i]['id']}')), onFavorite: () => toggleFavorite(products[i]), onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ProductDetailPage(api: widget.api, product: products[i], onAdd: add))), onAdd: () => add(products[i])))),
  ]));
}

class ProductCard extends StatelessWidget {
  const ProductCard({super.key, required this.product, required this.onAdd, required this.onTap, required this.isFavorite, required this.onFavorite});
  final Map<String, dynamic> product; final VoidCallback onAdd, onTap, onFavorite; final bool isFavorite;
  @override
  Widget build(BuildContext context) => Card(clipBehavior: Clip.antiAlias, elevation: 0, color: Colors.white, child: InkWell(onTap: onTap, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Expanded(child: Stack(fit: StackFit.expand, children: [_ProductImage(url: product['primary_image']?.toString()), Positioned(top: 3, right: 3, child: Material(color: Colors.white.withOpacity(.9), shape: const CircleBorder(), child: IconButton(visualDensity: VisualDensity.compact, onPressed: onFavorite, icon: Icon(isFavorite ? Icons.favorite : Icons.favorite_border, color: isFavorite ? Colors.red : Colors.black87))))])), Padding(padding: const EdgeInsets.fromLTRB(10, 6, 10, 0), child: Text('${product['brand'] ?? ''}', maxLines: 1, style: TextStyle(color: Colors.grey.shade600, fontSize: 11))), Padding(padding: const EdgeInsets.symmetric(horizontal: 10), child: Text(product['name'] ?? '', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700))), Padding(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2), child: Text('${product['pack_size'] ?? product['unit'] ?? ''}  ·  ${pkr(product['price'] ?? product['retail_price'])}', style: const TextStyle(fontWeight: FontWeight.w800, color: Color(0xff666a6e)))), Padding(padding: const EdgeInsets.fromLTRB(8, 2, 8, 8), child: SizedBox(width: double.infinity, height: 36, child: FilledButton.tonalIcon(onPressed: onAdd, icon: const Icon(Icons.add_shopping_cart, size: 16), label: const Text('Add'))))])));
}

class _ProductImage extends StatelessWidget {
  const _ProductImage({this.url}); final String? url;
  @override
  Widget build(BuildContext context) => Container(width: double.infinity, color: const Color(0xffeceeef), child: url == null || url!.isEmpty ? const Icon(Icons.local_grocery_store, size: 52, color: Color(0xff969a9e)) : Image.network(url!, fit: BoxFit.cover, errorBuilder: (_, __, ___) => const Icon(Icons.broken_image_outlined, size: 42)));
}

class ProductDetailPage extends StatefulWidget {
  const ProductDetailPage({super.key, required this.api, required this.product, required this.onAdd});
  final ApiClient api; final Map<String, dynamic> product; final Future<void> Function(Map<String, dynamic>, [int]) onAdd;
  @override
  State<ProductDetailPage> createState() => _ProductDetailPageState();
}
class _ProductDetailPageState extends State<ProductDetailPage> {
  int quantity = 1;
  @override
  Widget build(BuildContext context) {
    final p = widget.product;
    final imageUrls = (p['images'] is List ? (p['images'] as List).map((x) => x.toString()).where((x) => x.isNotEmpty).toList() : <String>[]);
    if (imageUrls.isEmpty && p['primary_image'] != null) imageUrls.add(p['primary_image'].toString());
    return Scaffold(appBar: AppBar(title: const Text('Product details')), body: ListView(padding: const EdgeInsets.all(18), children: [
      SizedBox(height: 250, child: ClipRRect(borderRadius: BorderRadius.circular(18), child: imageUrls.isEmpty ? const _ProductImage() : PageView(children: imageUrls.map((url) => _ProductImage(url: url)).toList()))),
      const SizedBox(height: 18), Text(p['brand'] ?? '', style: TextStyle(color: Colors.grey.shade700)),
      Text(p['name'] ?? '', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
      Text('${p['pack_size'] ?? p['unit'] ?? ''}  ·  ${pkr(p['price'] ?? p['retail_price'])}', style: const TextStyle(color: Color(0xff666a6e), fontSize: 18, fontWeight: FontWeight.bold)),
      const SizedBox(height: 12), Text(p['description'] ?? 'Fresh quality products for your home or business.'),
      if ((p['ingredients'] ?? '').toString().isNotEmpty) ...[const SizedBox(height: 10), Text('Ingredients: ${p['ingredients']}')],
      if ((p['allergens'] ?? '').toString().isNotEmpty) ...[const SizedBox(height: 6), Text('Allergens: ${p['allergens']}')],
      if ((p['price_tiers'] as List?)?.isNotEmpty ?? false) ...[const SizedBox(height: 18), const Text('Bulk price breaks', style: TextStyle(fontWeight: FontWeight.bold)), ...(p['price_tiers'] as List).map((t) => ListTile(contentPadding: EdgeInsets.zero, title: Text('Buy ${t['min_quantity']} or more'), trailing: Text(pkr(t['unit_price']))))],
      const SizedBox(height: 20), Row(children: [IconButton(onPressed: quantity > 1 ? () => setState(() => quantity--) : null, icon: const Icon(Icons.remove_circle_outline)), Text('$quantity', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)), IconButton(onPressed: () => setState(() => quantity++), icon: const Icon(Icons.add_circle_outline)), const Spacer(), FilledButton.icon(onPressed: () async { await widget.onAdd(p, quantity); if (context.mounted) Navigator.pop(context); }, icon: const Icon(Icons.add_shopping_cart), label: const Text('Add to cart'))]),
    ]));
  }
}

class CartPage extends StatefulWidget {
  const CartPage({super.key, required this.api, required this.refresh, required this.onChanged});
  final ApiClient api; final int refresh; final VoidCallback onChanged;
  @override
  State<CartPage> createState() => _CartPageState();
}
class _CartPageState extends State<CartPage> {
  Map<String, dynamic> cart = {}; bool loading = true; String? error;
  @override
  void initState() { super.initState(); load(); }
  @override
  void didUpdateWidget(covariant CartPage old) { super.didUpdateWidget(old); if (old.refresh != widget.refresh) load(); }
  Future<void> load() async {
    if (!widget.api.isSignedIn) { setState(() { cart = {}; loading = false; }); return; }
    setState(() { loading = true; error = null; });
    try { final d = await widget.api.get('/cart/'); if (mounted) setState(() => cart = Map<String, dynamic>.from(d)); }
    catch (e) { if (mounted) setState(() => error = readableError(e)); }
    finally { if (mounted) setState(() => loading = false); }
  }
  Future<void> setQty(Map<String, dynamic> line, int qty) async {
    try { if (qty < 1) { await widget.api.delete('/cart/items/${line['id']}/'); } else { await widget.api.patch('/cart/items/${line['id']}/', {'quantity': qty}); } await load(); widget.onChanged(); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  Future<void> checkout() async {
    final lines = asRows(cart['items']); if (lines.isEmpty) return;
    final addresses = asRows(await widget.api.get('/addresses/'));
    if (!mounted) return;
    final result = await showModalBottomSheet<Map<String, dynamic>>(context: context, isScrollControlled: true, builder: (_) => CheckoutSheet(api: widget.api, addresses: addresses, branchId: lines.first['branch']));
    if (result == null || !mounted) return;
    try { final order = await widget.api.post('/checkout/', result); widget.onChanged(); await load(); if (!mounted) return; final shortId = order['id'].toString().substring(0, 8); showDialog(context: context, builder: (ctx) => AlertDialog(title: const Text('Order placed'), content: Text('Your order $shortId is received. Total ${pkr(order['total'])}. ${result['fulfillment'] == 'pickup' ? 'Open My Orders, show this invoice at the store, and pay cash to collect.' : 'Pay cash to the delivery rider when your order arrives.'}'), actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))])); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  @override
  Widget build(BuildContext context) {
    if (!widget.api.isSignedIn) return const _Message(message: 'Sign in to view and manage your cart.');
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return _Message(message: error!, button: 'Retry', onPressed: load);
    final lines = asRows(cart['items']);
    if (lines.isEmpty) return const _Message(message: 'Your cart is empty. Browse the store to add products.', icon: Icons.shopping_cart_outlined);
    return Column(children: [Expanded(child: ListView.separated(padding: const EdgeInsets.all(12), itemCount: lines.length, separatorBuilder: (_, __) => const SizedBox(height: 8), itemBuilder: (context, i) { final l = lines[i], p = Map<String, dynamic>.from(l['product']); return Card(color: Colors.white, child: ListTile(leading: SizedBox(width: 58, child: ClipRRect(borderRadius: BorderRadius.circular(8), child: _ProductImage(url: p['primary_image']?.toString()))), title: Text(p['name'] ?? '', maxLines: 2, overflow: TextOverflow.ellipsis), subtitle: Text('${pkr(l['line_total'])} · ${p['pack_size'] ?? p['unit'] ?? ''}'), trailing: SizedBox(width: 106, child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [IconButton(onPressed: () => setQty(l, (l['quantity'] as int) - 1), icon: const Icon(Icons.remove, size: 19)), Text('${l['quantity']}'), IconButton(onPressed: () => setQty(l, (l['quantity'] as int) + 1), icon: const Icon(Icons.add, size: 19))])))); })), Container(color: Colors.white, padding: const EdgeInsets.fromLTRB(18, 12, 18, 18), child: SafeArea(top: false, child: Column(children: [Row(children: [const Text('Subtotal', style: TextStyle(fontWeight: FontWeight.w600)), const Spacer(), Text(pkr(cart['subtotal']), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900))]), const SizedBox(height: 10), SizedBox(width: double.infinity, child: FilledButton(onPressed: checkout, child: const Text('Continue to checkout')))]))) ]);
  }
}

class CheckoutSheet extends StatefulWidget {
  const CheckoutSheet({super.key, required this.api, required this.addresses, required this.branchId});
  final ApiClient api; final List<Map<String, dynamic>> addresses; final dynamic branchId;
  @override
  State<CheckoutSheet> createState() => _CheckoutSheetState();
}
class _CheckoutSheetState extends State<CheckoutSheet> {
  late List<Map<String, dynamic>> addresses; dynamic addressId; String fulfillment = 'delivery'; final instructions = TextEditingController(), discountCode = TextEditingController(); bool busy = false;
  @override
  void initState() { super.initState(); addresses = [...widget.addresses]; if (addresses.isNotEmpty) addressId = addresses.first['id']; }
  Future<void> addAddress() async {
    final name = TextEditingController(), phone = TextEditingController(), line = TextEditingController(), city = TextEditingController(), area = TextEditingController();
    final formKey = GlobalKey<FormState>();
    final data = await showDialog<Map<String, String>>(context: context, builder: (ctx) => AlertDialog(title: const Text('Add delivery address'), content: Form(key: formKey, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [for (final entry in [(name, 'Recipient name'), (phone, 'Phone number'), (line, 'Street address'), (area, 'Area'), (city, 'City')]) Padding(padding: const EdgeInsets.only(bottom: 8), child: TextFormField(controller: entry.$1, decoration: InputDecoration(labelText: entry.$2), validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null))]))), actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')), FilledButton(onPressed: () { if (formKey.currentState!.validate()) Navigator.pop(ctx, {'recipient_name': name.text, 'phone_number': phone.text, 'address_line': line.text, 'area': area.text, 'city': city.text, 'label': 'Home'}); }, child: const Text('Save'))]));
    if (data == null) return;
    try { final address = await widget.api.post('/addresses/', data); if (mounted) setState(() { addresses.add(Map<String, dynamic>.from(address)); addressId = address['id']; }); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  @override
  Widget build(BuildContext context) => Padding(padding: EdgeInsets.fromLTRB(18, 22, 18, MediaQuery.of(context).viewInsets.bottom + 18), child: SafeArea(child: SingleChildScrollView(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
    Text('Checkout', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)), const SizedBox(height: 12),
    DropdownButtonFormField<String>(value: fulfillment, decoration: const InputDecoration(labelText: 'How would you like to receive your order?'), items: const [DropdownMenuItem(value: 'delivery', child: Text('Deliver to my address')), DropdownMenuItem(value: 'pickup', child: Text('I will collect it from the store'))], onChanged: (v) => setState(() => fulfillment = v ?? 'delivery')),
    if (fulfillment == 'delivery') ...[const SizedBox(height: 10), if (addresses.isNotEmpty) DropdownButtonFormField<dynamic>(value: addressId, decoration: const InputDecoration(labelText: 'Delivery address'), items: addresses.map((a) => DropdownMenuItem(value: a['id'], child: Text('${a['label']} · ${a['city']}', overflow: TextOverflow.ellipsis))).toList(), onChanged: (v) => setState(() => addressId = v)) else const Text('Add an address to continue with delivery.'), TextButton.icon(onPressed: addAddress, icon: const Icon(Icons.add), label: const Text('Add address'))],
    const SizedBox(height: 10), Card(child: ListTile(leading: const Icon(Icons.payments_outlined, color: Color(0xff666a6e)), title: Text(fulfillment == 'delivery' ? 'Pay cash to the delivery rider' : 'Show your invoice at the store and pay cash'), subtitle: const Text('Cash payment only. Online and card payments are not accepted.'))),
    TextField(controller: instructions, decoration: const InputDecoration(labelText: 'Delivery instructions (optional)')),
    TextField(controller: discountCode, textCapitalization: TextCapitalization.characters, decoration: const InputDecoration(labelText: 'Discount code (optional)')),
    const SizedBox(height: 18), SizedBox(width: double.infinity, child: FilledButton(onPressed: busy || (fulfillment == 'delivery' && addressId == null) ? null : () => Navigator.pop(context, {'branch_id': widget.branchId, 'address_id': addressId, 'fulfillment': fulfillment, 'payment_method': fulfillment == 'delivery' ? 'cod' : 'pay_at_store', 'delivery_instructions': instructions.text, 'discount_code': discountCode.text.trim(), 'idempotency_key': DateTime.now().microsecondsSinceEpoch.toString()}), child: Text(fulfillment == 'delivery' ? 'Place cash-on-delivery order' : 'Place cash pickup order'))),
  ]))));
}

class OrdersPage extends StatefulWidget {
  const OrdersPage({super.key, required this.api, required this.refresh}); final ApiClient api; final int refresh;
  @override
  State<OrdersPage> createState() => _OrdersPageState();
}
class _OrdersPageState extends State<OrdersPage> {
  List<Map<String, dynamic>> orders = []; bool loading = true; String? error;
  @override
  void initState() { super.initState(); load(); }
  @override
  void didUpdateWidget(covariant OrdersPage old) { super.didUpdateWidget(old); if (old.refresh != widget.refresh) load(); }
  Future<void> load() async {
    if (!widget.api.isSignedIn) { setState(() { loading = false; orders = []; }); return; }
    setState(() { loading = true; error = null; });
    try { final d = await widget.api.get('/orders/'); if (mounted) setState(() => orders = asRows(d)); }
    catch (e) { if (mounted) setState(() => error = readableError(e)); }
    finally { if (mounted) setState(() => loading = false); }
  }
  Future<void> invoice(Map<String, dynamic> order) async {
    try { final id = order['id'].toString(); final bytes = await widget.api.getBytes('/orders/$id/invoice/'); final dir = await getTemporaryDirectory(); final file = File('${dir.path}/tariq-mart-invoice-${id.substring(0, 8)}.pdf'); await file.writeAsBytes(bytes); await Share.shareXFiles([XFile(file.path)], text: 'Tariq Cash and Carry Mart order invoice'); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  Future<void> cancelOrder(Map<String, dynamic> order) async {
    try { await widget.api.post('/orders/${order['id']}/cancel/'); await load(); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  @override
  Widget build(BuildContext context) {
    if (!widget.api.isSignedIn) return const _Message(message: 'Sign in to see your orders.');
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return _Message(message: error!, button: 'Retry', onPressed: load);
    if (orders.isEmpty) return const _Message(message: 'Your orders will appear here after checkout.', icon: Icons.receipt_long_outlined);
    return RefreshIndicator(onRefresh: load, child: ListView.builder(padding: const EdgeInsets.all(12), itemCount: orders.length, itemBuilder: (context, i) {
      final o = orders[i]; final id = o['id'].toString(); final canCancel = ['pending', 'confirmed'].contains(o['status']);
      return Card(color: Colors.white, child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Expanded(child: Text('Order ${id.substring(0, 8)}', style: const TextStyle(fontWeight: FontWeight.bold))), Text(pkr(o['total']), style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xff666a6e)))]),
        Text('${o['branch_name'] ?? ''} · ${o['fulfillment'] ?? ''}'), const SizedBox(height: 5),
        Chip(label: Text('${o['status']}'.replaceAll('_', ' ').toUpperCase())), const SizedBox(height: 4),
        Text('${asRows(o['items']).length} product line(s) · ${paymentLabel(o['payment_method'])}'),
        Wrap(alignment: WrapAlignment.end, children: [TextButton.icon(onPressed: () => invoice(o), icon: const Icon(Icons.picture_as_pdf_outlined), label: const Text('Invoice')), if (canCancel) TextButton.icon(onPressed: () => cancelOrder(o), icon: const Icon(Icons.cancel_outlined), label: const Text('Cancel order'))]),
      ])));
    }));
  }
}

class AccountPage extends StatefulWidget {
  const AccountPage({super.key, required this.api, required this.onChanged}); final ApiClient api; final VoidCallback onChanged;
  @override
  State<AccountPage> createState() => _AccountPageState();
}
class _AccountPageState extends State<AccountPage> {
  Map<String, dynamic>? user; bool loading = false;
  @override
  void initState() { super.initState(); if (widget.api.isSignedIn) load(); }
  Future<void> load() async { setState(() => loading = true); try { final d = await widget.api.get('/auth/me/'); if (mounted) setState(() => user = Map<String, dynamic>.from(d['user'])); } catch (_) {} finally { if (mounted) setState(() => loading = false); } }
  Future<void> signOut() async { await widget.api.signOut(); if (mounted) setState(() => user = null); widget.onChanged(); }
  Future<void> chooseLanguage() async {
    final selected = await showModalBottomSheet<String>(context: context, builder: (ctx) => SafeArea(child: Column(mainAxisSize: MainAxisSize.min, children: [const ListTile(title: Text('Preferred language')), ListTile(title: const Text('English'), onTap: () => Navigator.pop(ctx, 'en')), ListTile(title: const Text('Urdu'), onTap: () => Navigator.pop(ctx, 'ur'))])));
    if (selected == null) return;
    try { await widget.api.patch('/auth/me/', {'preferred_language': selected}); await load(); }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  Future<void> openList(String path, String title, {bool notifications = false}) async {
    try {
      final rows = asRows(await widget.api.get(path));
      if (!mounted) return;
      await showModalBottomSheet<void>(context: context, isScrollControlled: true, builder: (ctx) => SafeArea(child: SizedBox(height: MediaQuery.of(ctx).size.height * .72, child: Column(children: [Padding(padding: const EdgeInsets.all(18), child: Text(title, style: Theme.of(ctx).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold))), Expanded(child: rows.isEmpty ? const _Message(message: 'Nothing to show yet.') : ListView.separated(itemCount: rows.length, separatorBuilder: (_, __) => const Divider(height: 1), itemBuilder: (ctx, i) { final row = rows[i]; return ListTile(leading: Icon(notifications ? Icons.notifications_outlined : Icons.local_offer_outlined), title: Text(row['title']?.toString() ?? row['name']?.toString() ?? ''), subtitle: Text(row['body']?.toString() ?? row['description']?.toString() ?? ''), onTap: notifications ? () async { try { await widget.api.post('/notifications/${row['id']}/read/'); } catch (_) {} } : null); }))]))));
    } catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e)))); }
  }
  @override
  Widget build(BuildContext context) {
    if (!widget.api.isSignedIn || user == null) return AuthPanel(api: widget.api, onSuccess: () { load(); widget.onChanged(); });
    if (loading) return const Center(child: CircularProgressIndicator());
    return ListView(padding: const EdgeInsets.all(18), children: [CircleAvatar(radius: 35, child: Text((user?['username'] ?? 'U').toString().substring(0, 1).toUpperCase(), style: const TextStyle(fontSize: 25))), const SizedBox(height: 12), Center(child: Text(user?['username'] ?? '', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold))), Center(child: Text(user?['email'] ?? '')), const SizedBox(height: 20), Card(color: Colors.white, child: Column(children: [ListTile(leading: const Icon(Icons.business), title: const Text('Account type'), subtitle: Text(user?['role'] == 'business' ? (user?['business_approved'] == true ? 'Approved business buyer' : 'Business account pending approval') : 'Retail customer')), ListTile(leading: const Icon(Icons.language), title: const Text('Language preference'), subtitle: Text(user?['preferred_language'] == 'ur' ? 'Urdu' : 'English'), onTap: chooseLanguage), ListTile(leading: const Icon(Icons.card_membership), title: const Text('Membership'), subtitle: Text(user?['membership_number']?.toString().isNotEmpty == true ? user!['membership_number'] : 'No membership number')), ListTile(leading: const Icon(Icons.favorite_border), title: const Text('Saved favorites'), trailing: const Icon(Icons.chevron_right), onTap: () => openList('/wishlist/', 'Saved favorites')), ListTile(leading: const Icon(Icons.local_offer_outlined), title: const Text('Offers'), trailing: const Icon(Icons.chevron_right), onTap: () => openList('/promotions/', 'Current offers')), ListTile(leading: const Icon(Icons.notifications_outlined), title: const Text('Notifications'), trailing: const Icon(Icons.chevron_right), onTap: () => openList('/notifications/', 'Notifications', notifications: true))])), const SizedBox(height: 12), OutlinedButton.icon(onPressed: signOut, icon: const Icon(Icons.logout), label: const Text('Sign out'))]);
  }
}

class AuthPanel extends StatefulWidget {
  const AuthPanel({super.key, required this.api, required this.onSuccess}); final ApiClient api; final VoidCallback onSuccess;
  @override
  State<AuthPanel> createState() => _AuthPanelState();
}
class _AuthPanelState extends State<AuthPanel> {
  final form = GlobalKey<FormState>(); final username = TextEditingController(), password = TextEditingController(), email = TextEditingController(), phone = TextEditingController(), business = TextEditingController();
  bool register = false, busy = false, businessRole = false; String? error;
  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    setState(() { busy = true; error = null; });
    try {
      final data = register ? await widget.api.post('/auth/register/', {'username': username.text.trim(), 'email': email.text.trim(), 'password': password.text, 'phone_number': phone.text.trim(), 'role': businessRole ? 'business' : 'customer', 'business_name': business.text.trim()}) : await widget.api.post('/auth/login/', {'username': username.text.trim(), 'password': password.text});
      await widget.api.setToken(data['token']); widget.onSuccess();
    } catch (e) { if (mounted) setState(() => error = readableError(e)); }
    finally { if (mounted) setState(() => busy = false); }
  }
  @override
  Widget build(BuildContext context) => Center(child: SingleChildScrollView(padding: const EdgeInsets.all(22), child: Card(color: Colors.white, child: Padding(padding: const EdgeInsets.all(20), child: Form(key: form, child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [Image.asset('assets/tariq_mart_logo.png', width: 80, height: 80), const SizedBox(height: 8), Text(register ? 'Create your account' : 'Welcome to Tariq Cash and Carry Mart', textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)), const SizedBox(height: 18), TextFormField(controller: username, decoration: const InputDecoration(labelText: 'Username'), validator: (v) => v == null || v.trim().length < 3 ? 'Enter at least 3 characters.' : null), if (register) ...[TextFormField(controller: email, decoration: const InputDecoration(labelText: 'Email'), keyboardType: TextInputType.emailAddress), TextFormField(controller: phone, decoration: const InputDecoration(labelText: 'Phone number'), keyboardType: TextInputType.phone), SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Business / wholesale account'), value: businessRole, onChanged: (v) => setState(() => businessRole = v)), if (businessRole) TextFormField(controller: business, decoration: const InputDecoration(labelText: 'Business name'), validator: (v) => businessRole && (v == null || v.isEmpty) ? 'Enter business name.' : null)], TextFormField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Password'), validator: (v) => v == null || v.length < (register ? 8 : 1) ? (register ? 'Use at least 8 characters.' : 'Enter your password.') : null), if (error != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text(error!, style: const TextStyle(color: Colors.red))), const SizedBox(height: 16), FilledButton(onPressed: busy ? null : submit, child: busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : Text(register ? 'Create account' : 'Sign in')), TextButton(onPressed: () => setState(() { register = !register; error = null; }), child: Text(register ? 'Already registered? Sign in' : 'New here? Create an account'))]))))));
}

class _Message extends StatelessWidget {
  const _Message({required this.message, this.icon = Icons.shopping_basket_outlined, this.button, this.onPressed});
  final String message; final IconData icon; final String? button; final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) => Center(child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 46, color: Colors.grey), const SizedBox(height: 12), Text(message, textAlign: TextAlign.center), if (button != null) TextButton(onPressed: onPressed, child: Text(button!))])));
}
