import '../domain/models.dart';

/// データ層の抽象。将来 Firebase / 決算API / ETF Holdings API 実装に差し替える。
/// （仕様書 §3, §25：Repository パターンで複数プロバイダーへ切替可能に）
abstract class MarketDataRepository {
  List<Fund> get funds;
  List<FundMeta> get fundMetas; // 保有数と切り離したファンド定義
  Map<String, double> get defaultQuantities; // fundId -> 保有数（GitHub holdings.json 由来）
  Map<String, String> get fundCodeToId; // 投信協会コード -> fundId（GitHub同期用）
  String get holdingsSourceUrl; // GitHub上の holdings.json のURL
  Map<String, Map<String, double>> get holdingWeights; // symbol -> fundId -> %
  Map<String, String> get symbolNames;
  List<MarketEvent> get events;
  List<WeekSpec> get weeks;
  String get todayIso;
  String get aiWeeklySummary; // TODO: OpenAI API接続後は Cloud Functions から取得
  String get userName;
}

/// APIキー不要で全画面が動くモック実装（2026年7月・報道ベースの概算サンプル）
class MockMarketDataRepository implements MarketDataRepository {
  @override
  String get userName => 'あなた';

  @override
  String get todayIso => '2026-07-06';

  @override
  List<Fund> get funds => const [
        Fund('VTI', 'VTI 全米株式', 36.0),
        Fund('VYM', 'VYM 米国高配当', 25.0),
        Fund('SPX', 'SBI・V・S&P500', 10.8),
        Fund('FNG', 'iFreeNEXT FANG+', 8.1),
        Fund('SBH', 'SBI・S 米国高配当', 7.4),
        Fund('HDV', 'HDV 米国高配当', 7.0),
        Fund('QQQ', 'QQQ ナスダック100', 5.4),
        Fund('NDX', 'ニッセイNASDAQ100', 0.3),
      ];

  /// ファンド定義（単価は2026/7時点の円換算・概算モック。本番は価格APIへ差替）
  @override
  List<FundMeta> get fundMetas => const [
        FundMeta('VTI', 'VTI 全米株式', true, 48000),
        FundMeta('VYM', 'VYM 米国高配当', true, 20300),
        FundMeta('HDV', 'HDV 米国高配当', true, 18200),
        FundMeta('QQQ', 'QQQ ナスダック100', true, 90500),
        FundMeta('SPX', 'SBI・V・S&P500', false, 3.30), // 基準価額33,000円/万口
        FundMeta('FNG', 'iFreeNEXT FANG+', false, 6.80), // 68,000円/万口
        FundMeta('SBH', 'SBI・S 米国高配当', false, 1.35), // 13,500円/万口
        FundMeta('NDX', 'ニッセイNASDAQ100', false, 2.50), // 25,000円/万口
      ];

  /// GitHubの holdings.json と同じ初期値（オフライン時のフォールバック）
  @override
  Map<String, double> get defaultQuantities => const {
        'VYM': 313,
        'VTI': 195,
        'HDV': 495,
        'QQQ': 15,
        'FNG': 36374, // 29313233 iFreeNEXT FANG+
        'SPX': 850904, // 89311199 SBI・V・S&P500
        'NDX': 276836, // 04311181 ニッセイNASDAQ100
        'SBH': 1969774, // 8931224C SBI・S・米国高配当
      };

  /// 投信協会コード -> アプリ内fundId（holdings.json の "fund" キー対応）
  @override
  Map<String, String> get fundCodeToId => const {
        '29313233': 'FNG',
        '89311199': 'SPX',
        '04311181': 'NDX',
        '8931224C': 'SBH',
      };

  @override
  String get holdingsSourceUrl =>
      'https://raw.githubusercontent.com/sbaseball82-art/asset-tracker/main/holdings.json';

