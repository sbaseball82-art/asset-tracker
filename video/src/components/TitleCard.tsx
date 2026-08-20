import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { fontStack } from "../fonts";
import { FALLBACK_COLOR, TEXT } from "../theme";
import type { Company, Copy } from "../data/types";

interface Props {
  durationInFrames: number;
  copy: Copy;
  companies: Company[];
}

export const TitleCard: React.FC<Props> = ({ durationInFrames, copy, companies }) => {
  const frame = useCurrentFrame();
  const p = frame / durationInFrames;

  const rise = interpolate(p, [0, 0.3], [30, 0], { extrapolateRight: "clamp" });
  const fadeIn = interpolate(p, [0, 0.22], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(p, [0.86, 1], [1, 0], { extrapolateLeft: "clamp" });
  const opacity = Math.min(fadeIn, fadeOut);

  // 社名が増えるほど1行に収まらないので、行数に応じて見出しを詰める
  const titleSize = copy.title_lines.length >= 3 ? 84 : 92;

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
        <div style={{ fontSize: 30, fontWeight: 700, color: "#5FB0FF", marginBottom: 28 }}>
          {copy.kicker}
        </div>
        <div
          style={{
            fontSize: titleSize,
            fontWeight: 900,
            color: TEXT.primary,
            lineHeight: 1.24,
            letterSpacing: -2,
          }}
        >
          {copy.title_lines.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </div>
        <div style={{ fontSize: 31, fontWeight: 700, color: TEXT.secondary, marginTop: 40 }}>
          {copy.title_sub}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 52 }}>
          {companies.map((c) => (
            <div
              key={c.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 18px",
                borderRadius: 999,
                border: "2px solid #1E2A42",
                background: "#111A2E",
                fontSize: 24,
                fontWeight: 700,
                color: TEXT.secondary,
              }}
            >
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 999,
                  background: c.color ?? FALLBACK_COLOR,
                }}
              />
              {c.name_ja}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
