import sqlite3
import hashlib
import os
import random
import string
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "abds.db")


# ─────────────────────────────────────────────
# 連線管理
# ─────────────────────────────────────────────
@contextmanager
def get_conn():
    """取得資料庫連線，自動啟用外鍵約束與 WAL 模式"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # 啟用外鍵約束
    conn.execute("PRAGMA journal_mode = WAL")  # 提升並發效能
    conn.execute("PRAGMA busy_timeout = 5000") # 防鎖定衝突
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
# 資料庫初始化 / DDL
# ─────────────────────────────────────────────
DDL = """
-- 使用者表（以學號作為帳號）
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,          -- 學號，唯一
    password_hash   TEXT    NOT NULL,
    real_name       TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    anonymous_alias TEXT    NOT NULL UNIQUE,          -- 匿名代號，唯一
    role            TEXT    NOT NULL DEFAULT 'student'
                            CHECK(role IN ('student','admin')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 書籍表
CREATE TABLE IF NOT EXISTS books (
    book_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn            TEXT    UNIQUE,                   -- ISBN 可為 NULL（手動新增時）
    title           TEXT    NOT NULL,
    author          TEXT    NOT NULL DEFAULT '未知',
    publisher       TEXT    DEFAULT '未知',
    category        TEXT    DEFAULT '一般',
    description     TEXT    DEFAULT '',
    total_copies    INTEGER NOT NULL DEFAULT 1 CHECK(total_copies >= 0),
    available_copies INTEGER NOT NULL DEFAULT 1 CHECK(available_copies >= 0),
    avg_rating      REAL    NOT NULL DEFAULT 0.0
                            CHECK(avg_rating >= 0 AND avg_rating <= 5),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 書評表（每人每書只能一則，重複則 UPDATE）
CREATE TABLE IF NOT EXISTS reviews (
    review_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    book_id         INTEGER NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    rating          INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    content         TEXT    NOT NULL DEFAULT '',
    is_anonymous    INTEGER NOT NULL DEFAULT 1 CHECK(is_anonymous IN (0,1)),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(user_id, book_id)                          -- 防重複評論
);

-- 按讚表（複合主鍵，防重複按讚）
CREATE TABLE IF NOT EXISTS likes (
    user_id         INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
    review_id       INTEGER NOT NULL REFERENCES reviews(review_id) ON DELETE CASCADE,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY(user_id, review_id)                   -- 防重複按讚
);

-- 借閱紀錄表
CREATE TABLE IF NOT EXISTS borrow_records (
    borrow_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    book_id         INTEGER NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    borrow_date     TEXT    NOT NULL DEFAULT (date('now','localtime')),
    due_date        TEXT    NOT NULL,
    return_date     TEXT,
    status          TEXT    NOT NULL DEFAULT 'borrowed'
                            CHECK(status IN ('borrowed','returned','overdue'))
);

-- 索引（加速常用查詢）
CREATE INDEX IF NOT EXISTS idx_reviews_book   ON reviews(book_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user   ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_borrow_user    ON borrow_records(user_id);
CREATE INDEX IF NOT EXISTS idx_borrow_book    ON borrow_records(book_id);
CREATE INDEX IF NOT EXISTS idx_likes_review   ON likes(review_id);
"""


def init_db():
    """初始化資料庫，建立所有資料表與索引"""
    with get_conn() as conn:
        conn.executescript(DDL)
    print(f"[DB] 資料庫初始化完成：{DB_PATH}")


# ─────────────────────────────────────────────
# 工具函式
# ─────────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def generate_alias() -> str:
    """產生隨機匿名代號，格式：讀者_XXXXX"""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=5))
    return f"讀者_{suffix}"


def _recalc_avg_rating(conn, book_id: int):
    """重新計算書籍平均評分並更新"""
    row = conn.execute(
        "SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE book_id=?",
        (book_id,)
    ).fetchone()
    avg = round(row["avg"] or 0.0, 2)
    conn.execute("UPDATE books SET avg_rating=? WHERE book_id=?", (avg, book_id))


def _update_like_count(conn, review_id: int):
    """更新書評的按讚數（從 likes 表計算）"""
    # likes 表有 like_count 欄位在 reviews 表，需同步
    # 這裡直接用 SELECT COUNT 動態計算，不另存欄位以避免不一致
    pass  # like_count 改為動態查詢，見 get_reviews_by_book


# ─────────────────────────────────────────────
# 使用者 CRUD
# ─────────────────────────────────────────────
def register_user(username: str, password: str, real_name: str,
                  email: str, anonymous_alias: str = None) -> dict:
    """
    以學號註冊使用者。
    - username 必須唯一（學號）
    - email 必須唯一
    - anonymous_alias 若未提供則自動產生，確保唯一
    回傳 {'ok': True/False, 'msg': str, 'user_id': int}
    """
    if not username or not password or not real_name or not email:
        return {"ok": False, "msg": "所有欄位均為必填"}

    pw_hash = hash_password(password)

    with get_conn() as conn:
        # 確保匿名代號唯一
        if not anonymous_alias:
            for _ in range(20):
                alias = generate_alias()
                exists = conn.execute(
                    "SELECT 1 FROM users WHERE anonymous_alias=?", (alias,)
                ).fetchone()
                if not exists:
                    anonymous_alias = alias
                    break
            else:
                return {"ok": False, "msg": "無法產生唯一匿名代號，請稍後再試"}

        # 檢查學號是否已存在
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return {"ok": False, "msg": f"學號 {username} 已被註冊"}

        # 檢查 email 是否已存在
        if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            return {"ok": False, "msg": "此電子郵件已被使用"}

        # 檢查匿名代號是否已存在
        if conn.execute("SELECT 1 FROM users WHERE anonymous_alias=?", (anonymous_alias,)).fetchone():
            return {"ok": False, "msg": "此匿名代號已被使用，請換一個"}

        conn.execute(
            """INSERT INTO users (username, password_hash, real_name, email, anonymous_alias)
               VALUES (?,?,?,?,?)""",
            (username, pw_hash, real_name, email, anonymous_alias)
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"ok": True, "msg": "註冊成功", "user_id": user_id}


def login_user(username: str, password: str) -> dict:
    """
    使用學號登入。
    回傳 {'ok': True/False, 'msg': str, 'user': dict}
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        if not row:
            return {"ok": False, "msg": "學號不存在"}
        if not verify_password(password, row["password_hash"]):
            return {"ok": False, "msg": "密碼錯誤"}
        return {"ok": True, "msg": "登入成功", "user": dict(row)}


def get_user_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


# ─────────────────────────────────────────────
# 書籍 CRUD
# ─────────────────────────────────────────────
def get_book_by_id(book_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
        return dict(row) if row else None


def get_book_by_isbn(isbn: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM books WHERE isbn=?", (isbn,)).fetchone()
        return dict(row) if row else None


def search_books(keyword: str = "", category: str = "") -> list:
    """搜尋書籍（書名、作者、ISBN 模糊比對）"""
    with get_conn() as conn:
        q = "SELECT * FROM books WHERE 1=1"
        params = []
        if keyword:
            q += " AND (title LIKE ? OR author LIKE ? OR isbn LIKE ?)"
            kw = f"%{keyword}%"
            params += [kw, kw, kw]
        if category:
            q += " AND category=?"
            params.append(category)
        q += " ORDER BY avg_rating DESC, book_id DESC"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def get_all_books() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM books ORDER BY book_id DESC").fetchall()
        return [dict(r) for r in rows]


def add_book(title: str, author: str = "未知", publisher: str = "未知",
             category: str = "一般", isbn: str = None, description: str = "",
             total_copies: int = 1) -> dict:
    """
    新增書籍。若 ISBN 已存在則回傳現有書籍。
    回傳 {'ok': True/False, 'msg': str, 'book_id': int}
    """
    if not title:
        return {"ok": False, "msg": "書名為必填"}

    with get_conn() as conn:
        # 若有 ISBN，先檢查是否已存在
        if isbn:
            existing = conn.execute(
                "SELECT book_id FROM books WHERE isbn=?", (isbn,)
            ).fetchone()
            if existing:
                return {"ok": True, "msg": "書籍已存在（依 ISBN 比對）",
                        "book_id": existing["book_id"]}

        conn.execute(
            """INSERT INTO books (isbn, title, author, publisher, category,
               description, total_copies, available_copies)
               VALUES (?,?,?,?,?,?,?,?)""",
            (isbn, title, author, publisher, category, description,
             total_copies, total_copies)
        )
        book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"ok": True, "msg": "書籍新增成功", "book_id": book_id}


def ensure_book_exists(book_id: int = None, isbn: str = None,
                       title: str = None) -> dict:
    """
    確保書籍存在：若不存在則自動新增。
    優先以 book_id 查詢，其次 ISBN，最後以書名新增。
    回傳 {'ok': True/False, 'book_id': int, 'created': bool}
    """
    with get_conn() as conn:
        if book_id:
            row = conn.execute(
                "SELECT book_id FROM books WHERE book_id=?", (book_id,)
            ).fetchone()
            if row:
                return {"ok": True, "book_id": row["book_id"], "created": False}

        if isbn:
            row = conn.execute(
                "SELECT book_id FROM books WHERE isbn=?", (isbn,)
            ).fetchone()
            if row:
                return {"ok": True, "book_id": row["book_id"], "created": False}

    # 書籍不存在，自動新增
    if not title:
        title = f"書籍 #{book_id or isbn or '未知'}"
    result = add_book(title=title, isbn=isbn)
    if result["ok"]:
        return {"ok": True, "book_id": result["book_id"], "created": True}
    return {"ok": False, "book_id": None, "created": False}


def get_categories() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM books ORDER BY category"
        ).fetchall()
        return [r["category"] for r in rows]


# ─────────────────────────────────────────────
# 書評 CRUD
# ─────────────────────────────────────────────
def upsert_review(user_id: int, book_id: int, rating: int,
                  content: str, is_anonymous: bool = True) -> dict:
    """
    新增或更新書評（UPSERT）。
    同一使用者對同一書籍只能有一則書評，重複提交則更新。
    回傳 {'ok': True/False, 'msg': str, 'review_id': int, 'action': 'insert'/'update'}
    """
    if not (1 <= rating <= 5):
        return {"ok": False, "msg": "評分必須在 1 到 5 之間"}
    if not content.strip():
        return {"ok": False, "msg": "評論內容不能為空"}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    anon_int = 1 if is_anonymous else 0

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT review_id FROM reviews WHERE user_id=? AND book_id=?",
            (user_id, book_id)
        ).fetchone()

        if existing:
            # 更新現有書評
            conn.execute(
                """UPDATE reviews SET rating=?, content=?, is_anonymous=?, updated_at=?
                   WHERE review_id=?""",
                (rating, content, anon_int, now, existing["review_id"])
            )
            review_id = existing["review_id"]
            action = "update"
        else:
            # 新增書評
            conn.execute(
                """INSERT INTO reviews (user_id, book_id, rating, content, is_anonymous, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (user_id, book_id, rating, content, anon_int, now)
            )
            review_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            action = "insert"

        # 重新計算平均評分
        _recalc_avg_rating(conn, book_id)

    msg = "書評已更新" if action == "update" else "書評發表成功"
    return {"ok": True, "msg": msg, "review_id": review_id, "action": action}


def get_reviews_by_book(book_id: int, viewer_user_id: int = None) -> list:
    """
    取得書籍的所有書評，依按讚數排序。
    - 若 is_anonymous=1，前端顯示 anonymous_alias
    - 若 viewer_user_id 為管理員，顯示真實姓名
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.review_id, r.user_id, r.book_id, r.rating, r.content,
                      r.is_anonymous, r.created_at, r.updated_at,
                      u.username, u.real_name, u.anonymous_alias, u.role,
                      (SELECT COUNT(*) FROM likes l WHERE l.review_id=r.review_id) AS like_count,
                      CASE WHEN r.is_anonymous=1 THEN u.anonymous_alias
                           ELSE u.real_name END AS display_name
               FROM reviews r
               JOIN users u ON r.user_id = u.user_id
               WHERE r.book_id=?
               ORDER BY like_count DESC, r.updated_at DESC""",
            (book_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_reviews_by_user(user_id: int) -> list:
    """取得使用者的所有書評"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.*, b.title, b.author,
                      (SELECT COUNT(*) FROM likes l WHERE l.review_id=r.review_id) AS like_count
               FROM reviews r
               JOIN books b ON r.book_id = b.book_id
               WHERE r.user_id=?
               ORDER BY r.updated_at DESC""",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_review(review_id: int, user_id: int) -> dict:
    """刪除書評（只能刪除自己的）"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT book_id, user_id FROM reviews WHERE review_id=?", (review_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "msg": "書評不存在"}
        if row["user_id"] != user_id:
            return {"ok": False, "msg": "無權限刪除此書評"}
        book_id = row["book_id"]
        conn.execute("DELETE FROM reviews WHERE review_id=?", (review_id,))
        _recalc_avg_rating(conn, book_id)
    return {"ok": True, "msg": "書評已刪除"}


# ─────────────────────────────────────────────
# 按讚 CRUD
# ─────────────────────────────────────────────
def toggle_like(user_id: int, review_id: int) -> dict:
    """
    切換按讚狀態：已按讚則取消，未按讚則新增。
    複合主鍵確保不重複。
    回傳 {'ok': True, 'action': 'liked'/'unliked', 'like_count': int}
    """
    with get_conn() as conn:
        # 確認書評存在
        if not conn.execute(
            "SELECT 1 FROM reviews WHERE review_id=?", (review_id,)
        ).fetchone():
            return {"ok": False, "msg": "書評不存在"}

        existing = conn.execute(
            "SELECT 1 FROM likes WHERE user_id=? AND review_id=?",
            (user_id, review_id)
        ).fetchone()

        if existing:
            conn.execute(
                "DELETE FROM likes WHERE user_id=? AND review_id=?",
                (user_id, review_id)
            )
            action = "unliked"
        else:
            conn.execute(
                "INSERT INTO likes (user_id, review_id) VALUES (?,?)",
                (user_id, review_id)
            )
            action = "liked"

        like_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM likes WHERE review_id=?", (review_id,)
        ).fetchone()["cnt"]

    return {"ok": True, "action": action, "like_count": like_count}


def get_user_liked_reviews(user_id: int) -> set:
    """取得使用者已按讚的 review_id 集合"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT review_id FROM likes WHERE user_id=?", (user_id,)
        ).fetchall()
        return {r["review_id"] for r in rows}


# ─────────────────────────────────────────────
# 借閱 CRUD
# ─────────────────────────────────────────────
def borrow_book(user_id: int, book_id: int, days: int = 14) -> dict:
    """
    借閱書籍。
    - 檢查 available_copies > 0
    - 建立借閱紀錄
    - 更新 available_copies
    回傳 {'ok': True/False, 'msg': str, 'borrow_id': int}
    """
    with get_conn() as conn:
        book = conn.execute(
            "SELECT available_copies, title FROM books WHERE book_id=?", (book_id,)
        ).fetchone()
        if not book:
            return {"ok": False, "msg": "書籍不存在"}
        if book["available_copies"] <= 0:
            return {"ok": False, "msg": f"《{book['title']}》目前無可借閱館藏"}

        # 檢查使用者是否已借閱此書且未歸還
        active = conn.execute(
            """SELECT 1 FROM borrow_records
               WHERE user_id=? AND book_id=? AND status='borrowed'""",
            (user_id, book_id)
        ).fetchone()
        if active:
            return {"ok": False, "msg": "您已借閱此書，請先歸還"}

        borrow_date = datetime.now().strftime("%Y-%m-%d")
        due_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

        conn.execute(
            """INSERT INTO borrow_records (user_id, book_id, borrow_date, due_date, status)
               VALUES (?,?,?,?,'borrowed')""",
            (user_id, book_id, borrow_date, due_date)
        )
        borrow_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "UPDATE books SET available_copies=available_copies-1 WHERE book_id=?",
            (book_id,)
        )
    return {"ok": True, "msg": "借閱成功", "borrow_id": borrow_id,
            "due_date": due_date}


def return_book(borrow_id: int, user_id: int) -> dict:
    """
    歸還書籍。
    - 更新 return_date 與 status
    - 更新 available_copies
    回傳 {'ok': True/False, 'msg': str}
    """
    with get_conn() as conn:
        record = conn.execute(
            """SELECT borrow_id, book_id, status FROM borrow_records
               WHERE borrow_id=? AND user_id=?""",
            (borrow_id, user_id)
        ).fetchone()
        if not record:
            return {"ok": False, "msg": "借閱紀錄不存在"}
        if record["status"] == "returned":
            return {"ok": False, "msg": "此書已歸還"}

        return_date = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            """UPDATE borrow_records SET return_date=?, status='returned'
               WHERE borrow_id=?""",
            (return_date, borrow_id)
        )
        conn.execute(
            "UPDATE books SET available_copies=available_copies+1 WHERE book_id=?",
            (record["book_id"],)
        )
    return {"ok": True, "msg": "歸還成功"}


def get_borrow_history(user_id: int) -> list:
    """取得使用者借閱歷史"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT br.*, b.title, b.author
               FROM borrow_records br
               JOIN books b ON br.book_id = b.book_id
               WHERE br.user_id=?
               ORDER BY br.borrow_date DESC""",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_overdue_status():
    """更新逾期狀態（應定期呼叫）"""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            """UPDATE borrow_records SET status='overdue'
               WHERE status='borrowed' AND due_date < ?""",
            (today,)
        )


# ─────────────────────────────────────────────
# 推薦系統
# ─────────────────────────────────────────────
def get_popular_books(limit: int = 10) -> list:
    """熱門書籍推薦（依平均評分 + 評論數 + 借閱次數）"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT b.*,
                      COUNT(DISTINCT r.review_id) AS review_count,
                      COUNT(DISTINCT br.borrow_id) AS borrow_count,
                      (b.avg_rating * 0.5 +
                       COUNT(DISTINCT r.review_id) * 0.3 +
                       COUNT(DISTINCT br.borrow_id) * 0.2) AS popularity_score
               FROM books b
               LEFT JOIN reviews r ON b.book_id = r.book_id
               LEFT JOIN borrow_records br ON b.book_id = br.book_id
               GROUP BY b.book_id
               ORDER BY popularity_score DESC, b.avg_rating DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_cf_recommendations(user_id: int, limit: int = 5) -> list:
    """
    簡化版 User-Based Collaborative Filtering 推薦。
    - 找出與目標使用者評分相似的其他使用者
    - 推薦相似使用者高評分但目標使用者尚未評論的書籍
    - 若評分資料不足（< 3 筆），退回熱門推薦
    """
    with get_conn() as conn:
        # 取得目標使用者的評分資料
        user_ratings = conn.execute(
            "SELECT book_id, rating FROM reviews WHERE user_id=?", (user_id,)
        ).fetchall()

        if len(user_ratings) < 3:
            # 冷啟動：退回熱門推薦，排除已評論書籍
            rated_ids = [r["book_id"] for r in user_ratings]
            placeholder = ",".join("?" * len(rated_ids)) if rated_ids else "0"
            rows = conn.execute(
                f"""SELECT b.*, COUNT(r2.review_id) AS review_count,
                           COUNT(br.borrow_id) AS borrow_count
                    FROM books b
                    LEFT JOIN reviews r2 ON b.book_id = r2.book_id
                    LEFT JOIN borrow_records br ON b.book_id = br.book_id
                    WHERE b.book_id NOT IN ({placeholder})
                    GROUP BY b.book_id
                    ORDER BY b.avg_rating DESC, review_count DESC
                    LIMIT ?""",
                rated_ids + [limit]
            ).fetchall()
            return [dict(r) for r in rows]

        # 取得目標使用者已評論的書籍 ID
        rated_book_ids = {r["book_id"] for r in user_ratings}
        user_rating_map = {r["book_id"]: r["rating"] for r in user_ratings}

        # 找出評論過相同書籍的其他使用者
        if not rated_book_ids:
            return get_popular_books(limit)

        placeholder = ",".join("?" * len(rated_book_ids))
        other_users = conn.execute(
            f"""SELECT DISTINCT user_id FROM reviews
                WHERE book_id IN ({placeholder}) AND user_id != ?""",
            list(rated_book_ids) + [user_id]
        ).fetchall()

        if not other_users:
            return get_popular_books(limit)

        # 計算餘弦相似度（簡化版：共同評分書籍的評分差）
        similarities = []
        for other in other_users:
            other_id = other["user_id"]
            other_ratings = conn.execute(
                "SELECT book_id, rating FROM reviews WHERE user_id=?", (other_id,)
            ).fetchall()
            other_map = {r["book_id"]: r["rating"] for r in other_ratings}

            common = rated_book_ids & set(other_map.keys())
            if not common:
                continue

            # 計算相似度（共同書籍評分差的負值，越小越相似）
            diff_sum = sum(
                abs(user_rating_map[b] - other_map[b]) for b in common
            )
            similarity = len(common) / (1 + diff_sum)
            similarities.append((other_id, similarity))

        if not similarities:
            return get_popular_books(limit)

        # 取 Top-3 相似使用者
        top_users = sorted(similarities, key=lambda x: -x[1])[:3]
        top_user_ids = [u[0] for u in top_users]

        # 找出相似使用者高評分（>=4）但目標使用者未評論的書籍
        rated_placeholder = ",".join("?" * len(rated_book_ids))
        user_placeholder = ",".join("?" * len(top_user_ids))

        rows = conn.execute(
            f"""SELECT b.*, AVG(r.rating) AS neighbor_avg_rating,
                       COUNT(r.review_id) AS neighbor_review_count
                FROM books b
                JOIN reviews r ON b.book_id = r.book_id
                WHERE r.user_id IN ({user_placeholder})
                  AND r.rating >= 4
                  AND b.book_id NOT IN ({rated_placeholder})
                GROUP BY b.book_id
                ORDER BY neighbor_avg_rating DESC, neighbor_review_count DESC
                LIMIT ?""",
            top_user_ids + list(rated_book_ids) + [limit]
        ).fetchall()

        if not rows:
            return get_popular_books(limit)
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 管理員功能
# ─────────────────────────────────────────────
def get_all_users() -> list:
    """管理員：取得所有使用者（含真實身份）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, username, real_name, email, anonymous_alias, role, created_at FROM users ORDER BY user_id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_reviews_admin() -> list:
    """管理員：取得所有書評（含真實身份）"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.review_id, r.rating, r.content, r.is_anonymous,
                      r.created_at, r.updated_at,
                      u.username, u.real_name, u.anonymous_alias,
                      b.title AS book_title, b.book_id,
                      (SELECT COUNT(*) FROM likes l WHERE l.review_id=r.review_id) AS like_count
               FROM reviews r
               JOIN users u ON r.user_id = u.user_id
               JOIN books b ON r.book_id = b.book_id
               ORDER BY r.updated_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    """取得系統統計資料"""
    with get_conn() as conn:
        stats = {}
        stats["total_users"] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        stats["total_books"] = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        stats["total_reviews"] = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        stats["total_borrows"] = conn.execute("SELECT COUNT(*) FROM borrow_records").fetchone()[0]
        stats["active_borrows"] = conn.execute(
            "SELECT COUNT(*) FROM borrow_records WHERE status='borrowed'"
        ).fetchone()[0]
        stats["total_likes"] = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
        return stats


# ─────────────────────────────────────────────
# 種子資料（示範用）
# ─────────────────────────────────────────────
def seed_demo_data():
    """插入示範資料（僅在資料庫為空時執行）"""
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return  # 已有資料，跳過

    # 新增管理員
    register_user(
        username="admin001",
        password="admin1234",
        real_name="系統管理員",
        email="admin@library.edu.tw",
        anonymous_alias="管理員_ADMIN"
    )
    # 設定為管理員
    with get_conn() as conn:
        conn.execute("UPDATE users SET role='admin' WHERE username='admin001'")

    # 新增示範學生
    students = [
        ("S11001001", "pass1234", "王小明", "s11001001@student.edu.tw"),
        ("S11001002", "pass1234", "李小花", "s11001002@student.edu.tw"),
        ("S11001003", "pass1234", "張大偉", "s11001003@student.edu.tw"),
        ("S11001004", "pass1234", "陳美麗", "s11001004@student.edu.tw"),
        ("S11001005", "pass1234", "林志遠", "s11001005@student.edu.tw"),
    ]
    for s in students:
        register_user(*s)

    # 新增示範書籍
    books_data = [
        ("978-986-262-501-0", "資料庫系統概論", "Ramez Elmasri", "碁峰", "資訊科學",
         "深入介紹關聯式資料庫設計、SQL 語法與正規化理論。", 5),
        ("978-986-502-838-3", "Python 程式設計", "Eric Matthes", "碁峰", "程式語言",
         "從零開始學習 Python，涵蓋資料結構、函式與物件導向。", 3),
        ("978-957-32-8551-2", "人類大歷史", "Yuval Noah Harari", "天下文化", "歷史",
         "從認知革命到人工智慧，探索人類文明的演進歷程。", 4),
        ("978-986-262-400-6", "演算法導論", "Thomas H. Cormen", "碁峰", "資訊科學",
         "全球最廣泛使用的演算法教科書，涵蓋排序、圖論與動態規劃。", 2),
        ("978-957-32-8789-9", "原子習慣", "James Clear", "天下雜誌", "自我成長",
         "透過微小改變建立強大習慣系統，實現長期目標的科學方法。", 6),
        ("978-986-262-600-0", "機器學習實戰", "Aurélien Géron", "碁峰", "資訊科學",
         "使用 Scikit-Learn 與 TensorFlow 實作機器學習專案。", 3),
        ("978-957-32-9001-1", "被討厭的勇氣", "岸見一郎", "究竟", "心理學",
         "阿德勒心理學的哲學對話，探討自由與幸福的真諦。", 5),
        ("978-986-262-700-7", "深度學習", "Ian Goodfellow", "碁峰", "資訊科學",
         "深度學習領域的權威教科書，涵蓋神經網路理論與應用。", 2),
    ]
    book_ids = []
    for b in books_data:
        result = add_book(isbn=b[0], title=b[1], author=b[2], publisher=b[3],
                          category=b[4], description=b[5], total_copies=b[6])
        book_ids.append(result["book_id"])

    # 新增示範書評
    with get_conn() as conn:
        users = conn.execute("SELECT user_id FROM users WHERE role='student'").fetchall()
        user_ids = [u["user_id"] for u in users]

    reviews_data = [
        (user_ids[0], book_ids[0], 5, "這本書對資料庫正規化的解說非常清晰，是學習 SQL 的必讀教材！", True),
        (user_ids[1], book_ids[0], 4, "內容豐富但有點艱深，建議搭配實作練習效果更好。", False),
        (user_ids[2], book_ids[0], 5, "教授推薦的教科書，確實名不虛傳，ER 圖的章節特別精彩。", True),
        (user_ids[0], book_ids[1], 5, "Python 入門首選！範例豐富，循序漸進，非常適合初學者。", True),
        (user_ids[3], book_ids[1], 4, "寫得很清楚，但後半段的 Django 部分稍微跳太快了。", True),
        (user_ids[1], book_ids[2], 5, "改變我對歷史的看法，Harari 的文筆流暢，讀起來欲罷不能。", False),
        (user_ids[4], book_ids[2], 4, "宏觀視野令人震撼，但部分論點稍嫌武斷，仍是必讀好書。", True),
        (user_ids[2], book_ids[3], 3, "演算法聖經，但難度偏高，建議有一定基礎再讀。", True),
        (user_ids[0], book_ids[4], 5, "原子習慣真的改變了我的生活！每個概念都有科學依據支撐。", True),
        (user_ids[3], book_ids[4], 5, "這本書讓我重新思考習慣的力量，強烈推薦給每個想改變的人。", False),
        (user_ids[4], book_ids[6], 5, "阿德勒的思想很有啟發性，對話形式讓哲學變得易懂有趣。", True),
        (user_ids[1], book_ids[6], 4, "被討厭的勇氣教會我如何面對他人的評價，很有幫助。", True),
    ]
    for uid, bid, rating, content, anon in reviews_data:
        upsert_review(uid, bid, rating, content, anon)

    # 新增示範按讚
    likes_data = [
        (user_ids[0], 2), (user_ids[1], 1), (user_ids[2], 3),
        (user_ids[3], 1), (user_ids[4], 5), (user_ids[0], 6),
        (user_ids[1], 9), (user_ids[2], 10), (user_ids[3], 11),
    ]
    for uid, rid in likes_data:
        try:
            toggle_like(uid, rid)
        except Exception:
            pass

    # 新增示範借閱紀錄
    borrow_book(user_ids[0], book_ids[0])
    borrow_book(user_ids[1], book_ids[2])
    borrow_book(user_ids[2], book_ids[4])

    print("[DB] 示範資料已插入完成")


# ─────────────────────────────────────────────
# 主程式入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    seed_demo_data()
    stats = get_stats()
    print(f"[DB] 統計：{stats}")
