"""Gunicorn エントリーポイント.

Railway 側の起動コマンドが `gunicorn main:app` を想定しているため、
既存の `app.py` で定義された Flask アプリを公開する薄いラッパーです。
"""

import os

from app import app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

