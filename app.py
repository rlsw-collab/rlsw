import streamlit as st

# 設定網頁標題與排版
st.set_page_config(page_title="AI 智能教學工具箱", layout="centered")

# 主標題
st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🎒 AI 智能教學工具箱</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666; font-size: 18px;'>歡迎使用！請選擇您今天需要使用的教學輔助工具：</p>", unsafe_allow_html=True)
st.write("##")

# 提示文字移到大卡片的正上方
st.markdown("<p style='text-align: center; color: #999; font-size: 14px; font-style: italic;'>💡 提示：點擊下方大按鈕即可進入工具，您亦可以隨時使用左側選單快速切換。</p>", unsafe_allow_html=True)
st.write("#")

# 🎨 升級版 CSS：特別把按鈕內的第一行（Emoji）單獨放大！
st.markdown("""
<style>
    /* 讓按鈕變大、加上陰影和圓角 */
    div.stButton > button {
        background-color: #f8f9fa !important;
        border: 2px solid #e9ecef !important;
        border-radius: 15px !important;
        padding: 30px 20px !important;
        width: 100% !important;
        min-height: 220px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
        transition: all 0.3s ease !important;
        
        /* 💡 核心修正：允許按鈕內的文字識別換行，並調整基本字體 */
        white-space: pre-line !important;
        font-size: 16px !important;
        line-height: 1.5 !important;
    }
    
    /* 🚀 終極魔法：將按鈕內的第一個字（即係 Emoji）單獨放大到 64px！ */
    div.stButton > button::first-line {
        font-size: 64px !important;
        line-height: 1.2 !important;
    }
    
    /* 滑鼠游標移上去（Hover）的效果 */
    div.stButton > button:hover {
        transform: translateY(-5px) !important;
        box-shadow: 0 12px 20px rgba(0,0,0,0.1) !important;
        border-color: #ff4b4b !important;
        background-color: #ffffff !important;
    }
    
    /* 點擊時的效果 */
    div.stButton > button:active {
        transform: translateY(-2px) !important;
    }
</style>
""", unsafe_allow_html=True)

# 橫向排列兩個大按鈕
col1, col2 = st.columns(2)

with col1:
    # 📝 默書工具大按鈕 (Emoji 放在第一行，會被 CSS 自動放大)
    btn_dictation = st.button(
        "📝\n\n**默書工具**\n智能語音讀默、自動對手寫稿，輕鬆處理學生日常默書。",
        key="btn_
