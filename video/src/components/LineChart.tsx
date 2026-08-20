import React, { useMemo } from "react";
import { fontStack } from "../fonts";
import { TEXT, type Theme } from "../theme";
import type { Metric, Series } from "../data/types";
import { formatTick, formatValue } from "../format";
import { LogoBadge } from "./LogoBadge";
import {
  LABEL_H,
  LABEL_SPACING,
  LABEL_W,
  LABEL_X,
  PLOT,
  TOP_PAD,
  bezierPath,
  bottomPadFor,
  consecutiveRuns,
  makeScales,
  monotoneSegments,
  tipFor,
  truncateBezier,
  type Bezier,
} from "../layout/geometry";
import { domainFor, ticksFor, type Domain } from "../layout/scale";
import { resolveCollisions } from "../layout/collision";

const LOGO_SIZE = 40;

interface Props {
  slug: string;
  series: Series[];
  years: number[];
  metric: Metric;
  theme: Theme;
  /** 年インデックスの小数位置（イージング済み） */
  pos: number;
  /** 直近のフレームぶんの pos。縦軸のレンジをなめらかに動かすために使う */
  posHistory: number[];
}

/** pos の時点で見えている値（年をまたぐ途中の補間値も含む） */
function visibleValues(series: Series[], pos: number): number[] {
  const out: number[] = [];
  const k = Math.floor(pos + 1e-9);
  const t = pos - k;
  for (const s of series) {
    for (let i = 0; i <= Math.min(k, s.values.length - 1); i++) {
      const v = s.values[i];
      if (v !== null) out.push(v);
    }
    if (t > 1e-9 && k + 1 < s.values.length) {
      const a = s.values[k];
      const b = s.values[k + 1];
      if (a !== null && b !== null) out.push(a + (b - a) * t);
    }
  }
  return out;
}

/**
 * 縦軸のレンジ。
 *
 * 各時点の「切りのよいレンジ」を直近フレームぶん平均することで、
 * 目盛りが1本増える瞬間に軸が跳ねるのを均している。
 * 平均すると現在の値がはみ出しうるので、最後に必ず収まるところまで広げ直す。
 */
function smoothedDomain(series: Series[], pos: number, posHistory: number[]): Domain {
  const samples = posHistory.map((p) => domainFor(visibleValues(series, p)));
  const weightSum = samples.length * (samples.length + 1) / 2;
  let min = 0;
  let max = 0;
  samples.forEach((d, i) => {
    const w = (i + 1) / weightSum; // 新しいフレームほど重く
    min += d.min * w;
    max += d.max * w;
  });

  const now = visibleValues(series, pos);
  const needMax = Math.max(0, ...now) * 1.01;
  const needMin = Math.min(0, ...now) * 1.01;

  const result = { min: Math.min(min, needMin), max: Math.max(max, needMax) };
  return result.max === result.min ? { min: result.min, max: result.min + 1 } : result;
}

