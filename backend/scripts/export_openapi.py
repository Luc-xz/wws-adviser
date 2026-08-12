"""导出 OpenAPI 规范到 frontend/openapi.json（前端类型生成用，CI 友好）。

前端 `pnpm gen:api` 用 openapi-typescript 读此文件生成 src/api/generated/types.ts。
"""

import json
from pathlib import Path

from wws_adviser.api.app import create_app
from wws_adviser.core.config import load_settings


def main() -> None:
    settings = load_settings()
    app = create_app(settings)
    spec = app.openapi()
    out = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI 已导出: {out}")


if __name__ == "__main__":
    main()
