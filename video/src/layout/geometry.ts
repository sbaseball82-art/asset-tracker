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
 * 年をまたぐ途中での速度。0にすると年ごとに完全停止してカクついて見えるので、
 * 巡航速度を残して等速に近づけている。1.0で等速、0で年ごとに停止。
 */
const CRUISE = 0.65;

/**
 * フレーム位置を「年インデックスの小数」に変換する。
 *
 * 1期ぶんを両端の速度を指定したエルミート補間でつなぐ。
 * 中間の期は入りも出も巡航速度なので、年の境目で速度が途切れない。
 * 最初の期だけ速度0から入り、最後の期だけ速度0で止まる。
 */
export function easedPosition(rawPosition: number, lastIndex: number): number {
  const clamped = Math.max(0, Math.min(lastIndex, rawPosition));
  const k = Math.floor(clamped);
  const t = clamped - k;
  if (t === 0) return k;

  const enter = k === 0 ? 0 : CRUISE;
  const exit = k === lastIndex - 1 ? 0 : CRUISE;
  return k + hermite01(t, enter, exit);
}

/** f(0)=0, f(1)=1, f'(0)=m0, f'(1)=m1 を満たす3次エルミート */
function hermite01(t: number, m0: number, m1: number): number {
  return m0 * t * (1 - t) * (1 - t) + (3 * t * t - 2 * t * t * t) + m1 * (t * t * t - t * t);
}

export interface DataPointXY {
  i: number;
  v: number;
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

/** 最上段の目盛りが描画域の上端に張り付かないようにする余白 */
export const TOP_PAD = 26;
/** マイナスがあるときだけ、最下段の目盛りが横軸ラベルと当たらないよう空ける */
export const BOTTOM_PAD = 16;

export const bottomPadFor = (domain: { min: number }) => (domain.min < 0 ? BOTTOM_PAD : 0);

export function makeScales(
  years: number[],
  domain: { min: number; max: number },
  plot: Rect = PLOT,
) {
  const span = domain.max - domain.min || 1;
  const bottom = bottomPadFor(domain);
  const usable = plot.h - TOP_PAD - bottom;
  return {
    x: (i: number) => plot.x + (i / (years.length - 1)) * plot.w,
    y: (v: number) => plot.y + plot.h - bottom - ((v - domain.min) / span) * usable,
  };
}

/* ---------------------------------------------------------------------------
 * 折れ線を単調3次補間でなめらかにつなぐ
 *
 * Fritsch–Carlson の単調性条件を使うので、データ点の外側に膨らまない。
 * 「年と年のあいだで実際より高い/低い値があったように見える」ことを避けるため、
 * 素のCatmull-Romではなくこちらを使っている。
 * ------------------------------------------------------------------------- */

export interface Bezier {
  /** 区間の左右の年インデックス */
  i0: number;
  i1: number;
  p0: [number, number];
  c1: [number, number];
  c2: [number, number];
  p1: [number, number];
}

export interface ScreenPoint {
  i: number;
  sx: number;
  sy: number;
}

/** 欠損で切れていない、連続した年のかたまりを取り出す */
export function consecutiveRuns(values: (number | null)[]): number[][] {
  const runs: number[][] = [];
  let current: number[] = [];
  values.forEach((v, i) => {
    if (v === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push(i);
    }
  });
  if (current.length) runs.push(current);
  return runs;
}

export function monotoneSegments(points: ScreenPoint[]): Bezier[] {
  const n = points.length;
  if (n < 2) return [];

  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(points[i + 1].sx - points[i].sx);
    slope.push((points[i + 1].sy - points[i].sy) / (points[i + 1].sx - points[i].sx));
  }

  // 接線の初期値
  const m: number[] = new Array(n);
  m[0] = slope[0];
  m[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  }

  // 単調性を壊さないところまで接線を切り詰める
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    const a = m[i] / slope[i];
    const b = m[i + 1] / slope[i];
    const s = a * a + b * b;
    if (s > 9) {
      const scale = 3 / Math.sqrt(s);
      m[i] = scale * a * slope[i];
      m[i + 1] = scale * b * slope[i];
    }
  }

  const out: Bezier[] = [];
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3;
    out.push({
      i0: points[i].i,
      i1: points[i + 1].i,
      p0: [points[i].sx, points[i].sy],
      c1: [points[i].sx + h, points[i].sy + m[i] * h],
      c2: [points[i + 1].sx - h, points[i + 1].sy - m[i + 1] * h],
      p1: [points[i + 1].sx, points[i + 1].sy],
    });
  }
  return out;
}

/**
 * 区間の途中まで（媒介変数 t）に切り詰める。
 * 制御点の横位置を等間隔に置いてあるので、t は横方向の進み具合とちょうど一致する。
 */
export function truncateBezier(b: Bezier, t: number): Bezier {
  const lerp = (a: [number, number], c: [number, number]): [number, number] => [
    a[0] + (c[0] - a[0]) * t,
    a[1] + (c[1] - a[1]) * t,
  ];
  const q0 = lerp(b.p0, b.c1);
  const q1 = lerp(b.c1, b.c2);
  const q2 = lerp(b.c2, b.p1);
  const r0 = lerp(q0, q1);
  const r1 = lerp(q1, q2);
  const s0 = lerp(r0, r1);
  return { i0: b.i0, i1: b.i1, p0: b.p0, c1: q0, c2: r0, p1: s0 };
}

export function bezierPath(segments: Bezier[]): string {
  if (segments.length === 0) return "";
  const head = `M${fmt(segments[0].p0)}`;
  const rest = segments
    .map((s) => `C${fmt(s.c1)} ${fmt(s.c2)} ${fmt(s.p1)}`)
    .join(" ");
  return `${head} ${rest}`;
}

function fmt(p: [number, number]): string {
  return `${p[0].toFixed(2)},${p[1].toFixed(2)}`;
}