export const LineChart: React.FC<Props> = ({
  slug,
  series,
  years,
  metric,
  theme,
  pos,
  posHistory,
}) => {
  const runsPerSeries = useMemo(
    () => series.map((s) => consecutiveRuns(s.values)),
    [series],
  );

  const domain = smoothedDomain(series, pos, posHistory);
  const { x, y } = makeScales(years, domain);
  const ticks = ticksFor(domain, 5);

  const k = Math.min(years.length - 1, Math.floor(pos + 1e-9));
  const t = Math.max(0, Math.min(1, pos - k));

  // 各社の曲線を作る。接線は全期間の点から求めるので、
  // 先端が進んでも描き終わった部分の形は変わらない。
  const drawn = series.map((s, si) => {
    const visible: Bezier[] = [];
    const dots: { i: number; v: number }[] = [];
    let tip: { sx: number; sy: number; v: number; opacity: number } | null = null;

    for (const run of runsPerSeries[si]) {
      const segments = monotoneSegments(
        run.map((i) => ({ i, sx: x(i), sy: y(s.values[i] as number) })),
      );
      for (const seg of segments) {
        if (seg.i1 <= k) {
          visible.push(seg);
        } else if (seg.i0 === k && t > 1e-9) {
          const cut = truncateBezier(seg, t);
          visible.push(cut);
          tip = { sx: cut.p1[0], sy: cut.p1[1], v: invertY(cut.p1[1], domain), opacity: 1 };
        }
      }
      for (const i of run) {
        if (i <= k) dots.push({ i, v: s.values[i] as number });
      }
    }

    if (tip === null) {
      // 曲線が伸びていない＝欠損の縁にいる。0に落とさず、その場で濃度だけ変える
      const edge = tipFor(s.values, pos);
      if (edge !== null) {
        tip = { sx: x(edge.i), sy: y(edge.v), v: edge.v, opacity: edge.opacity };
      }
    }

    return { series: s, visible, dots, tip };
  });

  const withTip = drawn.filter(
    (d): d is typeof d & { tip: NonNullable<typeof d.tip> } => d.tip !== null,
  );

  const placed = resolveCollisions(
    withTip.map((d) => ({ id: d.series.companyId, desiredY: d.tip.sy })),
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

      {years.map((yr, i) => {
        const active = i === currentYearIndex;
        const cx = x(i);
        const ly = PLOT.y + PLOT.h + 40;
        return (
          <g key={yr}>
            {active ? (
              <rect x={cx - 32} y={ly - 25} width={64} height={34} rx={17} fill={theme.accent} />
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

      {/* 折れ線。欠損年をまたぐところは別のサブパスなので線が途切れる */}
      {drawn.map(({ series: s, visible, dots }) => (
        <g key={s.companyId}>
          {groupContiguous(visible).map((group, gi) => (
            <path
              key={gi}
              d={bezierPath(group)}
              fill="none"
              stroke={s.color}
              strokeWidth={4.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {/* 実際に開示されている年の点。曲線が実測点を勝手に作っていないことを示すので、
              線と同色で塗り潰さず中抜きにして必ず見えるようにする */}
          {dots.map((d) => (
            <circle
              key={d.i}
              cx={x(d.i)}
              cy={y(d.v)}
              r={3.9}
              fill={theme.background}
              stroke={s.color}
              strokeWidth={2.2}
            />
          ))}
        </g>
      ))}

      {/* リード線と先端の点は、カードより先にまとめて描く */}
      {withTip.map(({ series: s, tip }) => {
        const cardY = placedById.get(s.companyId) ?? tip.sy;
        const cardX = Math.min(tip.sx + 18, LABEL_X);
        return (
          <g key={`lead-${s.companyId}`} opacity={tip.opacity}>
            <polyline
              points={`${tip.sx},${tip.sy} ${tip.sx + 9},${tip.sy} ${cardX},${cardY}`}
              fill="none"
              stroke={s.color}
              strokeWidth={1.4}
              opacity={0.5}
            />
            <circle cx={tip.sx} cy={tip.sy} r={7} fill={s.color} stroke="#FFFFFF" strokeWidth={2.5} />
          </g>
        );
      })}

      {/* 先端のカード型ラベル */}
      {withTip.map(({ series: s, tip }) => {
        const cardY = placedById.get(s.companyId) ?? tip.sy;
        const cardTop = cardY - LABEL_H / 2;
        const cardX = Math.min(tip.sx + 18, LABEL_X);
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
            <LogoBadge
              slug={slug}
              companyId={s.companyId}
              monogram={s.monogram}
              color={s.color}
              x={cardX + 12}
              y={cardY - LOGO_SIZE / 2}
              size={LOGO_SIZE}
            />
            <text x={cardX + 62} y={cardY - 6} fontSize={23} fontWeight={700} fill={TEXT.onLight}>
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

/** 画面のY座標を値に戻す（曲線上の先端の値を出すため） */
function invertY(sy: number, domain: Domain): number {
  const bottom = bottomPadFor(domain);
  const ratio = (PLOT.y + PLOT.h - bottom - sy) / (PLOT.h - TOP_PAD - bottom);
  return domain.min + ratio * (domain.max - domain.min);
}

/** つながっている区間をひとつのパスにまとめる（欠損はここで切れる） */
function groupContiguous(segments: Bezier[]): Bezier[][] {
  const out: Bezier[][] = [];
  let current: Bezier[] = [];
  for (const seg of segments) {
    if (current.length && current[current.length - 1].i1 !== seg.i0) {
      out.push(current);
      current = [];
    }
    current.push(seg);
  }
  if (current.length) out.push(current);
  return out;
}
