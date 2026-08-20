import test from "node:test";
import assert from "node:assert/strict";

import {
  consecutiveRuns,
  easedPosition,
  monotoneSegments,
  tipFor,
  truncateBezier,
  type ScreenPoint,
} from "../src/layout/geometry.ts";
import { resolveCollisions } from "../src/layout/collision.ts";
import { domainFor, niceCeil, ticksFor } from "../src/layout/scale.ts";

test("欠損年をまたいで線をつながない", () => {
  //                       2016  2017  2018 2019 2020
  const runs = consecutiveRuns([null, null, 10, 20, 30]);
  assert.equal(runs.length, 1, "欠損の後ろだけが1本の線になる");
  assert.deepEqual(runs[0], [2, 3, 4]);
});

test("途中の欠損で線を2本に割る", () => {
  const runs = consecutiveRuns([10, 20, null, 40, 50]);
  assert.deepEqual(runs, [[0, 1], [3, 4]]);
});

test("欠損は線の一部にならない（0として描かれない）", () => {
  const runs = consecutiveRuns([10, null, 30]);
  assert.deepEqual(runs, [[0], [2]], "欠損をまたぐ区間そのものが存在しない");
});

test("先端の値は年をまたぐと線形に補間される", () => {
  const values = [100, 200, null];
  assert.deepEqual(tipFor(values, 0), { i: 0, v: 100, opacity: 1 });
  assert.deepEqual(tipFor(values, 0.5), { i: 0.5, v: 150, opacity: 1 });
  assert.deepEqual(tipFor(values, 1), { i: 1, v: 200, opacity: 1 });
});

test("欠損に入るときは0に落とさずフェードアウトする", () => {
  const tip = tipFor([100, null], 0.5);
  assert.equal(tip?.v, 100, "値は直前のまま");
  assert.equal(tip?.opacity, 0.5);
});

test("欠損から戻るときはフェードインする", () => {
  const tip = tipFor([null, 100], 0.25);
  assert.equal(tip?.v, 100);
  assert.equal(tip?.opacity, 0.25);
});

test("値が無ければ先端も無い", () => {
  assert.equal(tipFor([null, null], 0.5), null);
});

test("イージングは年の境目でぴったり整数に戻る", () => {
  assert.equal(easedPosition(0, 9), 0);
  assert.equal(easedPosition(3, 9), 3);
  assert.equal(Math.round(easedPosition(9, 9)), 9);
  assert.ok(Math.abs(easedPosition(3.5, 9) - 3.5) < 1e-9, "中間は対称なので3.5のまま");
});

test("ラベルは最低間隔を必ず保つ", () => {
  const slots = [
    { id: "a", desiredY: 500 },
    { id: "b", desiredY: 505 },
    { id: "c", desiredY: 510 },
    { id: "d", desiredY: 515 },
  ];
  const placed = resolveCollisions(slots, { minSpacing: 82, minY: 100, maxY: 900 });
  const ys = placed.map((p) => p.y).sort((a, b) => a - b);
  for (let i = 1; i < ys.length; i++) {
    assert.ok(ys[i] - ys[i - 1] >= 82 - 1e-9, `間隔が足りない: ${ys[i] - ys[i - 1]}`);
  }
});

test("ラベルの上下の並び順は値の順と一致する", () => {
  const slots = [
    { id: "high", desiredY: 200 },
    { id: "mid", desiredY: 210 },
    { id: "low", desiredY: 800 },
  ];
  const placed = resolveCollisions(slots, { minSpacing: 82, minY: 100, maxY: 900 });
  assert.deepEqual(placed.map((p) => p.id), ["high", "mid", "low"]);
});

test("ラベルは領域からはみ出さない", () => {
  const slots = Array.from({ length: 8 }, (_, i) => ({ id: `s${i}`, desiredY: 880 - i }));
  const placed = resolveCollisions(slots, { minSpacing: 82, minY: 100, maxY: 900 });
  for (const p of placed) {
    assert.ok(p.y >= 100 - 1e-9 && p.y <= 900 + 1e-9, `はみ出した: ${p.y}`);
  }
});

