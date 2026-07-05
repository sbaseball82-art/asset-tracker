import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'common.dart';

/// ETF一覧（仕様書 §8）。トグルでインパクト再計算、タップで構成銘柄へ。
class EtfScreen extends ConsumerWidget {
  const EtfScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(repositoryProvider);
    final enabled = ref.watch(enabledFundsProvider);
    final text = Theme.of(context).textTheme;

    return SafeArea(
      bottom: false,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: [
          Text('ポートフォリオ',
              style:
                  text.headlineMedium?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text('オンにしたファンドだけでImpact Scoreを再計算します。タップで構成銘柄。',
              style: text.bodySmall),
          const SizedBox(height: 16),
          ...repo.funds.map((f) {
            final on = enabled.contains(f.id);
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Opacity(
                opacity: on ? 1 : 0.55,
                child: GlassCard(
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(
                        builder: (_) => EtfDetailScreen(fund: f)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(f.name,
                                style: text.bodyLarge
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                            const SizedBox(height: 8),
                            ImpactBar(
                                pct: f.allocPct,
                                max: 40,
                                color: AppColors.earnings),
                            const SizedBox(height: 4),
                            Text('配分 ${f.allocPct}%', style: text.bodySmall),
                          ],
                        ),
                      ),
                      const SizedBox(width: 12),
                      Switch.adaptive(
                        value: on,
                        activeThumbColor: AppColors.green,
                        onChanged: (v) {
                          final next = {...enabled};
                          if (v) {
                            next.add(f.id);
                          } else {
                            next.remove(f.id);
                          }
                          ref.read(enabledFundsProvider.notifier).state = next;
                        },
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
          const SizedBox(height: 8),
          Text('配分は2026/7/3時点の構成（概算）。組入比率は公表ベースの概算値です。',
              style: text.bodySmall),
        ],
      ),
    );
  }
}

/// ETF詳細：構成銘柄・保有比率・前月比較（モック）
class EtfDetailScreen extends ConsumerWidget {
  final Fund fund;
  const EtfDetailScreen({super.key, required this.fund});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(repositoryProvider);
    final text = Theme.of(context).textTheme;

    // symbol -> weight（このファンド分）を抽出して降順に
    final rows = <MapEntry<String, double>>[];
    repo.holdingWeights.forEach((sym, m) {
      final w = m[fund.id];
      if (w != null) rows.add(MapEntry(sym, w));
    });
    rows.sort((a, b) => b.value.compareTo(a.value));

    return Scaffold(
      appBar: AppBar(
        title: Text(fund.name,
            style: const TextStyle(fontWeight: FontWeight.w800)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 40),
        children: [
          GlassCard(
            child: Row(
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('あなたの配分', style: text.bodySmall),
                    Text('${fund.allocPct}%',
                        style: text.displaySmall?.copyWith(
                            fontWeight: FontWeight.w800,
                            color: AppColors.earnings)),
                  ],
                ),
                const Spacer(),
                Expanded(
                  child: Text(
                    '主要な組入銘柄（決算カレンダー対象のみ抜粋・概算）',
                    style: text.bodySmall,
                    textAlign: TextAlign.right,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          ...rows.map((r) {
            // 前月比較のモック（決定的に生成：本番はETF Holdings APIの差分）
            final delta = ((r.key.codeUnitAt(0) + r.value * 10) % 7 - 3) / 10;
            final up = delta >= 0;
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: GlassCard(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(repo.symbolNames[r.key] ?? r.key,
                              style: text.bodyLarge
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                          Text(r.key, style: text.bodySmall),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('${r.value}%',
                            style: text.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        Text(
                          '前月 ${up ? '+' : ''}${delta.toStringAsFixed(1)}pt',
                          style: text.bodySmall?.copyWith(
                              color: up
                                  ? AppColors.green
                                  : const Color(0xFFF07A7A)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }),
          const SizedBox(height: 8),
          Text('※前月比較はサンプル値。ETF Holdings API接続後に実データへ置換されます。',
              style: text.bodySmall),
        ],
      ),
    );
  }
}
