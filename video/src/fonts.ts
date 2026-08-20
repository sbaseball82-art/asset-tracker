import { continueRender, delayRender, staticFile } from "remotion";

/**
 * Noto Sans JP をプロジェクト同梱のファイルから読み込む。
 * システムフォントに依存しないこと（豆腐の原因になる）。
 * サブセットは scripts/subset_fonts.py が作る。
 */
export const FONT_FAMILY = "NotoSansJPBundled";

const FACES: { file: string; weight: string }[] = [
  { file: "fonts/NotoSansJP-Bold.woff2", weight: "700" },
  { file: "fonts/NotoSansJP-Black.woff2", weight: "900" },
];

let started = false;

export function ensureFontsLoaded() {
  if (started) return;
  started = true;

  const handle = delayRender("Noto Sans JP を読み込み中");
  Promise.all(
    FACES.map(async ({ file, weight }) => {
      const face = new FontFace(
        FONT_FAMILY,
        `url(${staticFile(file)}) format("woff2")`,
        { weight, style: "normal", display: "block" },
      );
      const loaded = await face.load();
      document.fonts.add(loaded);
    }),
  )
    .then(() => continueRender(handle))
    .catch((err) => {
      // フォントが読めないまま描くと豆腐になるので、黙って続けない
      throw new Error(`フォントの読み込みに失敗した: ${String(err)}`);
    });
}

export const fontStack = `"${FONT_FAMILY}", "Noto Sans JP", sans-serif`;
