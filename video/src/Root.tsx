import React from "react";
import { Composition } from "remotion";
import { Memory10 } from "./Memory10";
import { dummyDataset, realDataset } from "./data/dataset";
import { FPS, HEIGHT, WIDTH, totalFrames } from "./timing";
import type { Dataset } from "./data/types";

const durationFor = (d: Dataset) => totalFrames(d.years.length, d.metrics.length);

/**
 * 本番用と動作確認用でコンポジションを分ける。
 * ダミーの数字が本番の書き出しに混ざらないようにするための分離なので、
 * Memory10 が dummyDataset を読むようにはしないこと。
 */
export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Memory10"
      component={Memory10}
      durationInFrames={durationFor(realDataset)}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      defaultProps={{ dataset: realDataset }}
    />
    <Composition
      id="Memory10Dummy"
      component={Memory10}
      durationInFrames={durationFor(dummyDataset)}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      defaultProps={{ dataset: dummyDataset }}
    />
  </>
);
