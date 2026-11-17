import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiFailure implements Exception {
  ApiFailure(this.message, [this.statusCode]);
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({String? baseUrl}) : baseUrl = (baseUrl ?? const String.fromEnvironment(
    'API_BASE_URL', defaultValue: 'http://10.0.2.2:8000')).replaceAll(RegExp(r'/$'), '');
  final String baseUrl;
  final _storage = const FlutterSecureStorage();
  String? _token;
  String? get token => _token;
  bool get isSignedIn => _token != null;

  Future<void> restore() async { _token = await _storage.read(key: 'api_token'); }
  Future<void> setToken(String token) async {
    _token = token;
    await _storage.write(key: 'api_token', value: token);
  }
  Future<void> signOut() async {
    _token = null;
    await _storage.delete(key: 'api_token');
  }

  Uri _uri(String path) => Uri.parse('$baseUrl/api/v1$path');
  Map<String, String> _headers({bool jsonBody = true}) => {
    if (jsonBody) 'Content-Type': 'application/json',
    if (_token != null) 'Authorization': 'Token $_token',
  };
  dynamic _decode(http.Response response) {
    dynamic body;
    try { body = response.body.isEmpty ? null : jsonDecode(utf8.decode(response.bodyBytes)); }
    catch (_) { body = null; }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      var message = 'Request failed (${response.statusCode}).';
      if (body is Map) {
        final values = body.values;
        final detail = body['detail'] ?? (values.isEmpty ? null : values.first);
        if (detail is String) message = detail;
        if (detail is List && detail.isNotEmpty) message = detail.first.toString();
      }
      throw ApiFailure(message, response.statusCode);
    }
    return body;
  }
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    final uri = _uri(path).replace(queryParameters: query);
    return _decode(await http.get(uri, headers: _headers()));
  }
  Future<dynamic> post(String path, [Map<String, dynamic>? data]) async =>
      _decode(await http.post(_uri(path), headers: _headers(), body: jsonEncode(data ?? {})));
  Future<dynamic> patch(String path, Map<String, dynamic> data) async =>
      _decode(await http.patch(_uri(path), headers: _headers(), body: jsonEncode(data)));
  Future<void> delete(String path) async {
    final response = await http.delete(_uri(path), headers: _headers());
    if (response.statusCode < 200 || response.statusCode >= 300) _decode(response);
  }
  Future<Uint8List> getBytes(String path) async {
    final response = await http.get(_uri(path), headers: {if (_token != null) 'Authorization': 'Token $_token'});
    if (response.statusCode < 200 || response.statusCode >= 300) _decode(response);
    return response.bodyBytes;
  }
}

