import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/repository.dart';
import '../domain/models.dart';

/// DI：本番では FirebaseMarketDataRepository 等に差し替え（仕様書 §25）
final repositoryProvider = Provider<MarketDataRepository>((ref) {
  return MockMarketDataRepository();
});

/// オンにしている保有ファンド
final enabledFundsProvider = StateProvider<Set<String>>((ref) {
  final repo = ref.watch(repositoryProvider);
  return repo.funds.map((f) => f.id).toSet();
});

/// 選択中の週インデックス
final weekIndexProvider = StateProvider<int>((ref) => 0);

/// Impact Score 算出エンジン（ルールベース初期版）
/// TODO: 仕様書 §17 のAI解析は Cloud Functions + OpenAI 接続後に置換
class ImpactEngine {
  static EventImpact evaluate(
    MarketEvent e,
    List<Fund> funds,
    Set<String> enabled,
    Map<String, Map<String, double>> weights,
  ) {
    double direct = 0;
    final contribs = <FundContribution>[];
    for (final sym in e.symbols) {
      final w = weights[sym];
      if (w == null) continue;
      for (final f in funds) {
        if (!enabled.contains(f.id)) continue;
        final wp = w[f.id];
        if (wp == null) continue;
        final c = f.allocPct * wp / 100;
        direct += c;
        contribs.add(FundContribution(f, sym, wp, c));
      }
    }
    contribs.sort((a, b) => b.contribPct.compareTo(a.contribPct));

    int score;
    double? directPct;
    if (e.symbols.isNotEmpty) {
      directPct = direct;
      score = (35 + direct * 8).clamp(0, 96).round();
    } else if (e.macroLevel == '高') {
      score = 88;
    } else if (e.macroLevel == '中') {
      score = 72;
    } else if (e.macroLevel != null) {
      score = 55;
    } else {
      score = 62; // 間接影響イベント
    }
    return EventImpact(
      directPct: directPct,
      macroLevel: e.macroLevel,
      contributions: contribs,
      score: score,
    );
  }
}

/// 全イベントをスコア付きで
final scoredEventsProvider = Provider<List<ScoredEvent>>((ref) {
  final repo = ref.watch(repositoryProvider);
  final enabled = ref.watch(enabledFundsProvider);
  return repo.events
      .map((e) => ScoredEvent(
          e, ImpactEngine.evaluate(e, repo.funds, enabled, repo.holdingWeights)))
      .toList();
});

/// ホーム最上部：影響TOP5（今後30日）仕様書 §7
final top5Provider = Provider<List<ScoredEvent>>((ref) {
  final all = [...ref.watch(scoredEventsProvider)];
  all.sort((a, b) => b.impact.score.compareTo(a.impact.score));
  return all.take(5).toList();
});

/// 今日のイベント 仕様書 §7
final todayEventsProvider = Provider<List<ScoredEvent>>((ref) {
  final repo = ref.watch(repositoryProvider);
  return ref
      .watch(scoredEventsProvider)
      .where((s) => s.event.date == repo.todayIso)
      .toList();
});

/// 選択中の週のイベント（日付順）
final weekEventsProvider = Provider<List<ScoredEvent>>((ref) {
  final repo = ref.watch(repositoryProvider);
  final week = repo.weeks[ref.watch(weekIndexProvider)];
  final list = ref
      .watch(scoredEventsProvider)
      .where((s) => week.days.contains(s.event.date))
      .toList();
  list.sort((a, b) => a.event.date.compareTo(b.event.date));
  return list;
});

/// 通知設定（仕様書 §10。FCM/APNs 接続までのローカル状態）
final notifSettingsProvider =
    StateProvider<Map<String, bool>>((ref) => {
          'today': true,
          'after': true,
          'macro': false,
        });
