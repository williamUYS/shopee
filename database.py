"""
数据库层 - SQLite3 初始化与 CRUD 操作
"""

import hashlib
import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT   NOT NULL DEFAULT '',
            online_sku  TEXT    NOT NULL,
            offline_sku TEXT    NOT NULL,
            size        TEXT    NOT NULL,
            cost        REAL    NOT NULL DEFAULT 0,
            price       REAL    NOT NULL DEFAULT 0,
            colors      TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    # 兼容旧库：添加 product_name 列
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN product_name TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 列已存在
    # 兼容旧库：添加 image_url 列
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 列已存在
    # 确保线下SKU唯一索引
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_offline_sku_unique
        ON products(offline_sku)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    # 确保默认管理员存在
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        pw_hash = hashlib.sha256("5877".encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", pw_hash)
        )
    # ── 货款对账表 ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            payment_date  TEXT    NOT NULL,
            total_amount  REAL    NOT NULL DEFAULT 0,
            status        TEXT    NOT NULL DEFAULT '未结算',
            created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id    INTEGER NOT NULL,
            product_name  TEXT    NOT NULL DEFAULT '',
            offline_sku   TEXT    NOT NULL,
            quantity      REAL    NOT NULL DEFAULT 0,
            cost_price    REAL    NOT NULL DEFAULT 0,
            cost_amount   REAL    NOT NULL DEFAULT 0,
            FOREIGN KEY (payment_id) REFERENCES payment_records(id) ON DELETE CASCADE
        )
    """)
    # 兼容升级：新增结算相关字段
    for col, defn in [("other_fee", "REAL NOT NULL DEFAULT 0"),
                       ("settlement_date", "TEXT NOT NULL DEFAULT ''"),
                       ("settlement_remark", "TEXT NOT NULL DEFAULT ''")]:
        try:
            cursor.execute(f"ALTER TABLE payment_records ADD COLUMN {col} {defn}")
        except Exception:
            pass  # 列已存在则忽略
    conn.commit()
    conn.close()


def verify_password(password: str) -> Optional[dict]:
    """验证密码，成功返回用户信息；使用 SHA256 哈希比对"""
    conn = get_connection()
    cursor = conn.cursor()
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute(
        "SELECT id, username FROM users WHERE username = 'admin' AND password_hash = ?",
        (pw_hash,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ── CRUD ──────────────────────────────────────────────

def check_offline_sku_exists(offline_sku: str, exclude_id: int = None) -> bool:
    """检查线下SKU是否已存在，可选排除指定ID（用于编辑场景）"""
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        cursor.execute(
            "SELECT id FROM products WHERE offline_sku = ? AND id != ?",
            (offline_sku.strip(), exclude_id)
        )
    else:
        cursor.execute(
            "SELECT id FROM products WHERE offline_sku = ?",
            (offline_sku.strip(),)
        )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def list_products(search: str = "", page: int = 1, page_size: int = 20) -> dict:
    """分页查询商品列表，支持按名称 / SKU / 尺码 / 颜色搜索"""
    conn = get_connection()
    cursor = conn.cursor()

    where = ""
    params: tuple = ()
    if search:
        where = "WHERE product_name LIKE ? OR online_sku LIKE ? OR offline_sku LIKE ? OR colors LIKE ? OR size LIKE ?"
        like = f"%{search}%"
        params = (like, like, like, like, like)

    # 总数
    count_sql = f"SELECT COUNT(*) FROM products {where}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]

    # 分页数据
    offset = (page - 1) * page_size
    data_sql = f"SELECT * FROM products {where} ORDER BY id DESC LIMIT ? OFFSET ?"
    cursor.execute(data_sql, params + (page_size, offset))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_product(product_id: int) -> Optional[dict]:
    """获取单个商品"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


class DuplicateOfflineSkuError(Exception):
    """线下SKU重复异常"""
    pass


def create_product(product_name: str, online_sku: str, offline_sku: str, size: str,
                   cost: float, price: float, colors: str, image_url: str = "") -> dict:
    """新增商品"""
    offline = offline_sku.strip()
    if check_offline_sku_exists(offline):
        raise DuplicateOfflineSkuError(f"线下SKU「{offline}」已存在，不允许重复")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO products (product_name, online_sku, offline_sku, size, cost, price, colors, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (product_name.strip(), online_sku.strip(), offline, size.strip(),
         cost, price, colors.strip(), image_url.strip())
    )
    conn.commit()
    pid = cursor.lastrowid
    conn.close()
    return get_product(pid)


