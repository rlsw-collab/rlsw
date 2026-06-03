import streamlit as st
import requests
import json
import base64
import datetime
import time

# ==========================================
# 0. 網頁基本設定 (歡迎頁已移除密碼鎖 🔓)
# ==========================================
st.set_page_config(page_title="AI 智能教學工具箱", layout="centered")

APP_TITLE = "🎒 AI 智能教學工具箱"

# ==========================================
# 1. 讀取 Secrets 設定與計數器引擎
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GIT_TOKEN"]
    GITHUB_REPO = st.secrets.get("GITHUB_REPO", "rlsw")
    GITHUB_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到 GitHub 憑證 (GIT_TOKEN)。")
    st.stop()

def get_hkt_time():
    """獲取當前香港時間 (UTC+8)"""
    tz_hkt = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_hkt)

def fetch_github_counter():
    """從 GitHub 讀取今日計數器，若跨日自動歸零 (全新扁平化架構)"""
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    today_str = get_hkt_time().strftime("%Y-%m-%d")
    default_counter = {
        "last_reset_date": today_str
    }
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            counter = json.loads(content)
            
            # 跨日檢查：如果 JSON 紀錄的日期不是今天，全盤重置歸零
            if counter.get("last_reset_date") != today_str:
                return default_counter
            return counter
        else:
            return default_counter
    except Exception:
        return default_counter

# 載入當前即時配額數據
counter = fetch_github_counter()

# ==========================================
# 2. 標題與橫幅
# ==========================================
st.title(APP_TITLE)
st.markdown(f"歡迎使用 AI 智能教學工具箱！本系統為香港中小學教師量身打造。當前伺服器時間 (香港)：`{get_hkt_time().strftime('%Y-%m-%d %H:%M:%S')}`")

# ==========================================
# 3. 功能導航大卡片 (精緻 CSS 樣式)
# ==========================================
st.write("---")
cards_html = (
    '<div style="display: block; margin-bottom: 20px;">'
    '  <a href="/默書工具" target="_self" style="text-decoration: none; display: block; background-color: #E0F2FE; border: 1px solid #7DD3FC; border-radius: 12px; padding: 20px; margin-bottom: 15px; transition: transform 0.2s; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">'
    '    <h3 style="margin: 0 0 8px 0; color: #0369A1; font-size: 18px;">📝 智能默書語音生成與批改工具</h3>'
    '    <span style="color: #0c4a6e; font-size: 14px;">上傳默書範圍課文圖片或直接輸入文本，一鍵自動分句、校對、導出多語音雙語(中/英)小學標準朗讀音頻及課堂配套。</span>'
    '  </a>'
    '  <a href="/考試卷生成器" target="_self" style="text-decoration: none; display: block; background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 12px; padding: 20px; transition: transform 0.2s; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">'
    '    <h3 style="margin: 0 0 8px 0; color: #15803D; font-size: 18px;">📚 香港小學測驗/考試卷生成器</h3>'
    '    <span style="color: #14532d; font-size: 14px;">根據教育局指引與香港小學主流教材，智能生成包含閱讀理解、語文基礎、平面幾何等完全符合專業排版的小學風格試卷。</span>'
    '  </a>'
    '</div>'
)
st.markdown(cards_html, unsafe_allow_html=True)

# ==========================================
# 4. 📊 實時計數器與進度條區塊 (全新動態自動感應排版)
# ==========================================
st.write("##")
st.markdown("""
<div style='text-align: center; font-weight: bold; font-size: 18px; margin-bottom: 15px; color: #1E3A8A;'>
    📊 各 AI 模型今日調用次數統計 (香港時間)
</div>
""", unsafe_allow_html=True)

# 預設各模型的每日上限控制（可在此自由擴充）
MODEL_LIMITS = {
    "gemini-2.5-flash": 30,
    "gemini-2.5-pro": 15,
    "gpt-4o": 20
}
DEFAULT_LIMIT = 25

# 過濾掉日期欄位，只留下真實模型數據
model_counts = {k: v for k, v in counter.items() if k != "last_reset_date"}

if not model_counts:
    st.info("💡 今日暫時未有 AI 模型調用記錄。開始使用工具後將在此實時顯示。")
else:
    # 採用雙欄排版展示各模型進度
    cols = st.columns(2)
    for idx, (model_name, count) in enumerate(model_counts.items()):
        col = cols[idx % 2]
        with col:
            limit = MODEL_LIMITS.get(model_name, DEFAULT_LIMIT)
            progress_val = min(count / limit, 1.0) if limit > 0 else 0.0
            
            # 模型精美動態卡片
            st.markdown(f"""
            <div style='background-color: #F8FAFC; padding: 10px; border-radius: 8px; border-left: 4px solid #3B82F6; margin-bottom: 5px; margin-top: 10px;'>
                <span style='font-weight: bold; color: #1E293B;'>🤖 {model_name}</span>
            </div>
            """, unsafe_allow_html=True)
            st.caption(f"今日已調用: {count} / {limit} 次")
            st.progress(progress_val)

# 底部全局手動刷新按鈕
st.write("##")
if st.button("🔄 重新整理 / 同步雲端配額數據", use_container_width=True):
    st.rerun()

st.write("---")
