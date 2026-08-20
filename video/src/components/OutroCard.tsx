import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { fontStack } from "../fonts";
import { TEXT } from "../theme";

interface Props {
  durationInFrames: number;
  headline: string;
  summaryLine: string;
}

export const OutroCard: React.FC<Props> = ({ durationInFrames, headline, summaryLine }) => {
  const frame = useCurrentFrame();
  const p = frame / durationInFrames;
  const opacity = interpolate(p, [0, 0.18], [0, 1], { extrapolateRight: "clamp" });
  const rise = interpolate(p, [0, 0.35], [22, 0], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "linear-gradient(165deg, #10254A 0%, #0A1428 60%, #0B1220 100%)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "0 80px",
        fontFamily: fontStack,
        opacity,
      }}
    >
      <div style={{ transform: `translateY(${rise}px)` }}>
        <div style={{ fontSize: 44, fontWeight: 900, color: TEXT.primary, marginBottom: 32 }}>
          {headline}
        </div>
        <div style={{ fontSize: 30, fontWeight: 700, color: TEXT.secondary, lineHeight: 1.6 }}>
          {summaryLine}
        </div>
        <div style={{ fontSize: 23, fontWeight: 700, color: "#8B96AB", marginTop: 44, lineHeight: 1.7 }}>
          ※記録・情報共有目的であり投資助言ではありません
          <br />
          ※公表データからの概算
        </div>
      </div>
    </div>
  );
};