def update_product(product_id: int, product_name: str, online_sku: str, offline_sku: str,
                   size: str, cost: float, price: float, colors: str,
                   image_url: str = "") -> Optional[dict]:
    """更新商品"""
    offline = offline_sku.strip()
    if check_offline_sku_exists(offline, exclude_id=product_id):
        raise DuplicateOfflineSkuError(f"线下SKU「{offline}」已被其他商品使用，不允许重复")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE products
           SET product_name = ?, online_sku = ?, offline_sku = ?, size = ?, cost = ?, price = ?,
               colors = ?, image_url = ?, updated_at = datetime('now','localtime')
           WHERE id = ?""",
        (product_name.strip(), online_sku.strip(), offline, size.strip(),
         cost, price, colors.strip(), image_url.strip(), product_id)
    )
    conn.commit()
    conn.close()
    return get_product(product_id)


def delete_product(product_id: int) -> bool:
    """删除商品"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def clear_all_products() -> int:
    """清空所有商品档案，返回被删除的记录数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    cursor.execute("DELETE FROM products")
    conn.commit()
    conn.close()
    return count


def export_products(search: str = "") -> list[dict]:
    """导出商品列表，根据搜索条件返回全部匹配结果（不分页）"""
    conn = get_connection()
    cursor = conn.cursor()
    where = ""
    params: tuple = ()
    if search:
        where = "WHERE product_name LIKE ? OR online_sku LIKE ? OR offline_sku LIKE ? OR colors LIKE ? OR size LIKE ?"
        like = f"%{search}%"
        params = (like, like, like, like, like)
    cursor.execute(f"SELECT * FROM products {where} ORDER BY id DESC", params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def batch_import(records: list[dict]) -> tuple[int, int, list[dict]]:
    """批量导入：返回 (成功数, 失败数, 失败详情列表)，
    失败详情格式: {"offline_sku": str, "reason": str}"""
    conn = get_connection()
    cursor = conn.cursor()
    success = 0
    fail = 0
    fail_details: list[dict] = []
    seen_sku = set()  # 当前批次内已导入的线下SKU
    for rec in records:
        offline = rec["offline_sku"].strip()
        # 批次内重复检查
        if offline in seen_sku:
            fail += 1
            fail_details.append({"offline_sku": offline, "reason": "本批次内重复"})
            continue
        # 数据库中已存在检查
        cursor.execute("SELECT id FROM products WHERE offline_sku = ?", (offline,))
        if cursor.fetchone():
            fail += 1
            fail_details.append({"offline_sku": offline, "reason": "数据库中已存在"})
            continue
        try:
            cursor.execute(
                """INSERT INTO products (product_name, online_sku, offline_sku, size, cost, price, colors, image_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec.get("product_name", "").strip(), rec["online_sku"].strip(),
                 offline, rec["size"].strip(),
                 float(rec["cost"]), float(rec["price"]),
                 rec.get("colors", "").strip(),
                 rec.get("image_url", "").strip())
            )
            seen_sku.add(offline)
            success += 1
        except Exception as e:
            fail += 1
            fail_details.append({"offline_sku": offline, "reason": f"写入失败: {e}"})
    conn.commit()
    conn.close()
    return success, fail, fail_details


# ── 货款对账 CRUD ──────────────────────────────────────

def match_sku_products(offline_skus: list[str]) -> tuple[dict[str, dict], list[str]]:
    """批量查询线下SKU对应的商品信息。
    返回 (sku→product映射, 未匹配到的SKU列表)"""
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in offline_skus)
    cursor.execute(
        f"SELECT offline_sku, product_name, cost FROM products WHERE offline_sku IN ({placeholders})",
        offline_skus
    )
    rows = cursor.fetchall()
    conn.close()
    found = {r["offline_sku"]: {"product_name": r["product_name"], "cost": r["cost"]} for r in rows}
    not_found = [s for s in offline_skus if s not in found]
    return found, not_found


