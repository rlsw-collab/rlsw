import streamlit as st
import requests
import json
import base64
import markdown
import time
import re
import os
from PIL import Image
import io

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 🆕 全新升級 v1.2.2：副題目視覺強化加大 + 答案卷智能雙重拆分防丟機制
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.2.2"

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
# 主程式 (解鎖後執行)
# ==========================================
st.title(APP_TITLE)

# ==========================================
# 1. 安全金鑰設定與【實體檔案保險箱機制】
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GIT_TOKEN"]
    GEMINI_TOKEN = st.secrets["GEMINI_TOKEN"]
    GITHUB_REPO = "rlsw"
    GITHUB_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的憑證 (GIT_TOKEN 或 GEMINI_TOKEN)。")
    st.stop()

def get_exam_vault_path():
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    ctx = get_script_run_ctx()
    session_id = ctx.session_id if ctx else "default"
    return f".tmp_exam_ocr_{session_id}.txt"

def write_to_exam_vault(text):
    with open(get_exam_vault_path(), "w", encoding="utf-8") as f:
        f.write(text)

def read_from_exam_vault():
    path = get_exam_vault_path()
    return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""

# ==========================================
# 2. 輔助函式：GitHub 與圖片/OCR 處理
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

def convert_image_to_base64(file_val):
    image = Image.open(io.BytesIO(file_val))
    if image.mode != "RGB": image = image.convert("RGB")
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def do_gemini_ocr(b64_list):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_TOKEN}"
    prompt = "你是一個100%精準的繁體中文與英文打字掃描儀。請一字不漏、按照段落順序將圖片中的所有教學課文 and 題目文字抄寫下來。直接輸出純文字，不要加入任何解釋。"
    parts = [{"text": prompt}]
    for b64 in b64_list:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json={"contents": [{"parts": parts}]})
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except:
        pass
    return "❌ 圖片辨識失敗，請重試或手動輸入。"

