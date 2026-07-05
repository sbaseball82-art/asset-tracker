/// ドメインモデル（Presentation / Data から独立）
library;

enum EventType { earnings, macro, special }

class Fund {
  final String id;
  final String name;
  final double allocPct; // ポートフォリオ内の配分（%）
  const Fund(this.id, this.name, this.allocPct);
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
