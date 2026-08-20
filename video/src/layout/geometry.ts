/** 折れ線の描画位置と先端の計算。純粋関数のみ。 */

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const PLOT: Rect = { x: 96, y: 596, w: 588, h: 848 };
export const LABEL_X = 700;
export const LABEL_W = 316;
export const LABEL_H = 74;
export const LABEL_SPACING = 82;

export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * フレーム位置を「年インデックスの小数」に変換する。
 * 1期ぶんの中でイージングをかけるので、年をまたぐたびに滑らかに切り替わる。
 */
export function easedPosition(rawPosition: number, lastIndex: number): number {
  const clamped = Math.max(0, Math.min(lastIndex, rawPosition));
  const k = Math.floor(clamped);
  const t = clamped - k;
  if (t === 0) return k;
  return k + easeInOutCubic(t);
}

export interface DataPointXY {
  i: number;
  v: number;
}

/**
 * pos までに見えている部分を、欠損で分割した折れ線の列として返す。
 * 欠損年をまたいで線をつながないのが目的。
 */
export function visibleRuns(values: (number | null)[], pos: number): DataPointXY[][] {
  const last = values.length - 1;
  const k = Math.min(last, Math.floor(pos + 1e-9));
  const t = pos - k;

  const pts: (DataPointXY | null)[] = [];
  for (let i = 0; i <= k; i++) {
    const v = values[i];
    pts.push(v === null ? null : { i, v });
  }

  if (t > 1e-9 && k + 1 <= last) {
    const a = values[k];
    const b = values[k + 1];
    if (a !== null && b !== null) {
      pts.push({ i: k + t, v: a + (b - a) * t });
    }
  }

  const runs: DataPointXY[][] = [];
  let current: DataPointXY[] = [];
  for (const p of pts) {
    if (p === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push(p);
    }
  }
  if (current.length) runs.push(current);
  return runs;
}

export interface Tip {
  i: number;
  v: number;
  opacity: number;
}

/**
 * 先端ラベルの位置と値。
 * 欠損に入るときはフェードアウト、欠損から戻るときはフェードインする。
 * 0に落とさないのは「欠損を0として見せない」ため。
 */
export function tipFor(values: (number | null)[], pos: number): Tip | null {
  const last = values.length - 1;
  const k = Math.min(last, Math.floor(pos + 1e-9));
  const t = pos - k;

  if (t <= 1e-9) {
    const v = values[k];
    return v === null ? null : { i: k, v, opacity: 1 };
  }

  const a = values[k];
  const b = k + 1 <= last ? values[k + 1] : null;

  if (a !== null && b !== null) return { i: k + t, v: a + (b - a) * t, opacity: 1 };
  if (a !== null) return { i: k, v: a, opacity: 1 - t };
  if (b !== null) return { i: k + 1, v: b, opacity: t };
  return null;
}

export function makeScales(
  years: number[],
  domain: { min: number; max: number },
  plot: Rect = PLOT,
) {
  const span = domain.max - domain.min || 1;
  return {
    x: (i: number) => plot.x + (i / (years.length - 1)) * plot.w,
    y: (v: number) => plot.y + plot.h - ((v - domain.min) / span) * plot.h,
  };
}
