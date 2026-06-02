import streamlit as st
import requests
import json
import base64
import markdown
import time
import re

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 🆕 升級至 v1.2.0：內容與排版分離調試版
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.2.0"

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
# 主程式
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
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的憑證 (GIT_TOKEN 或 GEMINI_TOKEN)。")
    st.stop()

# ==========================================
# 2. 輔助函式：GitHub API 互動邏輯
# ==========================================
def upload_to_github(path, content, is_bytes=False):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    sha = None
    if res.status_code == 200: sha = res.json().get("sha")
    encoded_content = base64.b64encode(content if is_bytes else content.encode("utf-8")).decode("utf-8")
    data = {"message": f"Upload/Update {path} via Streamlit", "content": encoded_content, "branch": "main"}
    if sha: data["sha"] = sha
    response = requests.put(url, headers=headers, json=data)
    return response.status_code in [200, 201]

def get_file_from_github(path):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    return base64.b64decode(res.json()["content"]) if res.status_code == 200 else None

# ==========================================
# 🚀 🚀 Python 核心排版引擎 🚀 🚀
# ==========================================
def python_layout_engine(raw_text, is_answer_key=False):
    lines = raw_text.split('\n')
    processed_lines = []
    
    for line in lines:
        if not line.strip():
            continue
            
        # 1. 清洗清除 AI 自己亂吐的長底線，避免重疊 Bug
        line = re.sub(r'_{4,}', '', line)
        
        # 2. 處理真·上下直式分數
        line = re.sub(r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', line)
        line = re.sub(r'(?<!/)(?<!<)(?<!\d)(\d+)/(\d+)(?!\d)(?!>)', r'<span class="v-frac"><span class="num">\1</span><span class="den">\2</span></span>', line)
        
        # 3. 選擇題選項 ○ A. ○ B. 強制獨立換行包裹
        if re.search(r'[○●]\s*[A-D]\.', line):
            if "●" in line:
                line = line.replace("●", '<span class="mc-ans">●</span>')
            processed_lines.append(f'<div class="mc-option">{line}</div>')
            continue

        # 4. 填充題加短底線
        if "填空" in line or "填充" in line or re.match(r'^\d+\.', line.strip()) and not re.search(r'[A-D]\.', line) and ("部" not in line) and ("題" not in line):
            if not is_answer_key and ("分" in line or "厘米" in line or "克" in line or "%" in line or "元" in line or line.strip()[-1] in ["：", ":", "。"]):
                if "丙部" not in raw_text or "計算" not in line:
                    line += ' <span class="short-line">______</span>'

        # 5. 計算題或應用題，題目後換行，鋪設 4 條虛線
        if re.match(r'^\d+\.', line.strip()) and ("丙部" in raw_text or "丁部" in raw_text or "應用題" in line or "計算" in line) and not re.search(r'[A-D]\.', line):
            processed_lines.append(f'<div class="question-text">{line}</div>')
            if not is_answer_key:
                lines_html = '<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>'
                processed_lines.append(lines_html)
            continue
            
        processed_lines.append(f'<div>{line}</div>')
        
    return "\n".join(processed_lines)

def process_full_exam(raw_gemini_output):
    if "---" in raw_gemini_output:
        parts = raw_gemini_output.split("---")
        exam_body = python_layout_engine(parts[0], is_answer_key=False)
        answer_body = python_layout_engine(parts[1], is_answer_key=True)
        return exam_body + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + answer_body
    else:
        return python_layout_engine(raw_gemini_output, is_answer_key=False)

# ==========================================
# 3. Streamlit 網頁介面設計與持久化數據
# ==========================================
# 初始化數據存儲，防刷新丟失
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
        
    if btn_load and load_package_name:
        config_path = f"exam_packages/{load_package_name}/config.json"
        config_bytes = get_file_from_github(config_path)
        if config_bytes:
            config_data = json.loads(config_bytes.decode("utf-8"))
            st.success(f"✅ 成功載入包裹：{load_package_name}")

st.write("---") 

# 左邊設定、右邊存放題目緩衝區（中轉站）
layout_col1, layout_col2 = st.columns([1, 1])

with layout_col1:
    st.subheader("📋 基本資料與生成題目")
    subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
    grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])
    range_text = st.text_area("微調範圍", placeholder="輸入調整需求...")
    package_name = st.text_input("請輸入這個考試包裹的名稱")
    
    # 🆕 按鈕一：純出卷（只聯絡 Gemini，拿到純文字內容）
    if st.button("🤖 步驟一：呼叫 Gemini AI 生成新題目", use_container_width=True):
        with st.spinner("正在向 Gemini 索取題目原始碼..."):
            prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格的資深老師。請為【香港小學{grade}】的學生，製作一份【{subject}】科測驗/考試卷。
