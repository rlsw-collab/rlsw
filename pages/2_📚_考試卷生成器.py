import streamlit as st
import requests
import json
import base64
import markdown
import time
from PIL import Image

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 定義統一的標題與版本號碼 (升級至 v1.0.6)
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.0.6"

# 初始化 session_state 來記住登入狀態
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# 如果還未登入，顯示密碼輸入框
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
            st.success(f"🎉 打包成功！所有資料已安全儲存。")

# ==========================================
# 4. 核心功能：【智慧自動重試】直連 2.5 Flash
# ==========================================
st.subheader("✨ 4. 生成測驗/考試卷")
if st.button("🚀 開始利用 Gemini AI 製作試卷"):
    with st.spinner("🚀 智能排版大腦正在為您構思香港小學風格試卷，請稍候..."):
        
        # 建立結合精準排版指令的 Prompt
        prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格與考試制度的資深小學老師。
請為【香港小學{grade}】的學生，製作一份符合教育局課程指引且難易度適中的【{subject}】科測驗/考試卷。

根據香港小學的真實排版要求，出的題型必須符合以下【精細排版與題型命令】：

⚠️【1. 數學分數與符號 - 鋼鐵禁用令】：
- 🚫 絕對禁止使用任何 LaTeX 數學格式！不允許出現任何 `$` 符號、`\\frac`、`\\times`、`\\div` 等學術程式碼。
- 🗣️ 分數和帶分數必須使用最地道、乾淨的香港小學純文字寫法：
  * 普通分數請用「斜線」表示，例如：3/5、7/9。
  * 帶分數請用「整數(分子/分母)」表示，例如：2(1/4) 代表二又四分之一。
  * 乘號請直接用「x」，除號請直接用「÷」。

⚠️【2. 多項選擇題 (MC) - 換行與答案獨立命令】：
- 題目自成一行。
- A、B、C、D 四個選項必須在問題的下方，且「每一個選項必須獨立佔滿一行」，絕對不允許將多個選項合併在同一行！
- 每個選項前加上一個空心圓圈 `○`。
  正確格式範例：
  1. 以下哪個分數與 2(1/4) 相等？
     ○ A. 5/4
     ○ B. 7/4
     ○ C. 9/4
     ○ D. 10/4

⚠️【3. 題型分流與特別限制】：
- 🚫【找錯處 (Proofreading)】題型：這是【英文】科的專屬題型！當前科目是【{subject}】。如果目前不是英文科，絕對不要生成任何找錯處題型！只有英文科需要。
- 📝【填充題】：空格的答案線必須加長一倍，請統一使用 16 個底線 `________________` 作為答案線。
- 🧮【列式計算應用題 / 長題目】：題目後面不需要出現「列式：」和「答：」等任何提示文字。請直接提供「4 條長長的空底橫線」讓學生有足夠的空間進行自由列式與寫出計算步驟。
  格式範例：
  ______________________________________________________
  ______________________________________________________
  ______________________________________________________
  ______________________________________________________

【試卷整體結構要求】：
試卷必須嚴格分為以下兩個部分，並在中間使用 `---` 分割線分開：
1. 【試卷正文】：包含虛構校名、學生個人資料欄（姓名、班別、學號）、總分、限時。題目要有明確題號、分值。
2. 【答案頁 (Answer Key)】：緊接在 `---` 之後。多項選擇題的正確答案，請將對應的圓圈變成實心圓圈 `●` 作為示範（例如：● C. 9/4）。
"""
        if range_text:
            prompt_text += f"\n【使用者特別指定的微調範圍與重點】：\n{range_text}\n"
            
        # 智慧 API 調用
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
            #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", Arial, sans-serif; line-height: 1.8; color: #000000; padding: 10px; }}
            
            #exam-body p {{ margin-bottom: 12px; }}
            
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
        components.html(html_for_printing, height=900, scrolling=True)
