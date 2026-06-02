import streamlit as st
import requests
import json
import base64
import markdown
import time
import re
from PIL import Image
import io

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 🆕 應您要求：升級至 v1.1.1，內容視覺看圖出題版
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.1.1"

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
    prompt = "你是一個100%精準的繁體中文與英文打字掃描儀。請一字不漏、按照段落順序將圖片中的所有教學課文和題目文字抄寫下來。直接輸出純文字，不要加入任何解釋。"
    parts = [{"text": prompt}]
    for b64 in b64_list:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, json={"contents": [{"parts": parts}]})
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except:
        pass
    return "❌ 圖片辨識失敗，請手動輸入範圍。"

# ==========================================
# 🚀 🚀 Python 終極分數與視覺排版引擎 🚀 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
    text_content = re.sub(r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', text_content)
    text_content = re.sub(r'(?<!/)(?<!<)(?<!\d)(?<!">)(\d+)/(\d+)(?!\d)(?!>)(?!/body)', r'<span class="v-frac"><span class="num">\1</span><span class="den">\2</span></span>', text_content)
    return text_content

def python_layout_engine(raw_text, is_answer_key=False):
    lines = raw_text.split('\n')
    processed_lines = []
    for line in lines:
        if not line.strip(): continue
        line = re.sub(r'_{4,}', '', line)
        if re.search(r'[○●]\s*[A-D]\.', line):
            if "●" in line: line = line.replace("●", '<span class="mc-ans">●</span>')
            line = convert_to_vertical_fractions(line)
            processed_lines.append(f'<div class="mc-option">{line}</div>')
            continue
        if "填空" in line or "填充" in line or re.match(r'^\d+\.', line.strip()) and not re.search(r'[A-D]\.', line) and ("部" not in line) and ("題" not in line):
            if not is_answer_key and ("分" in line or "厘米" in line or "克" in line or "%" in line or "元" in line or line.strip()[-1] in ["：", ":", "。"]):
                if "丙部" not in raw_text or "計算" not in line: line += ' <span class="short-line">______</span>'
        if re.match(r'^\d+\.', line.strip()) and ("丙部" in raw_text or "丁部" in raw_text or "應用題" in line or "計算" in line) and not re.search(r'[A-D]\.', line):
            line = convert_to_vertical_fractions(line)
            processed_lines.append(f'<div class="question-text">{line}</div>')
            if not is_answer_key:
                processed_lines.append('<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>')
            continue
        line = convert_to_vertical_fractions(line)
        processed_lines.append(f'<div>{line}</div>')
    return "\n".join(processed_lines)

def process_full_exam(raw_gemini_output):
    if "---" in raw_gemini_output:
        parts = raw_gemini_output.split("---")
        return python_layout_engine(parts[0], is_answer_key=False) + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + python_layout_engine(parts[1], is_answer_key=True)
    return python_layout_engine(raw_gemini_output, is_answer_key=False)

# ==========================================
# 3. Streamlit 網頁持久化數據狀態機
# ==========================================
if 'generated_exam' not in st.session_state: st.session_state['generated_exam'] = ""
if 'ocr_box_content' not in st.session_state: st.session_state['ocr_box_content'] = ""

layout_col1, layout_col2 = st.columns([1, 1])

with layout_col1:
    st.subheader("📋 基本資料與功能設定")
    subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
    grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])
    
    st.markdown("🔢 **設定各題型生成數量：**")
    mc_count = st.slider("1. 多項選擇題 (題數)", 0, 30, 5, step=5)
    fill_count = st.slider("2. 填充題 (題數)", 0, 30, 5, step=5)
    calc_count = st.slider("3. 列式計算題 (題數)", 0, 30, 5, step=5)
    text_count = st.slider("4. 長題目文字題 (題數)", 0, 30, 5, step=5)

    st.write("---")
    st.markdown("🎯 **選擇範圍提供方式：**")
    # 🆕 精準修訂選項標籤，更貼合您的操作本意
    range_mode = st.radio("範圍模式：", ["提供範圍", "提供作業/工作紙"], horizontal=True)
    
    uploaded_files = st.file_uploader("上傳課本圖片或工作紙 (可多選)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        img_files = [f for f in uploaded_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
        if img_files:
            st.markdown("📸 **上傳檔案預覽：**")
            preview_cols = st.columns(min(len(img_files), 5))
            for idx, f in enumerate(img_files):
                with preview_cols[idx % 5]:
                    st.image(Image.open(f), caption=f.name if len(f.name) < 12 else f.name[:9]+"...", use_container_width=True)

    st.markdown("📝 **範圍與備忘文字框 (TextBox)：**")
    
    if range_mode == "提供範圍":
        if uploaded_files and st.button("🔍 點擊執行 Gemini 圖片字元識別 (OCR)"):
            with st.spinner("正在將圖片文字提取至下方 TextBox..."):
                b64_list = [convert_image_to_base64(f.getvalue()) for f in uploaded_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
                st.session_state['ocr_box_content'] = do_gemini_ocr(b64_list)
                st.rerun()
        
        text_input_val = st.text_area("在此修改或輸入考試範圍文字：", value=st.session_state['ocr_box_content'], height=150, key="ocr_text_box")
        st.session_state['ocr_box_content'] = text_input_val
        
    else:
        # 🆕 作業/工作紙模式：自動鎖定提示，逼 AI 直接看圖理解內容
        st.session_state['ocr_box_content'] = "根據提供之作業/工作紙"
        st.text_area("範圍狀態：", value=st.session_state['ocr_box_content'], height=60, disabled=True)

    st.write("##")
    package_name = st.text_input("請輸入這個考試包裹的名稱 (選填)")

    # 🤖 點擊生成題目 (智慧判斷雙流向)
    if st.button("🤖 步驟一：呼叫 Gemini AI 生成新題目", use_container_width=True):
        if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
            st.error("❌ 請至少將一項題型的滑桿調大於 0！")
        else:
            with st.spinner("🚀 正在開啟 Gemini 雙向大腦，全面透視內容出題中..."):
                contents = []
                
                # 建立主 Prompt
                prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格的資深老師。請為【香港小學{grade}】的學生，製作一份【{subject}】科測驗/考試卷。
                
                🎯【題型與數量滑桿硬命令】：
                你出的題型和數量必須嚴格按照以下數字，不准多也不准少：
                - 多項選擇題：【{mc_count}】題
                - 填充題：【{fill_count}】題
                - 列式計算題：【{calc_count}】題
                - 長題目文字題：【{text_count}】題
                """
                
                # 🆕 雙流智慧 Prompt 注入
                if range_mode == "提供範圍":
                    prompt_text += f"\n🎯【出題內容命令】：請完全根據用家在 TextBox 提供並修改好的以下文本內容進行出題：\n「{st.session_state['ocr_box_content']}」\n"
                else:
                    prompt_text += f"\n🎯【出題內容命令】：用家這次選擇了『提供作業/工作紙』模式。請你【一定要用視覺功能看懂】下方附帶的上傳圖片，全盤理解這些工作紙裡面的題目核心概念、知識考點和題型難度，並根據圖片入面的實質內容出一套相似且全新嘅題目！\n"
                
                prompt_text += """
                分數格式請一律採用最單純的數字加斜線表示（例如：3/5 或 2 1/4），乘號用 x，除號用 ÷。
                選擇題格式：
                1. 問題文字
                ○ A. 選項一
                ○ B. 選項二
                ○ C. 選項三
                ○ D. 選項四
                試卷與答案頁中間使用 `---` 分割。"""
                
                contents.append(prompt_text)
                
                # 將圖片打包進去
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
                        st.session_state['generated_exam'] = res.json()['candidates'][0]['content']['parts'][0]['text']
                        st.success("🎉 考卷題目已成功對接生成！請點擊下方排版按鈕渲染。")
                        st.rerun()
                    else: st.error(f"❌ API 出題報錯: {res.text}")
                except Exception as e: st.error(f"❌ 網絡異常: {str(e)}")

with layout_col2:
    st.subheader("📝 題目原始碼暫存區")
    st.caption("💡 提示：你可以直接在這裡修改文字，或貼上之前的舊試卷，再點擊下方「排版渲染」進行測試。")
    stored_text = st.text_area("試卷原始文本控制台", value=st.session_state['generated_exam'], height=520, key="exam_editor")
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
            
            .v-frac {{
                display: inline-flex;
                flex-direction: column;
                vertical-align: middle;
                text-align: center;
                line-height: 1.0;
                padding: 0 3px;
                font-size: 0.78em;
                position: relative;
                top: -0.15em;
            }}
            .v-frac .num {{ border-bottom: 1.5px solid #000000; padding-bottom: 1px; min-width: 12px; }}
            .v-frac .den {{ padding-top: 2px; min-width: 12px; }}
            
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
