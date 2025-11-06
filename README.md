# 案件管理システム

## セットアップ

### 1. 仮想環境の有効化

```bash
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate  # Windows
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. アプリケーションの起動

```bash
python app.py
```

ブラウザで `http://localhost:5000` にアクセスしてください。


## 本番デプロイ（Railway）

1. **リポジトリを Railway プロジェクトに接続**
   - Railway ダッシュボードで新しいサービスを作成し、GitHub リポジトリをリンクします。
   - デプロイ対象ブランチを指定してください（例: `main`）。

2. **環境変数の設定**
   - `DATABASE_URL`：PostgreSQL 接続文字列。Railway の Postgres アドオンを利用する場合は自動で発行される値をそのまま使用できます。
   - `FLASK_SECRET_KEY`：Flask セッション用の秘密鍵。十分にランダムな文字列を設定してください。
   - （任意）`WEB_CONCURRENCY`：Gunicorn のワーカー数。デフォルトは `2`。トラフィックに応じて調整します。

3. **起動コマンドの確認**
   - リポジトリには `Procfile` を配置しており、Railway で自動的に `gunicorn main:app` が実行されます。

4. **ポートの公開**
   - Railway サービスは `PORT=8080` で待ち受けます。ダッシュボードの `Settings` → `Networking` で「Expose a Port」を選択し、ポート `8080` を公開します。
   - 公開後、`*.railway.app` のドメインが自動発行されます。カスタムドメインを利用する場合は同画面の「Domains」から追加してください。

5. **データベース初期化**
   - アプリ起動時に `ensure_tables()` が自動でテーブルを作成し、初期ユーザー（`admin@example.com` など）を投入します。
   - 既存データベースを利用する場合は、必要に応じて初期ユーザーを削除／更新してください。

6. **ログの確認**
   - 本番デプロイ後に `View logs` から Gunicorn/Flask ログを確認し、エラーがないかをチェックします。

## 運用時のヒント

- Railways の `Variables` で環境変数を更新した場合は、再デプロイ（Restart）を実行すると即時反映されます。
- セッションタイムアウトやアクセスログ等を強化する場合は、`app.py` の設定を適宜拡張してください。





