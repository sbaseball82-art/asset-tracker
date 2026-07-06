import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../domain/models.dart';

/// ===== デザイントークン（Copilot / Apple HIG 参照） =====
class AppColors {
  static const earnings = Color(0xFF7C8CF8); // 決算
  static const macro = Color(0xFF35C7B8); // 経済指標
  static const special = Color(0xFFE0AC4E); // イベント
  static const green = Color(0xFF4FC985);

  static Color typeColor(EventType t) {
    switch (t) {
      case EventType.earnings:
        return earnings;
      case EventType.macro:
        return macro;
      case EventType.special:
        return special;
    }
  }

  static String typeLabel(EventType t) {
    switch (t) {
      case EventType.earnings:
        return '決算';
      case EventType.macro:
        return '経済指標';
      case EventType.special:
        return 'イベント';
    }
  }
}

/// スコア→タイムライン色（仕様書 §18：赤=重要/黄=普通/青=低）
Color timelineColor(int score) {
  if (score >= 80) return const Color(0xFFF07A7A);
  if (score >= 60) return const Color(0xFFE0AC4E);
  return const Color(0xFF6FA8F0);
}

/// ===== 汎用カード（Glassmorphism・仕様書 §4） =====
class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final bool blur;

  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.onTap,
    this.blur = false,
  });

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final body = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: dark
            ? Colors.white.withValues(alpha: blur ? 0.06 : 0.05)
            : Colors.white.withValues(alpha: blur ? 0.65 : 0.85),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: dark
              ? Colors.white.withValues(alpha: 0.08)
              : Colors.black.withValues(alpha: 0.05),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: dark ? 0.35 : 0.06),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
    final card = blur
        ? ClipRRect(
            borderRadius: BorderRadius.circular(22),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
              child: body,
            ),
          )
        : body;
    if (onTap == null) return card;
    return GestureDetector(onTap: onTap, child: card);
  }
}

class TypePill extends StatelessWidget {
  final EventType type;
  const TypePill(this.type, {super.key});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.typeColor(type);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        AppColors.typeLabel(type),
        style: TextStyle(
            color: c, fontSize: 11, fontWeight: FontWeight.w700),
      ),
    );
  }
}

/// インパクトバー（アニメーション付き）
class ImpactBar extends StatelessWidget {
  final double pct;
  final double max;
  final Color color;
  const ImpactBar(
      {super.key, required this.pct, this.max = 12, required this.color});

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final frac = (pct / max).clamp(0.0, 1.0);
    return ClipRRect(
      borderRadius: BorderRadius.circular(999),
      child: Container(
        height: 6,
        color: dark
            ? Colors.white.withValues(alpha: 0.08)
            : Colors.black.withValues(alpha: 0.06),
        child: TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: frac),
          duration: const Duration(milliseconds: 650),
          curve: Curves.easeOutCubic,
          builder: (context, v, _) => Align(
            alignment: Alignment.centerLeft,
            child: FractionallySizedBox(
              widthFactor: v,
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                      colors: [color, color.withValues(alpha: 0.7)]),
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class Stars extends StatelessWidget {
  final int count;
  const Stars(this.count, {super.key});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(
        5,
        (i) => Icon(
          i < count ? Icons.star_rounded : Icons.star_border_rounded,
          size: 14,
          color: i < count
              ? AppColors.special
              : Theme.of(context).colorScheme.outline.withValues(alpha: 0.5),
        ),
      ),
    );
  }
}

/// ===== イベント詳細ボトムシート（仕様書 §9） =====
Future<void> showEventDetail(BuildContext context, ScoredEvent s) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (context) => EventDetailSheet(scored: s),
  );
}

