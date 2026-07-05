import 'package:flutter_test/flutter_test.dart';
import 'package:my_earnings_calendar/data/repository.dart';
import 'package:my_earnings_calendar/domain/models.dart';
import 'package:my_earnings_calendar/state/providers.dart';

void main() {
  final repo = MockMarketDataRepository();
  final allFunds = repo.funds.map((f) => f.id).toSet();

  group('ImpactEngine', () {
    test('MSFT決算の直接エクスポージャーが正しく合算される', () {
      final e = repo.events.firstWhere((x) => x.symbols.contains('MSFT'));
      final im = ImpactEngine.evaluate(e, repo.funds, allFunds, repo.holdingWeights);
      // VTI 36×5.2% + SPX 10.8×6.1% + QQQ 5.4×7.6% + NDX 0.3×7.6% + FNG 8.1×10%
      const expected = 36.0 * 5.2 / 100 + 10.8 * 6.1 / 100 + 5.4 * 7.6 / 100 + 0.3 * 7.6 / 100 + 8.1 * 10 / 100;
      expect(im.directPct, isNotNull);
      expect(im.directPct!, closeTo(expected, 0.001));
      expect(im.score, inInclusiveRange(0, 100));
      expect(im.contributions, isNotEmpty);
    });

    test('ファンドをオフにするとエクスポージャーが減る', () {
      final e = repo.events.firstWhere((x) => x.symbols.contains('MSFT'));
      final full = ImpactEngine.evaluate(e, repo.funds, allFunds, repo.holdingWeights);
      final without = ImpactEngine.evaluate(
          e, repo.funds, allFunds.difference({'VTI'}), repo.holdingWeights);
      expect(without.directPct!, lessThan(full.directPct!));
    });

    test('マクロ「高」はスコア88、直接%はnull', () {
      final e = repo.events.firstWhere((x) => x.macroLevel == '高');
      final im = ImpactEngine.evaluate(e, repo.funds, allFunds, repo.holdingWeights);
      expect(im.directPct, isNull);
      expect(im.score, 88);
    });

    test('複数銘柄イベント（AAPL+AMZN）は合算される', () {
      final e = repo.events.firstWhere((x) => x.symbols.length == 2);
      final im = ImpactEngine.evaluate(e, repo.funds, allFunds, repo.holdingWeights);
      final aaplOnly = ImpactEngine.evaluate(
          MarketEvent(id: 99, date: e.date, dow: e.dow, type: e.type, title: 't', time: 't', symbols: const ['AAPL'], note: ''),
          repo.funds, allFunds, repo.holdingWeights);
      expect(im.directPct!, greaterThan(aaplOnly.directPct!));
    });

    test('starsは1〜5に収まる', () {
      for (final e in repo.events) {
        final im = ImpactEngine.evaluate(e, repo.funds, allFunds, repo.holdingWeights);
        expect(im.stars, inInclusiveRange(1, 5));
      }
    });
  });
}
