import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:my_earnings_calendar/data/holdings_sync.dart';
import 'package:my_earnings_calendar/data/repository.dart';
import 'package:my_earnings_calendar/state/providers.dart';

void main() {
  final repo = MockMarketDataRepository();

  group('Portfolio.build（保有数→評価額・配分%）', () {
    test('評価額 = 保有数 × 単価、配分は合計100%', () {
      final funds = Portfolio.build(repo.fundMetas, repo.defaultQuantities);
      expect(funds.length, repo.fundMetas.length);
      final vti = funds.firstWhere((f) => f.id == 'VTI');
      expect(vti.quantity, 195);
      expect(vti.valueJpy, 195 * 48000);
      final totalAlloc = funds.fold(0.0, (a, f) => a + f.allocPct);
      expect(totalAlloc, closeTo(100, 0.5));
      // 評価額の大きい順に並ぶ
      for (var i = 1; i < funds.length; i++) {
        expect(funds[i - 1].valueJpy, greaterThanOrEqualTo(funds[i].valueJpy));
      }
    });

    test('保有数を増やすと配分%が上がる（編集機能の心臓部）', () {
      final before = Portfolio.build(repo.fundMetas, repo.defaultQuantities)
          .firstWhere((f) => f.id == 'QQQ');
      final edited = {...repo.defaultQuantities, 'QQQ': 150.0};
      final after = Portfolio.build(repo.fundMetas, edited)
          .firstWhere((f) => f.id == 'QQQ');
      expect(after.quantity, 150);
      expect(after.allocPct, greaterThan(before.allocPct));
    });

    test('保有数0のファンドは配分0%（クラッシュしない）', () {
      final funds = Portfolio.build(repo.fundMetas, const {});
      expect(funds.every((f) => f.allocPct == 0), isTrue);
    });
  });

  group('HoldingsSyncService.parseHoldings（GitHub holdings.json）', () {
    test('リポジトリ直下の holdings.json（実物）を解析できる', () {
      final jsonStr = File('assets/holdings.json').readAsStringSync();
      final q = HoldingsSyncService.parseHoldings(jsonStr, repo.fundCodeToId);
      expect(q['VYM'], 313);
      expect(q['VTI'], 195);
      expect(q['HDV'], 495);
      expect(q['QQQ'], 15);
      expect(q['FNG'], 36374); // 29313233
      expect(q['SPX'], 850904); // 89311199
      expect(q['NDX'], 276836); // 04311181
      expect(q['SBH'], 1969774); // 8931224C
    });

    test('未知のティッカー・コードは無視される', () {
      const jsonStr =
          '{"etf": {"VTI": 10, "ZZZZ": 5}, "fund": {"99999999": 1, "89311199": 2}}';
      final q = HoldingsSyncService.parseHoldings(jsonStr, repo.fundCodeToId);
      expect(q['VTI'], 10);
      expect(q['ZZZZ'], 5); // ETFはティッカーそのまま（将来の追加銘柄を許容）
      expect(q.containsKey('99999999'), isFalse);
      expect(q['SPX'], 2);
    });

    test('壊れたJSONは FormatException', () {
      expect(
          () => HoldingsSyncService.parseHoldings('{"x": 1}', repo.fundCodeToId),
          throwsFormatException);
    });
  });

  group('EventImpact.byFund（ニュース→ファンド影響の集計）', () {
    test('複数銘柄イベントはファンド単位に合算され、影響度%の降順', () {
      final funds = Portfolio.build(repo.fundMetas, repo.defaultQuantities);
      final e = repo.events.firstWhere((x) => x.symbols.length == 2); // AAPL+AMZN
      final im = ImpactEngine.evaluate(
          e, funds, funds.map((f) => f.id).toSet(), repo.holdingWeights);
      final byFund = im.byFund;
      expect(byFund, isNotEmpty);
      // VTI は AAPL 5.0% + AMZN 3.4% = 8.4% が反応
      final vti = byFund.firstWhere((fi) => fi.fund.id == 'VTI');
      expect(vti.fundPct, closeTo(5.0 + 3.4, 0.001));
      expect(vti.symbols, containsAll(['AAPL', 'AMZN']));
      // 降順ソート
      for (var i = 1; i < byFund.length; i++) {
        expect(byFund[i - 1].fundPct, greaterThanOrEqualTo(byFund[i].fundPct));
      }
      // 各ファンドの寄与の合計 = directPct
      final sum = byFund.fold(0.0, (a, fi) => a + fi.contribPct);
      expect(sum, closeTo(im.directPct!, 0.001));
    });
  });
}