class EventDetailSheet extends ConsumerWidget {
  final ScoredEvent scored;
  const EventDetailSheet({super.key, required this.scored});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final e = scored.event;
    final im = scored.impact;
    final byFund = im.byFund;
    final c = AppColors.typeColor(e.type);
    final text = Theme.of(context).textTheme;
    final dark = Theme.of(context).brightness == Brightness.dark;

    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          constraints:
              BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          color: dark
              ? const Color(0xFF141A2C).withValues(alpha: 0.92)
              : Colors.white.withValues(alpha: 0.92),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 16),
                    decoration: BoxDecoration(
                      color: Colors.grey.withValues(alpha: 0.4),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                Row(children: [
                  TypePill(e.type),
                  const SizedBox(width: 8),
                  Text('${e.mmdd}（${e.dow}）· ${e.time}',
                      style: text.bodySmall),
                ]),
                const SizedBox(height: 10),
                Text(e.title,
                    style: text.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w800, height: 1.25)),
                const SizedBox(height: 8),
                Text(e.note, style: text.bodyMedium),
                const SizedBox(height: 20),

                // Impact Score
                GlassCard(
                  child: Row(
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('IMPACT SCORE',
                              style: text.labelSmall?.copyWith(
                                  letterSpacing: 1.2,
                                  fontWeight: FontWeight.w700)),
                          const SizedBox(height: 4),
                          Text('${im.score}',
                              style: text.displaySmall?.copyWith(
                                  fontWeight: FontWeight.w800,
                                  color: c,
                                  height: 1.0)),
                        ],
                      ),
                      const Spacer(),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Stars(im.stars),
                          const SizedBox(height: 6),
                          if (im.directPct != null)
                            Text(
                                '総資産の ${im.directPct!.toStringAsFixed(1)}% が直接反応',
                                style: text.bodySmall),
                          if (im.directPct == null && im.macroLevel != null)
                            Text('資産全体への影響度：${im.macroLevel}',
                                style: text.bodySmall),
                          if (im.directPct == null && im.macroLevel == null)
                            Text('間接的な影響', style: text.bodySmall),
                        ],
                      ),
                    ],
                  ),
                ),

                // どのETF・投信にどれだけ効くか（ファンド別影響度%）
                if (byFund.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  Text('どのETF・投信に効く？（影響度）',
                      style: text.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  GlassCard(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      children: [
                        for (final fi in byFund) ...[
                          Row(children: [
                            Expanded(
                                child: Text(fi.fund.name,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: text.bodyMedium?.copyWith(
                                        fontWeight: FontWeight.w700))),
                            Text('${fi.fundPct.toStringAsFixed(1)}%',
                                style: text.titleSmall?.copyWith(
                                    fontWeight: FontWeight.w800, color: c)),
                          ]),
                          const SizedBox(height: 4),
                          ImpactBar(pct: fi.fundPct, max: 25, color: c),
                          const SizedBox(height: 3),
                          Row(children: [
                            Expanded(
                              child: Text(
                                  '対象銘柄：${fi.symbols.join('・')}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: text.bodySmall),
                            ),
                            Text(
                                '資産全体へ +${fi.contribPct.toStringAsFixed(2)}%',
                                style: text.bodySmall),
                          ]),
                          if (fi != byFund.last)
                            const Padding(
                              padding: EdgeInsets.symmetric(vertical: 10),
                              child: Divider(height: 1),
                            ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                      '「影響度」＝そのファンドの中で、このイベントの銘柄が占める割合（％）。'
                      '大きいほどファンドの値動きに直結します。',
                      style: text.bodySmall),
                ],

                // 保有ETFへの影響（内訳）
                if (im.contributions.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  Text('銘柄×ファンドの内訳',
                      style: text.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  ...im.contributions.map((p) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: GlassCard(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(children: [
                                Expanded(
                                    child: Text(p.fund.name,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: text.bodyMedium?.copyWith(
                                            fontWeight: FontWeight.w700))),
                                Text('+${p.contribPct.toStringAsFixed(2)}%',
                                    style: text.bodyMedium?.copyWith(
                                        fontWeight: FontWeight.w800,
                                        color: c)),
                              ]),
                              const SizedBox(height: 4),
                              Text(
                                  '${p.symbol} をファンド内 ${p.weightPct}% 組入 × 配分 ${p.fund.allocPct}%',
                                  style: text.bodySmall),
                              const SizedBox(height: 8),
                              ImpactBar(pct: p.contribPct, max: 4, color: c),
                            ],
                          ),
                        ),
                      )),
                ],

                if (e.indirect != null) ...[
                  const SizedBox(height: 16),
                  GlassCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('間接的な影響',
                            style: text.titleSmall?.copyWith(
                                color: c, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 4),
                        Text(e.indirect!, style: text.bodyMedium),
                      ],
                    ),
                  ),
                ],

                // 今回見るポイント（仕様書 §9）
                if (e.watchPoints.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  Text('今回見るポイント',
                      style: text.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: e.watchPoints
                        .map((w) => Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 12, vertical: 7),
                              decoration: BoxDecoration(
                                color: c.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text(w,
                                  style: TextStyle(
                                      color: c,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w700)),
                            ))
                        .toList(),
                  ),
                ],

                const SizedBox(height: 20),
                GlassCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('自分のスタンス',
                          style: text.labelMedium?.copyWith(
                              color: AppColors.special,
                              fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      Text('イベントで売買はしない。結果を眺めて、積立は淡々と継続。',
                          style: text.bodyMedium),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16)),
                    ),
                    child: const Text('閉じる',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
