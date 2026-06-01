import streamlit as st
import google.generativeai as genai
import requests
import json
import base64
import markdown
import uuid

# ==========================================
# 1. 初始化與安全金鑰設定 (從 Streamlit Secrets 讀取)
# ==========================================
# 請確保你在 Streamlit Community Cloud 的 Settings -> Secrets 裡設定了以下變數：
# GITHUB_TOKEN = "你的_github_token"
# GITHUB_REPO = "你的帳號/你的儲存庫名稱"
# GEMINI_API_KEY = "你的_gemini_api_key"

try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的 Token 憑證，請先進行設定。")
    st.stop()

# 初始化 Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 輔助函式：GitHub API 互動邏輯
# ==========================================
def upload_to_github(path, content, is_bytes=False):
    """將檔案上傳或更新到 GitHub 儲存庫"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 先檢查檔案是否已存在，若存在需要獲取 sha 才能更新
    res = requests.get(url, headers=headers)
    sha = None
    if res.status_code == 200:
        sha = res.json().get("sha")
        
    # 編碼內容
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
    """從 GitHub 讀取檔案內容"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        file_data = res.json()
        return base64.b64decode(file_data["content"])
    return None

def list_files_in_github_dir(dir_path):
    """列出 GitHub 某個資料夾下的所有檔案"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{dir_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json()  # 回傳檔案列表資訊
    return []

# ==========================================
# 3. Streamlit 網頁介面設計
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")
st.title("📚 香港小學測驗/考試卷生成工具")

# 初始化 Session State 用於儲存生成的試卷
if 'generated_exam' not in st.session_state:
    st.session_state['generated_exam'] = ""

# --- 側邊欄：讀取舊包裹功能 ---
with st.sidebar:
    st.header("📂 開啟/修改現有包裹")
    load_package_name = st.text_input("輸入欲讀取的包裹名稱：")
    if st.button("🔍 載入包裹資料"):
        if load_package_name:
            config_path = f"exam_packages/{load_package_name}/config.json"
            config_bytes = get_file_from_github(config_path)
            if config_bytes:
                config_data = json.loads(config_bytes.decode("utf-8"))
                st.success(f"✅ 成功載入包裹：{load_package_name}")
                st.info(f"原設定科目：{config_data.get('subject')} | 年級：{config_data.get('grade')}")
                st.warning("提示：您可以在右側重新上傳檔案或修改微調文字，儲存時輸入相同名稱即可覆蓋更新。")
            else:
                st.error("❌ 找不到該名稱的包裹，請檢查拼字。")
        else:
            st.error("請輸入包裹名稱")

# --- 主畫面布局 ---
# 區塊 1：基本資料選擇
st.subheader("📋 基本資料設定")
col1, col2 = st.columns(2)
with col1:
    subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
with col2:
    grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])

# 區塊 2：考試範圍設定
st.subheader("🎯 1. 設定考試範圍")
range_files = st.file_uploader("上傳範圍圖片/文件 (可多選，支援目錄、範圍紙、A4相片)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="range")
range_text = st.text_area("微調範圍 (例如：只考第一至三課、加強應用題、不考標點符號等)", placeholder="輸入想讓 AI 特別注意的調整...")

# 區塊 3：題目類型參考
st.subheader("📝 2. 題目類型參考")
style_files = st.file_uploader("上傳工作紙/作業參考 (可多選，讓 AI 參考題型格式)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="style")

# 區塊 4：打包與存檔設定
st.subheader("💾 3. 打包與儲存設定 (GitHub)")
package_name = st.text_input("請輸入這個考試包裹的名稱 (例如：2026_Term1_Math_Ch1-3)", placeholder="同名將會覆蓋/更新 GitHub 上的舊資料")

if st.button("📦 儲存並打包資料到 GitHub"):
    if not package_name:
        st.error("❌ 請先輸入包裹名稱才能進行打包儲存！")
    else:
        with st.spinner("正在將文件上傳至 GitHub 倉庫..."):
            base_path = f"exam_packages/{package_name}"
            
            # 1. 儲存文字與基本設定為 JSON
            config_info = {
                "subject": subject,
                "grade": grade,
                "range_text": range_text
            }
            upload_to_github(f"{base_path}/config.json", json.dumps(config_info, ensure_ascii=False, indent=4))
            
            # 2. 上傳範圍圖片/文件
            if range_files:
                for f in range_files:
                    upload_to_github(f"{base_path}/range_images/{f.name}", f.getvalue(), is_bytes=True)
                    
            # 3. 上傳題型參考圖片/文件
            if style_files:
                for f in style_files:
                    upload_to_github(f"{base_path}/style_images/{f.name}", f.getvalue(), is_bytes=True)
                    
            st.success(f"🎉 打包成功！所有資料已安全儲存於 GitHub 目錄: `exam_packages/{package_name}/`。您可以隨時在側邊欄輸入此名稱重新載入與修改。")

# ==========================================
# 4. 核心功能：測驗/考試卷生成 (Gemini API)
# ==========================================
st.subheader("✨ 4. 生成測驗/考試卷")
if st.button("🚀 開始利用 Gemini AI 製作試卷"):
    with st.spinner("AI 正在仔細審閱您提供的範圍與工作紙，並撰寫試卷中，請稍候（約需 15-30 秒）..."):
        
        # 建立傳給 Gemini 的內容清單
        contents = []
        
        # 注入系統核心 Prompt 角色設定
        system_instruction = f"你是一位熟知香港小學課程與考試制度的資深小學老師。請為【香港小學{grade}】的學生，製作一份符合教育局課程指引且難易度適中的【{subject}】科測驗/考試卷。\n"
        contents.append(system_instruction)
        
        # 讀取並注入範圍檔案 (Multimodal 處理)
        if range_files:
            contents.append("\n【以下是使用者上傳的考試範圍/教科書目錄圖片或文件資料】：\n")
            for f in range_files:
                file_bytes = f.getvalue()
                # 簡單判斷 mime_type
                mime_type = "application/pdf" if f.name.endswith(".pdf") else "image/jpeg"
                contents.append({
                    "mime_type": mime_type,
                    "data": file_bytes
                })
                
        if range_text:
            contents.append(f"\n【使用者特別指定的微調範圍與注意事項】：\n{range_text}\n")
            
        # 讀取並注入題型參考檔案
        if style_files:
            contents.append("\n【以下是使用者希望參考的題目類型、排版格式或工作紙範例圖片】：\n")
            for f in style_files:
                file_bytes = f.getvalue()
                mime_type = "application/pdf" if f.name.endswith(".pdf") else "image/jpeg"
                contents.append({
                    "mime_type": mime_type,
                    "data": file_bytes
                })
                
        # 核心出題指令 Prompt
        core_prompt = """
        🎯 【出題任務與排版要求】：
        請結合上方所有提供的範圍資料、微調文字以及題型參考圖片，製作一份最符合香港本地小學風格的專業試卷。
        
        試卷必須嚴格分為以下兩個部分，並在中間使用 `---` 分割線分開：
        
        1. 【試卷正文】：
           - 頂部必須包含校名橫幅（請虛構一個得體的校名，例如：香港仁愛小學）、學生姓名欄、班別欄、學號欄、總分（如 50 分 或 100 分）、限時（如 45 分鐘）。
           - 題目設計必須包含清晰的題號、每題的分數（例如：每題 2 分，共 10 分）。
           - 題型必須多元化。例如：中文科（看拼音寫詞語、改錯字、選詞填空、閱讀理解）；數學科（直接計算、文字應用題、列式計算）；常識科（選擇題、填充題、連線題、短答題）。請務必多參考用戶提供的題型相片。
           - 難易度必須完全符合該年級香港小學生的水準。
           - 若題目需要圖表（如數學的幾何圖形或統計圖），請在題目中用文字清楚描述，或者留下醒目的提示格（例如：[請在此處畫出一個底 6 厘米、高 4 厘米的直角三角形]），方便老師印出後補圖。
        
        2. 【答案頁 (Answer Key)】：
           - 必須緊接在試卷正文的 `---` 分割線之後。
           - 清晰、對齊地列出每道題目的標準答案。
           - 對於數學應用題、常識思考題等較複雜的題目，必須提供簡短的解題步驟、算式或評分標準（例如：列式對給1分，答案對給1分）。

        請使用清晰的 Markdown 格式（利用 #, ##, ### 等標題標籤）輸出，不要包含任何多餘的解釋文字，直接輸出試卷與答案內容。
        """
        contents.append(core_prompt)
        
        try:
            # 呼叫 Gemini 1.5 Pro（看圖及理解複雜指令能力最強）
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(contents)
            
            # 將結果記錄到 Session State
            st.session_state['generated_exam'] = response.text
        except Exception as e:
            st.error(f"❌ Gemini API 呼叫失敗，錯誤訊息: {str(e)}")

# ==========================================
# 5. 試卷預覽、儲存至 GitHub 與 HTML 高清打印功能
# ==========================================
if st.session_state['generated_exam']:
    st.success("🎉 試卷與答案生成成功！")
    
    # 建立分頁標籤：一頁看網頁預覽，一頁供排版打印
    tab1, tab2 = st.tabs(["📺 網頁預覽與導出儲存", "🖨️ 專業打印預覽 (支援另存 PDF)"])
    
    with tab1:
        st.markdown("### 📋 試卷內容草稿")
        st.markdown(st.session_state['generated_exam'])
        
        st.write("---")
        st.subheader("💾 將這份生成的試卷文字儲存回當前 GitHub 包裹")
        if st.button("📝 儲存試卷文本 (exam.md) 到 GitHub"):
            if not package_name:
                st.error("❌ 請先在上方輸入包裹名稱才能進行儲存！")
            else:
                exam_path = f"exam_packages/{package_name}/exam.md"
                success = upload_to_github(exam_path, st.session_state['generated_exam'])
                if success:
                    st.success(f"✅ 試卷成功儲存至 GitHub 路徑: `{exam_path}`！")
                else:
                    st.error("❌ 儲存失敗，請檢查 GitHub Token 與網路連線。")
                    
    with tab2:
        st.write("💡 **打印提示：** 點擊下方的「立即打印 / 匯出 PDF」按鈕，將會喚起瀏覽器的打印視窗。在目的地中選擇**「另存為 PDF (Save as PDF)」**即可完美匯出。我們已經設定了自動分頁，答案頁會自動推到新的一頁，不會與試卷擠在一起。")
        
        # 將 Markdown 轉換成 HTML
        html_exam_content = markdown.markdown(st.session_state['generated_exam'])
        
        # 封裝具備 A4 打印優化 CSS 的 HTML 程式碼
        html_for_printing = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            /* 網頁上看到的控制列樣式 */
            .print-control-bar {{
                background-color: #f0f2f6;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-family: sans-serif;
            }}
            .print-btn {{
                background-color: #ff4b4b;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
                cursor: pointer;
            }}
            .print-btn:hover {{
                background-color: #e04141;
            }}
            
            #exam-body {{
                font-family: "Microsoft JhengHei", "微軟正黑體", Arial, sans-serif;
                line-height: 1.6;
                color: #000000;
                padding: 10px;
            }}
            
            /* 針對系統打印 [@media print] 的專業設定 */
            @media print {{
                .print-control-bar {{
                    display: none; /* 打印時隱藏按鈕列 */
                }}
                body {{
                    background-color: white;
                }}
                #exam-body {{
                    padding: 0;
                }}
                /* 讓 Gemini 生成的 <hr> 變成強制換頁符號，切開試卷與答案 */
                hr {{
                    page-break-after: always;
                    border: none;
                    visibility: hidden;
                }}
            }}
        </style>
        </head>
        <body>
            <div class="print-control-bar">
                <button class="print-btn" onclick="window.print()">🖨️ 立即打印 / 匯出 PDF</button>
                <span style="margin-left: 15px; color: #555;">(點擊後可自由調整邊距、紙張大小)</span>
            </div>
            <div id="exam-body">
                {html_exam_content}
            </div>
        </body>
        </html>
        """
        
        # 透過 Streamlit Component 將 HTML 渲染出來
        import streamlit.components.v1 as components
        components.html(html_for_printing, height=900, scroller=True)
