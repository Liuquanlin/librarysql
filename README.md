# librarysql
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import database as db

# ─────────────────────────────────────────────
# 頁面設定
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="ABDS 書籍匿名討論系統",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# 自訂 CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* 整體背景 */
.main { background-color: #f8f9fa; }

/* 卡片樣式 */
.book-card {
    background: white;
    border-radius: 12px;
    padding: 16px;
    margin: 8px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    border-left: 4px solid #2e7d5e;
}
.review-card {
    background: white;
    border-radius: 10px;
    padding: 14px;
    margin: 6px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    border-left: 3px solid #4a9d7a;
}
.stat-card {
    background: linear-gradient(135deg, #2e7d5e, #4a9d7a);
    color: white;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.anon-badge {
    background: #e8f5e9;
    color: #2e7d5e;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.85em;
    font-weight: bold;
}
.real-badge {
    background: #e3f2fd;
    color: #1565c0;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.85em;
    font-weight: bold;
}
.admin-badge {
    background: #fce4ec;
    color: #c62828;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.85em;
    font-weight: bold;
}
/* 星星評分顯示 */
.stars { color: #f4a261; font-size: 1.1em; }
/* 標題樣式 */
.page-title {
    color: #2e7d5e;
    font-size: 1.8em;
    font-weight: bold;
    margin-bottom: 0.5em;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Session State 初始化
# ─────────────────────────────────────────────
def init_session():
    defaults = {
        "logged_in": False,
        "user": None,
        "page": "home",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─────────────────────────────────────────────
# 工具函式
# ─────────────────────────────────────────────
def stars(rating: float) -> str:
    full = int(rating)
    half = 1 if (rating - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + "½" * half + "☆" * empty


def format_date(dt_str: str) -> str:
    if not dt_str:
        return "—"
    return dt_str[:10]


def show_success(msg): st.success(f"✅ {msg}")
def show_error(msg):   st.error(f"❌ {msg}")
def show_info(msg):    st.info(f"ℹ️ {msg}")
def show_warning(msg): st.warning(f"⚠️ {msg}")


# ─────────────────────────────────────────────
# 側邊欄導航
# ─────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## 📚 ABDS")
        st.markdown("**書籍匿名討論系統**")
        st.divider()

        if st.session_state.logged_in:
            user = st.session_state.user
            role_badge = "🔴 管理員" if user["role"] == "admin" else "🟢 學生"
            st.markdown(f"**已登入：** {user['username']}")
            st.markdown(f"**身份：** {role_badge}")
            st.markdown(f"**匿名代號：** `{user['anonymous_alias']}`")
            st.divider()

            # 導航選單
            pages = {
                "🏠 首頁": "home",
                "📖 書籍瀏覽": "books",
                "✍️ 發表書評": "write_review",
                "❤️ 我的書評": "my_reviews",
                "📋 借閱管理": "borrow",
                "🎯 個人化推薦": "recommend",
                "👤 個人資料": "profile",
            }
            if user["role"] == "admin":
                pages["🔧 管理後台"] = "admin"

            for label, page_key in pages.items():
                if st.button(label, use_container_width=True,
                             type="primary" if st.session_state.page == page_key else "secondary"):
                    st.session_state.page = page_key
                    st.rerun()

            st.divider()
            if st.button("🚪 登出", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.user = None
                st.session_state.page = "home"
                st.rerun()
        else:
            if st.button("🔑 登入 / 註冊", use_container_width=True, type="primary"):
                st.session_state.page = "auth"
                st.rerun()
            if st.button("🏠 首頁", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
            if st.button("📖 書籍瀏覽", use_container_width=True):
                st.session_state.page = "books"
                st.rerun()

        st.divider()
        st.caption("© 2024 ABDS | 資料庫管理系統專題")


# ─────────────────────────────────────────────
# 頁面：首頁
# ─────────────────────────────────────────────
def page_home():
    db.update_overdue_status()
    stats = db.get_stats()
    popular = db.get_popular_books(6)

    st.markdown('<div class="page-title">📚 書籍匿名討論系統 ABDS</div>', unsafe_allow_html=True)
    st.markdown("*前台匿名、後台可追蹤的圖書館書評社群平台*")
    st.divider()

    # 統計卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📚 館藏書籍", stats["total_books"])
    with col2:
        st.metric("👥 註冊使用者", stats["total_users"])
    with col3:
        st.metric("✍️ 書評總數", stats["total_reviews"])
    with col4:
        st.metric("📋 借閱中", stats["active_borrows"])

    st.divider()

    # 熱門書籍
    st.subheader("🔥 熱門書籍推薦")
    if popular:
        cols = st.columns(3)
        for i, book in enumerate(popular):
            with cols[i % 3]:
                with st.container():
                    st.markdown(f"""
<div class="book-card">
  <strong>{book['title']}</strong><br>
  <small>✍️ {book['author']} | 🏷️ {book['category']}</small><br>
  <span class="stars">{stars(book['avg_rating'])}</span>
  <small> {book['avg_rating']:.1f}</small>
</div>
""", unsafe_allow_html=True)
    else:
        show_info("目前尚無書籍資料")

    st.divider()

    # 系統說明
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🔒 匿名機制說明")
        st.markdown("""
本系統採用「**前台匿名、後台可追蹤**」設計：

- 發表書評時可選擇以**匿名代號**顯示，保護個人隱私
- 後台資料庫保留完整使用者身份，供管理員必要時查詢
- 每位使用者擁有獨一無二的匿名代號（如：`讀者_A3K7M`）
        """)
    with col_b:
        st.subheader("✨ 系統功能")
        st.markdown("""
- 📖 **書籍瀏覽**：搜尋館藏、查看書籍詳情
- ✍️ **匿名書評**：發表評論、給予 1-5 星評分
- ❤️ **按讚互動**：對優質書評表示認同
- 📋 **借閱管理**：借書、還書、查看歷史
- 🎯 **個人化推薦**：基於協同過濾的書單推薦
        """)


# ─────────────────────────────────────────────
# 頁面：登入 / 註冊
# ─────────────────────────────────────────────
def page_auth():
    st.markdown('<div class="page-title">🔑 登入 / 註冊</div>', unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊"])

    with tab_login:
        st.subheader("使用學號登入")
        with st.form("login_form"):
            username = st.text_input("學號", placeholder="例：S11001001")
            password = st.text_input("密碼", type="password")
            submitted = st.form_submit_button("登入", use_container_width=True, type="primary")

        if submitted:
            if not username or not password:
                show_error("請填寫學號與密碼")
            else:
                result = db.login_user(username, password)
                if result["ok"]:
                    st.session_state.logged_in = True
                    st.session_state.user = result["user"]
                    st.session_state.page = "home"
                    show_success(f"歡迎回來，{result['user']['real_name']}！")
                    st.rerun()
                else:
                    show_error(result["msg"])

        st.divider()
        st.caption("示範帳號：學號 `S11001001`，密碼 `pass1234`")
        st.caption("管理員帳號：學號 `admin001`，密碼 `admin1234`")

    with tab_register:
        st.subheader("以學號註冊新帳號")
        with st.form("register_form"):
            col1, col2 = st.columns(2)
            with col1:
                reg_username = st.text_input("學號 *", placeholder="例：S11001006")
                reg_name = st.text_input("真實姓名 *", placeholder="例：王小明")
            with col2:
                reg_email = st.text_input("電子郵件 *", placeholder="例：s11001006@student.edu.tw")
                reg_alias = st.text_input("自訂匿名代號（可留空自動產生）",
                                          placeholder="例：神秘讀者_X")
            reg_password = st.text_input("密碼 *", type="password", placeholder="至少 6 個字元")
            reg_password2 = st.text_input("確認密碼 *", type="password")
            reg_submit = st.form_submit_button("立即註冊", use_container_width=True, type="primary")

        if reg_submit:
            if not all([reg_username, reg_name, reg_email, reg_password]):
                show_error("請填寫所有必填欄位（標有 * 者）")
            elif len(reg_password) < 6:
                show_error("密碼至少需要 6 個字元")
            elif reg_password != reg_password2:
                show_error("兩次密碼輸入不一致")
            else:
                alias = reg_alias.strip() if reg_alias.strip() else None
                result = db.register_user(
                    username=reg_username.strip(),
                    password=reg_password,
                    real_name=reg_name.strip(),
                    email=reg_email.strip(),
                    anonymous_alias=alias
                )
                if result["ok"]:
                    show_success(f"註冊成功！請使用學號 {reg_username} 登入")
                    st.balloons()
                else:
                    show_error(result["msg"])


# ─────────────────────────────────────────────
# 頁面：書籍瀏覽
# ─────────────────────────────────────────────
def page_books():
    st.markdown('<div class="page-title">📖 書籍瀏覽</div>', unsafe_allow_html=True)

    # 搜尋列
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        keyword = st.text_input("🔍 搜尋書名、作者或 ISBN", placeholder="輸入關鍵字...")
    with col2:
        categories = ["全部"] + db.get_categories()
        category = st.selectbox("分類篩選", categories)
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        search_btn = st.button("搜尋", use_container_width=True, type="primary")

    # 取得書籍列表
    cat_filter = "" if category == "全部" else category
    books = db.search_books(keyword=keyword, category=cat_filter)

    st.markdown(f"**共找到 {len(books)} 本書籍**")
    st.divider()

    if not books:
        show_info("找不到符合條件的書籍")
        return

    # 書籍列表
    for book in books:
        with st.expander(
            f"📗 [{book['book_id']}] {book['title']} — {book['author']} "
            f"| {stars(book['avg_rating'])} {book['avg_rating']:.1f} "
            f"| 可借：{book['available_copies']}/{book['total_copies']}"
        ):
            col_info, col_action = st.columns([3, 1])
            with col_info:
                st.markdown(f"**書籍編號：** `{book['book_id']}`")
                st.markdown(f"**ISBN：** {book['isbn'] or '—'}")
                st.markdown(f"**出版社：** {book['publisher']}")
                st.markdown(f"**分類：** {book['category']}")
                if book["description"]:
                    st.markdown(f"**簡介：** {book['description']}")
                st.markdown(f"**平均評分：** {stars(book['avg_rating'])} **{book['avg_rating']:.1f}** / 5.0")
                st.markdown(f"**館藏狀態：** 可借 {book['available_copies']} / 共 {book['total_copies']} 本")

            with col_action:
                if st.session_state.logged_in:
                    if st.button(f"✍️ 評論此書", key=f"review_btn_{book['book_id']}"):
                        st.session_state["review_target_book_id"] = book["book_id"]
                        st.session_state["review_target_book_title"] = book["title"]
                        st.session_state.page = "write_review"
                        st.rerun()
                    if book["available_copies"] > 0:
                        if st.button(f"📋 借閱", key=f"borrow_btn_{book['book_id']}"):
                            result = db.borrow_book(
                                st.session_state.user["user_id"], book["book_id"]
                            )
                            if result["ok"]:
                                show_success(f"借閱成功！應還日期：{result['due_date']}")
                                st.rerun()
                            else:
                                show_error(result["msg"])
                    else:
                        st.button("❌ 無庫存", disabled=True, key=f"no_stock_{book['book_id']}")

            # 顯示書評
            reviews = db.get_reviews_by_book(book["book_id"])
            if reviews:
                st.markdown(f"**📝 書評（{len(reviews)} 則）**")
                for rev in reviews[:3]:
                    liked_set = db.get_user_liked_reviews(
                        st.session_state.user["user_id"]
                    ) if st.session_state.logged_in else set()
                    is_liked = rev["review_id"] in liked_set
                    like_icon = "❤️" if is_liked else "🤍"

                    st.markdown(f"""
<div class="review-card">
  <span class="{'anon-badge' if rev['is_anonymous'] else 'real-badge'}">
    {'🎭 ' + rev['display_name'] if rev['is_anonymous'] else '👤 ' + rev['display_name']}
  </span>
  &nbsp; <span class="stars">{stars(rev['rating'])}</span> {rev['rating']} 星
  &nbsp; <small>{format_date(rev['updated_at'])}</small><br>
  <p style="margin:6px 0">{rev['content']}</p>
  <small>{like_icon} {rev['like_count']} 人按讚</small>
</div>
""", unsafe_allow_html=True)

                    if st.session_state.logged_in and rev["user_id"] != st.session_state.user["user_id"]:
                        if st.button(
                            f"{'取消讚' if is_liked else '👍 按讚'}",
                            key=f"like_{rev['review_id']}_{book['book_id']}"
                        ):
                            result = db.toggle_like(
                                st.session_state.user["user_id"], rev["review_id"]
                            )
                            if result["ok"]:
                                st.rerun()

                if len(reviews) > 3:
                    st.caption(f"還有 {len(reviews)-3} 則書評，請前往書評頁面查看")


# ─────────────────────────────────────────────
# 頁面：發表書評
# ─────────────────────────────────────────────
def page_write_review():
    if not st.session_state.logged_in:
        show_warning("請先登入才能發表書評")
        if st.button("前往登入"):
            st.session_state.page = "auth"
            st.rerun()
        return

    st.markdown('<div class="page-title">✍️ 發表書評</div>', unsafe_allow_html=True)
    st.markdown("*輸入書籍編號，若書籍不在館藏中將自動新增*")
    st.divider()

    user = st.session_state.user

    # 預填書籍 ID（從書籍頁面跳轉過來時）
    default_book_id = st.session_state.get("review_target_book_id", "")
    default_book_title = st.session_state.get("review_target_book_title", "")

    with st.form("review_form"):
        st.subheader("📚 書籍資訊")

        col1, col2 = st.columns([1, 2])
        with col1:
            book_id_input = st.text_input(
                "書籍編號 *",
                value=str(default_book_id) if default_book_id else "",
                placeholder="輸入書籍編號（如：1、2、3...）"
            )
        with col2:
            book_title_input = st.text_input(
                "書名（若書籍不存在，將以此名稱新增）",
                value=default_book_title,
                placeholder="例：資料庫系統概論"
            )

        # 查詢書籍資訊
        book_info_placeholder = st.empty()

        st.subheader("✍️ 評論內容")
        rating = st.slider("評分 ★", min_value=1, max_value=5, value=4,
                           help="1 = 很差，5 = 非常好")
        st.markdown(f"您的評分：{stars(rating)} **{rating} 星**")

        content = st.text_area(
            "評論內容 *",
            placeholder="分享您對這本書的看法、心得或建議...",
            height=150
        )

        col_anon, col_submit = st.columns([2, 1])
        with col_anon:
            is_anonymous = st.checkbox(
                "🎭 以匿名代號發表",
                value=True,
                help=f"勾選後將以「{user['anonymous_alias']}」顯示，不勾選則顯示真實姓名「{user['real_name']}」"
            )
            if is_anonymous:
                st.caption(f"將以匿名代號顯示：`{user['anonymous_alias']}`")
            else:
                st.caption(f"將以真實姓名顯示：`{user['real_name']}`")

        submitted = st.form_submit_button("📤 發表書評", use_container_width=True, type="primary")

    if submitted:
        # 驗證輸入
        if not book_id_input.strip():
            show_error("請輸入書籍編號")
            return
        if not content.strip():
            show_error("評論內容不能為空")
            return

        # 解析書籍編號
        try:
            book_id = int(book_id_input.strip())
        except ValueError:
            show_error("書籍編號必須為數字")
            return

        # 確保書籍存在（若不存在則自動新增）
        title = book_title_input.strip() if book_title_input.strip() else None
        ensure_result = db.ensure_book_exists(book_id=book_id, title=title)

        if not ensure_result["ok"]:
            show_error("無法確認書籍資訊，請稍後再試")
            return

        actual_book_id = ensure_result["book_id"]
        if ensure_result["created"]:
            show_info(f"書籍編號 {book_id} 不存在，已自動新增書籍：「{title or f'書籍 #{book_id}'}」")

        # 發表書評（UPSERT）
        result = db.upsert_review(
            user_id=user["user_id"],
            book_id=actual_book_id,
            rating=rating,
            content=content,
            is_anonymous=is_anonymous
        )

        if result["ok"]:
            action_msg = "書評已更新！" if result["action"] == "update" else "書評發表成功！"
            show_success(action_msg)
            # 清除預填資料
            if "review_target_book_id" in st.session_state:
                del st.session_state["review_target_book_id"]
            if "review_target_book_title" in st.session_state:
                del st.session_state["review_target_book_title"]
            st.balloons()
        else:
            show_error(result["msg"])

    # 顯示書籍資訊預覽
    if book_id_input and book_id_input.strip().isdigit():
        book = db.get_book_by_id(int(book_id_input.strip()))
        if book:
            st.divider()
            st.subheader("📗 書籍資訊預覽")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**書名：** {book['title']}")
                st.markdown(f"**作者：** {book['author']}")
                st.markdown(f"**分類：** {book['category']}")
            with col2:
                st.markdown(f"**出版社：** {book['publisher']}")
                st.markdown(f"**平均評分：** {stars(book['avg_rating'])} {book['avg_rating']:.1f}")
                st.markdown(f"**館藏：** {book['available_copies']}/{book['total_copies']}")
        else:
            st.divider()
            show_info(f"書籍編號 {book_id_input} 尚未在館藏中，發表後將自動新增。")


# ─────────────────────────────────────────────
# 頁面：我的書評
# ─────────────────────────────────────────────
def page_my_reviews():
    if not st.session_state.logged_in:
        show_warning("請先登入")
        return

    user = st.session_state.user
    st.markdown('<div class="page-title">❤️ 我的書評</div>', unsafe_allow_html=True)

    reviews = db.get_reviews_by_user(user["user_id"])

    if not reviews:
        show_info("您尚未發表任何書評，快去分享您的閱讀心得吧！")
        if st.button("✍️ 發表第一則書評"):
            st.session_state.page = "write_review"
            st.rerun()
        return

    st.markdown(f"**您共發表了 {len(reviews)} 則書評**")
    st.divider()

    for rev in reviews:
        anon_display = f"🎭 匿名（{user['anonymous_alias']}）" if rev["is_anonymous"] else f"👤 具名（{user['real_name']}）"
        with st.expander(
            f"📗 {rev['title']} — {stars(rev['rating'])} {rev['rating']} 星 | {anon_display} | {format_date(rev['updated_at'])}"
        ):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**書名：** {rev['title']} (作者：{rev['author']})")
                st.markdown(f"**評分：** {stars(rev['rating'])} **{rev['rating']} 星**")
                st.markdown(f"**評論：** {rev['content']}")
                st.markdown(f"**按讚數：** ❤️ {rev['like_count']}")
                st.markdown(f"**發表時間：** {format_date(rev['created_at'])} | **更新：** {format_date(rev['updated_at'])}")
                st.markdown(f"**顯示方式：** {anon_display}")

            with col2:
                if st.button("✏️ 修改書評", key=f"edit_{rev['review_id']}"):
                    st.session_state["review_target_book_id"] = rev["book_id"]
                    st.session_state["review_target_book_title"] = rev["title"]
                    st.session_state.page = "write_review"
                    st.rerun()

                if st.button("🗑️ 刪除", key=f"del_{rev['review_id']}", type="secondary"):
                    result = db.delete_review(rev["review_id"], user["user_id"])
                    if result["ok"]:
                        show_success("書評已刪除")
                        st.rerun()
                    else:
                        show_error(result["msg"])


# ─────────────────────────────────────────────
# 頁面：借閱管理
# ─────────────────────────────────────────────
def page_borrow():
    if not st.session_state.logged_in:
        show_warning("請先登入")
        return

    user = st.session_state.user
    db.update_overdue_status()
    st.markdown('<div class="page-title">📋 借閱管理</div>', unsafe_allow_html=True)

    tab_current, tab_history, tab_borrow = st.tabs(["📌 目前借閱", "📜 借閱歷史", "📚 借閱書籍"])

    with tab_current:
        history = db.get_borrow_history(user["user_id"])
        active = [h for h in history if h["status"] == "borrowed"]
        overdue = [h for h in history if h["status"] == "overdue"]

        if overdue:
            show_warning(f"您有 {len(overdue)} 本書籍已逾期，請盡快歸還！")

        if not active and not overdue:
            show_info("目前沒有借閱中的書籍")
        else:
            for record in active + overdue:
                status_icon = "⚠️ 逾期" if record["status"] == "overdue" else "📌 借閱中"
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"""
**{record['title']}** — {record['author']}
- 借閱日期：{format_date(record['borrow_date'])}
- 應還日期：{format_date(record['due_date'])} {status_icon}
""")
                    with col2:
                        if st.button("✅ 歸還", key=f"return_{record['borrow_id']}",
                                     type="primary"):
                            result = db.return_book(
                                record["borrow_id"], user["user_id"]
                            )
                            if result["ok"]:
                                show_success("歸還成功！")
                                st.rerun()
                            else:
                                show_error(result["msg"])
                    st.divider()

    with tab_history:
        history = db.get_borrow_history(user["user_id"])
        returned = [h for h in history if h["status"] == "returned"]
        if not returned:
            show_info("尚無歸還紀錄")
        else:
            for record in returned:
                st.markdown(f"""
- 📗 **{record['title']}** | 借閱：{format_date(record['borrow_date'])} → 歸還：{format_date(record['return_date'])}
""")

    with tab_borrow:
        st.subheader("借閱新書籍")
        with st.form("borrow_form"):
            borrow_book_id = st.number_input("書籍編號", min_value=1, step=1)
            borrow_days = st.selectbox("借閱天數", [7, 14, 21, 30], index=1)
            borrow_submit = st.form_submit_button("📋 確認借閱", type="primary")

        if borrow_submit:
            result = db.borrow_book(user["user_id"], int(borrow_book_id), borrow_days)
            if result["ok"]:
                show_success(f"借閱成功！應還日期：{result['due_date']}")
                st.rerun()
            else:
                show_error(result["msg"])

        # 顯示可借閱書籍
        st.subheader("📚 可借閱書籍")
        all_books = db.get_all_books()
        available_books = [b for b in all_books if b["available_copies"] > 0]
        if available_books:
            for book in available_books[:10]:
                st.markdown(
                    f"- `[{book['book_id']}]` **{book['title']}** — {book['author']} "
                    f"| 可借：{book['available_copies']} 本"
                )
        else:
            show_info("目前無可借閱書籍")


# ─────────────────────────────────────────────
# 頁面：個人化推薦
# ─────────────────────────────────────────────
def page_recommend():
    if not st.session_state.logged_in:
        show_warning("請先登入以獲得個人化推薦")
        return

    user = st.session_state.user
    st.markdown('<div class="page-title">🎯 個人化推薦</div>', unsafe_allow_html=True)

    # 取得使用者評分數量
    user_reviews = db.get_reviews_by_user(user["user_id"])
    review_count = len(user_reviews)

    if review_count < 3:
        st.info(f"ℹ️ 您目前有 {review_count} 則書評（需至少 3 則才能啟用個人化推薦）。以下為熱門書籍推薦：")
        mode = "熱門推薦"
    else:
        st.success(f"✅ 您已有 {review_count} 則書評，已啟用個人化協同過濾推薦！")
        mode = "個人化推薦（User-Based CF）"

    st.markdown(f"**推薦模式：** {mode}")
    st.divider()

    recommendations = db.get_cf_recommendations(user["user_id"], limit=8)

    if not recommendations:
        show_info("目前無推薦書籍，請先瀏覽並評論更多書籍")
        return

    cols = st.columns(2)
    for i, book in enumerate(recommendations):
        with cols[i % 2]:
            st.markdown(f"""
<div class="book-card">
  <strong>[{book['book_id']}] {book['title']}</strong><br>
  <small>✍️ {book['author']} | 🏷️ {book['category']}</small><br>
  <span class="stars">{stars(book['avg_rating'])}</span>
  <small> {book['avg_rating']:.1f} / 5.0</small><br>
  <small>📚 可借：{book['available_copies']}/{book['total_copies']} 本</small>
</div>
""", unsafe_allow_html=True)
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✍️ 評論", key=f"rec_review_{book['book_id']}_{i}"):
                    st.session_state["review_target_book_id"] = book["book_id"]
                    st.session_state["review_target_book_title"] = book["title"]
                    st.session_state.page = "write_review"
                    st.rerun()
            with col_b:
                if book["available_copies"] > 0:
                    if st.button("📋 借閱", key=f"rec_borrow_{book['book_id']}_{i}"):
                        result = db.borrow_book(user["user_id"], book["book_id"])
                        if result["ok"]:
                            show_success(f"借閱成功！應還：{result['due_date']}")
                            st.rerun()
                        else:
                            show_error(result["msg"])


# ─────────────────────────────────────────────
# 頁面：個人資料
# ─────────────────────────────────────────────
def page_profile():
    if not st.session_state.logged_in:
        show_warning("請先登入")
        return

    user = st.session_state.user
    st.markdown('<div class="page-title">👤 個人資料</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("基本資料")
        st.markdown(f"**學號：** `{user['username']}`")
        st.markdown(f"**真實姓名：** {user['real_name']}")
        st.markdown(f"**電子郵件：** {user['email']}")
        st.markdown(f"**匿名代號：** `{user['anonymous_alias']}`")
        st.markdown(f"**身份：** {'🔴 管理員' if user['role'] == 'admin' else '🟢 學生'}")
        st.markdown(f"**加入時間：** {format_date(user['created_at'])}")

    with col2:
        st.subheader("活動統計")
        reviews = db.get_reviews_by_user(user["user_id"])
        history = db.get_borrow_history(user["user_id"])
        liked = db.get_user_liked_reviews(user["user_id"])

        st.metric("✍️ 發表書評", len(reviews))
        st.metric("📋 借閱紀錄", len(history))
        st.metric("❤️ 按讚次數", len(liked))

    st.divider()
    st.subheader("🔒 匿名機制說明")
    st.markdown(f"""
您的匿名代號為 **`{user['anonymous_alias']}`**。

當您選擇匿名發表書評時，其他使用者只會看到此代號，**不會看到您的真實姓名或學號**。
管理員在必要情況下（如違規處理）可查詢匿名代號對應的真實身份。
    """)


# ─────────────────────────────────────────────
# 頁面：管理後台
# ─────────────────────────────────────────────
def page_admin():
    if not st.session_state.logged_in:
        show_warning("請先登入")
        return
    if st.session_state.user["role"] != "admin":
        show_error("您沒有管理員權限")
        return

    st.markdown('<div class="page-title">🔧 管理後台</div>', unsafe_allow_html=True)
    st.markdown('<span class="admin-badge">🔴 管理員專區</span>', unsafe_allow_html=True)
    st.divider()

    tab_stats, tab_users, tab_reviews, tab_books, tab_add_book = st.tabs([
        "📊 系統統計", "👥 使用者管理", "📝 書評管理", "📚 書籍管理", "➕ 新增書籍"
    ])

    with tab_stats:
        stats = db.get_stats()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👥 使用者總數", stats["total_users"])
            st.metric("📚 書籍總數", stats["total_books"])
        with col2:
            st.metric("✍️ 書評總數", stats["total_reviews"])
            st.metric("❤️ 按讚總數", stats["total_likes"])
        with col3:
            st.metric("📋 借閱總數", stats["total_borrows"])
            st.metric("📌 借閱中", stats["active_borrows"])

    with tab_users:
        st.subheader("所有使用者（含真實身份）")
        users = db.get_all_users()
        if users:
            import pandas as pd
            df = pd.DataFrame(users)
            df.columns = ["ID", "學號", "真實姓名", "電子郵件", "匿名代號", "身份", "加入時間"]
            st.dataframe(df, use_container_width=True)
        else:
            show_info("尚無使用者資料")

    with tab_reviews:
        st.subheader("所有書評（含真實身份）")
        reviews = db.get_all_reviews_admin()
        if reviews:
            import pandas as pd
            df = pd.DataFrame(reviews)
            display_cols = ["review_id", "book_title", "real_name", "anonymous_alias",
                            "rating", "content", "is_anonymous", "like_count", "updated_at"]
            df_display = df[display_cols].copy()
            df_display.columns = ["ID", "書名", "真實姓名", "匿名代號",
                                   "評分", "內容", "匿名", "按讚數", "更新時間"]
            df_display["匿名"] = df_display["匿名"].map({1: "是", 0: "否"})
            st.dataframe(df_display, use_container_width=True)
        else:
            show_info("尚無書評資料")

    with tab_books:
        st.subheader("所有書籍")
        books = db.get_all_books()
        if books:
            import pandas as pd
            df = pd.DataFrame(books)
            display_cols = ["book_id", "title", "author", "category",
                            "avg_rating", "available_copies", "total_copies", "isbn"]
            df_display = df[display_cols].copy()
            df_display.columns = ["ID", "書名", "作者", "分類",
                                   "平均評分", "可借閱", "總館藏", "ISBN"]
            st.dataframe(df_display, use_container_width=True)
        else:
            show_info("尚無書籍資料")

    with tab_add_book:
        st.subheader("新增書籍到館藏")
        with st.form("admin_add_book"):
            col1, col2 = st.columns(2)
            with col1:
                a_title = st.text_input("書名 *")
                a_author = st.text_input("作者", value="未知")
                a_publisher = st.text_input("出版社", value="未知")
                a_isbn = st.text_input("ISBN（可留空）")
            with col2:
                a_category = st.selectbox("分類", ["資訊科學", "程式語言", "歷史", "自我成長",
                                                   "心理學", "文學", "科學", "商業", "一般"])
                a_copies = st.number_input("館藏數量", min_value=1, value=1)
                a_desc = st.text_area("書籍簡介", height=100)
            add_submit = st.form_submit_button("➕ 新增書籍", type="primary")

        if add_submit:
            if not a_title:
                show_error("書名為必填")
            else:
                result = db.add_book(
                    title=a_title, author=a_author, publisher=a_publisher,
                    category=a_category, isbn=a_isbn if a_isbn else None,
                    description=a_desc, total_copies=a_copies
                )
                if result["ok"]:
                    show_success(f"書籍新增成功！書籍編號：{result['book_id']}")
                    st.rerun()
                else:
                    show_error(result["msg"])


# ─────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────
def main():
    # 初始化資料庫
    db.init_db()
    db.seed_demo_data()

    # 初始化 Session State
    init_session()

    # 渲染側邊欄
    render_sidebar()

    # 路由
    page = st.session_state.page
    if page == "home":
        page_home()
    elif page == "auth":
        page_auth()
    elif page == "books":
        page_books()
    elif page == "write_review":
        page_write_review()
    elif page == "my_reviews":
        page_my_reviews()
    elif page == "borrow":
        page_borrow()
    elif page == "recommend":
        page_recommend()
    elif page == "profile":
        page_profile()
    elif page == "admin":
        page_admin()
    else:
        page_home()


if __name__ == "__main__":
    main()
