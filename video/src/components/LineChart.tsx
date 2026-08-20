import React, { useMemo } from "react";
import { fontStack } from "../fonts";
import { TEXT, type Theme } from "../theme";
import type { Metric, Series } from "../data/types";
import { formatTick, formatValue } from "../format";
import {
  LABEL_H,
  LABEL_SPACING,
  LABEL_W,
  LABEL_X,
  PLOT,
  makeScales,
  tipFor,
  visibleRuns,
} from "../layout/geometry";
import { blendDomain, domainFor, ticksFor } from "../layout/scale";
import { resolveCollisions } from "../layout/collision";

interface Props {
  series: Series[];
  years: number[];
  metric: Metric;
  theme: Theme;
  /** 年インデックスの小数位置（イージング済み） */
  pos: number;
}

export const LineChart: React.FC<Props> = ({ series, years, metric, theme, pos }) => {
  // 各年時点での縦軸レンジを先に出しておき、年をまたぐときに滑らかに混ぜる
  const domains = useMemo(
    () =>
      years.map((_, k) => {
        const seen: number[] = [];
        for (const s of series) {
          for (let i = 0; i <= k; i++) {
            const v = s.values[i];
            if (v !== null) seen.push(v);
          }
        }
        return domainFor(seen);
      }),
    [series, years],
  );

  const k = Math.min(years.length - 1, Math.floor(pos + 1e-9));
  const t = Math.min(1, Math.max(0, pos - k));
  const domain = blendDomain(domains[k], domains[Math.min(years.length - 1, k + 1)], t);
  const { x, y } = makeScales(years, domain);
  const ticks = ticksFor(domain, 5);

  const tips = series
    .map((s) => ({ s, tip: tipFor(s.values, pos) }))
    .filter((e): e is { s: Series; tip: NonNullable<ReturnType<typeof tipFor>> } =>
      e.tip !== null,
    );

  const placed = resolveCollisions(
    tips.map(({ s, tip }) => ({ id: s.companyId, desiredY: y(tip.v) })),
    {
      minSpacing: LABEL_SPACING,
      minY: PLOT.y + LABEL_H / 2,
      maxY: PLOT.y + PLOT.h - LABEL_H / 2,
    },
  );
  const placedById = new Map(placed.map((p) => [p.id, p.y]));

  const guideX = x(pos);
  const currentYearIndex = Math.round(pos);

  return (
    <svg
      width={1080}
      height={1920}
      style={{ position: "absolute", top: 0, left: 0 }}
      fontFamily={fontStack}
    >
      {/* 横罫線と縦軸ラベル */}
      {ticks.map((tv) => {
        const ty = y(tv);
        const isZero = Math.abs(tv) < 1e-9;
        return (
          <g key={tv}>
            <line
              x1={PLOT.x}
              x2={PLOT.x + PLOT.w}
              y1={ty}
              y2={ty}
              stroke={isZero ? theme.gridZero : theme.grid}
              strokeWidth={isZero ? 2.5 : 1.5}
            />
            <text
              x={PLOT.x - 14}
              y={ty + 8}
              textAnchor="end"
              fontSize={23}
              fontWeight={700}
              fill={TEXT.muted}
            >
              {formatTick(tv, metric.id)}
            </text>
          </g>
        );
      })}

      {/* 現在年のガイド線 */}
      <line
        x1={guideX}
        x2={guideX}
        y1={PLOT.y - 12}
        y2={PLOT.y + PLOT.h + 6}
        stroke={theme.accent}
        strokeWidth={2}
        strokeDasharray="6 8"
        opacity={0.55}
      />

      {/* 横軸ラベル */}
      {years.map((yr, i) => {
        const active = i === currentYearIndex;
        const cx = x(i);
        const ly = PLOT.y + PLOT.h + 40;
        return (
          <g key={yr}>
            {active ? (
              <rect
                x={cx - 32}
                y={ly - 25}
                width={64}
                height={34}
                rx={17}
                fill={theme.accent}
              />
            ) : null}
            <text
              x={cx}
              y={ly}
              textAnchor="middle"
              fontSize={20}
              fontWeight={active ? 900 : 700}
              fill={active ? TEXT.onLight : TEXT.muted}
            >
              {yr}
            </text>
          </g>
        );
      })}

      {/* 折れ線。欠損年をまたぐところは別のサブパスにして途切れさせる */}
      {series.map((s) => {
        const runs = visibleRuns(s.values, pos);
        return (
          <g key={s.companyId}>
            {runs.map((run, ri) => {
              if (run.length === 1) {
                return (
                  <circle
                    key={ri}
                    cx={x(run[0].i)}
                    cy={y(run[0].v)}
                    r={5}
                    fill={s.color}
                  />
                );
              }
              const d = run
                .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.i).toFixed(2)},${y(p.v).toFixed(2)}`)
                .join(" ");
              return (
                <path
                  key={ri}
                  d={d}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={4.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              );
            })}
          </g>
        );
      })}

      {/* リード線と先端の点は、カードより先にまとめて描く（他社のカードで切れないように） */}
      {tips.map(({ s, tip }) => {
        const px = x(tip.i);
        const py = y(tip.v);
        const cardY = placedById.get(s.companyId) ?? py;
        const cardX = Math.min(px + 18, LABEL_X);
        return (
          <g key={`lead-${s.companyId}`} opacity={tip.opacity}>
            <polyline
              points={`${px},${py} ${px + 9},${py} ${cardX},${cardY}`}
              fill="none"
              stroke={s.color}
              strokeWidth={1.4}
              opacity={0.5}
            />
            <circle cx={px} cy={py} r={7} fill={s.color} stroke="#FFFFFF" strokeWidth={2.5} />
          </g>
        );
      })}

      {/* 先端のカード型ラベル */}
      {tips.map(({ s, tip }) => {
        const px = x(tip.i);
        const cardY = placedById.get(s.companyId) ?? y(tip.v);
        const cardTop = cardY - LABEL_H / 2;
        // カードは線の先端を追う。右端では画面からはみ出さないところで止める
        const cardX = Math.min(px + 18, LABEL_X);
        return (
          <g key={s.companyId} opacity={tip.opacity}>
            <rect
              x={cardX}
              y={cardTop}
              width={LABEL_W}
              height={LABEL_H}
              rx={14}
              fill="#FFFFFF"
              stroke={s.color}
              strokeWidth={3}
            />
            {/* 社名と数値は上下に分ける。横並びだと社名の長さで数値と当たる */}
            <circle cx={cardX + 24} cy={cardY - 14} r={8} fill={s.color} />
            <text
              x={cardX + 42}
              y={cardY - 6}
              fontSize={23}
              fontWeight={700}
              fill={TEXT.onLight}
            >
              {s.nameJa}
            </text>
            <text
              x={cardX + LABEL_W - 16}
              y={cardY + 26}
              textAnchor="end"
              fontSize={33}
              fontWeight={900}
              fill={s.color}
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {formatValue(tip.v, metric.id)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