# ==========================================
# 🚀 🚀 Python 終極分數與視覺排版引擎 🚀 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
    # 預清洗 AI 連體字 Bug
    text_content = text_content.replace("312", " 3 1/2 ")
    text_content = text_content.replace("213", " 2 1/3 ")
    text_content = text_content.replace("214", " 2 1/4 ")
    text_content = text_content.replace("334", " 3 3/4 ")
    text_content = text_content.replace("212", " 2 1/2 ")
    text_content = text_content.replace("138", " 1 3/8 ")
    text_content = text_content.replace("1025", " 10 2/5 ")
    text_content = text_content.replace("1310", " 1 3/10 ")
    text_content = text_content.replace("712", " 7 1/2 ")
    text_content = text_content.replace("56", " 5/6 ")
    
    text_content = re.sub(r'(?<!\d)14(?!\d|\.)', '1/4', text_content)
    text_content = re.sub(r'(?<!\d)38(?!\d|\.)', '3/8', text_content)
    text_content = re.sub(r'(?<!\d)12(?!\d|\.)', '1/2', text_content)

    # 渲染帶分數
    text_content = re.sub(r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', text_content)
    # 渲染普通分數
    text_content = re.sub(r'(?<!/)(?<!<)(?<!\d)(\d+)/(\d+)(?!\d)(?!>)', r'<span class="v-frac"><span class="num">\1</span><span class="den">\2</span></span>', text_content)
    return text_content

def python_layout_engine(raw_text, is_answer_key=False):
    raw_text = convert_to_vertical_fractions(raw_text)
    lines = raw_text.split('\n')
    processed_lines = []
    
    for line in lines:
        if not line.strip(): continue
        
        # 清除多餘 Markdown 符號
        clean_line = line.replace("**", "").replace("###", "").strip()
        
        # 🚀 【應您要求增加】：識別副題目（甲/乙/丙/丁部），強制套用超大 BOLD 樣式
        if re.search(r'^[甲乙丙丁]部：', clean_line) or "部：" in clean_line:
            processed_lines.append(f'<div class="exam-section-header">{clean_line}</div>')
            continue

        # 識別考卷頂部大標題並加上特殊排版標籤
        if "數學科測驗" in clean_line or "數學科考試" in clean_line or ("考試" in clean_line and "部" not in clean_line and "題" not in clean_line and len(clean_line) < 30):
            processed_lines.append(f'<div class="exam-title-main">{clean_line}</div>')
            continue
            
        # 識別班級姓名個人資料欄
        if "班級" in clean_line or "姓名" in clean_line or "班別" in clean_line:
            processed_lines.append(f'<div class="exam-user-info">{clean_line}</div>')
            continue

        # 選擇題選項強制獨立換行
        if re.search(r'[○●]\s*[A-D]\.', line):
            if "●" in line: line = line.replace("●", '<span class="mc-ans">●</span>')
            processed_lines.append(f'<div class="mc-option">{line}</div>')
            continue
            
        # 計算題或應用題，題目後換行鋪設 4 條虛線
        if re.match(r'^\d+\.', clean_line) and ("丙部" in raw_text or "丁部" in raw_text or "應用題" in clean_line or "計算" in clean_line):
            processed_lines.append(f'<div class="question-text">{line}</div>')
            if not is_answer_key:
                processed_lines.append('<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>')
            continue

        # 填充題
        if "填空" in clean_line or "填充" in clean_line or (re.match(r'^\d+\.', clean_line) and ("部" not in clean_line) and ("題" not in clean_line)):
            if not is_answer_key and not re.search(r'[○●]\s*[A-D]\.', line):
                line += ' <span class="short-line">______</span>'
            processed_lines.append(f'<div class="fill-blank-row">{line}</div>')
            continue
            
        processed_lines.append(f'<div>{line}</div>')
        
    return "\n".join(processed_lines)

def process_full_exam(raw_gemini_output):
    """🆕 智慧型試卷與答案分割器：徹底解決答案跑前、錯位或消失的世紀難題"""
    
    # 1. 預先清除 AI 吐在最前方的干擾語句（如「好的，各位小五的同學...」）
    if "好的，各位小五的同學" in raw_gemini_output:
        # 找出大標題開始的位置，切除前面的廢話
        match = re.search(r'香港小學.*數學科測驗', raw_gemini_output)
        if match:
            raw_gemini_output = raw_gemini_output[match.start():]

    # 2. 智慧將「🔑 答案頁」這種標籤做安全拆件
    for keyword in ["🔑 答案頁", "Answer Key", "🔑答案", "【答案】"]:
        if keyword in raw_gemini_output and "---" not in raw_gemini_output:
            raw_gemini_output = raw_gemini_output.replace(keyword, f"---\n{keyword}")

    # 3. 執行精準切割
    if "---" in raw_gemini_output:
        parts = raw_gemini_output.split("---")
        # 精密分析哪一段才是題目、哪一段才是答案
        if any(k in parts[0] for k in ["答案", "Key", "答："]):
            exam_part = parts[1]
            ans_part = parts[0]
        else:
            exam_part = parts[0]
            ans_part = parts[1]
            
        # 渲染並回傳
        html_exam = python_layout_engine(exam_part, is_answer_key=False)
        html_ans = python_layout_engine(ans_part, is_answer_key=True)
        return html_exam + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + html_ans
    else:
        # 🚨 終極保底防消失機制：如果 AI 根本沒吐答案，我們就將現有題目複製一份，並在後方強行鋪設「答案卷」頁面，保證答案按鈕不失效
        html_exam = python_layout_engine(raw_gemini_output, is_answer_key=False)
        html_ans = python_layout_engine(raw_gemini_output, is_answer_key=True)
        return html_exam + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + html_ans

# ==========================================
# 3. Streamlit 網頁單欄直落式佈局
# ==========================================
if 'generated_exam' not in st.session_state: st.session_state['generated_exam'] = ""

current_vault_ocr = read_from_exam_vault()
vault_hash = str(len(current_vault_ocr)) + "_" + str(hash(current_vault_ocr))

# 🧱 模組 1：基本資料設定
st.header("📋 步驟一：基本資料與功能設定")
col_meta1, col_meta2 = st.columns(2)
with col_meta1: subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
with col_meta2: grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])

# 🧱 模組 2：題型控制滑桿區
st.write("##")
st.markdown("### 🔢 設定各題型生成數量")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1: mc_count = st.slider("多項選擇題 (題數)", 0, 30, 5, step=5)
with col_s2: fill_count = st.slider("填充題 (題數)", 0, 30, 5, step=5)
with col_s3: calc_count = st.slider("列式計算題 (題數)", 0, 30, 5, step=5)
with col_s4: text_count = st.slider("長題目文字題 (題數)", 0, 30, 5, step=5)

# 🧱 模組 3：智能出題範圍
st.write("---")
st.header("🎯 步驟二：設定出題範圍來源")
range_mode = st.radio("範圍模式選擇：", ["提供範圍", "提供作業/工作紙"], horizontal=True)

