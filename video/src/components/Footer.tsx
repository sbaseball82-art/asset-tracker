import React from "react";
import { fontStack } from "../fonts";
import { TEXT } from "../theme";

interface Props {
  lines: string[];
}

/** 画面下200pxはUIに隠れる想定なので、そこには置かない */
export const Footer: React.FC<Props> = ({ lines }) => (
  <div
    style={{
      position: "absolute",
      left: 64,
      right: 64,
      top: 1546,
      fontFamily: fontStack,
      fontSize: 21,
      fontWeight: 700,
      lineHeight: "32px",
      color: TEXT.muted,
    }}
  >
    {lines.map((l) => (
      <div key={l}>{l}</div>
    ))}
  </div>
);
