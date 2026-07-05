import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:my_earnings_calendar/data/repository.dart';
import 'package:my_earnings_calendar/domain/models.dart';
import 'package:my_earnings_calendar/main.dart';
import 'package:my_earnings_calendar/state/providers.dart';
import 'package:my_earnings_calendar/ui/common.dart';

void main() {
  testWidgets('アプリが起動しホームが表示される', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: MyEarningsCalendarApp()));
    await tester.pump(const Duration(milliseconds: 700)); // バーのアニメーション分

    expect(find.textContaining('こんにちは'), findsOneWidget);
    expect(find.text('あなたの資産に影響するイベント TOP5'), findsOneWidget);
    expect(find.text('ホーム'), findsOneWidget);
    expect(find.text('ETF'), findsOneWidget);
    expect(find.text('通知'), findsOneWidget);
  });

  testWidgets('ETFタブに切り替えられる', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: MyEarningsCalendarApp()));
    await tester.pump(const Duration(milliseconds: 700));

    await tester.tap(find.text('ETF'));
    await tester.pump(const Duration(milliseconds: 700));
    expect(find.text('ポートフォリオ'), findsOneWidget);
    expect(find.textContaining('VTI'), findsWidgets);
    expect(find.text('GitHub同期'), findsOneWidget);
    expect(find.textContaining('合計評価額'), findsOneWidget);
  });

  testWidgets('保有数を編集すると表示と配分が更新される', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: MyEarningsCalendarApp()));
    await tester.pump(const Duration(milliseconds: 700));

    await tester.tap(find.text('ETF'));
    await tester.pumpAndSettle();

    // 先頭カード（評価額最大のファンド）の鉛筆アイコンから編集
    await tester.tap(find.byIcon(Icons.edit_rounded).first);
    await tester.pumpAndSettle();
    expect(find.textContaining('の保有数を編集'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '999');
    await tester.tap(find.text('保存'));
    await tester.pumpAndSettle();

    expect(find.textContaining('999株'), findsWidgets);
  });

  testWidgets('GitHub同期ボタンでオフライン時は同梱値へフォールバック', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: MyEarningsCalendarApp()));
    await tester.pump(const Duration(milliseconds: 700));

    await tester.tap(find.text('ETF'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('GitHub同期'));
    await tester.pumpAndSettle();

    // テスト環境はネットワーク遮断（HTTP 400）→ 同梱 holdings.json を使用
    expect(find.textContaining('オフライン：アプリ内蔵の登録値を使用'), findsOneWidget);
    // holdings.json の値（VTI 195株）が反映されている
    expect(find.textContaining('195株'), findsWidgets);
  });

  testWidgets('イベント詳細にファンド別影響度%が表示される', (tester) async {
    final repo = MockMarketDataRepository();
    final funds = Portfolio.build(repo.fundMetas, repo.defaultQuantities);
    final e = repo.events.firstWhere((x) => x.symbols.contains('MSFT'));
    final scored = ScoredEvent(
        e,
        ImpactEngine.evaluate(
            e, funds, funds.map((f) => f.id).toSet(), repo.holdingWeights));

    await tester.pumpWidget(ProviderScope(
      child: MaterialApp(
        home: Scaffold(body: EventDetailSheet(scored: scored)),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 700));

    expect(find.text('どのETF・投信に効く？（影響度）'), findsOneWidget);
    // MSFT はファンド内組入%が最大の FANG+（10%）が先頭に来る
    expect(find.textContaining('iFreeNEXT FANG+'), findsWidgets);
    expect(find.textContaining('10.0%'), findsWidgets);
    expect(find.textContaining('資産全体へ +'), findsWidgets);
  });
}
