import streamlit as st

# ==========================================
# 0. 網頁基本設定 (歡迎頁已移除密碼鎖 🔓)
# ==========================================
st.set_page_config(page_title="AI 智能教學工具箱", layout="centered")

APP_TITLE = "🎒 AI 智能教學工具箱"

# ==========================================
# 1. 主標題與提示文字 (原有設計)
# ==========================================
st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🎒 AI 智能教學工具箱</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666; font-size: 18px;'>歡迎使用！請選擇您今天需要使用的教學輔助工具：</p>", unsafe_allow_html=True)

st.markdown("<p style='text-align: center; color: #999; font-size: 14px; font-style: italic;'>💡 提示：點擊下方大按鈕即可進入工具，您亦可以隨時使用左側選單快速切換。</p>", unsafe_allow_html=True)
st.write("#")

# ==========================================
# 2. 🎨 原有卡片 CSS 樣式表
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

st.write("---")