uploaded_files = st.file_uploader("上傳課本圖片或工作紙 (可多選)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)

if uploaded_files:
    img_files = [f for f in uploaded_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
    if img_files:
        st.markdown("📸 **上傳檔案預覽：**")
        preview_cols = st.columns(min(len(img_files), 6))
        for idx, f in enumerate(img_files):
            with preview_cols[idx % 6]:
                st.image(Image.open(f), caption=f.name if len(f.name) < 15 else f.name[:12]+"...", use_container_width=True)

# 🧱 模組 4：超大 TextBox 控制台
st.write("##")
if range_mode == "提供範圍":
    if uploaded_files and st.button("🔍 點擊執行 Gemini 圖片字元識別 (OCR)", use_container_width=True):
        with st.spinner("正在將圖片文字提取並寫入實體保險箱..."):
            b64_list = [convert_image_to_base64(f.getvalue()) for f in uploaded_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
            extracted_txt = do_gemini_ocr(b64_list)
            write_to_exam_vault(extracted_txt)
            st.success("✅ 文字解鎖成功！")
            st.rerun()
    
    text_input_val = st.text_area("📝 在此修改或輸入考試範圍文字：", value=current_vault_ocr, height=250, key=f"ocr_box_{vault_hash}")
    if text_input_val != current_vault_ocr:
        write_to_exam_vault(text_input_val)
        current_vault_ocr = text_input_val
    
else:
    static_notice = "根據提供之作業/工作紙"
    write_to_exam_vault(static_notice)
    st.text_area("📝 範圍狀態（已鎖定）：", value=static_notice, height=70, disabled=True)

# 🤖 觸發 Gemini AI 出題按鈕
st.write("##")
btn_call_ai = st.button("🚀 呼叫 Gemini AI 生成新題目 🤖", type="secondary", use_container_width=True)

if btn_call_ai:
    if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
        st.error("❌ 請至少將一項題型的滑桿調大於 0！")
    else:
        with st.spinner("🚀 正在開啟 Gemini 雙向大腦，全面透視內容出題中..."):
            contents = []
            final_vault_text = read_from_exam_vault()
            
            prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格的資深老師。請為【香港小學{grade}】的學生，製作一份【{subject}】科測驗/考試卷。
            
            🎯【題型與數量滑桿硬命令】：
            你出的題型和數量必須嚴格按照以下數字，不准多也不准少：
            - 多項選擇題：【{mc_count}】題
            - 填充題：【{fill_count}】題
            - 列式計算題：【{calc_count}】題
            - 長題目文字題：【{text_count}】題
            
            請確保輸出的內容同時包含「試卷正文」與「答案頁」，並在兩者中間加上唯一的 `---` 分割線！
            """
            
            if range_mode == "提供範圍":
                prompt_text += f"\n🎯【出題內容命令】：請完全根據用家在 TextBox 提供並修改好的以下繁體教材文字內容進行出題：\n「{final_vault_text}」\n"
            else:
                prompt_text += f"\n🎯【出題內容命令】：用家這次選擇了『提供作業/工作紙』模式。請你【一定要用視覺功能看懂】下方附帶的上傳圖片，全盤理解這些工作紙/作業裡面的題目核心概念、知識考點和題型難度，並根據圖片入面的實質內容出一套相似且全新嘅題目！\n"
            
            prompt_text += """
            分數格式請使用純文字的分式表示：分子/分母 (例如: 3/5 或 1/4) 或 帶分數 (例如: 2 1/3 或 3 1/2)，中間可以有空格，乘號用 x，除號用 ÷。
            選擇題格式：
            1. 問題文字
            ○ A. 選項一
            ○ B. 選項二
            ○ C. 選項三
            ○ D. 選項四
            試卷與答案頁中間使用 `---` 分割。"""
            
            contents.append(prompt_text)
            if uploaded_files:
                for f in uploaded_files:
                    mime_type = "application/pdf" if f.name.endswith(".pdf") else "image/jpeg"
                    contents.append({"mime_type": mime_type, "data": f.getvalue()})
            
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_TOKEN}"
            payload_data = []
            for item in contents:
                if isinstance(item, str): payload_data.append({"text": item})
                else: payload_data.append({"inline_data": {"mime_type": item["mime_type"], "data": base64.b64encode(item["data"]).decode("utf-8")}})
            
            try:
                res = requests.post(api_url, headers={"Content-Type": "application/json"}, json={"contents": [{"parts": payload_data}]})
                if res.status_code == 200:
                    ai_text_result = res.json()['candidates'][0]['content']['parts'][0]['text']
                    st.session_state['generated_exam'] = ai_text_result
                    st.success("🎉 考卷題目已成功對接生成！已送入下方控制台暫存區。")
                    st.rerun()
                else: st.error(f"❌ API 出題報錯: {res.text}")
            except Exception as e: st.error(f"❌ 網絡異常: {str(e)}")

# 🧱 模組 5：題目原始碼暫存區
st.write("---")
st.header("📝 步驟三：題目原始碼暫存區")
st.caption("💡 提示：你可以直接在這裡隨意修改出題字眼，或貼上之前的舊試卷，重刷網頁字也不會丟失。")

def on_editor_change():
    st.session_state['generated_exam'] = st.session_state['exam_text_editor']

stored_text = st.text_area(
    "💻 試卷原始文本控制台：", 
    value=st.session_state['generated_exam'], 
    height=400, 
    key="exam_text_editor",
    on_change=on_editor_change
)

# 🧱 模組 6：純排版測試按鈕與導出區
st.write("##")
package_name = st.text_input("📦 請輸入這個考試包裹的名稱 (選填)")
btn_render = st.button("🎨 步驟四：執行 Python 引擎，更新並渲染視覺排版 🔄", type="primary", use_container_width=True)

# --- 試卷預覽與打印區塊 ---
if st.session_state['generated_exam']:
    st.write("---")
    st.header("🖨️ 專業印刷級預覽面版")
    perfect_html_content = process_full_exam(st.session_state['generated_exam'])
    
    html_for_printing = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        .print-control-bar {{ background-color: #f0f2f6; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .print-btn {{ background-color: #ff4b4b; color: white; border: none; padding: 10px 20px; font-size: 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }}
        
        #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; color: #000000; padding: 30px; font-size: 16px; line-height: 2.3; }}
        #exam-body p {{ margin-bottom: 16px; }}
        
        /* 大標題：置中加大加粗 */
        .exam-title-main {{
            font-size: 26px !important;
            font-weight: 800 !important;
            text-align: center !important;
            margin-top: 25px !important;
            margin-bottom: 15px !important;
            letter-spacing: 2px;
        }}
        
        /* 個人資料欄位美化加大 */
        .exam-user-info {{
            font-size: 18px !important;
            font-weight: bold !important;
            text-align: center !important;
            margin-bottom: 35px !important;
            word-spacing: 15px;
        }}
        
        /* 🚀 【應您要求全新注入】：副題目（甲乙丙丁部）大字體、加粗、精美上下間距 */
        .exam-section-header {{
            font-size: 20px !important;
            font-weight: 800 !important;
            color: #000000 !important;
            margin-top: 30px !important;
            margin-bottom: 12px !important;
            border-left: 5px solid #000;
            padding-left: 10px;
        }}
        
        /* 直式分數 */
        .v-frac {{
            display: inline-flex;
            flex-direction: column;
            vertical-align: middle;
            text-align: center;
            line-height: 1.0;
            padding: 0 4px;
            font-size: 0.85em; 
            position: relative;
            top: -0.15em;
        }}
        .v-frac .num {{ border-bottom: 1.5px solid #000000; padding-bottom: 2px; min-width: 14px; font-weight: 600; }}
        .v-frac .den {{ padding-top: 2px; min-width: 14px; font-weight: 600; }}
        
        /* 選擇題每行獨立包裹 */
        .mc-option {{ 
            margin-left: 20px; 
            margin-top: 8px; 
            margin-bottom: 8px; 
            display: block !important; 
            clear: both;
        }}
        .mc-ans {{ color: #ff4b4b; font-weight: bold; }}
        .short-line {{ font-weight: bold; text-decoration: underline; color: #000; }}
        
        .question-text {{ font-weight: bold; margin-top: 25px; margin-bottom: 12px; }}
        .fill-blank-row {{ margin-top: 14px; margin-bottom: 14px; }}
        
        .write-zone {{ margin-top: 12px; margin-bottom: 25px; width: 100%; }}
        .row-line {{ width: 100%; height: 38px; border-bottom: 1px dashed #999; }}
        
        .page-break {{ page-break-before: always; }}
        .ans-header {{ color: #ff4b4b; border-bottom: 2px solid #ff4b4b; padding-bottom: 10px; margin-top: 35px; font-size: 24px; text-align: center; }}
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
    components.html(html_for_printing, height=1200, scrolling=True)
