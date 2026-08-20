import React from "react";
import { interpolate } from "remotion";
import { fontStack } from "../fonts";
import { TEXT, type Theme } from "../theme";

interface Props {
  label: string;
  mark: string;
  theme: Theme;
  /** 0→1。1に近づくとワイプで開けてグラフを見せる */
  progress: number;
}

const WIPE_START = 0.66;

export const Interstitial: React.FC<Props> = ({ label, mark, theme, progress }) => {
  // 左から右へ抜けるワイプ
  const wipe = interpolate(progress, [WIPE_START, 1], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const textOpacity = interpolate(progress, [0, 0.12, WIPE_START, WIPE_START + 0.12], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const rise = interpolate(progress, [0, 0.35], [26, 0], { extrapolateRight: "clamp" });

  if (wipe >= 100) return null;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: theme.interstitial,
        clipPath: `inset(0 0 0 ${wipe}%)`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: fontStack,
      }}
    >
      <div
        style={{
          opacity: textOpacity,
          transform: `translateY(${rise}px)`,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: 64, fontWeight: 900, color: theme.accent, marginBottom: 18 }}>
          {mark}
        </div>
        <div style={{ fontSize: 108, fontWeight: 900, color: TEXT.primary, letterSpacing: -2 }}>
          {label}
        </div>
      </div>
    </div>
  );
};
