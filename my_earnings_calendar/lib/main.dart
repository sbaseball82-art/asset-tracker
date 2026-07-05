import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'state/providers.dart';
import 'ui/common.dart';
import 'ui/etf_screen.dart';
import 'ui/home_screen.dart';

void main() {
  runApp(const ProviderScope(child: MyEarningsCalendarApp()));
}

/// テーマ：昼＝ライト／夜＝ダーク自動切替（仕様書 §4, §14）
ThemeData buildTheme(Brightness b) {
  final dark = b == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF7C8CF8),
    brightness: b,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor:
        dark ? const Color(0xFF0A0E1A) : const Color(0xFFF3F4F9),
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      foregroundColor: dark ? Colors.white : const Color(0xFF16181D),
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.android: ZoomPageTransitionsBuilder(),
    }),
  );
}

class MyEarningsCalendarApp extends StatelessWidget {
  const MyEarningsCalendarApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'My Earnings Calendar',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: ThemeMode.system,
      home: const RootShell(),
    );
  }
}

class RootShell extends StatefulWidget {
  const RootShell({super.key});
  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      body: IndexedStack(
        index: _index,
        children: const [HomeScreen(), EtfScreen(), NotifScreen()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        backgroundColor:
            Theme.of(context).colorScheme.surface.withValues(alpha: 0.85),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.home_outlined),
              selectedIcon: Icon(Icons.home_rounded),
              label: 'ホーム'),
          NavigationDestination(
              icon: Icon(Icons.pie_chart_outline),
              selectedIcon: Icon(Icons.pie_chart_rounded),
              label: 'ETF'),
          NavigationDestination(
              icon: Icon(Icons.notifications_outlined),
              selectedIcon: Icon(Icons.notifications_rounded),
              label: '通知'),
        ],
      ),
    );
  }
}

/// 通知設定（仕様書 §10。FCM/APNs 実接続はTODO）
class NotifScreen extends ConsumerWidget {
  const NotifScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(notifSettingsProvider);
    final text = Theme.of(context).textTheme;

    Widget tile(String key, String title, String desc) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: GlassCard(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: text.bodyLarge
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(desc, style: text.bodySmall),
                  ],
                ),
              ),
              Switch.adaptive(
                value: settings[key] ?? false,
                activeThumbColor: AppColors.green,
                onChanged: (v) {
                  ref.read(notifSettingsProvider.notifier).state = {
                    ...settings,
                    key: v,
                  };
                },
              ),
            ],
          ),
        ),
      );
    }

    return SafeArea(
      bottom: false,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: [
          Text('通知',
              style:
                  text.headlineMedium?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 16),
          tile('today', '当日の朝に通知', '「今日はNVIDIA決算です」形式で、その日のイベントを通知'),
          tile('after', '決算終了後に結果を通知', '売上・EPS・ガイダンス・AI要約（API接続後）'),
          tile('macro', '経済指標もすべて通知', 'CPI・雇用統計など影響度「高」以外も含む'),
          const SizedBox(height: 8),
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('ネイティブ接続で有効になる機能',
                    style: text.titleSmall?.copyWith(
                        color: AppColors.special,
                        fontWeight: FontWeight.w800)),
                const SizedBox(height: 6),
                Text(
                  'プッシュ通知（FCM / APNs）、ロック画面のLive Activity（決算までのカウントダウン・Dynamic Island）、'
                  'ホーム画面ウィジェット、Siriショートカット「今週の注目は？」は、'
                  'Firebase設定ファイルとApple Developer設定を追加すると有効になります。'
                  '接続ポイントはリポジトリのTODOコメントに明記しています。',
                  style: text.bodyMedium?.copyWith(height: 1.6),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
