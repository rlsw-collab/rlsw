import streamlit as st

# 設定網頁標題與排版
st.set_page_config(page_title="AI 智能教學工具箱", layout="centered")

# 主標題
st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🎒 AI 智能教學工具箱</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666; font-size: 18px;'>歡迎使用！請選擇您今天需要使用的教學輔助工具：</p>", unsafe_allow_html=True)
st.write("##")

# 使用 HTML & CSS 製作兩個精美的大圖標卡片
# 這裡利用了 Streamlit 內建的錨點連結，點擊後會直接觸發左邊選單的跳轉
custom_css = """
<style>
    .container {
        display: flex;
        gap: 25px;
        justify-content: center;
        flex-wrap: wrap;
        margin-top: 20px;
    }
    .card {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        border-radius: 15px;
        padding: 30px;
        width: 280px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
        text-decoration: none !important;
        color: #333 !important;
    }
    .card:hover {
        transform: translateY(-8px);
        box-shadow: 0 12px 20px rgba(0,0,0,0.1);
        border-color: #ff4b4b;
        cursor: pointer;
    }
    .icon {
        font-size: 64px;
        margin-bottom: 15px;
    }
    .title {
        font-size: 22px;
        font-weight: bold;
        margin-bottom: 10px;
        color: #212529;
    }
    .desc {
        font-size: 14px;
        color: #6c757d;
        line-height: 1.4;
    }
</style>
"""

# 渲染 CSS 樣式
st.markdown(custom_css, unsafe_allow_html=True)

# 建立大卡片 HTML (注意：href 的名字要跟 pages 裡面的檔名（去掉數字和底線）對應)
# Streamlit 官方支援用 href="/📝_默書工具" 這種方式在多頁面間跳轉
cards_html = """
<div class="container">
    <a href="/📝_默書工具" target="_self" class="card">
        <div class="icon">📝</div>
        <div class="title">默書工具</div>
        <div class="desc">智能語音讀默、自動對手寫稿、標準答案比對，輕鬆處理學生日常默書。</div>
    </a>
    
    <a href="/📚_考試卷生成器" target="_self" class="card">
        <div class="icon">📚</div>
        <div class="title">試卷生成器</div>
        <div class="desc">上傳課本目錄或工作紙，由 Gemini AI 自動生成香港小學本地風格的測驗考試卷連答案。</div>
    </a>
</div>
"""

# 渲染大卡片
st.markdown(cards_html, unsafe_allow_html=True)

st.write("##")
st.write("---")
st.markdown("<p style='text-align: center; color: #aaa; font-size: 12px;'>💡 提示：您亦可以隨時使用左側的選單欄在各個工具之間快速切換。</p>", unsafe_allow_html=True)
