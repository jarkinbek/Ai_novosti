import json
import os
from typing import Optional

DB_PATH = "data.json"

class Database:
    def __init__(self):
        if not os.path.exists(DB_PATH):
            self._write({"users": {}, "articles": {}, "cache": {}})

    def _read(self) -> dict:
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"users": {}, "articles": {}, "cache": {}}

    def _write(self, data: dict):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_user(self, user_id: int, data: dict):
        db = self._read()
        db["users"][str(user_id)] = data
        self._write(db)

    def get_user(self, user_id: int) -> Optional[dict]:
        return self._read()["users"].get(str(user_id))

    def save_article(self, article_id: str, data: dict):
        db = self._read()
        db.setdefault("articles", {})[article_id] = data
        arts = db["articles"]
        if len(arts) > 300:
            for k in list(arts.keys())[:-300]:
                del arts[k]
        self._write(db)

    def get_article(self, article_id: str) -> Optional[dict]:
        return self._read()["articles"].get(article_id)

    def save_category_cache(self, category: str, article_ids: list):
        db = self._read()
        db.setdefault("cache", {})[category] = article_ids
        self._write(db)

    def get_category_cache(self, category: str) -> Optional[list]:
        return self._read().get("cache", {}).get(category)

    def get_all_users(self) -> list:
        return list(self._read()["users"].values())