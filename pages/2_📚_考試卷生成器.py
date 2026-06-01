import streamlit as st
import google.generativeai as genai
import requests
import json
import base64
import markdown

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 初始化 session_state 來記住登入狀態
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# 如果還未登入，顯示密碼輸入框
if not st.session_state['authenticated']:
    st.title("🔒 考試卷生成工具 (受保護)")
    st.info("請輸入密碼以解鎖並使用此工具。")
    
    # 密碼輸入框 (type="password" 會將輸入的字元變成黑點)
    pwd_input = st.text_input("輸入密碼：", type="password")
    
    if st.button("解鎖 🔓"):
        if pwd_input == "royroy":
            st.session_state['authenticated'] = True
            st.success("✅ 密碼正確！正在載入工具...")
            st.rerun()  # 重新整理網頁，進入下方主程式
        elif pwd_input != "":
            st.error("❌ 密碼錯誤，請重試！")
            
    # st.stop() 非常重要！它會阻止未登入的用戶看到或執行下方的所有代碼
    st.stop()

# ==========================================
# 以下為原本的考試卷生成器代碼 (只有解鎖後才會執行)
# ==========================================
st.title("📚 香港小學測驗/考試卷生成工具")

# ==========================================
# 1. 初始化與安全金鑰設定
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的 Token 憑證，請先進行設定。")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 輔助函式：GitHub API 互動邏輯
# ==========================================
def upload_to_github(path, content, is_bytes=False):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    res = requests.get(url, headers=headers)
    sha = None
    if res.status_code == 200:
        sha = res.json().get("sha")
        
    if is_bytes:
        encoded_content = base64.b64encode(content).decode("utf-8")
    else:
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
    data = {
        "message": f"Upload/Update {path} via Streamlit",
        "content": encoded_content
    }
    if sha:
        data["sha"] = sha
        
    response = requests.put(url, headers=headers, json=data)
    return response.status_code in [200, 201]

def get_file_from_github(path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        file_data = res.json()
        return base64.b64decode(file_data["content"])
    return None

# ==========================================
# 3. Streamlit 網頁介面設計
# ==========================================
if 'generated_exam' not in st.session_state:
    st.session_state['generated_exam'] = ""

# --- 舊包裹載入區塊 ---
st.markdown("### 📂 開啟 / 修改現有包裹")
with st.container():
    col_load1, col_load2 = st.columns([3, 1])
    with col_load1:
        load_package_name = st.text_input("輸入欲讀取的舊包裹名稱：", placeholder="例如：2026_Term1_Math_Ch1-3", label_visibility="collapsed")
    with col_load2:
        btn_load = st.button("🔍 載入包裹資料", use_container_width=True)
        
    if btn_load:
        if load_package_name:
            config_path = f"exam_packages/{load_package_name}/config.json"
            config_bytes = get_file_from_github(config_path)
            if config_bytes:
                config_data = json.loads(config_bytes.decode("utf-8"))
                st.success(f"✅ 成功載入包裹：{load_package_name}")
                st.info(f"原設定科目：{config_data.get('subject')} | 年級：{config_data.get('grade')}")
                st.warning("提示：您可以在下方重新上傳檔案或修改微調文字，儲存時輸入相同名稱即可覆蓋更新。")
            else:
                st.error("❌ 找不到該名稱的包裹，請檢查拼字。")
        else:
            st.error("請輸入包裹名稱")

st.write("---") 

# --- 主畫面其餘布局 ---
st.subheader("📋 基本資料設定")
col1, col2 = st.columns(2)
with col1:
    subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
with col2:
    grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])

