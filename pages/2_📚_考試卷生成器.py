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

# 🆕 升級至 v1.2.1：終極直式分數完美對齊版
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.0.9"

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
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的憑證。")
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
    data = {"message": f"Upload {path}", "content": encoded_content, "branch": "main"}
    if sha: data["sha"] = sha
    requests.put(url, headers=headers, json=data)
    return True

def get_file_from_github(path):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    return base64.b64decode(res.json()["content"]) if res.status_code == 200 else None

# ==========================================
# 🚀 🚀 Python 終極分數與視覺排版引擎 (全新優化) 🚀 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
    """
    極度精準的 Python 分數轉化引擎。
    將所有 3/5, 2 1/4, 5(3/8) 轉化為真·上下直式分數 HTML 結構。
    """
    # 1. 處理帶分數：整數 + 空格/或括號 + 分子/分母 (e.g., "2 1/4", "5(3/8)", "51/4")
    # 攔截 2 1/4 或 2(1/4)
    text_content = re.sub(
        r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?',
        r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>',
        text_content
    )
    
    # 2. 處理獨立的普通分數：分子/分母 (e.g., "3/5", "13/3")
    # 排除掉網頁標籤內部的斜線（如 </div> 或 <br/>），只抓純數字分數
    text_content = re.sub(
        r'(?<!/)(?<!<)(?<!\d)(?<!">)(\d+)/(\d+)(?!\d)(?!>)(?!/body)',
        r'<span class="v-frac"><span class="num">\1</span><span class="den">\2</span></span>',
        text_content
    )
    return text_content

def python_layout_engine(raw_text, is_answer_key=False):
    lines = raw_text.split('\n')
    processed_lines = []
    
    for line in lines:
        if not line.strip():
            continue
            
        # 清除 AI 自己亂吐的混亂長底線
        line = re.sub(r'_{4,}', '', line)
        
        # 選擇題選項 ○ A. ○ B. 強制獨立換行包裹
        if re.search(r'[○●]\s*[A-D]\.', line):
            if "●" in line:
                line = line.replace("●", '<span class="mc-ans">●</span>')
            # 進行分數轉換
            line = convert_to_vertical_fractions(line)
            processed_lines.append(f'<div class="mc-option">{line}</div>')
            continue

        # 填充題加短底線
        if "填空" in line or "填充" in line or re.match(r'^\d+\.', line.strip()) and not re.search(r'[A-D]\.', line) and ("部" not in line) and ("題" not in line):
            if not is_answer_key and ("分" in line or "厘米" in line or "克" in line or "%" in line or "元" in line or line.strip()[-1] in ["：", ":", "。"]):
                if "丙部" not in raw_text or "計算" not in line:
                    line += ' <span class="short-line">______</span>'

        # 計算題或應用題，題目後換行，鋪設 4 條全寬印刷虛線
        if re.match(r'^\d+\.', line.strip()) and ("丙部" in raw_text or "丁部" in raw_text or "應用題" in line or "計算" in line) and not re.search(r'[A-D]\.', line):
            line = convert_to_vertical_fractions(line)
            processed_lines.append(f'<div class="question-text">{line}</div>')
            if not is_answer_key:
                lines_html = '<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>'
                processed_lines.append(lines_html)
            continue
            
        # 其他普通行也通通過濾一次分數
        line = convert_to_vertical_fractions(line)
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
        if st.button("🔍 載入包裹資料", use_container_width=True) and load_package_name:
            config_bytes = get_file_from_github(f"exam_packages/{load_package_name}/config.json")
            if config_bytes: st.success(f"✅ 成功載入包裹：{load_package_name}")

st.write("---") 

layout_col1, layout_col2 = st.columns([1, 1])

with layout_col1:
    st.subheader("📋 基本資料與生成題目")
    subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
    grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])
    range_text = st.text_area("微調範圍", placeholder="輸入調整需求...")
    package_name = st.text_input("請輸入這個考試包裹的名稱")
    
    if st.button("🤖 步驟一：呼叫 Gemini AI 生成新題目", use_container_width=True):
        with st.spinner("正在向 Gemini 索取題目原始碼..."):
            prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格的資深老師。請為【香港小學{grade}】的學生，製作一份【{subject}】科測驗/考試卷。
出的題型必須豐富多樣（包括多項選擇題、填充題、計算題、應用題等）。
分數格式請嚴格使用純文字：分子/分母 (如 3/5) 或 帶分數 (如 2 1/4)，乘號 x，除號 ÷。
選擇題格式：
1. 問題文字
○ A. 選項一
○ B. 選項二
○ C. 選項三
○ D. 選項四
試卷與答案頁中間使用 `---` 分割。"""
            if range_text: prompt_text += f"\n【範圍】：\n{range_text}\n"
            
            res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_TOKEN}", headers={"Content-Type": "application/json"}, json={"contents": [{"parts": [{"text": prompt_text}]}]})
            if res.status_code == 200:
                st.session_state['generated_exam'] = res.json()['candidates'][0]['content']['parts'][0]['text']
                st.rerun()

with layout_col2:
    st.subheader("📝 題目原始碼暫存區")
    stored_text = st.text_area("試卷原始文本控制台", value=st.session_state['generated_exam'], height=290, key="exam_editor")
    if stored_text != st.session_state['generated_exam']:
        st.session_state['generated_exam'] = stored_text

st.write("---")
st.subheader("🎨 視覺排版測試與導出")
btn_render = st.button("🎨 步驟二：執行 Python 引擎，更新試卷排版 🔄", type="primary", use_container_width=True)

# --- 試卷預覽與打印區塊 ---
if st.session_state['generated_exam']:
    tab1, tab2 = st.tabs(["📺 網頁完美預覽", "🖨️ 專業打印預覽 (支援直式分數)"])
    perfect_html_content = process_full_exam(st.session_state['generated_exam'])
    
    with tab1:
        st.markdown(f'<div id="preview-box">{perfect_html_content}</div>', unsafe_allow_html=True)
        if st.button("📝 儲存試卷文本 (exam.md) 到 GitHub"):
            if package_name and upload_to_github(f"exam_packages/{package_name}/exam.md", st.session_state['generated_exam']):
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
            
            /* 🚀 真正完美的直式分數：分子在上面，一橫劃，分母在下面，且與普通文字完美對齊 */
            .v-frac {{
                display: inline-flex;
                flex-direction: column;
                vertical-align: middle;
                text-align: center;
                line-height: 1.0;
                padding: 0 3px;
                font-size: 0.78em; /* 縮小分數比例，符合真實考卷外觀 */
                position: relative;
                top: -0.15em; /* 微調高度，與中文字對齊 */
            }}
            .v-frac .num {{
                border-bottom: 1.5px solid #000000; /* 實心黑色的直式分數線 */
                padding-bottom: 1px;
                min-width: 12px;
            }}
            .v-frac .den {{
                padding-top: 2px;
                min-width: 12px;
            }}
            
            .mc-option {{ margin-left: 20px; margin-top: 6px; margin-bottom: 6px; display: block !important; }}
            .mc-ans {{ color: #ff4b4b; font-weight: bold; }}
            .short-line {{ font-weight: bold; text-decoration: underline; color: #000; }}
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
