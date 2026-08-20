import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { TitleCard } from "./components/TitleCard";
import { ChartSection } from "./components/ChartSection";
import { OutroCard } from "./components/OutroCard";
import { ensureFontsLoaded } from "./fonts";
import { OUTRO_FRAMES, TITLE_FRAMES, sectionFrames } from "./timing";
import { seriesFor } from "./data/dataset";
import type { Dataset } from "./data/types";

/** 最終年の売上高で1位の会社を1行にまとめる。値が無ければ数字を作らない。 */
function summaryLine(dataset: Dataset): string {
  const series = seriesFor(dataset, "revenue");
  const last = dataset.years.length - 1;
  const ranked = series
    .map((s) => ({ name: s.nameJa, v: s.values[last] }))
    .filter((e): e is { name: string; v: number } => e.v !== null)
    .sort((a, b) => b.v - a.v);

  if (ranked.length < 2) {
    return "数値が揃っていないため、順位のまとめは出していません。";
  }
  const [first, second] = ranked;
  return `${dataset.years[last]}年の売上高は ${first.name} が最大で、${second.name} が続いています。`;
}

export const ComparisonVideo: React.FC<{ dataset: Dataset }> = ({ dataset }) => {
  ensureFontsLoaded();

  const section = sectionFrames(dataset.years.length);

  return (
    <AbsoluteFill style={{ background: "#0B1220" }}>
      <Sequence durationInFrames={TITLE_FRAMES}>
        <TitleCard
          durationInFrames={TITLE_FRAMES}
          copy={dataset.copy}
          companies={dataset.companies}
        />
      </Sequence>

      {dataset.metrics.map((metric, i) => (
        <Sequence
          key={metric.id}
          from={TITLE_FRAMES + i * section}
          durationInFrames={section}
        >
          <ChartSection dataset={dataset} metric={metric} metricIndex={i} />
        </Sequence>
      ))}

      <Sequence
        from={TITLE_FRAMES + dataset.metrics.length * section}
        durationInFrames={OUTRO_FRAMES}
      >
        <OutroCard
          durationInFrames={OUTRO_FRAMES}
          headline={dataset.copy.outro_headline}
          summaryLine={summaryLine(dataset)}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