出的題型必須豐富多樣（包括多項選擇題、填充題、計算題、應用題等）。
分數格式：分子/分母 (e.g. 3/5) 或 帶分數整數 空格 分子/分母 (e.g. 2 1/4)，乘號 x，除號 ÷。
選擇題格式：
1. 問題文字
○ A. 選項一
○ B. 選項二
○ C. 選項三
○ D. 選項四
試卷與答案頁中間使用 `---` 分割。"""
            if range_text: prompt_text += f"\n【範圍】：\n{range_text}\n"
            
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_TOKEN}"
            try:
                res = requests.post(api_url, headers={"Content-Type": "application/json"}, json={"contents": [{"parts": [{"text": prompt_text}]}]})
                if res.status_code == 200:
                    st.session_state['generated_exam'] = res.json()['candidates'][0]['content']['parts'][0]['text']
                    st.success("🤖 題目生成完畢！已送入右側暫存區。")
                    st.rerun()
                else: st.error(f"❌ API 報錯: {res.text}")
            except Exception as e: st.error(f"❌ 失敗: {str(e)}")

with layout_col2:
    st.subheader("📝 題目原始碼暫存區")
    st.caption("💡 提示：你可以直接在這裡修改文字，或貼上之前的舊試卷，再點擊下方「排版渲染」進行測試。")
    # 🆕 密技中轉站：利用 Text Area 持久化保存文字，允許用家手動改字或黏貼
    stored_text = st.text_area("試卷原始文本控制台", value=st.session_state['generated_exam'], height=290, key="exam_editor")
    if stored_text != st.session_state['generated_exam']:
        st.session_state['generated_exam'] = stored_text

# 🆕 按鈕二：純排版（完全不花 API Key 錢，100% 用 Python 本地渲染最新的 CSS 視覺外觀）
st.write("---")
st.subheader("🎨 視覺排版測試與導出")
btn_render = st.button("🎨 步驟二：執行 Python 引擎，更新試卷排版 🔄", type="primary", use_container_width=True)

# --- 試卷預覽與打印區塊 ---
if st.session_state['generated_exam']:
    tab1, tab2 = st.tabs(["📺 網頁完美預覽", "🖨️ 專業打印預覽 (支援直式分數)"])
    
    # 呼叫 Python 終極排版引擎進行視覺加工
    perfect_html_content = process_full_exam(st.session_state['generated_exam'])
    
    with tab1:
        st.markdown(f'<div id="preview-box">{perfect_html_content}</div>', unsafe_allow_html=True)
        if st.button("📝 儲存試卷文本 (exam.md) 到 GitHub"):
            if not package_name: st.error("❌ 請先輸入包裹名稱！")
            else:
                if upload_to_github(f"exam_packages/{package_name}/exam.md", st.session_state['generated_exam']):
                    st.success(f"✅ 試卷成功儲存至 GitHub！")
                    
    with tab2:
        html_for_printing = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            .print-control-bar {{ background-color: #f0f2f6; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
            .print-btn {{ background-color: #ff4b4b; color: white; border: none; padding: 10px 20px; font-size: 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }}
            #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; color: #000000; padding: 30px; font-size: 16px; line-height: 2.2; }}
            #exam-body p {{ margin-bottom: 16px; }}
            
            /* 🚀 1. 直式分數 CSS */
            .v-frac {{
                display: inline-flex;
                flex-direction: column;
                vertical-align: middle;
                text-align: center;
                line-height: 1.1;
                padding: 0 4px;
                font-size: 0.8em;
                position: relative;
                top: -2px;
            }}
            .v-frac .num {{ border-bottom: 1.5px solid #000; padding-bottom: 1px; }}
            .v-frac .den {{ padding-top: 1px; }}
            
            /* 🚀 2. 選擇題強制換行排版 */
            .mc-option {{ margin-left: 20px; margin-top: 6px; margin-bottom: 6px; display: block !important; }}
            .mc-ans {{ color: #ff4b4b; font-weight: bold; }}
            
            /* 🚀 3. 填充題短底線 */
            .short-line {{ font-weight: bold; text-decoration: underline; color: #000; }}
            
            /* 🚀 4. 計算題與應用題：全寬虛線 */
            .question-text {{ font-weight: bold; margin-top: 20px; margin-bottom: 10px; }}
            .write-zone {{ margin-top: 12px; margin-bottom: 25px; width: 100%; }}
            .row-line {{ width: 100%; height: 38px; border-bottom: 1px dashed #999; }}
            
            .page-break {{ page-break-before: always; }}
            .ans-header {{ color: #ff4b4b; border-bottom: 2px solid #ff4b4b; padding-bottom: 10px; }}
            @media print {{ .print-control-bar {{ display: none; }} body {{ background-color: white; }} }}
        </style>
        </head>
        <body>
            <div class="print-control-bar">
                <button class="print-btn" onclick="window.print()">🖨️ 立即打印 / 匯出 PDF 考卷</button>
            </div>
            <div id="exam-body">{perfect_html_content}</div>
        </body>
        </html>
        """
        import streamlit.components.v1 as components
        components.html(html_for_printing, height=1000, scrolling=True)
