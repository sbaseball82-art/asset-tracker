import React from "react";
import { interpolate } from "remotion";
import { fontStack } from "../fonts";
import { TEXT, type Theme } from "../theme";
import type { Metric } from "../data/types";

const TAB_MARKS = ["①", "②", "③"];

export const HEADER_HEIGHT = 478;

interface Props {
  metrics: Metric[];
  activeIndex: number;
  metric: Metric;
  year: number;
  yearFlash: number;
  subtitle: string;
  theme: Theme;
}

export const Header: React.FC<Props> = ({
  metrics,
  activeIndex,
  metric,
  year,
  yearFlash,
  subtitle,
  theme,
}) => {
  // 年が切り替わった直後だけ、数字をわずかに持ち上げて気づかせる
  const lift = interpolate(yearFlash, [0, 1], [-10, 0], { extrapolateRight: "clamp" });
  const yearOpacity = interpolate(yearFlash, [0, 0.6], [0.35, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: HEADER_HEIGHT,
        background: `linear-gradient(160deg, ${theme.header} 0%, ${theme.headerDeep} 100%)`,
        borderBottomLeftRadius: 40,
        borderBottomRightRadius: 40,
        fontFamily: fontStack,
      }}
    >
      <div style={{ position: "absolute", top: 206, left: 64, display: "flex", gap: 14 }}>
        {metrics.map((m, i) => {
          const active = i === activeIndex;
          return (
            <div
              key={m.id}
              style={{
                padding: "12px 22px",
                borderRadius: 999,
                fontSize: 27,
                fontWeight: 700,
                letterSpacing: 0.5,
                whiteSpace: "nowrap",
                background: active ? theme.accent : "transparent",
                color: active ? TEXT.onLight : "rgba(255,255,255,0.62)",
                border: active
                  ? `2px solid ${theme.accent}`
                  : "2px solid rgba(255,255,255,0.3)",
              }}
            >
              {TAB_MARKS[i]} {m.label_ja}
            </div>
          );
        })}
      </div>

      <div
        style={{
          position: "absolute",
          top: 292,
          left: 64,
          right: 64,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <span
            style={{
              fontSize: 84,
              fontWeight: 900,
              color: TEXT.primary,
              letterSpacing: -1,
              lineHeight: 1,
            }}
          >
            {metric.label_ja}
          </span>
          <span style={{ fontSize: 34, fontWeight: 700, color: "rgba(255,255,255,0.72)" }}>
            （{metric.unit_ja}）
          </span>
        </div>
        <span
          style={{
            fontSize: 76,
            fontWeight: 900,
            color: theme.accent,
            lineHeight: 1,
            transform: `translateY(${lift}px)`,
            opacity: yearOpacity,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {year}年
        </span>
      </div>

      <div
        style={{
          position: "absolute",
          top: 412,
          left: 64,
          fontSize: 27,
          fontWeight: 700,
          color: "rgba(255,255,255,0.66)",
        }}
      >
        {subtitle}
      </div>
    </div>
  );
};