st.subheader("🎯 1. 設定考試範圍")
range_files = st.file_uploader("上傳範圍圖片/文件 (可多選)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="range")
range_text = st.text_area("微調範圍 (例如：只考第一至三課、加強應用題等)", placeholder="輸入想讓 AI 特別注意的調整...")

st.subheader("📝 2. 題目類型參考")
style_files = st.file_uploader("上傳工作紙/作業參考 (可多選)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="style")

st.subheader("💾 3. 打包與儲存設定 (GitHub)")
package_name = st.text_input("請輸入這個考試包裹的名稱", placeholder="同名將會覆蓋/更新 GitHub 上的舊資料")

if st.button("📦 儲存並打包資料到 GitHub"):
    if not package_name:
        st.error("❌ 請先輸入包裹名稱才能進行打包儲存！")
    else:
        with st.spinner("正在將文件上傳至 GitHub 倉庫..."):
            base_path = f"exam_packages/{package_name}"
            config_info = {
                "subject": subject,
                "grade": grade,
                "range_text": range_text
            }
            upload_to_github(f"{base_path}/config.json", json.dumps(config_info, ensure_ascii=False, indent=4))
            
            if range_files:
                for f in range_files:
                    upload_to_github(f"{base_path}/range_images/{f.name}", f.getvalue(), is_bytes=True)
            if style_files:
                for f in style_files:
                    upload_to_github(f"{base_path}/style_images/{f.name}", f.getvalue(), is_bytes=True)
            st.success(f"🎉 打包成功！所有資料已安全儲存。")

# --- 核心功能：測驗/考試卷生成 ---
st.subheader("✨ 4. 生成測驗/考試卷")
if st.button("🚀 開始利用 Gemini AI 製作試卷"):
    with st.spinner("AI 正在出題中，請稍候..."):
        contents = []
        system_instruction = f"你是一位熟知香港小學課程與考試制度的資深小學老師。請為【香港小學{grade}】的學生，製作一份符合教育局課程指引且難易度適中的【{subject}】科測驗/考試卷。\n"
        contents.append(system_instruction)
        
        if range_files:
            contents.append("\n【以下是使用者上傳的考試範圍圖片/文件】：\n")
            for f in range_files:
                mime_type = "application/pdf" if f.name.endswith(".pdf") else "image/jpeg"
                contents.append({"mime_type": mime_type, "data": f.getvalue()})
                
        if range_text:
            contents.append(f"\n【使用者特別指定的微調範圍】：\n{range_text}\n")
            
        if style_files:
            contents.append("\n【以下是使用者希望參考的題型圖片】：\n")
            for f in style_files:
                mime_type = "application/pdf" if f.name.endswith(".pdf") else "image/jpeg"
                contents.append({"mime_type": mime_type, "data": f.getvalue()})
                
        core_prompt = """
        🎯 【出題任務與排版要求】：
        請結合上方所有提供的資料，製作一份最符合香港本地小學風格的專業試卷。
        
        試卷必須嚴格分為以下兩個部分，並在中間使用 `---` 分割線分開：
        1. 【試卷正文】：包含虛構校名、學生個人資料欄、總分、限時。題目要有題號、分數。題型要多元化並符合該年級水準。若需要圖表，請用文字描述或留下提示格。
        2. 【答案頁 (Answer Key)】：緊接在 `---` 之後，列出標準答案及簡短算式或評分標準。
        請使用清晰的 Markdown 格式輸出。
        """
        contents.append(core_prompt)
        
        try:
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(contents)
            st.session_state['generated_exam'] = response.text
        except Exception as e:
            st.error(f"❌ Gemini API 呼叫失敗: {str(e)}")

# --- 試卷預覽與打印 ---
if st.session_state['generated_exam']:
    st.success("🎉 試卷與答案生成成功！")
    tab1, tab2 = st.tabs(["📺 網頁預覽與導出儲存", "🖨️ 專業打印預覽"])
    
    with tab1:
        st.markdown(st.session_state['generated_exam'])
        st.write("---")
        if st.button("📝 儲存試卷文本 (exam.md) 到 GitHub"):
            if not package_name:
                st.error("❌ 請先輸入包裹名稱！")
            else:
                exam_path = f"exam_packages/{package_name}/exam.md"
                if upload_to_github(exam_path, st.session_state['generated_exam']):
                    st.success(f"✅ 試卷成功儲存至 GitHub！")
                else:
                    st.error("❌ 儲存失敗。")
                    
    with tab2:
        html_exam_content = markdown.markdown(st.session_state['generated_exam'])
        html_for_printing = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            .print-control-bar {{ background-color: #f0f2f6; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-family: sans-serif; }}
            .print-btn {{ background-color: #ff4b4b; color: white; border: none; padding: 10px 20px; font-size: 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }}
            #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", Arial, sans-serif; line-height: 1.6; color: #000000; padding: 10px; }}
            @media print {{
                .print-control-bar {{ display: none; }}
                body {{ background-color: white; }}
                hr {{ page-break-after: always; border: none; visibility: hidden; }}
            }}
        </style>
        </head>
        <body>
            <div class="print-control-bar">
                <button class="print-btn" onclick="window.print()">🖨️ 立即打印 / 匯出 PDF</button>
            </div>
            <div id="exam-body">{html_exam_content}</div>
        </body>
        </html>
        """
        import streamlit.components.v1 as components
        components.html(html_for_printing, height=900, scroller=True)
