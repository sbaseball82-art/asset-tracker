import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("png");
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setChromiumOpenGlRenderer("angle");

// 音声なしの動画にする（既定だと無音のオーディオトラックが付く）
Config.setMuted(true);
Config.setEnforceAudioTrack(false);

// Remotion は旧ヘッドレスモードを使うため、chrome-headless-shell を指す必要がある。
// 環境ごとにパスが違うので環境変数で渡す。
// 例: REMOTION_BROWSER_EXECUTABLE=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
const browser = process.env.REMOTION_BROWSER_EXECUTABLE;
if (browser) {
  Config.setBrowserExecutable(browser);
}
