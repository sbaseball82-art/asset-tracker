import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Header } from "./Header";
import { Footer } from "./Footer";
import { LineChart } from "./LineChart";
import { Interstitial } from "./Interstitial";
import { fontStack } from "../fonts";
import { THEMES, TEXT } from "../theme";
import { CHART_LEAD, INTER_FRAMES, YEAR_STEP } from "../timing";
import { easedPosition, PLOT } from "../layout/geometry";
import { hasAnyValue, seriesFor } from "../data/dataset";
import type { Dataset, Metric } from "../data/types";

const MARKS = ["①", "②", "③"];

interface Props {
  dataset: Dataset;
  metric: Metric;
  metricIndex: number;
}

export const ChartSection: React.FC<Props> = ({ dataset, metric, metricIndex }) => {
  const frame = useCurrentFrame();
  const theme = THEMES[metric.theme];
  const years = dataset.years;
  const lastIndex = years.length - 1;

  const series = seriesFor(dataset, metric.id);
  const populated = hasAnyValue(series);

  const chartFrame = frame - INTER_FRAMES;
  const rawPos = Math.max(0, Math.min(lastIndex, (chartFrame - CHART_LEAD) / YEAR_STEP));
  const pos = easedPosition(rawPos, lastIndex);

  const yearIndex = Math.round(rawPos);
  const sinceSwitch = rawPos - (yearIndex - 0.5);
  const yearFlash = Math.max(0, Math.min(1, sinceSwitch / 0.3));

  const missing = series.some((s) => s.values.some((v) => v === null));
  const footerLines = [
    "出典：各社IR資料（10-K／有価証券報告書／決算説明資料）",
    "米ドル換算は各年度の期中平均レート。営業利益率は営業利益÷売上高",
    "決算期：マイクロン8月期／サンディスク6月期／キオクシア3月期／他12月期",
    "サムスンはDS部門ベース（メモリ単独の営業利益は非開示）",
  ];
  if (missing) footerLines.push("未開示・未取得の年は線を途切れさせている（0では描いていない）");

  return (
    <AbsoluteFill style={{ background: theme.background }}>
      <Header
        metrics={dataset.metrics}
        activeIndex={metricIndex}
        metric={metric}
        year={years[yearIndex]}
        yearFlash={yearFlash}
        theme={theme}
      />

      <div
        style={{
          position: "absolute",
          top: 500,
          left: 96,
          right: 64,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: fontStack,
          fontSize: 23,
          fontWeight: 700,
          color: TEXT.muted,
        }}
      >
        <span>縦軸：{metric.unit_ja}</span>
        <span>横軸：各社会計年度（暦年ベース）</span>
      </div>

      {populated ? (
        <LineChart series={series} years={years} metric={metric} theme={theme} pos={pos} />
      ) : (
        <div
          style={{
            position: "absolute",
            top: PLOT.y,
            left: PLOT.x,
            width: 1080 - PLOT.x * 2,
            height: PLOT.h,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            border: `2px dashed ${theme.grid}`,
            borderRadius: 20,
            fontFamily: fontStack,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 46, fontWeight: 900, color: TEXT.secondary }}>
            データ未取得
          </div>
          <div style={{ fontSize: 25, fontWeight: 700, color: TEXT.muted, marginTop: 20, lineHeight: 1.7 }}>
            data/memory10.csv がまだ埋まっていない。
            <br />
            推測値では埋めない方針のため、空欄のまま表示している。
          </div>
        </div>
      )}

      <Footer lines={footerLines} />

      <Interstitial
        label={metric.label_ja}
        mark={MARKS[metricIndex]}
        theme={theme}
        progress={Math.min(1, frame / INTER_FRAMES)}
      />
    </AbsoluteFill>
  );
};
