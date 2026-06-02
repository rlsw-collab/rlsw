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

# 🆕 全新升級 v1.3.3：動態注入題型數量(支援0條) + 徹底解決雙控制台變空白 Bug
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.3.3"

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
# 2. 輔助函式：GitHub 與圖片處理
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
    api_host = "https://generativelanguage.googleapis.com"
    api_route = "/v1beta/models/gemini-2.5-flash:generateContent"
    api_url = f"{api_host}{api_route}?key={GEMINI_TOKEN}"
    
    prompt = "你是一個100%精準的繁體中文與英文打字掃描儀。請一字不漏、按照段落順序將圖片中的所有教學課文 and 題目文字抄寫下來。直接輸出純文字，不要加入任何解釋。"
    parts = [{"text": prompt}]
    for b64 in b64_list:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    try:
        res = requests.post(api_url, headers={"Content-Type": "application/json"}, json={"contents": [{"parts": parts}]})
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except:
        pass
    return "❌ 圖片辨識失敗，請重試或手動輸入。"

# ==========================================
# 🚀 🚀 Python 終極分數與視覺排版引擎 (雙區獨立渲染) 🚀 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
    # 暴力預清洗 AI 連體字 Bug
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
    # 選擇題選項強制斷行清洗
    raw_text = re.sub(r'\s*([○●]\s*[A-D]\.)', r'\n\1', raw_text)
    
    raw_text = convert_to_vertical_fractions(raw_text)
    lines = raw_text.split('\n')
    processed_lines = []
    
    # 引入「當前章節追蹤器」
    current_section = ""
    
    for line in lines:
        if not line.strip(): continue
        
        clean_line = line.replace("**", "").replace("###", "").strip()
        
        # 1. 識別考卷大標題（置中加大）
        if "數學科測驗" in clean_line or "數學科考試" in clean_line or ("考試" in clean_line and "部" not in clean_line and "題" not in clean_line and len(clean_line) < 35):
            processed_lines.append(f'<div class="exam-title-main">{clean_line}</div>')
            continue
            
        # 2. 識別個人資料欄
        if "班級" in clean_line or "姓名" in clean_line or "班別" in clean_line:
            processed_lines.append(f'<div class="exam-user-info">{clean_line}</div>')
            continue

        # 3. 識別副題目（甲乙丙丁部）
        if re.search(r'^[甲乙丙丁]部：', clean_line) or "部：" in clean_line:
            current_section = clean_line
            processed_lines.append(f'<div class="exam-section-header">{clean_line}</div>')
            continue

        # 4. 選擇題選項強制換行
        if re.search(r'[○●]\s*[A-D]\.', line):
            if "●" in line: line = line.replace("●", '<span class="mc-ans">●</span>')
            processed_lines.append(f'<div class="mc-option">{line}</div>')
            continue
            
        # 5. 填充題
        if "填空" in clean_line or "填充" in clean_line:
            processed_lines.append(f'<div class="fill-blank-row">{line}</div>')
            continue

        # 6. 計算題或應用題（只有在題目卷、且當前章節為丙部/丁部、且非答案卷時，才鋪設 4 條虛線！）
        is_applied_or_calc_section = any(s in current_section for s in ["丙部", "丁部", "計算", "應用題", "文字題"])
        if re.match(r'^\d+\.', clean_line) and not is_answer_key and is_applied_or_calc_section:
            processed_lines.append(f'<div class="question-text">{line}</div>')
            processed_lines.append('<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>')
            continue
            
        processed_lines.append(f'<div>{line}</div>')
        
    return "\n".join(processed_lines)

