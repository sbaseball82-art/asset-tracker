import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/holdings_sync.dart';
import '../data/repository.dart';
import '../domain/models.dart';

/// DI：本番では FirebaseMarketDataRepository 等に差し替え（仕様書 §25）
final repositoryProvider = Provider<MarketDataRepository>((ref) {
  return MockMarketDataRepository();
});

/// ポートフォリオ計算（保有数×単価 → 評価額・配分%）
class Portfolio {
  /// quantities（fundId->保有数）から Fund リストを構築。配分%は評価額比で自動計算。
  static List<Fund> build(
      List<FundMeta> metas, Map<String, double> quantities) {
    final values = <String, double>{};
    double total = 0;
    for (final m in metas) {
      final q = quantities[m.id] ?? 0;
      final v = q * m.unitPriceJpy;
      values[m.id] = v;
      total += v;
    }
    final funds = metas.map((m) {
      final v = values[m.id]!;
      final alloc = total > 0 ? v / total * 100 : 0.0;
      return Fund(m.id, m.name, double.parse(alloc.toStringAsFixed(1)),
          isEtf: m.isEtf, quantity: quantities[m.id] ?? 0, valueJpy: v);
    }).toList();
    funds.sort((a, b) => b.valueJpy.compareTo(a.valueJpy));
    return funds;
  }
}

/// 保有数（fundId -> 株数/口数）。編集・GitHub同期の両方からここを更新する。
class HoldingsNotifier extends StateNotifier<Map<String, double>> {
  HoldingsNotifier(super.initial);

  void setQuantity(String fundId, double quantity) {
    state = {...state, fundId: quantity < 0 ? 0 : quantity};
  }

  void replaceAll(Map<String, double> next) => state = {...next};
}

final holdingsProvider =
    StateNotifierProvider<HoldingsNotifier, Map<String, double>>((ref) {
  final repo = ref.watch(repositoryProvider);
  return HoldingsNotifier(repo.defaultQuantities);
});

/// 保有数から評価額・配分%を計算したファンド一覧（画面とスコア計算の元データ）
final fundsProvider = Provider<List<Fund>>((ref) {
  final repo = ref.watch(repositoryProvider);
  final q = ref.watch(holdingsProvider);
  return Portfolio.build(repo.fundMetas, q);
});

/// ポートフォリオ合計評価額（円）
final totalValueProvider = Provider<double>((ref) =>
    ref.watch(fundsProvider).fold(0.0, (a, f) => a + f.valueJpy));

/// GitHub holdings.json 同期の状態と実行
class SyncController extends StateNotifier<SyncState> {
  final Ref ref;
  SyncController(this.ref) : super(SyncState.initial);

  HoldingsSyncService _service() {
    final repo = ref.read(repositoryProvider);
    return HoldingsSyncService(
        url: repo.holdingsSourceUrl, fundCodeToId: repo.fundCodeToId);
  }

  /// GitHub→失敗なら同梱コピー の順で保有数を反映
  Future<void> sync() async {
    state = const SyncState(SyncStatus.loading, 'GitHubから同期中…');
    final service = _service();
    try {
      final q = await service.fetchFromGitHub();
      ref.read(holdingsProvider.notifier).replaceAll(q);
      state = SyncState(SyncStatus.github, 'GitHubと同期済み', DateTime.now());
    } catch (_) {
      try {
        final q = await service.loadBundled();
        ref.read(holdingsProvider.notifier).replaceAll(q);
        state = SyncState(SyncStatus.bundled,
            'オフライン：アプリ内蔵の登録値を使用', DateTime.now());
      } catch (e) {
        state = const SyncState(SyncStatus.error, '同期に失敗しました');
      }
    }
  }
}

final syncProvider =
    StateNotifierProvider<SyncController, SyncState>((ref) {
  return SyncController(ref);
});

/// オンにしている保有ファンド
final enabledFundsProvider = StateProvider<Set<String>>((ref) {
  final repo = ref.watch(repositoryProvider);
  return repo.fundMetas.map((m) => m.id).toSet();
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

/// 全イベントをスコア付きで（保有数の編集・同期が即スコアに反映される）
final scoredEventsProvider = Provider<List<ScoredEvent>>((ref) {
  final repo = ref.watch(repositoryProvider);
  final funds = ref.watch(fundsProvider);
  final enabled = ref.watch(enabledFundsProvider);
  return repo.events
      .map((e) => ScoredEvent(
          e, ImpactEngine.evaluate(e, funds, enabled, repo.holdingWeights)))
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
