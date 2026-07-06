# データベース設計

**SQLite (GRDB.swift)** を主ストアに採用。CoreData ではなく GRDB を選択した理由は、FTS5・
BLOB ベクトル・明示的なマイグレーション・`Sendable` な値型マッピングを素直に扱えるためです。
CloudKit 同期は将来 `CKSyncEngine` をリポジトリ層に差し込む設計（下記参照）。

保存場所: `Application Support/PhotoMind/photomind.sqlite`（WAL モード、
`FileProtectionType.completeUntilFirstUserAuthentication` で暗号化）。

## ER 図

```
asset (1) ──< category_tag (N)
asset (1) ──  embedding (1)          embedding.assetLocalIdentifier = asset.localIdentifier
asset (N) >──< album  via album_membership
asset (1) ──  asset_fts (FTS5, 同期)
usage_counter                         月次検索カウンタ（フリーミアム）
```

## テーブル

### `asset`
| 列 | 型 | 説明 |
|----|----|------|
| id | INTEGER PK | ローカル行 ID |
| localIdentifier | TEXT UNIQUE | `PHAsset.localIdentifier`（Photos への安定ポインタ） |
| mediaType | INT | 0=photo 1=video 2=livePhoto 3=raw |
| creationDate | DATETIME (index) | 撮影日時 |
| pixelWidth/Height | INT | 解像度 |
| durationSeconds | REAL | 動画長 |
| isFavorite | BOOL | お気に入り |
| latitude/longitude | REAL? | 撮影地 |
| placeName | TEXT? (index) | 逆ジオコーディング結果 |
| analysisState | INT | 0=pending 1=classified 2=embedded 3=failed |
| qualityScore | REAL | 0…1 シャープネス |
| isScreenshot | BOOL | スクショ判定 |
| perceptualHash | INT | 64-bit dHash（重複検出） |
| ocrText | TEXT? | OCR 結果 |
| captionSummary | TEXT? | AI/ローカルキャプション |

### `category_tag`
`id, assetId(FK cascade), category(index), confidence` — 1 写真に複数カテゴリ。

### `embedding`
`assetLocalIdentifier(PK), model, dimension, vector(BLOB)` —
ベクトルは **正規化済み Float32 リトルエンディアン** を BLOB 格納。
検索時は起動時に `VectorIndex`（インメモリ）へロードし、ブルートフォース top-k。

### `album` / `album_membership`
自動生成アルバム。`AlbumBuilder` が再生成するたびに置き換え（ユーザー編集はしない設計）。
`aiSummary` に「京都旅行 2025年4月 写真128枚 …」を格納。

### `asset_fts`（FTS5 仮想テーブル）
`ocrText / captionSummary / placeName` を unicode61 トークナイザでインデックス。
`asset` と `synchronize` して自動更新。キーワード/OCR 完全一致の高速前段フィルタに使用。

### `usage_counter`
`periodKey("YYYY-MM") PK, searchCount` — 無料プランの月100検索を永続化。

## マイグレーション

`DatabaseMigrator` で `v1_core → v2_fts → v3_search_meta` を順に適用（`AppDatabase.swift`）。
DEBUG は `eraseDatabaseOnSchemaChange`、リリースは前方互換の追記マイグレーションのみ。

## 100,000 枚でのスケール

- メタデータ検索は `creationDate` / `placeName` / `category` のインデックスで高速。
- ベクトル検索は 512 次元 × 10万件でも `VectorMath.cosine`（4-wide アンロール）で 1 フレーム未満。
  さらに拡大する場合は `VectorIndex` を IVF/HNSW に差し替え（インターフェース不変）。
- 解析はバックグラウンドでバッチ処理（`AnalysisPipeline`、既定 50 件/バッチ、中断・再開可）。
- サムネイルは `NSCache` + ImageIO サムネイルで decode コストを最小化。

## CloudKit 同期（設計）

リポジトリ層が唯一の書き込み口なので、各 `save*` の後に mirror レコードを
`CKSyncEngine` のキューに積む方式を想定。写真ピクセルは同期せず、**メタデータ・カテゴリ・
埋め込みのみ**を同期（写真本体は各デバイスの Photos/iCloud に既に存在）。
Entitlements に `iCloud.com.photomind.ai` を用意済み。
