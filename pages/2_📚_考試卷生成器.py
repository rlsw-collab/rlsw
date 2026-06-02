import streamlit as st
import requests
import json
import base64
import markdown
import time
import re
from PIL import Image

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 定義統一的標題與版本號碼 (升級至 v1.0.8)
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.0.8"

# 初始化 session_state 來記住登入狀態
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    st.title(APP_TITLE)
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
# 主程式 (只有解鎖後才會執行)
# ==========================================
st.title(APP_TITLE)

# ==========================================
# 1. 安全金鑰設定
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GIT_TOKEN"]
    GEMINI_TOKEN = st.secrets["GEMINI_TOKEN"]
    GITHUB_REPO = "rlsw"
    GITHUB_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的憑證 (GIT_TOKEN 或 GEMINI_TOKEN)，請先檢查密碼箱。")
    st.stop()

# ==========================================
# 2. 輔助函式：GitHub API 互動邏輯
# ==========================================
def upload_to_github(path, content, is_bytes=False):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
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
        "content": encoded_content,
        "branch": "main"
    }
    if sha:
        data["sha"] = sha
        
    response = requests.put(url, headers=headers, json=data)
    return response.status_code in [200, 201]

def get_file_from_github(path):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        file_data = res.json()
        return base64.b64decode(file_data["content"])
    return None

# 🚀 🚀 核心黑科技：用 Python 自動將傳統的 3/5 或 2 1/4 渲染成漂亮的「真·上下直式分數」
def convert_to_vertical_fractions(html_content):
    # 1. 先處理帶分數 格式如: 2 1/4 或 2(1/4) -> 2<span class="frac"><sup>1</sup><sub>4</sub></span>
    html_content = re.sub(
        r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?',
        r'\1<span class="v-frac"><sup>\2</sup><sub>\3</sub></span>',
        html_content
    )
    # 2. 再處理普通分數 格式如: 3/5 -> <span class="v-frac"><sup>3</sup><sub>5</sub></span>
    # 排除掉網頁標籤入面的斜線 (如 </div> 或 <br/>)
    html_content = re.sub(
        r'(?<!/)(?<!<)(?<!\d)(\d+)/(\d+)(?!\d)(?!>)',
        r'<span class="v-frac"><sup>\1</sup><sub>\2</sub></span>',
        html_content
    )
    return html_content

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
            else:
                st.error("❌ 找不到該名稱的包裹，請檢查拼字。")

st.write("---") 

# --- 基本資料設定 ---
st.subheader("📋 基本資料設定")
col1, col2 = st.columns(2)
with col1:
    subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
with col2:
    grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])