# ==========================================
# 3. Streamlit 網頁單欄直落式佈局
# ==========================================
# 初始化雙獨立狀態機記憶
if 'generated_exam' not in st.session_state: st.session_state['generated_exam'] = ""
if 'generated_answers' not in st.session_state: st.session_state['generated_answers'] = ""

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
        with st.spinner("🚀 正在開啟 Gemini 智慧分流大腦，全力出題中..."):
            contents = []
            final_vault_text = read_from_exam_vault()
            
            # 定義動態說明的文字，精準限制題數
            mc_instruction = f"必須剛好生成【{mc_count}】題。編號接著前面。" if mc_count > 0 else "不要出任何多項選擇題，甲部留空。"
            fill_instruction = f"必須剛好生成【{fill_count}】題。編號接著前面。" if fill_count > 0 else "不要出任何填充題，乙部留空。"
            calc_instruction = f"必須剛好生成【{calc_count}】題。編號接著前面。" if calc_count > 0 else "不要出任何列式計算題，丙部留空。"
            text_instruction = f"必須剛好生成【{text_count}】題。編號接著前面。" if text_count > 0 else "不要出任何長題目文字題，丁部留空。"
            
            prompt_text = f"""你是一位熟知香港小學課程、傳統名校考卷風格的資深老師。請為【香港小學{grade}】的學生，製作一份【{subject}】科測驗/考試卷。
            
            🎯【格式輸出最高命令 - 請嚴格回傳標準 JSON 結構】：
            請輸出一個標準的 JSON 物件，結構如下：
            {{
              "exam_body": "這裡填寫整份試卷的題目正文（包含試卷大標題、班級姓名欄位、甲乙丙丁部副題目、以及所有題目文字。選擇題選項使用 ○ A. 格式開頭。分數一律採用純文字 3/5 或 2 1/4）",
              "answer_body": "這裡填寫完整的答案頁內容（包含答案大標題、甲乙丙丁部，每道題都要列出詳細計算過程及最終正確答案）"
            }}
            """
            
            if range_mode == "提供範圍":
                prompt_text += f"\n🎯【出題內容命令】：請完全根據以下文本內容出題：\n「{final_vault_text}」\n"
            else:
                prompt_text += f"\n🎯【出題內容命令】：請精準看懂下方上傳圖片的工作紙內容、考點和難度，並出一套相似且全新的題目！\n"
            
            prompt_text += """
            分數格式請使用純文字的分式表示：分子/分母 (例如: 3/5 或 1/4) 或 帶分數 (例如: 2 1/3 或 3 1/2)，中間可以有空格，乘號用 x，除號用 ÷。
            選擇題格式：
            1. 問題文字 ○ A. 選項一 ○ B. 選項二 ○ C. 選項三 ○ D. 選項四
            """
            
            contents.append(prompt_text)
            if uploaded_files:
                for f in uploaded_files:
                    mime_type = "application/pdf" if f.name.endswith(".pdf") else "image/jpeg"
                    contents.append({
                        "mime_type": mime_type, 
                        "data": f.getvalue()
                    })
            
            api_host = "https://generativelanguage.googleapis.com"
            api_route = "/v1beta/models/gemini-2.5-flash:generateContent"
            api_url = f"{api_host}{api_route}?key={GEMINI_TOKEN}"
            
            # 🌟 核心修正一：將 Slider 嘅題數與0條控制，以強硬的 JSON Schema 規則灌入 AI 限制器
            payload = {
                "contents": [],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "exam_body": {
                                "type": "STRING",
                                "description": f"題目正卷。要求：甲部多項選擇題：{mc_instruction}；乙部填充題：{fill_instruction}；丙部列式計算題：{calc_instruction}；丁部長題目應用題：{text_instruction}"
                            },
                            "answer_body": {
                                "type": "STRING",
                                "description": "答案頁。必須對應上述出好的題目，一題不漏地提供詳細計算步驟和最終正確答案。"
                            }
                        },
                        "required": ["exam_body", "answer_body"]
                    }
                }
            }
            
            for item in contents:
                if isinstance(item, str):
                    payload["contents"].append({"parts": [{"text": item}]})
                else:
                    payload["contents"].append({
                        "parts": [
                            {"text": "如下是工作紙的圖片內容："},
                            {"inline_data": {"mime_type": item["mime_type"], "data": base64.b64encode(item["data"]).decode("utf-8")}}
                        ]
                    })
            
            try:
                res = requests.post(api_url, headers={"Content-Type": "application/json"}, json=payload)
                if res.status_code == 200:
                    raw_ai_output = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    parsed_json = json.loads(raw_ai_output)
                    
                    # ✨ 寫入後台狀態，並同步寫入 TextBox 內置狀態，防丟記憶鎖死！
                    st.session_state['generated_exam'] = parsed_json.get("exam_body", "")
                    st.session_state['generated_answers'] = parsed_json.get("answer_body", "")
                    st.session_state['exam_text_editor'] = parsed_json.get("exam_body", "")
                    st.session_state['ans_text_editor'] = parsed_json.get("answer_body", "")
                    
                    st.success("🎉 題目與答案分流成功！已各自送入下方獨立控制台。")
                    st.rerun()
                else:
                    st.error(f"❌ API 出題報錯: {res.text}")
            except Exception as e:
                st.error(f"❌ 分流解析失敗，請重試。原因: {str(e)}")

