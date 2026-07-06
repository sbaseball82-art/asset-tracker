# リリース手順（App Store 公開）

## 0. 前提

- macOS + Xcode 16 以降
- Apple Developer Program 登録済み
- [XcodeGen](https://github.com/yonyz/XcodeGen)（`brew install xcodegen`）

## 1. プロジェクト生成

```bash
cd PhotoMindAI
xcodegen generate
open PhotoMindAI.xcodeproj
```

`project.yml` から `.xcodeproj` を生成します（`.xcodeproj` はコミットしません）。

## 2. 署名 / Capabilities

1. Xcode → Signing & Capabilities で **Team** を選択（`project.yml` の `DEVELOPMENT_TEAM` でも可）。
2. 以下の Capability を有効化（Entitlements は用意済み）:
   - App Groups: `group.com.photomind.ai`（ウィジェット共有）
   - iCloud → CloudKit: `iCloud.com.photomind.ai`
   - Push Notifications（Live Activity 更新に使用する場合）
3. Bundle ID を自分のものに変更する場合は `project.yml` と entitlements、
   `WidgetStore.appGroup` を合わせて更新。

## 3. App Store Connect

1. 新規 App を作成（Bundle ID: `com.photomind.ai`）。
2. **サブスクリプション**を作成:
   - Product ID: `com.photomind.ai.premium.yearly`（`StoreService.premiumProductID` と一致）
   - 自動更新・年額。ローカルテストは `Configuration.storekit` を Xcode に追加。
3. プライバシー「栄養ラベル」:
   - 写真: **端末内処理**。外部 AI を使う場合のみ「解析目的で送信」（縮小画像）を申告。
   - トラッキングなし・広告なし（Premium）。

## 4. アイコン

`Resources/Assets.xcassets/AppIcon.appiconset/icon-1024.png` を本番アイコンに差し替え。

## 5. アーカイブ & 提出

```bash
xcodebuild -project PhotoMindAI.xcodeproj -scheme PhotoMindAI \
  -sdk iphoneos -configuration Release archive \
  -archivePath build/PhotoMindAI.xcarchive
```

Xcode Organizer → Distribute App → App Store Connect → Upload。
または `xcodebuild -exportArchive` + `xcrun altool`/`notarytool`。

## 6. TestFlight → 審査

1. TestFlight で内部テスト（写真アクセス許可フロー、検索、課金 sandbox を確認）。
2. 審査ノートに「写真は端末内処理。外部 AI 送信はユーザー任意・送信前確認・縮小画像のみ」を明記。
3. 審査提出。

## CI

`.github/workflows/photomind-ci.yml`（リポジトリルート）が push/PR で
`xcodegen generate` → `xcodebuild test` を macOS runner 上で実行します。

## チェックリスト

- [ ] `DEVELOPMENT_TEAM` 設定
- [ ] App Group / iCloud / Push Capability
- [ ] サブスク Product ID 一致
- [ ] 本番アイコン差し替え
- [ ] プライバシーラベル・使用目的文字列
- [ ] スクリーンショット（6.7" / 6.1"）
- [ ] プライバシーポリシー / 利用規約 URL 有効化