# --- 1. 設定考試範圍與縮圖預覽 ---
st.subheader("🎯 1. 設定考試範圍")
range_files = st.file_uploader("上傳範圍圖片/文件 (可多選)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="range")

if range_files:
    img_files = [f for f in range_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
    if img_files:
        st.markdown("📸 **已上傳的範圍圖片預覽：**")
        cols = st.columns(min(len(img_files), 6))
        for idx, f in enumerate(img_files):
            with cols[idx % 6]:
                try:
                    img = Image.open(f)
                    st.image(img, caption=f.name if len(f.name) < 15 else f.name[:12]+"...", use_container_width=True)
                except:
                    pass

range_text = st.text_area("微調範圍 (例如：只考第一至三課、加強應用題等)", placeholder="輸入想讓 AI 特別注意的調整...")

# --- 2. 題目類型參考與縮圖預覽 ---
st.subheader("📝 2. 題目類型參考")
style_files = st.file_uploader("上傳工作紙/作業參考 (可多選)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key="style")

if style_files:
    style_img_files = [f for f in style_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
    if style_img_files:
        st.markdown("📸 **已上傳的題型參考圖片預覽：**")
        cols_style = st.columns(min(len(style_img_files), 6))
        for idx, f in enumerate(style_img_files):
            with cols_style[idx % 6]:
                try:
                    img = Image.open(f)
                    st.image(img, caption=f.name if len(f.name) < 15 else f.name[:12]+"...", use_container_width=True)
                except:
                    pass

# --- 3. 打包與儲存設定 ---
st.subheader("💾 3. 打包與儲存設定 (GitHub)")
package_name = st.text_input("請輸入這個考試包裹的名稱", placeholder="同名將會覆蓋/更新 GitHub 上的舊資料")

if st.button("📦 儲存並打包資料到 GitHub"):
    if not package_name:
        st.error("❌ 請先輸入包裹名稱才能進行打包儲存！")
    else:
        with st.spinner("正在將文件上傳至 GitHub 倉庫..."):
            base_path = f"exam_packages/{package_name}"
            config_info = {"subject": subject, "grade": grade, "range_text": range_text}
            upload_to_github(f"{base_path}/config.json", json.dumps(config_info, ensure_ascii=False, indent=4))
            st.success(f"🎉 打包成功！所有資料已 safe 儲存。")

# ==========================================
# 4. 核心功能：【智慧自動重試】直連 2.5 Flash
# ==========================================
st.subheader("✨ 4. 生成測驗/考試卷")
if st.button("🚀 開始利用 Gemini AI 製作試卷"):
    with st.spinner("🚀 智能排版大腦正在為您構思香港小學風格試卷，請稍候..."):
        
        # 建立簡化、方便 Python 在前端攔截與轉化直式分數的 Prompt
        prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格與考試制度的資深小學老師。
請為【香港小學{grade}】的學生，製作一份符合教育局課程指引且難易度適中的【{subject}】科測驗/考試卷。

根據香港小學的真實排版要求，出的題型必須符合以下【全新修訂版：答題線與排版命令】：

⚠️【1. 數學分數與符號格式命令】：
- 🚫 絕對禁止使用任何 LaTeX 數學格式，禁止出現任何 `$` 符號、`\\frac` 等學術程式碼。
- 🗣️ 為了方便後台處理，分數請直接用最簡單的純文字格式輸出：
  * 普通分數格式：分子/分母，例如：3/5、13/3。
  * 帶分數格式：整數 空格 分子/分母，例如：2 1/4、5 1/4。
  * 乘號請用「x」，除號請用「÷」。

⚠️【2. 填充題與計算題的答題線縮短 2/3 命令】：
- 【填充題】：空格答題線請統一縮減為 6 個底線 `______`。
- 【計算題 / 簡答題】：每道計算題下面請空出適當的手寫白位，並在題目的正下方或右側尾端提供一條和填充題一樣長度的短答案線 `______` 供填寫最終答案。

⚠️【3. 多項選擇題 (MC) 命令】：
- 題目自成一行。
- A、B、C、D 四個選項必須在問題的下方，且每一個選項必須獨立換行！
- 每個選項前加上一個空心圓圈 `○`。在每個選項的結尾，請加上 `<br>` 標籤。

⚠️【4. 列式計算應用題 - 換行與答題橫線命令】：
- 應用題題目文字結束後，必須立刻強制換行。
- 【第一條答題線】必須直接出現在題目的正下方！
- 題目下方不需要出現「列式：」和「答：」等文字，請直接提供 4 條長長的空白橫線。
  格式規範（題目下一行立刻開始）：
  ______________________________________________________<br>
  ______________________________________________________<br>
  ______________________________________________________<br>
  ______________________________________________________<br>

⚠️【5. 題型分流限制】：
- 🚫【找錯處 (Proofreading)】題型：這是【英文】科的專屬題型！當前科目是【{subject}】。如果目前不是英文科，絕對不要生成任何找錯處題型！

【試卷整體結構要求】：
試卷必須嚴格分為【試卷正文】與【答案頁 (Answer Key)】，中間使用 `---` 分割線分開。
"""
        if range_text:
            prompt_text += f"\n【使用者特別指定的微調範圍與重點】：\n{range_text}\n"
            
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_TOKEN}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
        
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                res = requests.post(api_url, headers=headers, json=payload)
                if res.status_code == 200:
                    res_json = res.json()
                    ai_result = res_json['candidates'][0]['content']['parts'][0]['text']
                    st.session_state['generated_exam'] = ai_result
                    success = True
                    break
                elif res.status_code == 503 and attempt < max_retries - 1:
                    st.warning(f"⚠️ 伺服器目前較為繁忙（503），正在進行第 {attempt + 1} 次自動重新連線...")
                    time.sleep(3)
                else:
                    st.error(f"❌ Gemini 2.5 Flash 伺服器拒絕請求 (錯誤代碼 {res.status_code}): {res.text}")
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    st.error(f"❌ 聯絡 Gemini 伺服器失敗: {str(e)}")
                    break
                    
        if success:
            st.rerun()

# --- 試卷預覽與打印 ---
if st.session_state['generated_exam']:
    st.success("🎉 試卷與答案生成成功！")
    tab1, tab2 = st.tabs(["📺 網頁預覽與導出儲存", "🖨️ 專業打印預覽"])
    
    # 進行 Python 的「直式分數過濾轉化」
    raw_markdown_content = st.session_state['generated_exam']
    html_raw_content = markdown.markdown(raw_markdown_content)
    
    # 🚀 在前端透過 Python Regex 暴力轉化真·直式分數
    perfect_html_content = convert_to_vertical_fractions(html_raw_content)
    
    with tab1:
        # 在前端完美渲染
        st.markdown(perfect_html_content, unsafe_allow_html=True)
        st.write("---")
        if st.button("📝 儲存試卷文本 (exam.md) 到 GitHub"):
            if not package_name:
                st.error("❌ 請先輸入包裹名稱！")
            else:
                exam_path = f"exam_packages/{package_name}/exam.md"
                if upload_to_github(exam_path, st.session_state['generated_exam']):
                    st.success(f"✅ 試卷成功儲存至 GitHub！")
                    
    with tab2:
        html_for_printing = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            .print-control-bar {{ background-color: #f0f2f6; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-family: sans-serif; }}
            .print-btn {{ background-color: #ff4b4b; color: white; border: none; padding: 10px 20px; font-size: 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }}
            #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", Arial, sans-serif; line-height: 2.2; color: #000000; padding: 10px; font-size: 16px; }}
            
            #exam-body p {{ margin-bottom: 16px; }}
            
            /* 🚀 頂級直式分數 CSS：分子在上，一條橫劃線，分母在下 */
            .v-frac {{
                display: inline-flex;
                flex-direction: column;
                vertical-align: middle;
                text-align: center;
                line-height: 1.0;
                padding: 0 4px;
                font-size: 0.85em;
            }}
            .v-frac sup {{
                border-bottom: 1.5px solid #000; /* 中間精美的一劃分數線 */
                padding-bottom: 2px;
                vertical-align: baseline;
                position: static;
            }}
            .v-frac sub {{
                padding-top: 2px;
                vertical-align: baseline;
                position: static;
            }}
        </style>
        </head>
        <body>
            <div class="print-control-bar">
                <button class="print-btn" onclick="window.print()">🖨️ 立即打印 / 匯出 PDF</button>
            </div>
            <div id="exam-body">{perfect_html_content}</div>
        </body>
        </html>
        """
        import streamlit.components.v1 as components
        components.html(html_for_printing, height=900, scrolling=True)
