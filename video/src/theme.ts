export type ThemeName = "navy" | "green" | "rust";

export interface Theme {
  /** 画面全体の背景 */
  background: string;
  /** ヘッダー帯 */
  header: string;
  headerDeep: string;
  /** タブのハイライトと強調線 */
  accent: string;
  /** 中扉カードの地色 */
  interstitial: string;
  /** グラフの罫線 */
  grid: string;
  gridZero: string;
}

export const THEMES: Record<ThemeName, Theme> = {
  navy: {
    background: "#0A1428",
    header: "#173A73",
    headerDeep: "#102A55",
    accent: "#5FB0FF",
    interstitial: "#14315E",
    grid: "#1E2A42",
    gridZero: "#33425F",
  },
  green: {
    background: "#08170F",
    header: "#12513A",
    headerDeep: "#0C3A29",
    accent: "#3FDD95",
    interstitial: "#0B3B2A",
    grid: "#16302A",
    gridZero: "#2A4C41",
  },
  rust: {
    background: "#1A0D08",
    header: "#6B2E1C",
    headerDeep: "#4E2114",
    accent: "#FF9563",
    interstitial: "#5A2717",
    grid: "#33211A",
    gridZero: "#54372C",
  },
};

/** 系列色が spec に無いときの逃げ道。通常は data/specs/<slug>.yml の color を使う */
export const FALLBACK_COLOR = "#8B96AB";

export const TEXT = {
  primary: "#FFFFFF",
  secondary: "#C3CCDC",
  muted: "#8B96AB",
  onLight: "#0B1220",
};
