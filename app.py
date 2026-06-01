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

# 🎨 核心隱形按鈕與卡片美化 CSS
st.markdown("""
<style>
    /* 1. 定義底層 HTML 卡片的樣式 */
    .custom-container {
        display: flex;
        gap: 25px;
        justify-content: center;
        flex-wrap: wrap;
        position: relative;
    }
    .custom-card {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        border-radius: 15px;
        padding: 30px 20px;
        width: 260px;
        min-height: 240px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
        pointer-events: none; /* 讓滑鼠事件穿透到上層的隱形按鈕 */
    }
    
    /* 2. 定義上層 Streamlit 原生按鈕「整容兼隱形」 */
    div.stButton {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 10;
    }
    div.stButton > button {
        background: transparent !important;
        border: none !important;
        color: transparent !important; /* 文字變透明 */
        width: 100% !important;
        height: 100% !important;
        min-height: 260px !important;
        box-shadow: none !important;
        cursor: pointer !important;
    }
    
    /* 3. 當滑鼠懸停在整個欄位區塊時，連動底層卡片產生特效 */
    .column-wrapper {
        position: relative;
        width: 100%;
        min-height: 260px;
    }
    .column-wrapper:hover .custom-card {
        transform: translateY(-8px);
        box-shadow: 0 12px 20px rgba(0,0,0,0.1);
        border-color: #ff4b4b;
        background-color: #ffffff;
    }
    .column-wrapper:hover .card-title {
        color: #ff4b4b;
    }
    
    /* 4. 內文精細字體控制 */
    .card-emoji {
        font-size: 64px !important; /* 👈 真正的大 Emoji 尺寸！ */
        display: block;
        margin-bottom: 15px;
    }
    .card-title {
        font-size: 22px !important;
        font-weight: bold !important;
        color: #212529;
        display: block;
        margin-bottom: 10px;
        transition: color 0.3s ease;
    }
    .card-desc {
        font-size: 14px;
        color: #6c757d;
        line-height: 1.5;
        display: block;
    }
</style>
""", unsafe_allow_html=True)

# 橫向分開兩欄
col1, col2 = st.columns(2)

with col1:
    # 使用一個容器把 HTML 卡片和隱形按鈕疊在一起
    st.markdown("""
    <div class="column-wrapper">
        <div class="custom-card">
            <span class="card-emoji">📝</span>
            <span class="card-title">默書工具</span>
            <span class="card-desc">智能語音讀默、自動對手寫稿，輕鬆處理學生日常默書。</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 這個按鈕會因為上面的 CSS 變得完全透明，但撐滿整張卡片
    if st.button("go_dictation", key="hidden_dict", use_container_width=True):
        st.switch_page("pages/1_📝_默書工具.py")

with col2:
    st.markdown("""
    <div class="column-wrapper">
        <div class="custom-card">
            <span class="card-emoji">📚</span>
            <span class="card-title">試卷生成器</span>
            <span class="card-desc">上傳範圍與工作紙，AI 自動生成香港小學風格試卷。</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 這個按鈕也會變得完全透明，但撐滿整張卡片
    if st.button("go_exam", key="hidden_exam", use_container_width=True):
        st.switch_page("pages/2_📚_考試卷生成器.py")

st.write("##")
st.write("---")