# ==========================================
# 🧱 模組 5：題目與答案超大雙暫存區控制台（橫向拉滿）
# ==========================================
st.write("---")
st.header("📝 步驟三：獨立原始碼控制台 (雙區獨立)")

col_edit1, col_edit2 = st.columns(2)

with col_edit1:
    st.subheader("💻 題目原始碼暫存區 (只管題目)")
    # 🌟 核心修正二：完美的 Session 雙向對齊同步函數，保證不丟失不打架
    if 'exam_text_editor' not in st.session_state:
        st.session_state['exam_text_editor'] = st.session_state['generated_exam']
        
    def on_exam_change(): 
        st.session_state['generated_exam'] = st.session_state['exam_text_editor']
        
    stored_exam = st.text_area(
        "可在這裡直接手動修改或貼上題目：",
        value=st.session_state['exam_text_editor'],
        height=450,
        key="exam_text_editor",
        on_change=on_exam_change
    )

with col_edit2:
    st.subheader("🔑 答案原始碼暫存區 (只管答案)")
    if 'ans_text_editor' not in st.session_state:
        st.session_state['ans_text_editor'] = st.session_state['generated_answers']
        
    def on_ans_change(): 
        st.session_state['generated_answers'] = st.session_state['ans_text_editor']
        
    stored_ans = st.text_area(
        "可在這裡直接手動修改或貼上答案、過程：",
        value=st.session_state['ans_text_editor'],
        height=450,
        key="ans_text_editor",
        on_change=on_ans_change
    )

# 🧱 模組 6：純排版測試按鈕與導出區
st.write("##")
package_name = st.text_input("📦 請輸入這個考試包裹的名稱 (選填)")
btn_render = st.button("🎨 步驟四：執行 Python 引擎，更新並渲染視覺排版 🔄", type="primary", use_container_width=True)

# --- 試卷預覽與專業打印區塊 ---
if st.session_state['generated_exam'] or st.session_state['generated_answers']:
    st.write("---")
    st.header("🖨️ 專業印刷級預覽面版 (雙區完美對齊)")
    
    # 智慧調用各自的渲染引擎
    perfect_exam_html = python_layout_engine(st.session_state['generated_exam'], is_answer_key=False)
    perfect_ans_html = python_layout_engine(st.session_state['generated_answers'], is_answer_key=True)
    
    # 組合雙區，中間置入印刷強制換頁標籤
    full_html_content = perfect_exam_html + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + perfect_ans_html
    
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
        
        /* 個人資料欄位 */
        .exam-user-info {{
            font-size: 18px !important;
            font-weight: bold !important;
            text-align: center !important;
            margin-bottom: 35px !important;
            word-spacing: 15px;
        }}
        
        /* 副題目（甲乙丙丁部）大字體、加粗、精美左邊框 */
        .exam-section-header {{
            font-size: 20px !important;
            font-weight: 800 !important;
            color: #000000 !important;
            margin-top: 30px !important;
            margin-bottom: 12px !important;
            border-left: 5px solid #000;
            padding-left: 10px;
        }}
        
        /* 真正完美的直式分數 */
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
        
        /* 印刷答題虛線（精準綁定題目頁） */
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
        <div id="exam-body">{full_html_content}</div>
    </body>
    </html>
    """
    import streamlit.components.v1 as components
    components.html(html_for_printing, height=1200, scrolling=True)
