/** 先端ラベルの縦方向の衝突回避。純粋関数のみ。 */

export interface LabelSlot {
  id: string;
  /** 本来置きたい中心Y（＝線の先端の高さ） */
  desiredY: number;
}

export interface PlacedLabel {
  id: string;
  desiredY: number;
  /** 押し出した後の中心Y */
  y: number;
}

export interface CollisionOptions {
  /** ラベル中心どうしが保つ最小間隔 */
  minSpacing: number;
  /** 置ける範囲（中心Yの下限・上限） */
  minY: number;
  maxY: number;
}

/**
 * 上下に押し出して重なりを解く。
 *
 * 1. 上から順に、直前のラベルとの間隔が足りなければ下へ押し下げる
 * 2. 下端をはみ出したぶんを、今度は下から順に押し上げて回収する
 * 3. それでも収まらない（本数×間隔 > 領域）場合は等間隔に並べる
 *
 * 元の位置との対応は呼び出し側がリード線で結ぶ。
 */
export function resolveCollisions(
  slots: LabelSlot[],
  opts: CollisionOptions,
): PlacedLabel[] {
  const { minSpacing, minY, maxY } = opts;
  const n = slots.length;
  if (n === 0) return [];

  const sorted = [...slots].sort((a, b) => a.desiredY - b.desiredY);

  // 領域に対して本数が多すぎるときは等間隔に置くしかない
  const needed = (n - 1) * minSpacing;
  if (needed > maxY - minY) {
    const gap = (maxY - minY) / Math.max(1, n - 1);
    return sorted.map((s, i) => ({ id: s.id, desiredY: s.desiredY, y: minY + i * gap }));
  }

  const y = sorted.map((s) => clamp(s.desiredY, minY, maxY));

  // 上から押し下げ
  for (let i = 1; i < n; i++) {
    if (y[i] - y[i - 1] < minSpacing) y[i] = y[i - 1] + minSpacing;
  }
  // 下端からあふれたぶんを押し上げ
  if (y[n - 1] > maxY) {
    y[n - 1] = maxY;
    for (let i = n - 2; i >= 0; i--) {
      if (y[i + 1] - y[i] < minSpacing) y[i] = y[i + 1] - minSpacing;
    }
  }
  // 押し上げすぎて上端を割ったら全体を下げ直す
  if (y[0] < minY) {
    const shift = minY - y[0];
    for (let i = 0; i < n; i++) y[i] += shift;
  }

  return sorted.map((s, i) => ({ id: s.id, desiredY: s.desiredY, y: y[i] }));
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v));
}
