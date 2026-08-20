import React from "react";
import { Composition } from "remotion";
import { ComparisonVideo } from "./ComparisonVideo";
import { DATASETS, DUMMY_DATASETS, type DatasetSlug } from "./data/dataset";
import { FPS, HEIGHT, WIDTH, totalFrames } from "./timing";
import type { Dataset } from "./data/types";

const durationFor = (d: Dataset) => totalFrames(d.years.length, d.metrics.length);

/** 書き出すときの id。本番とダミーで別の Composition にしてある */
const COMPOSITION_IDS: Record<DatasetSlug, string> = {
  memory10: "Memory10",
  security8: "Security8",
};

/**
 * データセットごとに、本番用と動作確認用のコンポジションを1つずつ登録する。
 * ダミーの数字が本番の書き出しに混ざらないようにするための分離なので、
 * 本番側が DUMMY_DATASETS を読むようにはしないこと。
 */
export const RemotionRoot: React.FC = () => (
  <>
    {(Object.keys(DATASETS) as DatasetSlug[]).flatMap((slug) => [
      <Composition
        key={slug}
        id={COMPOSITION_IDS[slug]}
        component={ComparisonVideo}
        durationInFrames={durationFor(DATASETS[slug])}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ dataset: DATASETS[slug] }}
      />,
      <Composition
        key={`${slug}-dummy`}
        id={`${COMPOSITION_IDS[slug]}Dummy`}
        component={ComparisonVideo}
        durationInFrames={durationFor(DUMMY_DATASETS[slug])}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ dataset: DUMMY_DATASETS[slug] }}
      />,
    ])}
  </>
);
