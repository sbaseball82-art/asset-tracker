/// ドメインモデル（Presentation / Data から独立）
library;

enum EventType { earnings, macro, special }

class Fund {
  final String id;
  final String name;
  final double allocPct; // ポートフォリオ内の配分（%）
  final bool isEtf; // true=ETF（株数）/ false=投資信託（口数）
  final double quantity; // 保有数（株 or 口）
  final double valueJpy; // 評価額（円）
  const Fund(this.id, this.name, this.allocPct,
      {this.isEtf = true, this.quantity = 0, this.valueJpy = 0});

  String get unitLabel => isEtf ? '株' : '口';
}

/// ファンドの静的メタ情報（保有数と切り離した定義）
class FundMeta {
  final String id;
  final String name;
  final bool isEtf;
  final double unitPriceJpy; // 1株/1口あたりの概算価格（円）
  const FundMeta(this.id, this.name, this.isEtf, this.unitPriceJpy);
}

class MarketEvent {
  final int id;
  final String date; // ISO: 2026-07-14
  final String dow; // 月〜金
  final EventType type;
  final String title;
  final String time;
  final List<String> symbols; // 直接影響する保有関連銘柄
  final String? indirect; // 間接影響の説明
  final String? macroLevel; // 高 / 中 / 低
  final String note;
  final List<String> watchPoints;

  const MarketEvent({
    required this.id,
    required this.date,
    required this.dow,
    required this.type,
    required this.title,
    required this.time,
    this.symbols = const [],
    this.indirect,
    this.macroLevel,
    required this.note,
    this.watchPoints = const [],
  });

  String get mmdd => date.substring(5).replaceAll('-', '/');
}

class FundContribution {
  final Fund fund;
  final String symbol;
  final double weightPct; // ファンド内ウェイト
  final double contribPct; // 総資産への寄与（%）
  const FundContribution(this.fund, this.symbol, this.weightPct, this.contribPct);
}

/// ファンド単位に集計したイベント影響（可視化用）
class FundImpact {
  final Fund fund;
  final double fundPct; // そのファンドの中で反応する割合（%）
  final double contribPct; // 総資産への寄与（%）
  final List<String> symbols; // 影響銘柄
  const FundImpact(this.fund, this.fundPct, this.contribPct, this.symbols);
}

class EventImpact {
  final double? directPct; // 総資産の直接反応（%）
  final String? macroLevel;
  final List<FundContribution> contributions;
  final int score; // Impact Score 0-100

  const EventImpact({
    this.directPct,
    this.macroLevel,
    this.contributions = const [],
    required this.score,
  });

  int get stars => (score / 20).ceil().clamp(1, 5).toInt();

  /// contributions をファンド単位に集計（影響度の大きい順）
  List<FundImpact> get byFund {
    final map = <String, List<FundContribution>>{};
    for (final c in contributions) {
      map.putIfAbsent(c.fund.id, () => []).add(c);
    }
    final list = map.values.map((cs) {
      final fundPct = cs.fold(0.0, (a, c) => a + c.weightPct);
      final contrib = cs.fold(0.0, (a, c) => a + c.contribPct);
      final syms = cs.map((c) => c.symbol).toSet().toList();
      return FundImpact(cs.first.fund, fundPct, contrib, syms);
    }).toList();
    list.sort((a, b) => b.fundPct.compareTo(a.fundPct));
    return list;
  }
}

class ScoredEvent {
  final MarketEvent event;
  final EventImpact impact;
  const ScoredEvent(this.event, this.impact);
}

class WeekSpec {
  final String label;
  final String range;
  final List<String> days;
  const WeekSpec(this.label, this.range, this.days);
}
