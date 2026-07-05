import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'common.dart';

/// ホーム（仕様書 §7）
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(repositoryProvider);
    final funds = ref.watch(fundsProvider);
    final top5 = ref.watch(top5Provider);
    final today = ref.watch(todayEventsProvider);
    final weekIdx = ref.watch(weekIndexProvider);
    final weekEvents = ref.watch(weekEventsProvider);
    final enabled = ref.watch(enabledFundsProvider);
    final text = Theme.of(context).textTheme;

    return SafeArea(
      bottom: false,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: [
          // ヘッダー
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('こんにちは、${repo.userName}',
                        style: text.bodyMedium),
                    const SizedBox(height: 2),
                    Text('あなたの一週間',
                        style: text.headlineMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                  ],
                ),
              ),
              Text('2026年7月', style: text.bodySmall),
            ],
          ),
          const SizedBox(height: 18),

          // TOP5（最重要・最上部固定相当）
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('あなたの資産に影響するイベント TOP5',
                    style:
                        text.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                Text('今後30日 · Impact Score順', style: text.bodySmall),
                const SizedBox(height: 12),
                ...List.generate(top5.length, (i) {
                  final s = top5[i];
                  final c = AppColors.typeColor(s.event.type);
                  return InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: () => showEventDetail(context, s),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 26,
                            child: Text('${i + 1}',
                                style: text.titleMedium?.copyWith(
                                    fontWeight: FontWeight.w800,
                                    color: i == 0
                                        ? AppColors.special
                                        : null)),
                          ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(s.event.title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: text.bodyMedium?.copyWith(
                                        fontWeight: FontWeight.w700)),
                                const SizedBox(height: 2),
                                Row(children: [
                                  Text('${s.event.mmdd}（${s.event.dow}）',
                                      style: text.bodySmall),
                                  const SizedBox(width: 8),
                                  Stars(s.impact.stars),
                                ]),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text('${s.impact.score}',
                                  style: text.titleLarge?.copyWith(
                                      fontWeight: FontWeight.w800, color: c)),
                              Text('IMPACT',
                                  style: text.labelSmall
                                      ?.copyWith(letterSpacing: 1.1)),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                }),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // 今日のイベント
          Text('今日のイベント',
              style: text.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          if (today.isEmpty)
            GlassCard(
              child: Text('今日は、あなたの資産に効くイベントはありません。積立は自動で続きます。',
                  style: text.bodyMedium),
            )
          else
            ...today.map((s) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _EventCard(s: s),
                )),
          const SizedBox(height: 20),

          // 今週のイベント + 週切替
          Row(
            children: [
              Text('今週のイベント',
                  style:
                      text.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              const Spacer(),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: 40,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: repo.weeks.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, i) {
                final sel = i == weekIdx;
                final scheme = Theme.of(context).colorScheme;
                return InkWell(
                  borderRadius: BorderRadius.circular(999),
                  onTap: () =>
                      ref.read(weekIndexProvider.notifier).state = i,
                  child: Container(
                    alignment: Alignment.center,
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    decoration: BoxDecoration(
                      color: sel ? scheme.primary : scheme.surface,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: sel ? scheme.primary : scheme.outlineVariant,
                      ),
                    ),
                    child: Text(
                      repo.weeks[i].label,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: sel ? scheme.onPrimary : scheme.onSurface,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 10),
          if (weekEvents.isEmpty)
            GlassCard(
                child: Text('この週は静かです。', style: text.bodyMedium))
          else
            ...weekEvents.map((s) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _EventCard(s: s),
                )),
          const SizedBox(height: 20),

          // 保有ETF
          Text('保有ETF',
              style: text.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: funds
                .where((f) => enabled.contains(f.id))
                .map((f) => Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 7),
                      decoration: BoxDecoration(
                        color: AppColors.earnings.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text('${f.id} ${f.allocPct}%',
                          style: const TextStyle(
                              color: AppColors.earnings,
                              fontWeight: FontWeight.w700,
                              fontSize: 13)),
                    ))
                .toList(),
          ),
          const SizedBox(height: 20),

          // AI Weekly Summary（仕様書 §11。現状はモック文面）
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.auto_awesome,
                      size: 18, color: AppColors.special),
                  const SizedBox(width: 6),
                  Text('AI Weekly Summary',
                      style: text.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w800)),
                ]),
                const SizedBox(height: 8),
                Text(repo.aiWeeklySummary,
                    style: text.bodyMedium?.copyWith(height: 1.6)),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Text(
            '日程・構成比は報道／公表ベースの概算サンプル。Impact Scoreは保有配分×組入比率から算出した目安で、値動きの予想ではありません。投資助言ではありません。',
            style: text.bodySmall?.copyWith(height: 1.5),
          ),
        ],
      ),
    );
  }
}

class _EventCard extends ConsumerWidget {
  final ScoredEvent s;
  const _EventCard({required this.s});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final text = Theme.of(context).textTheme;
    final c = AppColors.typeColor(s.event.type);
    final byFund = s.impact.byFund;
    return GlassCard(
      onTap: () => showEventDetail(context, s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                  color: timelineColor(s.impact.score), shape: BoxShape.circle),
            ),
            const SizedBox(width: 8),
            TypePill(s.event.type),
            const SizedBox(width: 8),
            Expanded(
                child: Text('${s.event.mmdd}（${s.event.dow}）· ${s.event.time}',
                    style: text.bodySmall,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis)),
            Text('${s.impact.score}',
                style: text.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w800, color: c)),
          ]),
          const SizedBox(height: 6),
          Text(s.event.title,
              style: text.bodyLarge?.copyWith(fontWeight: FontWeight.w700)),
          if (s.impact.directPct != null) ...[
            const SizedBox(height: 8),
            ImpactBar(pct: s.impact.directPct!, color: c),
            const SizedBox(height: 4),
            Text('総資産の ${s.impact.directPct!.toStringAsFixed(1)}% が直接反応',
                style: text.bodySmall),
            // 影響を受けるファンド（上位3件をチップ表示）
            if (byFund.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  ...byFund.take(3).map((fi) => Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: c.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          '${fi.fund.id} ${fi.fundPct.toStringAsFixed(1)}%',
                          style: TextStyle(
                              color: c,
                              fontSize: 11,
                              fontWeight: FontWeight.w700),
                        ),
                      )),
                  if (byFund.length > 3)
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Text('+${byFund.length - 3}',
                          style: text.bodySmall),
                    ),
                ],
              ),
            ],
          ],
        ],
      ),
    );
  }
}