  @override
  Map<String, String> get symbolNames => const {
        'MSFT': 'マイクロソフト',
        'NVDA': 'エヌビディア',
        'AAPL': 'アップル',
        'AMZN': 'アマゾン',
        'GOOGL': 'アルファベット',
        'META': 'メタ',
        'NFLX': 'ネットフリックス',
        'TSLA': 'テスラ',
        'MU': 'マイクロン',
        'JPM': 'JPモルガン',
        'XOM': 'エクソンモービル',
      };

  @override
  Map<String, Map<String, double>> get holdingWeights => const {
        'MSFT': {'VTI': 5.2, 'SPX': 6.1, 'QQQ': 7.6, 'NDX': 7.6, 'FNG': 10},
        'NVDA': {'VTI': 6.0, 'SPX': 7.0, 'QQQ': 9.3, 'NDX': 9.3, 'FNG': 10},
        'AAPL': {'VTI': 5.0, 'SPX': 5.9, 'QQQ': 7.9, 'NDX': 7.9, 'FNG': 10},
        'AMZN': {'VTI': 3.4, 'SPX': 4.0, 'QQQ': 5.4, 'NDX': 5.4, 'FNG': 10},
        'GOOGL': {'VTI': 3.2, 'SPX': 3.8, 'QQQ': 4.8, 'NDX': 4.8, 'FNG': 10},
        'META': {'VTI': 2.4, 'SPX': 2.8, 'QQQ': 4.0, 'NDX': 4.0, 'FNG': 10},
        'NFLX': {'VTI': 0.9, 'SPX': 1.1, 'QQQ': 2.0, 'NDX': 2.0, 'FNG': 10},
        'TSLA': {'VTI': 1.5, 'SPX': 1.8, 'QQQ': 2.7, 'NDX': 2.7},
        'MU': {'VTI': 0.6, 'SPX': 0.7, 'QQQ': 2.1, 'NDX': 2.1, 'FNG': 10},
        'JPM': {'VTI': 1.3, 'SPX': 1.5, 'VYM': 3.4, 'SBH': 3.0},
        'XOM': {'VTI': 0.9, 'SPX': 1.0, 'VYM': 3.0, 'SBH': 2.8, 'HDV': 8.5},
      };

  @override
  List<WeekSpec> get weeks => const [
        WeekSpec('今週', '7/6 – 7/10', ['2026-07-06', '2026-07-07', '2026-07-08', '2026-07-09', '2026-07-10']),
        WeekSpec('来週', '7/13 – 7/17', ['2026-07-13', '2026-07-14', '2026-07-15', '2026-07-16', '2026-07-17']),
        WeekSpec('7/20週', '7/20 – 7/24', ['2026-07-20', '2026-07-21', '2026-07-22', '2026-07-23', '2026-07-24']),
        WeekSpec('7/27週', '7/27 – 7/31', ['2026-07-27', '2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31']),
      ];

