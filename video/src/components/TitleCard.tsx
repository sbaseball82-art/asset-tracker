import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { fontStack } from "../fonts";
import { COMPANY_COLORS, TEXT } from "../theme";

interface Props {
  durationInFrames: number;
  companyNames: string[];
}

export const TitleCard: React.FC<Props> = ({ durationInFrames, companyNames }) => {
  const frame = useCurrentFrame();
  const p = frame / durationInFrames;

  const rise = interpolate(p, [0, 0.3], [30, 0], { extrapolateRight: "clamp" });
  const fadeIn = interpolate(p, [0, 0.22], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(p, [0.86, 1], [1, 0], { extrapolateLeft: "clamp" });
  const opacity = Math.min(fadeIn, fadeOut);

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
          ASSET LOG ／ 業界データ
        </div>
        <div
          style={{
            fontSize: 92,
            fontWeight: 900,
            color: TEXT.primary,
            lineHeight: 1.24,
            letterSpacing: -2,
          }}
        >
          世界のメモリ大手
          <br />
          8社を10期ぶん
          <br />
          比べてみた
        </div>
        <div style={{ fontSize: 31, fontWeight: 700, color: TEXT.secondary, marginTop: 40 }}>
          2016年 → 2025年／売上高・営業利益・営業利益率
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 52 }}>
          {companyNames.map((name, i) => (
            <div
              key={name}
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
                  background: Object.values(COMPANY_COLORS)[i] ?? "#8B96AB",
                }}
              />
              {name}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
