import streamlit as st
import streamlit.components.v1 as components

# 設定網頁標題與排版
st.set_page_config(page_title="AI 智能教學工具箱", layout="centered")

# 主標題
st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🎒 AI 智能教學工具箱</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666; font-size: 18px;'>歡迎使用！請選擇您今天需要使用的教學輔助工具：</p>", unsafe_allow_html=True)
st.write("##")

# 將所有的 CSS 同 HTML 封裝成一個純網頁字串
all_html_content = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: transparent;
    }
    .container {
        display: flex;
        gap: 25px;
        justify-content: center;
        flex-wrap: wrap;
        padding: 10px;
    }
    .card {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        border-radius: 15px;
        padding: 30px;
        width: 260px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
        text-decoration: none !important;
        color: #333 !important;
        display: block;
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
</head>
<body>

<div class="container">
    <a href="/%E9%BB%98%E6%9B%B8%E5%B7%A5%E5%85%B7" target="_parent" class="card">
        <div class="icon">📝</div>
        <div class="title">默書工具</div>
        <div class="desc">智能語音讀默、自動對手寫稿、標準答案比對，輕鬆處理學生日常默書。</div>
    </a>
    
    <a href="/%E8%80%83%E8%A9%A6%E5%8D%B7%E7%94%9F%E6%88%90%E5%99%A8" target="_parent" class="card">
        <div class="icon">📚</div>
        <div class="title">試卷生成器</div>
        <div class="desc">上傳課本目錄或工作紙，由 Gemini AI 自動生成香港小學本地風格的測驗考試卷連答案。</div>
    </a>
</div>

</body>
</html>
"""

components.html(all_html_content, height=420, scrolling=False)

st.write("##")
st.write("---")
st.markdown("<p style='text-align: center; color: #aaa; font-size: 12px;'>💡 提示：您亦可以隨時使用左側的選單欄在各個工具之間快速切換。</p>", unsafe_allow_html=True)
