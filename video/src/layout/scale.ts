/** 目盛りとスケールの計算。純粋関数のみ。 */

/**
 * 縦軸の上限に使う刻み。
 * 目盛りより細かくしてある。粗いとデータの倍近くまで上限が飛んで、
 * グラフの上半分が空いてしまうため。
 */
const CEIL_STEPS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

/** 目盛りの間隔に使う刻み。ラベルが丸い数字になるものだけ */
const TICK_STEPS = [1, 2, 2.5, 5, 10];

/** v 以上で最も小さい「切りのよい」値 */
export function niceCeil(v: number): number {
  if (v === 0) return 0;
  const sign = Math.sign(v);
  const a = Math.abs(v);
  const mag = Math.pow(10, Math.floor(Math.log10(a)));
  for (const s of CEIL_STEPS) {
    if (a <= s * mag * 1.0000001) return sign * s * mag;
  }
  return sign * 10 * mag;
}

/** v 以下で最も大きい「切りのよい」値 */
export function niceFloor(v: number): number {
  if (v === 0) return 0;
  return -niceCeil(-v);
}

export interface Domain {
  min: number;
  max: number;
}

/**
 * 系列値から縦軸の範囲を決める。
 * 上下に少し余白を足したうえで切りのよい値に丸める。0は常に含める。
 */
export function domainFor(values: number[]): Domain {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return { min: 0, max: 1 };

  const rawMax = Math.max(0, ...finite);
  const rawMin = Math.min(0, ...finite);
  const span = rawMax - rawMin || Math.abs(rawMax) || 1;

  // 余白を大きく取ると niceCeil が一段上の目盛りへ飛んでグラフ上部が空くので、
  // ここは詰めておき、線が上端に触れないぶんは描画側の余白（TOP_PAD）で確保する
  const max = niceCeil(rawMax + span * 0.02);
  const min = rawMin < 0 ? niceFloor(rawMin - span * 0.02) : 0;
  return { min, max: max === min ? min + 1 : max };
}

/** 目盛り位置。おおむね count 本になるよう刻み幅を選ぶ */
export function ticksFor(domain: Domain, count = 5): number[] {
  const span = domain.max - domain.min;
  if (span <= 0) return [domain.min];

  const rough = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  let step = 10 * mag;
  for (const s of TICK_STEPS) {
    if (s * mag >= rough) {
      step = s * mag;
      break;
    }
  }

  const out: number[] = [];
  const start = Math.ceil(domain.min / step) * step;
  for (let t = start; t <= domain.max + step * 1e-6; t += step) {
    out.push(Math.abs(t) < step * 1e-6 ? 0 : t);
  }
  return out;
}

