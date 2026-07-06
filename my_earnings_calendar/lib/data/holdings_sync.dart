import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;

/// GitHubに登録した holdings.json を取得・解析するサービス。
/// 取得失敗時はアプリ同梱のコピー（assets/holdings.json）へフォールバックする。
class HoldingsSyncService {
  final String url;
  final Map<String, String> fundCodeToId;
  final http.Client Function() clientFactory;

  HoldingsSyncService({
    required this.url,
    required this.fundCodeToId,
    http.Client Function()? clientFactory,
  }) : clientFactory = clientFactory ?? http.Client.new;

  /// holdings.json（{"etf": {ticker: 株数}, "fund": {協会コード: 口数}}）を
  /// fundId -> 保有数 に変換する。未知のティッカー/コードは無視。
  static Map<String, double> parseHoldings(
      String jsonStr, Map<String, String> fundCodeToId) {
    final root = json.decode(jsonStr);
    if (root is! Map<String, dynamic>) {
      throw const FormatException('holdings.json のルートがオブジェクトではありません');
    }
    final result = <String, double>{};
    final etf = root['etf'];
    if (etf is Map<String, dynamic>) {
      etf.forEach((ticker, v) {
        if (v is num) result[ticker] = v.toDouble();
      });
    }
    final fund = root['fund'];
    if (fund is Map<String, dynamic>) {
      fund.forEach((code, v) {
        final id = fundCodeToId[code];
        if (id != null && v is num) result[id] = v.toDouble();
      });
    }
    if (result.isEmpty) {
      throw const FormatException('holdings.json に保有データがありません');
    }
    return result;
  }

  /// GitHub（raw URL）から取得。ネットワーク不通・非公開リポジトリ等は例外。
  Future<Map<String, double>> fetchFromGitHub() async {
    final client = clientFactory();
    try {
      final res = await client
          .get(Uri.parse(url))
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) {
        throw Exception('GitHub応答 ${res.statusCode}');
      }
      return parseHoldings(utf8.decode(res.bodyBytes), fundCodeToId);
    } finally {
      client.close();
    }
  }

  /// アプリ同梱コピー（ビルド時点のGitHub登録値）を読む。
  /// cache:false — テスト間でゾーンをまたぐキャッシュFuture共有を避ける。
  Future<Map<String, double>> loadBundled() async {
    final s =
        await rootBundle.loadString('assets/holdings.json', cache: false);
    return parseHoldings(s, fundCodeToId);
  }
}

/// 同期状態（UI表示用）
enum SyncStatus { idle, loading, github, bundled, error }

class SyncState {
  final SyncStatus status;
  final String message;
  final DateTime? syncedAt;
  const SyncState(this.status, this.message, [this.syncedAt]);

  static const initial = SyncState(SyncStatus.idle, '未同期');
}
