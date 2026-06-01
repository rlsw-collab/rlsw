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

# 🎨 終極魔法 CSS (直接由 CSS 產生巨型 Emoji)
st.markdown("""
<style>
    /* 1. 確保左右兩邊的 column 高度一致 */
    [data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
    }

    /* 2. 重塑 Streamlit 原生按鈕的外觀 */
    div.stButton > button {
        background-color: #f8f9fa !important;
        border: 2px solid #e9ecef !important;
        border-radius: 15px !important;
        padding: 30px 20px !important;
        width: 100% !important;
        height: 100% !important; 
        min-height: 250px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
        transition: all 0.3s ease !important;
        white-space: pre-line !important;
        text-align: center !important;
    }
    
    /* 清除 Streamlit 內部 p 標籤的干擾 */
    div.stButton > button p {
        font-size: 14px !important;
        color: #6c757d !important;
        line-height: 1.6 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* 🚀 3. 終極魔法：左邊卡片強制注入 64px 的 📝 */
    [data-testid="column"]:nth-of-type(1) div.stButton > button p::before {
        content: "📝";
        font-size: 64px !important;
        display: block !important;
        margin-bottom: 10px !important;
        line-height: 1.2 !important;
    }
    
    /* 🚀 4. 終極魔法：右邊卡片強制注入 64px 的 📚 */
    [data-testid="column"]:nth-of-type(2) div.stButton > button p::before {
        content: "📚";
        font-size: 64px !important;
        display: block !important;
        margin-bottom: 10px !important;
        line-height: 1.2 !important;
    }

    /* 5. 標題樣式 */
    div.stButton > button strong {
        font-size: 22px !important;
        color: #212529 !important;
        display: block !important;
        margin-top: 5px !important;
        margin-bottom: 10px !important;
    }
    
    /* 6. 介紹文字樣式 */
    div.stButton > button em {
        font-size: 14px !important;
        color: #6c757d !important;
        font-style: normal !important;
        display: block !important;
    }

    /* 7. Hover 懸停特效 */
    div.stButton > button:hover {
        transform: translateY(-6px) !important;
        box-shadow: 0 12px 20px rgba(0,0,0,0.1) !important;
        border-color: #ff4b4b !important;
        background-color: #ffffff !important;
    }
    div.stButton > button:hover strong {
        color: #ff4b4b !important; 
    }
    div.stButton > button:active {
        transform: translateY(-2px) !important;
    }
</style>
""", unsafe_allow_html=True)

# 橫向排列兩個大按鈕
col1, col2 = st.columns(2)

with col1:
    # 📝 注意：Python 這裡的文字【已經刪除了 Emoji】，交由上方 CSS 自動生成巨大版！
    btn_text_1 = """**默書工具**
_智能語音讀默、自動對手寫稿，輕鬆處理學生日常默書。_"""
    
    if st.button(btn_text_1, key="btn_dict_final", use_container_width=True):
        st.switch_page("pages/1_📝_默書工具.py")

with col2:
    # 📚 注意：Python 這裡的文字【已經刪除了 Emoji】，交由上方 CSS 自動生成巨大版！
    btn_text_2 = """**試卷生成器**
_上傳範圍與工作紙，AI 自動生成香港小學風格試卷。_"""
    
    if st.button(btn_text_2, key="btn_exam_final", use_container_width=True):
        st.switch_page("pages/2_📚_考試卷生成器.py")

st.write("##")
st.write("---")
