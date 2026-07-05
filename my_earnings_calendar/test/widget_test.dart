import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:my_earnings_calendar/main.dart';

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
  });
}