def create_payment(name: str, payment_date: str, items: list[dict]) -> dict:
    """创建货款记录及明细。items 格式: [{"offline_sku":str, "quantity":float,
    "product_name":str, "cost_price":float, "cost_amount":float}]"""
    total = sum(item["cost_amount"] for item in items)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payment_records (name, payment_date, total_amount, status) VALUES (?, ?, ?, '未结算')",
        (name.strip(), payment_date, total)
    )
    pid = cursor.lastrowid
    for item in items:
        cursor.execute(
            "INSERT INTO payment_items (payment_id, product_name, offline_sku, quantity, cost_price, cost_amount) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, item["product_name"], item["offline_sku"], item["quantity"],
             item["cost_price"], item["cost_amount"])
        )
    conn.commit()
    conn.close()
    return get_payment(pid)


def get_payment(payment_id: int) -> Optional[dict]:
    """获取货款记录及其明细"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payment_records WHERE id = ?", (payment_id,))
    record = cursor.fetchone()
    if not record:
        conn.close()
        return None
    cursor.execute("SELECT * FROM payment_items WHERE payment_id = ? ORDER BY id", (payment_id,))
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()
    result = dict(record)
    result["items"] = items
    return result


def list_payments(search: str = "", page: int = 1, page_size: int = 20) -> dict:
    """分页查询货款列表，支持按名称搜索"""
    conn = get_connection()
    cursor = conn.cursor()
    where = ""
    params: tuple = ()
    if search:
        where = "WHERE name LIKE ?"
        params = (f"%{search}%",)

    count_sql = f"SELECT COUNT(*) FROM payment_records {where}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]

    offset = (page - 1) * page_size
    data_sql = f"SELECT * FROM payment_records {where} ORDER BY id DESC LIMIT ? OFFSET ?"
    cursor.execute(data_sql, params + (page_size, offset))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


class PaymentNotEditableError(Exception):
    """货款状态不允许编辑"""
    pass


def update_payment(payment_id: int, name: str, payment_date: str, items: list[dict]) -> dict:
    """更新货款及明细（仅未结算状态）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM payment_records WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    if row["status"] != "未结算":
        conn.close()
        raise PaymentNotEditableError("已结算的货款不允许编辑")

    total = sum(item["cost_amount"] for item in items)
    cursor.execute(
        "UPDATE payment_records SET name=?, payment_date=?, total_amount=?, updated_at=datetime('now','localtime') WHERE id=?",
        (name.strip(), payment_date, total, payment_id)
    )
    cursor.execute("DELETE FROM payment_items WHERE payment_id = ?", (payment_id,))
    for item in items:
        cursor.execute(
            "INSERT INTO payment_items (payment_id, product_name, offline_sku, quantity, cost_price, cost_amount) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (payment_id, item["product_name"], item["offline_sku"], item["quantity"],
             item["cost_price"], item["cost_amount"])
        )
    conn.commit()
    conn.close()
    return get_payment(payment_id)


def delete_payment(payment_id: int) -> bool:
    """删除货款（仅未结算状态）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM payment_records WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    if row["status"] != "未结算":
        conn.close()
        raise PaymentNotEditableError("已结算的货款不允许删除")
    cursor.execute("DELETE FROM payment_records WHERE id = ?", (payment_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def toggle_payment_status(payment_id: int) -> Optional[dict]:
    """切换货款结算状态（仅用于撤销结算→未结算）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM payment_records WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    new_status = "已结算" if row["status"] == "未结算" else "未结算"
    cursor.execute(
        "UPDATE payment_records SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
        (new_status, payment_id)
    )
    conn.commit()
    conn.close()
    return get_payment(payment_id)


def settle_payment(payment_id: int, other_fee: float, settlement_date: str,
                   settlement_remark: str) -> Optional[dict]:
    """结算货款（写入其他费用、结算日期、备注，状态置为已结算）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM payment_records WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    if row["status"] == "已结算":
        conn.close()
        return None  # 不允许重复结算
    cursor.execute(
        "UPDATE payment_records SET status='已结算', other_fee=?, settlement_date=?, "
        "settlement_remark=?, updated_at=datetime('now','localtime') WHERE id=?",
        (other_fee, settlement_date, settlement_remark, payment_id)
    )
    conn.commit()
    conn.close()
    return get_payment(payment_id)
