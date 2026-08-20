import React from "react";
import { staticFile } from "remotion";
import logos from "../data/logos.generated.json";
import { fontStack } from "../fonts";

const LOGO_FILES = logos as Record<string, Record<string, string>>;

interface Props {
  /** データセットのスラッグ。ロゴはデータセットごとに置き場が分かれている */
  slug: string;
  companyId: string;
  monogram: string;
  color: string;
  /** 左上の座標 */
  x: number;
  y: number;
  size: number;
}

/**
 * 各社のしるし。
 *
 * video/public/logos/<企業ID>.<svg|png> が置かれていればその画像を、
 * 無ければ頭文字バッジを描く。ロゴは商標なので同梱するかは人間が決める。
 * 一覧は scripts/build_logo_manifest.py が作る。
 */
export const LogoBadge: React.FC<Props> = ({ slug, companyId, monogram, color, x, y, size }) => {
  const file = LOGO_FILES[slug]?.[companyId];
  const radius = Math.round(size * 0.24);

  if (file) {
    const clipId = `logo-clip-${slug}-${companyId}`;
    return (
      <g>
        <clipPath id={clipId}>
          <rect x={x} y={y} width={size} height={size} rx={radius} />
        </clipPath>
        <rect x={x} y={y} width={size} height={size} rx={radius} fill="#FFFFFF" />
        <image
          href={staticFile(file)}
          x={x}
          y={y}
          width={size}
          height={size}
          preserveAspectRatio="xMidYMid meet"
          clipPath={`url(#${clipId})`}
        />
        <rect
          x={x}
          y={y}
          width={size}
          height={size}
          rx={radius}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          opacity={0.5}
        />
      </g>
    );
  }

  return (
    <g>
      <rect x={x} y={y} width={size} height={size} rx={radius} fill={color} />
      <text
        x={x + size / 2}
        y={y + size / 2 + size * 0.135}
        textAnchor="middle"
        fontFamily={fontStack}
        fontSize={monogram.length >= 2 ? size * 0.42 : size * 0.54}
        fontWeight={900}
        fill="#FFFFFF"
        letterSpacing={monogram.length >= 2 ? -0.5 : 0}
      >
        {monogram}
      </text>
    </g>
  );
};
