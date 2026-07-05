import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/holdings_sync.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'common.dart';

String formatJpy(double v) {
  final s = v.round().toString();
  final b = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return '¥$b';
}

String formatQty(double q) {
  if (q == q.roundToDouble()) {
    final s = q.round().toString();
    final b = StringBuffer();
    for (var i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
      b.write(s[i]);
    }
    return b.toString();
  }
  return q.toString();
}

/// ETF一覧（仕様書 §8）。保有数の編集・GitHub同期・トグルでインパクト再計算。
class EtfScreen extends ConsumerWidget {
  const EtfScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final funds = ref.watch(fundsProvider);
    final total = ref.watch(totalValueProvider);
    final enabled = ref.watch(enabledFundsProvider);
    final sync = ref.watch(syncProvider);
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

          // 合計評価額 + GitHub同期
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('合計評価額（概算）', style: text.bodySmall),
                          Text(formatJpy(total),
                              style: text.headlineSmall?.copyWith(
                                  fontWeight: FontWeight.w800,
                                  color: AppColors.earnings)),
                        ],
                      ),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: sync.status == SyncStatus.loading
                          ? null
                          : () => ref.read(syncProvider.notifier).sync(),
                      icon: sync.status == SyncStatus.loading
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.sync, size: 18),
                      label: const Text('GitHub同期',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Icon(
                    switch (sync.status) {
                      SyncStatus.github => Icons.cloud_done_rounded,
                      SyncStatus.bundled => Icons.cloud_off_rounded,
                      SyncStatus.error => Icons.error_outline_rounded,
                      _ => Icons.cloud_outlined,
                    },
                    size: 15,
                    color: switch (sync.status) {
                      SyncStatus.github => AppColors.green,
                      SyncStatus.error => const Color(0xFFF07A7A),
                      _ => Theme.of(context).colorScheme.outline,
                    },
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      sync.syncedAt == null
                          ? sync.message
                          : '${sync.message}（${sync.syncedAt!.hour}:${sync.syncedAt!.minute.toString().padLeft(2, '0')}）',
                      style: text.bodySmall,
                    ),
                  ),
                ]),
              ],
            ),
          ),
          const SizedBox(height: 12),

          ...funds.map((f) {
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
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(f.name,
                                style: text.bodyLarge
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                          ),
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
                              ref.read(enabledFundsProvider.notifier).state =
                                  next;
                            },
                          ),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                ImpactBar(
                                    pct: f.allocPct,
                                    max: 40,
                                    color: AppColors.earnings),
                                const SizedBox(height: 4),
                                Text(
                                    '配分 ${f.allocPct}% · ${formatQty(f.quantity)}${f.unitLabel} · ${formatJpy(f.valueJpy)}',
                                    style: text.bodySmall),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          // 保有数の編集
                          IconButton.filledTonal(
                            tooltip: '保有数を編集',
                            iconSize: 17,
                            visualDensity: VisualDensity.compact,
                            icon: const Icon(Icons.edit_rounded),
                            onPressed: () => _showEditDialog(context, ref, f),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
          const SizedBox(height: 8),
          Text(
              '単価は2026/7時点の概算（本番は価格APIに置換）。保有数は鉛筆アイコンから編集、'
              'またはGitHubの holdings.json を書き換えて「GitHub同期」を押すと自動反映されます。',
              style: text.bodySmall),
        ],
      ),
    );
  }

  Future<void> _showEditDialog(
      BuildContext context, WidgetRef ref, Fund f) async {
    final controller =
        TextEditingController(text: formatQty(f.quantity).replaceAll(',', ''));
    final repo = ref.read(repositoryProvider);
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: Text('${f.id} の保有数を編集',
            style: const TextStyle(fontWeight: FontWeight.w800)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
              ],
              decoration: InputDecoration(
                suffixText: f.unitLabel,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14)),
                labelText: '保有${f.unitLabel}数',
              ),
            ),
            const SizedBox(height: 8),
            Text('保存すると配分％とImpact Scoreがすぐ再計算されます。',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              // GitHub登録値（初期値）に戻す
              final def = repo.defaultQuantities[f.id] ?? 0;
              ref.read(holdingsProvider.notifier).setQuantity(f.id, def);
              Navigator.of(context).pop();
            },
            child: const Text('初期値に戻す'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('キャンセル'),
          ),
          FilledButton(
            onPressed: () {
              final v = double.tryParse(controller.text.trim());
              if (v != null) {
                ref.read(holdingsProvider.notifier).setQuantity(f.id, v);
              }
              Navigator.of(context).pop();
            },
            child: const Text('保存'),
          ),
        ],
      ),
    );
  }
}