test("切りのよい上限", () => {
  assert.equal(niceCeil(0), 0);
  assert.equal(niceCeil(1), 1);
  assert.equal(niceCeil(1.1), 1.5);
  assert.equal(niceCeil(230), 250);
  assert.equal(niceCeil(1295), 1500, "2000まで飛ばさない");
  assert.equal(niceCeil(1899), 2000);
});

test("目盛りのラベルは丸い数字になる", () => {
  const ticks = ticksFor({ min: 0, max: 1500 }, 5);
  assert.deepEqual(ticks, [0, 500, 1000, 1500]);
});

test("マイナスがあれば0を挟んだ範囲にする", () => {
  const d = domainFor([-120, 300, 50]);
  assert.ok(d.min < 0 && d.max > 300);
  assert.ok(ticksFor(d).includes(0), "0の目盛りが必ず要る");
});

test("全部プラスなら下限は0", () => {
  assert.equal(domainFor([10, 20, 30]).min, 0);
});

// --- 曲線 -----------------------------------------------------------------

const pts = (ys: number[]): ScreenPoint[] =>
  ys.map((sy, i) => ({ i, sx: i * 100, sy }));

test("曲線はデータ点の外に膨らまない", () => {
  // 上げて下げる形。素のCatmull-Romだと山を越えて膨らむところ
  const segments = monotoneSegments(pts([300, 100, 200]));
  for (const seg of segments) {
    const lo = Math.min(seg.p0[1], seg.p1[1]);
    const hi = Math.max(seg.p0[1], seg.p1[1]);
    for (let t = 0; t <= 1.0001; t += 0.05) {
      const yv = truncateBezier(seg, Math.min(1, t)).p1[1];
      assert.ok(
        yv >= lo - 1e-6 && yv <= hi + 1e-6,
        `区間の外に出た: ${yv} (${lo}..${hi})`,
      );
    }
  }
});

test("横ばいの区間はまっすぐ横ばいのまま", () => {
  const segments = monotoneSegments(pts([200, 200, 50]));
  const mid = truncateBezier(segments[0], 0.5).p1[1];
  assert.ok(Math.abs(mid - 200) < 1e-9, `横ばいが崩れた: ${mid}`);
});

test("媒介変数は横方向の進み具合と一致する", () => {
  const segments = monotoneSegments(pts([100, 400]));
  const cut = truncateBezier(segments[0], 0.25);
  assert.ok(Math.abs(cut.p1[0] - 25) < 1e-9, `横位置がずれた: ${cut.p1[0]}`);
});

test("切り詰めた曲線の始点は元のまま", () => {
  const segments = monotoneSegments(pts([100, 400, 250]));
  const cut = truncateBezier(segments[1], 0.6);
  assert.deepEqual(cut.p0, segments[1].p0);
});

// --- 動きのなめらかさ -------------------------------------------------------

const LAST = 9;
const velocity = (p: number) =>
  (easedPosition(p + 1e-4, LAST) - easedPosition(p - 1e-4, LAST)) / 2e-4;

test("年の境目で速度が途切れない", () => {
  for (const boundary of [1, 2, 5, 8]) {
    const before = velocity(boundary - 1e-3);
    const after = velocity(boundary + 1e-3);
    assert.ok(
      Math.abs(before - after) < 0.05,
      `${boundary}年目の境目で速度が跳ねた: ${before} → ${after}`,
    );
  }
});

test("途中の年で止まらない", () => {
  for (const boundary of [1, 2, 3, 4, 5, 6, 7]) {
    assert.ok(velocity(boundary) > 0.5, `${boundary}年目で失速した: ${velocity(boundary)}`);
  }
});

test("入りと終わりだけは静かに始まって静かに止まる", () => {
  assert.ok(velocity(0.001) < 0.05, "出だしは静止から");
  assert.ok(velocity(LAST - 0.001) < 0.05, "最後は静止で終わる");
});

test("位置は必ず前に進む", () => {
  let prev = -1;
  for (let p = 0; p <= LAST; p += 0.01) {
    const v = easedPosition(p, LAST);
    assert.ok(v >= prev - 1e-9, `後戻りした: ${p} → ${v}`);
    prev = v;
  }
});

test("年の境目ではぴったり整数に乗る", () => {
  for (let k = 0; k <= LAST; k++) {
    assert.ok(Math.abs(easedPosition(k, LAST) - k) < 1e-9);
  }
});
