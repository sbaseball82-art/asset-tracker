import test from "node:test";
import assert from "node:assert/strict";

import { tipFor, visibleRuns, easedPosition } from "../src/layout/geometry.ts";
import { resolveCollisions } from "../src/layout/collision.ts";
import { domainFor, niceCeil, ticksFor } from "../src/layout/scale.ts";

test("欠損年をまたいで線をつながない", () => {
  //             2016  2017  2018 2019 2020
  const values = [null, null, 10, 20, 30];
  const runs = visibleRuns(values, 4);
  assert.equal(runs.length, 1, "欠損の後ろだけが1本の線になる");
  assert.deepEqual(runs[0].map((p) => p.i), [2, 3, 4]);
});

test("途中の欠損で線を2本に割る", () => {
  const values = [10, 20, null, 40, 50];
  const runs = visibleRuns(values, 4);
  assert.equal(runs.length, 2);
  assert.deepEqual(runs[0].map((p) => p.i), [0, 1]);
  assert.deepEqual(runs[1].map((p) => p.i), [3, 4]);
});

test("欠損を0として描かない", () => {
  const values = [10, null, 30];
  const runs = visibleRuns(values, 2);
  const drawn = runs.flat().map((p) => p.v);
  assert.ok(!drawn.includes(0), `0が混ざっている: ${JSON.stringify(drawn)}`);
});

test("途中までしか描かない", () => {
  const values = [10, 20, 30, 40];
  const runs = visibleRuns(values, 1.5);
  // 1と2の中間まで。10,20 と 中間点(25)
  assert.deepEqual(runs[0].map((p) => p.v), [10, 20, 25]);
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
  assert.equal(niceCeil(1.1), 2);
  assert.equal(niceCeil(230), 250);
  assert.equal(niceCeil(1899), 2000);
});

test("マイナスがあれば0を挟んだ範囲にする", () => {
  const d = domainFor([-120, 300, 50]);
  assert.ok(d.min < 0 && d.max > 300);
  assert.ok(ticksFor(d).includes(0), "0の目盛りが必ず要る");
});

test("全部プラスなら下限は0", () => {
  assert.equal(domainFor([10, 20, 30]).min, 0);
});
