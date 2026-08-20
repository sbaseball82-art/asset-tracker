export const FPS = 60;
export const WIDTH = 1080;
export const HEIGHT = 1920;

/** タイトルカード */
export const TITLE_FRAMES = 150; // 2.5s
/** 各セクション頭の中扉 */
export const INTER_FRAMES = 66; // 1.1s
/** グラフが動き出すまでの間 */
export const CHART_LEAD = 45; // 0.75s
/** 1期あたりの伸長時間 */
export const YEAR_STEP = 114; // 1.9s
/** 最終年に到達してからの静止 */
export const CHART_HOLD = 165; // 2.75s
/** 締めカード */
export const OUTRO_FRAMES = 108; // 1.8s

export const sectionFrames = (yearCount: number) =>
  INTER_FRAMES + CHART_LEAD + (yearCount - 1) * YEAR_STEP + CHART_HOLD;

export const totalFrames = (yearCount: number, metricCount: number) =>
  TITLE_FRAMES + metricCount * sectionFrames(yearCount) + OUTRO_FRAMES;