  @override
  List<MarketEvent> get events => const [
        MarketEvent(id: 0, date: '2026-07-06', dow: '月', type: EventType.macro, title: '米ISM非製造業（6月）', time: '日本 23:00', macroLevel: '中', note: 'サービス業の景況感。50割れが続くかに注目。'),
        MarketEvent(id: 1, date: '2026-07-07', dow: '火', type: EventType.earnings, title: 'サムスン電子 暫定決算', time: '日本 8:00頃', indirect: 'メモリ市況のセンチメントに波及（MU・SKHY関連）', note: 'HBM出荷と在庫が焦点。数字は速報のみ。', watchPoints: ['HBM出荷', 'NAND価格', '在庫水準']),
        MarketEvent(id: 2, date: '2026-07-08', dow: '水', type: EventType.macro, title: 'FOMC議事録（6月分）', time: '日本 3:00', macroLevel: '中', note: '利上げバイアスの温度感を確認。Warsh体制下の初議事録。'),
        MarketEvent(id: 3, date: '2026-07-10', dow: '金', type: EventType.special, title: 'SKハイニックス 米国上場（SKHY）', time: '米国市場', indirect: '史上最大ADR。メモリ・半導体の需給に注目', note: '調達最大約290億ドル。初値は読めない。', watchPoints: ['初値', '既存半導体株の需給']),
        MarketEvent(id: 4, date: '2026-07-14', dow: '火', type: EventType.earnings, title: 'JPモルガン 決算（銀行決算開幕）', time: '日本 20:00頃', symbols: ['JPM'], note: 'Q2決算シーズンの号砲。', watchPoints: ['純金利収入', '貸倒引当', '通期ガイダンス']),
        MarketEvent(id: 5, date: '2026-07-14', dow: '火', type: EventType.macro, title: '米CPI（6月）', time: '日本 21:30', macroLevel: '高', note: '利上げ観測を左右する最重要指標。'),
        MarketEvent(id: 6, date: '2026-07-16', dow: '木', type: EventType.earnings, title: 'TSMC 決算', time: '日本 15:00頃', indirect: 'AI半導体の需要全体を映す。NVDA・AVGO等に波及', note: 'AIサーバー向け受注動向が焦点。', watchPoints: ['AI向け売上比率', '設備投資計画']),
        MarketEvent(id: 7, date: '2026-07-17', dow: '金', type: EventType.earnings, title: 'ネットフリックス 決算', time: '引け後', symbols: ['NFLX'], note: '会員数と広告事業の伸びに注目。', watchPoints: ['会員純増', '広告Tier', '営業利益率']),
        MarketEvent(id: 8, date: '2026-07-22', dow: '水', type: EventType.earnings, title: 'テスラ 決算', time: '引け後', symbols: ['TSLA'], note: '販売台数とエナジー事業。', watchPoints: ['粗利率', 'エナジー事業', 'ロボタクシー進捗']),
        MarketEvent(id: 9, date: '2026-07-23', dow: '木', type: EventType.earnings, title: 'アルファベット 決算', time: '引け後', symbols: ['GOOGL'], note: '検索広告とクラウドのAI収益化。', watchPoints: ['検索広告', 'クラウド成長率', 'AI投資額']),
        MarketEvent(id: 10, date: '2026-07-28', dow: '火', type: EventType.earnings, title: 'マイクロソフト 決算', time: '引け後', symbols: ['MSFT'], note: 'AzureとAI投資のROIが最大焦点。', watchPoints: ['Azure成長率', 'Copilot収益', '設備投資ガイダンス']),
        MarketEvent(id: 11, date: '2026-07-29', dow: '水', type: EventType.earnings, title: 'メタ 決算 / SKHY 初決算', time: '引け後', symbols: ['META'], indirect: 'SKHYはQ2決算（上場3週後）', note: '広告×AIの利益率。SKHYはHBM出荷。', watchPoints: ['広告単価', 'AI設備投資', 'Reality Labs損益']),
        MarketEvent(id: 12, date: '2026-07-30', dow: '木', type: EventType.earnings, title: 'アップル / アマゾン 決算', time: '引け後', symbols: ['AAPL', 'AMZN'], note: 'メガテック決算のクライマックス。', watchPoints: ['iPhone売上', 'AWS成長率', 'サービス部門']),
        MarketEvent(id: 13, date: '2026-07-31', dow: '金', type: EventType.macro, title: '米PCE（6月）', time: '日本 21:30', macroLevel: '高', note: 'FRBが最重視するインフレ指標。'),
      ];

  @override
  String get aiWeeklySummary =>
      '今週の注目は「メモリ・半導体」。サムスン暫定決算（7/7）とSKハイニックス米国上場（7/10）でメモリ市況のセンチメントが試されます。FOMC議事録（7/8）では利上げバイアスの温度感を確認。来週からは銀行決算とCPIで本格的な決算シーズンに入ります。イベントで売買せず、結果を眺めて淡々と。';
}
