import streamlit as st
import requests
import json
import base64
import datetime
import time

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="AI 智能教學工具箱", layout="centered")

APP_TITLE = "🎒 AI 智能教學工具箱"

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    st.markdown(f"<h1 style='text-align: center; color: #4A90E2;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
    st.info("🔒 此工具受保護，請輸入密碼以解鎖並使用。")
    pwd_input = st.text_input("輸入專屬訪問密碼：", type="password")
    if st.button("解鎖 🔓"):
        if pwd_input == "royroy":
            st.session_state['authenticated'] = True
            st.success("✅ 密碼正確！正在載入工具...")
            st.rerun()
        elif pwd_input != "":
            st.error("❌ 密碼錯誤，請重試！")
    st.stop()

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
    """從 GitHub 讀取今日計數器，若跨日自動歸零"""
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    today_str = get_hkt_time().strftime("%Y-%m-%d")
    default_counter = {
        "last_reset_date": today_str,
        "exam_tool": {"main": 0, "backup": 0},
        "dictation_tool": {"main": 0, "backup": 0}
    }
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            counter = json.loads(content)
            sha = data["sha"]
        else:
            counter = default_counter
            sha = None
    except:
        counter = default_counter
        sha = None
        
    # 🌟 00:00 - 23:59 跨日自動重置邏輯
    if counter.get("last_reset_date") != today_str:
        counter["last_reset_date"] = today_str
        counter["exam_tool"] = {"main": 0, "backup": 0}
        counter["dictation_tool"] = {"main": 0, "backup": 0}
        update_github_counter(counter, sha)
        
    return counter

def update_github_counter(counter, sha=None):
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    if not sha:
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                sha = res.json()["sha"]
        except:
            pass
            
    content_str = json.dumps(counter, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": "Auto-reset usage counter [skip ci]",
        "content": content_b64
    }
    if sha:
        payload["sha"] = sha
        
    try:
        res = requests.put(url, headers=headers, json=payload)
        return res.status_code in [200, 201]
    except:
        return False

# 同步讀取雲端計數器
with st.spinner("正在同步 GitHub 雲端配額..."):
    counter = fetch_github_counter()

# ==========================================
# 2. 主標題與提示文字 (原有設計)
# ==========================================
st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🎒 AI 智能教學工具箱</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666; font-size: 18px;'>歡迎使用！請選擇您今天需要使用的教學輔助工具：</p>", unsafe_allow_html=True)

# 顯示即時香港時間監控提示
now_hkt = get_hkt_time()
st.markdown(f"<p style='text-align: center; color: #4A90E2; font-size: 14px; font-weight: bold; margin-bottom: 5px;'>📊 雲端配額監控：{now_hkt.strftime('%Y-%m-%d %H:%M:%S')} (計數週期 00:00 至 23:59)</p>", unsafe_allow_html=True)

st.markdown("<p style='text-align: center; color: #999; font-size: 14px; font-style: italic;'>💡 提示：點擊下方大按鈕即可進入工具，您亦可以隨時使用左側選單快速切換。</p>", unsafe_allow_html=True)
st.write("#")

# ==========================================
# 3. 🎨 原有卡片 CSS 樣式表
# ==========================================
st.markdown("""
<style>
    .my-card-container {
        display: flex;
        gap: 25px;
        justify-content: center;
        flex-wrap: wrap;
        margin-top: 10px;
    }
    .my-card {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        border-radius: 15px;
        padding: 30px 20px;
        width: 260px;
        min-height: 250px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        text-decoration: none !important;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
    }
    .my-card:hover {
        transform: translateY(-6px);
        box-shadow: 0 12px 20px rgba(0,0,0,0.1);
        border-color: #ff4b4b;
        background-color: #ffffff;
    }
    .my-card-emoji {
        font-size: 64px;
        margin-bottom: 15px;
        line-height: 1.2;
    }
    .my-card-title {
        font-size: 22px;
        font-weight: bold;
        color: #212529;
        margin-bottom: 10px;
        transition: color 0.3s ease;
    }
    .my-card:hover .my-card-title {
        color: #ff4b4b;
    }
    .my-card-desc {
        font-size: 14px;
        color: #6c757d;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

# 渲染原有大卡片 (拼接 HTML)
cards_html = (
    '<div class="my-card-container">'
    '<a href="/%E9%BB%98%E6%9B%B8%E5%B7%A5%E5%85%B7" target="_self" class="my-card">'
    '<span class="my-card-emoji">📝</span>'
    '<span class="my-card-title">默書工具</span>'
    '<span class="my-card-desc">智能語音讀默、自動對手寫稿，輕鬆處理學生日常默書。</span>'
    '</a>'
    '<a href="/%E8%80%83%E8%A9%A6%E5%8D%B7%E7%94%9F%E6%88%90%E5%99%A8" target="_self" class="my-card">'
    '<span class="my-card-emoji">📚</span>'
    '<span class="my-card-title">試卷生成器</span>'
    '<span class="my-card-desc">上傳範圍與工作紙，AI 自動生成香港小學風格試卷。</span>'
    '</a>'
    '</div>'
)
st.markdown(cards_html, unsafe_allow_html=True)

# ==========================================
# 4. 📊 實時計數器與進度條區塊 (精緻緊湊排版)
# ==========================================
st.write("##")
MAIN_LIMIT = 20
BACKUP_LIMIT = 40

# 建立左右兩欄，完美對齊上方的大卡片
col_count1, col_count2 = st.columns(2)

with col_count1:
    st.markdown("""
    <div style='text-align: center; font-weight: bold; font-size: 15px; margin-bottom: 8px; color: #212529;'>
        📝 默書工具今日已用通道
    </div>
    """, unsafe_allow_html=True)
    d_main = counter["dictation_tool"]["main"]
    d_backup = counter["dictation_tool"]["backup"]
    
    st.caption(f"🎯 主攻通道 (Flash): {d_main} / {MAIN_LIMIT}")
    st.progress(min(d_main / MAIN_LIMIT, 1.0))
    st.caption(f"🔄 後備通道 (Pro/v3): {d_backup} / {BACKUP_LIMIT}")
    st.progress(min(d_backup / BACKUP_LIMIT, 1.0))

with col_count2:
    st.markdown("""
    <div style='text-align: center; font-weight: bold; font-size: 15px; margin-bottom: 8px; color: #212529;'>
        📚 試卷生成今日已用通道
    </div>
    """, unsafe_allow_html=True)
    e_main = counter["exam_tool"]["main"]
    e_backup = counter["exam_tool"]["backup"]
    
    st.caption(f"🎯 主攻通道 (Flash): {e_main} / {MAIN_LIMIT}")
    st.progress(min(e_main / MAIN_LIMIT, 1.0))
    st.caption(f"🔄 後備通道 (Pro/v3): {e_backup} / {BACKUP_LIMIT}")
    st.progress(min(e_backup / BACKUP_LIMIT, 1.0))

# 底部刷新按鈕
st.write("##")
if st.button("🔄 重新整理 / 同步雲端配額數據", use_container_width=True):
    st.rerun()

st.write("---")
