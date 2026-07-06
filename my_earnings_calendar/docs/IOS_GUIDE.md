# 📱 iPhoneでアプリを動かす方法（ぜんぶで5ステップ）

むずかしい言葉は使いません。**上から順番に、1つずつ**やってください。
ぜんぶ「ターミナル」というアプリにコピペするだけです。

> 🖥 ターミナルの開き方：キーボードで `⌘（コマンド）+ スペース` を押して「ターミナル」と入力してEnter

---

## ステップ0️⃣：自分のMacの種類を調べる（30秒）

前に「**Bad CPU type**」というエラーが出たのは、**Macの種類に合わないFlutterを入れてしまった**のが原因です。まずMacの種類を調べます。

1. 画面左上の **リンゴマーク** をクリック
2. 「**このMacについて**」をクリック
3. 「チップ」または「プロセッサ」の行を見る
   - 「**Apple M1 / M2 / M3 / M4**」→ あなたは【**Appleチップ**】
   - 「**Intel**」と書いてある → あなたは【**Intel**】

---

## ステップ1️⃣：Flutterを正しく入れ直す（10分・コピペ1回）

⚠️ 前に入れたFlutterは種類違いなので、**捨てて入れ直します**。

下の**まほうの呪文**をターミナルに**まるごとコピペ**してEnterを押してください。
（Macの種類を自動で見分けて、正しいFlutterをダウンロードします）

```bash
rm -rf ~/flutter ~/flutter.zip
cd ~
if [ "$(uname -m)" = "arm64" ]; then
  curl -L -o flutter.zip https://storage.googleapis.com/flutter_infra_release/releases/stable/macos/flutter_macos_arm64_3.44.4-stable.zip
else
  curl -L -o flutter.zip https://storage.googleapis.com/flutter_infra_release/releases/stable/macos/flutter_macos_3.44.4-stable.zip
fi
unzip -q flutter.zip
rm flutter.zip
echo 'export PATH="$PATH:$HOME/flutter/bin"' >> ~/.zshrc
source ~/.zshrc
flutter --version
```

✅ 最後に「**Flutter 3.44.4**」のように表示されたら**成功**！
❌ エラーが出たら、その画面をコピーして私に見せてください。

---

## ステップ2️⃣：Xcode（アップル公式の道具）を入れる（30分〜・ほったらかしでOK）

1. このリンクを開く → **[App StoreのXcodeページ](https://apps.apple.com/jp/app/xcode/id497799835)**
2. 「**入手**」を押してインストール（大きいのでしばらく待つ☕）
3. 終わったら、ターミナルにこれをコピペしてEnter：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
```

> 🔑 `sudo` はMacのパスワードを聞いてきます。**文字が見えなくても打てています**。打ってEnter。

---

## ステップ3️⃣：アプリのファイルをダウンロードする（2分）

1. このリンクをクリック → **[アプリのダウンロード（zip）](https://github.com/sbaseball82-art/asset-tracker/archive/refs/heads/main.zip)**
2. ダウンロードフォルダにできた `asset-tracker-main.zip` を**ダブルクリック**で解凍
3. `asset-tracker-main` というフォルダができればOK

---

## ステップ4️⃣：iPhoneシミュレータを起動する（1分）

ターミナルにコピペしてEnter：

```bash
open -a Simulator
```

→ 画面に**iPhoneの形**が出てきたら成功！

---

## ステップ5️⃣：アプリを起動する！（初回5分）

ターミナルにこれをコピペしてEnter：

```bash
cd ~/Downloads/asset-tracker-main/my_earnings_calendar
flutter pub get
flutter run
```

⏳ 初回は5分くらいかかります。じっと待つ。

🎉 **iPhoneの画面にアプリが出たら完成！**

- やめたいとき：ターミナルで `q` を押す
- もう一度起動：ステップ5️⃣の3行をもう一度コピペ

---

## 😵 うまくいかないときは（よくある3つ）

| 出てきたエラー | なおし方 |
|---|---|
| `command not found: flutter` | ターミナルを**いったん閉じて開き直す**。ダメならステップ1️⃣をもう一度 |
| `Bad CPU type` | Macの種類違い。**ステップ1️⃣をもう一度**（自動で正しい方が入ります） |
| `Signing requires a development team`（Xcodeの署名エラー） | シミュレータなら署名は**不要**。Xcodeは使わず、**ステップ5️⃣のコマンドだけ**でOK |

それでもダメなら、**エラーの画面をそのままコピー**して私に見せてください。

---

## 🌐 おまけ：iPhoneを使わずブラウザで見る（いちばん簡単・2分）

```bash
cd ~/Downloads/asset-tracker-main/my_earnings_calendar
flutter run -d chrome
```

Chromeが自動で開いてアプリが動きます。