/// ETF詳細：構成銘柄・保有比率・評価額換算・前月比較（モック）
class EtfDetailScreen extends ConsumerWidget {
  final Fund fund;
  const EtfDetailScreen({super.key, required this.fund});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(repositoryProvider);
    // 最新の保有数を反映したファンド情報を取得（一覧から渡された値は古い可能性）
    final live = ref
        .watch(fundsProvider)
        .firstWhere((f) => f.id == fund.id, orElse: () => fund);
    final text = Theme.of(context).textTheme;

    // symbol -> weight（このファンド分）を抽出して降順に
    final rows = <MapEntry<String, double>>[];
    repo.holdingWeights.forEach((sym, m) {
      final w = m[live.id];
      if (w != null) rows.add(MapEntry(sym, w));
    });
    rows.sort((a, b) => b.value.compareTo(a.value));
    final covered = rows.fold(0.0, (a, r) => a + r.value);
    final others = (100 - covered).clamp(0.0, 100.0);

    return Scaffold(
      appBar: AppBar(
        title: Text(live.name,
            style: const TextStyle(fontWeight: FontWeight.w800)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 40),
        children: [
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('あなたの配分', style: text.bodySmall),
                        Text('${live.allocPct}%',
                            style: text.displaySmall?.copyWith(
                                fontWeight: FontWeight.w800,
                                color: AppColors.earnings)),
                      ],
                    ),
                    const Spacer(),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('保有 ${formatQty(live.quantity)}${live.unitLabel}',
                            style: text.bodyMedium
                                ?.copyWith(fontWeight: FontWeight.w700)),
                        Text('評価額 ${formatJpy(live.valueJpy)}',
                            style: text.bodyMedium
                                ?.copyWith(fontWeight: FontWeight.w700)),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                // 構成の帯グラフ（上位銘柄＋その他）
                Text('ファンドの中身（株式の割合）',
                    style:
                        text.bodySmall?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: SizedBox(
                    height: 10,
                    child: Row(
                      children: [
                        for (var i = 0; i < rows.length; i++)
                          Expanded(
                            flex: (rows[i].value * 10).round(),
                            child: Container(
                                color: AppColors.earnings.withValues(
                                    alpha: 1 - i * 0.09)),
                          ),
                        Expanded(
                          flex: (others * 10).round(),
                          child: Container(
                              color: Theme.of(context)
                                  .colorScheme
                                  .outlineVariant),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                    '主要銘柄 ${covered.toStringAsFixed(1)}% ＋ その他 ${others.toStringAsFixed(1)}%（決算カレンダー対象銘柄のみ抜粋・概算）',
                    style: text.bodySmall),
              ],
            ),
          ),
          const SizedBox(height: 16),
          ...rows.map((r) {
            // 前月比較のモック（決定的に生成：本番はETF Holdings APIの差分）
            final delta = ((r.key.codeUnitAt(0) + r.value * 10) % 7 - 3) / 10;
            final up = delta >= 0;
            final yourShare = live.valueJpy * r.value / 100; // あなたの投資額換算
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
                          Text('${r.key} · あなたの投資額 約${formatJpy(yourShare)}',
                              style: text.bodySmall),
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
