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

# 🎨 終極改良版 CSS
st.markdown("""
<style>
    /* 1. 基礎卡片樣式設定 */
    div.stButton > button {
        background-color: #f8f9fa !important;
        border: 2px solid #e9ecef !important;
        border-radius: 15px !important;
        padding: 25px 20px !important;
        width: 100% !important;
        min-height: 240px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
        transition: all 0.3s ease !important;
        
        /* 允許多行顯示，並設定介紹文字的大小 */
        white-space: pre-line !important;
        color: #6c757d !important;
        font-size: 14px !important;
        line-height: 1.6 !important;
    }
    
    /* 🚀 2. 核心修正：直接定位 Streamlit 按鈕裡面的文字容器，將整體結構與開頭放大 */
    div.stButton > button p {
        font-size: 14px !important;
        color: #6c757d !important;
    }
    
    /* 🌟 3. 神奇魔法：直接把按鈕裡面的巨大標題跟 Emoji 分開處理 */
    .big-emoji {
        font-size: 55px !important;
        display: block;
        margin-bottom: 10px;
        line-height: 1.2 !important;
    }
    .big-title {
        font-size: 22px !important;
        font-weight: bold !important;
        color: #212529 !important;
        display: block;
        margin-bottom: 8px;
    }
    
    /* 4. 滑鼠移上去的效果 */
    div.stButton > button:hover {
        transform: translateY(-5px) !important;
        box-shadow: 0 12px 20px rgba(0,0,0,0.1) !important;
        border-color: #ff4b4b !important;
        background-color: #ffffff !important;
    }
    div.stButton > button:hover .big-title {
        color: #ff4b4b !important; /* 移上去時標題變紅 */
    }
</style>
""", unsafe_allow_html=True)

# 橫向排列兩個大按鈕
col1, col2 = st.columns(2)

with col1:
    # 📝 默書工具 (我們在文字裡面直接嵌入 HTML Span 標籤，這樣 100% 能由 CSS 控制放大！)
    btn_text_1 = """<span class="big-emoji">📝</span><span class="big-title">默書工具</span>智能語音讀默、自動對手寫稿，輕鬆處理學生日常默書。"""
    
    btn_dictation = st.button(btn_text_1, key="btn_dict", use_container_width=True)
    if btn_dictation:
        st.switch_page("pages/1_📝_默書工具.py")

with col2:
    # 📚 試卷生成器
    btn_text_2 = """<span class="big-emoji">📚</span><span class="big-title">試卷生成器</span>上傳範圍與工作紙，AI 自動生成香港小學風格試卷。"""
    
    btn_exam = st.button(btn_text_2, key="btn_exam", use_container_width=True)
    if btn_exam:
        st.switch_page("pages/2_📚_考試卷生成器.py")

st.write("##")
st.write("---")
