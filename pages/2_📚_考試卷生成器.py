import streamlit as st
import requests
import json
import base64
import time
import re
import os
import datetime
from PIL import Image
import io

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 🆕 升級 v1.5.9：純免費特攻版 (Google 3路免費大腦 + GitHub 綠色通道 GPT-4o 終極防線 + iPad OS 列印優化 + 填充答題線 3 倍長優化)
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.5.9"

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

# 注入母網頁的 @media print 打印樣式
st.markdown("""
<style>
@media print {
    div[data-testid="stSidebar"],
    header[data-testid="stHeader"],
    footer,
    div[data-testid="stToolbar"],
    .stButton, .stSlider, .stRadio, .stSelectbox, .stTextArea, .stFileUploader,
    h1, h2, h3, h4, h5, h6, p, span, hr, .stMarkdown {
        display: none !important;
    }
    iframe {
        display: block !important;
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        height: 100% !important;
        border: none !important;
        margin: 0 !important;
        padding: 0 !important;
        z-index: 9999999 !important;
        background-color: white !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 安全金鑰設定與【實體檔案保險箱機制】
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GIT_TOKEN"]
    GEMINI_TOKEN = st.secrets["GEMINI_TOKEN"]
    AI_TOKEN = st.secrets.get("AI_TOKEN", "") # 默書工具用的 GitHub Key，用來開闢 GitHub 免費 Models 綠色通道
    GITHUB_REPO = "rlsw"
    GITHUB_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到基礎憑證 (GIT_TOKEN 或 GEMINI_TOKEN)。")
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
# 🛡️ GitHub 雲端實時計數同步邏輯 (防衝突 ＆ 安全自癒)
# ==========================================
def get_hkt_date_str():
    tz_hkt = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_hkt).strftime("%Y-%m-%d")

def increment_github_counter(counter_type):
    """
    counter_type: "main" (主攻) 或 "backup" (後備)
    """
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    today_str = get_hkt_date_str()
    default_counter = {
        "last_reset_date": today_str,
        "exam_tool": {"main": 0, "backup": 0},
        "dictation_tool": {"main": 0, "backup": 0}
    }
    
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                counter = json.loads(content)
                sha = data["sha"]
            else:
                counter = default_counter
                sha = None
                
            # 安全自癒：如果舊 JSON 缺少新欄位，自動初始化它，防止 KeyError 崩潰
            if "exam_tool" not in counter:
                counter["exam_tool"] = {"main": 0, "backup": 0}
            if "dictation_tool" not in counter:
                counter["dictation_tool"] = {"main": 0, "backup": 0}
                
            if counter.get("last_reset_date") != today_str:
                counter["last_reset_date"] = today_str
                counter["exam_tool"] = {"main": 0, "backup": 0}
                counter["dictation_tool"] = {"main": 0, "backup": 0}
                
            # 累加計數至試卷生成專屬欄位
            counter["exam_tool"][counter_type] += 1
            
            content_str = json.dumps(counter, indent=2)
            content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"Increment exam {counter_type} counter [skip ci]",
                "content": content_b64
            }
            if sha:
                payload["sha"] = sha
                
            put_res = requests.put(url, headers=headers, json=payload)
            if put_res.status_code in [200, 201]:
                st.toast(f"📊 試卷雲端配額同步成功！今日已用「{counter_type}」：{counter['exam_tool'][counter_type]} 次", icon="📝")
                break
            time.sleep(0.5)
        except Exception as e:
            st.toast(f"⚠️ 雲端計數器同步失敗: {str(e)}", icon="❌")
            time.sleep(0.5)

# ==========================================
# 🧠 結構化 JSON 欄位修補與安全展平防護器
# ==========================================
def ensure_flat_string(val):
    """
    防護核心：若 AI 回傳了巢狀的 Dictionary 或 List 結構，
    自動且漂亮地將其還原成人類易讀的排版純文字，徹底阻斷 'dict' has no attribute 'replace' 報錯。
    """
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "\n".join(ensure_flat_string(item) for item in val)
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            k_clean = str(k).strip()
            # 針對常見考卷屬性進行人性化文本還原
            if k_clean.lower() in ["title", "header", "name", "subject", "grade"]:
                lines.append(ensure_flat_string(v))
            elif k_clean.lower() in ["questions", "items", "choices", "options", "body", "content", "exam_body", "answer_body"]:
                lines.append(ensure_flat_string(v))
            else:
                lines.append(f"{k_clean}: {ensure_flat_string(v)}")
        return "\n".join(lines)
    return str(val)

# ==========================================
# 🛡️ 智慧純免費出題：GitHub 綠色通道 GPT-4o (100% 繞過 Gemini)
# ==========================================
def call_pure_free_multiverse_ai(text_prompt):
    """
    題目生成：100% 僅調用 GitHub 綠色通道 GPT-4o (使用 AI_TOKEN)
    """
    if AI_TOKEN:
        st.toast("🚀 正在啟用 GitHub 綠色通道：GPT-4o 題目生成...", icon="⚡")
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_TOKEN}",
            "Content-Type": "application/json"
        }
        github_payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a professional JSON output assistant. You must return a strict JSON object with fields 'exam_body' and 'answer_body' without any markdown block formatting. Do not output nested dictionaries or lists under these fields."},
                {"role": "user", "content": text_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }
        try:
            res = requests.post(url, headers=headers, json=github_payload, timeout=75)
            if res.status_code == 200:
                raw_content = res.json()['choices'][0]['message']['content'].strip()
                # 預防性清洗 markdown 符號
                raw_content = re.sub(r'^```json\s*', '', raw_content)
                raw_content = re.sub(r'\s*```$', '', raw_content).strip()
                
                # 併入後備計數器統計中 (GitHub 綠色通道對應後備進度條)
                increment_github_counter("backup")
                return json.loads(raw_content), "github-gpt-4o"
            else:
                st.toast(f"⚠️ GitHub 綠色通道接口回應異常: {res.status_code}", icon="❌")
        except Exception as e:
            st.toast(f"⚠️ GitHub 綠色通道請求失敗: {str(e)}", icon="❌")

    return None, None

# ==========================================
# 2. 輔育函式：圖片處理 & OCR 保底 (100% 僅調用 Gemini)
# ==========================================
def convert_image_to_base64(file_val):
    image = Image.open(io.BytesIO(file_val))
    if image.mode != "RGB": image = image.convert("RGB")
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def do_gemini_ocr_with_fallback(b64_list, gemini_token):
    prompt = "你是一個100%精準的繁體中文與英文打字掃描儀。請一字不漏、按照段落順序將圖片中的所有教學課文 and 題目文字抄寫下來。直接輸出純文字，不要加入任何解釋。"
    parts = [{"text": prompt}]
    for b64 in b64_list:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        
    payload = {"contents": [{"parts": parts}]}
    models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash"]
    
    for model_id in models:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_token}"
        try:
            res = requests.post(api_url, headers={"Content-Type": "application/json"}, json=payload, timeout=40)
            if res.status_code == 200:
                st.toast(f"📸 OCR 成功調用模型：{model_id}", icon="✅")
                # OCR 成功調用 Gemini，計入主攻通道 (Flash)
                increment_github_counter("main")
                return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except:
            continue
    return "❌ 圖片辨識失敗，所有 Google 免費通道均超時，請稍候重試或手動輸入。"

# ==========================================
# 🚀 🚀 Python 終極分數與視覺排版引擎 🚀 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
    text_content = text_content.replace("312", " 3 1/2 ").replace("213", " 2 1/3 ").replace("214", " 2 1/4 ")
    text_content = text_content.replace("334", " 3 3/4 ").replace("212", " 2 1/2 ").replace("138", " 1 3/8 ")
    text_content = text_content.replace("1025", " 10 2/5 ").replace("1310", " 1 3/10 ").replace("712", " 7 1/2 ").replace("56", " 5/6 ")
    
    text_content = re.sub(r'(?<!\d)14(?!\d|\.)', '1/4', text_content)
    text_content = re.sub(r'(?<!\d)38(?!\d|\.)', '3/8', text_content)
    text_content = re.sub(r'(?<!\d)12(?!\d|\.)', '1/2', text_content)

    text_content = re.sub(r'(\d+)\s*又\s*(\d+)\s*分之\s*(\d+)', r'\1<span class="v-frac"><span class="num">\3</span><span class="den">\2</span></span>', text_content)
    text_content = re.sub(r'(\d+)\s*又\s*(\d+)/(\d+)', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', text_content)
    text_content = re.sub(r'(?<!\d)(\d+)\s*分之\s*(\d+)(?!\d)', r'<span class="v-frac"><span class="num">\2</span><span class="den">\1</span></span>', text_content)

    text_content = re.sub(r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', text_content)
    text_content = re.sub(r'(?<!/)(?<!<)(?<!\d)(\d+)/(\d+)(?!\d)(?!>)', r'<span class="v-frac"><span class="num">\1</span><span class="den">\2</span></span>', text_content)
    return text_content

def python_layout_engine(raw_text, is_answer_key=False):
    if raw_text:
        raw_text = raw_text.replace("\\n", "\n").replace("\\\\n", "\n")
        
    raw_text = re.sub(r'\s*([○●]\s*[A-D]\.)', r'\n\1', raw_text)
    raw_text = convert_to_vertical_fractions(raw_text)
    lines = raw_text.split('\n')
    processed_lines = []
    current_section = ""
    
    for line in lines:
        if not line.strip(): continue
        clean_line = line.replace("**", "").replace("###", "").strip()
        
        # 🌟 智慧正則：將任何連續 2 個以上的半形底線（_）或全形底線（＿）替換成拉長 3 倍的專業 HTML 答題線
        line = re.sub(r'([_＿]{2,})', r'<span class="fill-blank-underline"></span>', line)
        # 🌟 智慧正則：將括號內有空格的（如 "(   )" 或 "（   ）"）替換為內嵌 3 倍寬度底線的精緻答題區
        line = re.sub(r'([\(（])\s{2,}([\)）])', r'\1 <span class="fill-blank-underline"></span> \2', line)
        
        if "數學科測驗" in clean_line or "數學科考試" in clean_line or ("考試" in clean_line and "部" not in clean_line and "题" not in clean_line and len(clean_line) < 35):
            processed_lines.append(f'<div class="exam-title-main">{clean_line}</div>')
            continue
            
        if "班級" in clean_line or "姓名" in clean_line or "班別" in clean_line:
            processed_lines.append(f'<div class="exam-user-info">{clean_line}</div>')
            continue

        if re.search(r'^[甲乙丙丁]部：', clean_line) or "部：" in clean_line:
            current_section = clean_line
            processed_lines.append(f'<div class="exam-section-header">{clean_line}</div>')
            continue

        if re.search(r'[○●]\s*[A-D]\.', line):
            if "●" in line: line = line.replace("●", '<span class="mc-ans">●</span>')
            processed_lines.append(f'<div class="mc-option">{line}</div>')
            continue
            
        if "填空" in clean_line or "填充" in clean_line:
            processed_lines.append(f'<div class="fill-blank-row">{line}</div>')
            continue

        is_applied_or_calc_section = any(s in current_section for s in ["丙部", "丁部", "計算", "應用題", "文字題"])
        if re.match(r'^\d+\.', clean_line) and not is_answer_key and is_applied_or_calc_section:
            processed_lines.append(f'<div class="question-text">{line}</div>')
            processed_lines.append('<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>')
            continue
            
        processed_lines.append(f'<div>{line}</div>')
        
    return "\n".join(processed_lines)

# ==========================================
# 3. Streamlit 網頁佈局
# ==========================================
if 'generated_exam' not in st.session_state: st.session_state['generated_exam'] = ""
if 'generated_answers' not in st.session_state: st.session_state['generated_answers'] = ""

current_vault_ocr = read_from_exam_vault()
vault_hash = str(len(current_vault_ocr)) + "_" + str(hash(current_vault_ocr))

st.header("📋 步驟一：基本資料與功能設定")
col_meta1, col_meta2 = st.columns(2)
with col_meta1: subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
with col_meta2: grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])

st.write("##")
st.markdown("### 🔢 設定各題型生成數量 (可調成 0 表示該題型不需出題)")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1: mc_count = st.slider("多項選擇題 (題數)", 0, 30, 5, step=5)
with col_s2: fill_count = st.slider("填充題 (題數)", 0, 30, 5, step=5)
with col_s3: calc_count = st.slider("列式計算題 (題數)", 0, 30, 5, step=5)
with col_s4: text_count = st.slider("長題目文字題 (題數)", 0, 30, 5, step=5)

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

st.write("##")
if range_mode == "提供範圍":
    if uploaded_files and st.button("🔍 點擊執行 Gemini 圖片字元識別 (OCR)", use_container_width=True):
        with st.spinner("正在將圖片文字提取並寫入實體保險箱..."):
            b64_list = [convert_image_to_base64(f.getvalue()) for f in uploaded_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
            extracted_txt = do_gemini_ocr_with_fallback(b64_list, GEMINI_TOKEN)
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

st.write("##")
btn_call_ai = st.button("🚀 呼叫 AI 免費多通道生成新題目 🤖", type="secondary", use_container_width=True)

if btn_call_ai:
    # 這裡的防護：只有在「所有滑桿都調到 0」的情況下才會阻擋。任一題型大於 0（其餘為 0）是完全允許的！
    if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
        st.error("❌ 請至少將一項題型的滑桿調大於 0！")
    else:
        with st.spinner("🚀 正在連動 GitHub 綠色通道 GPT-4o，全力出題中..."):
            contents = []
            final_vault_text = read_from_exam_vault()
            
            # 設定個別題型的指令，如果是 0 則明確命令不要生成
            mc_instruction = f"必須剛好生成【{mc_count}】題。" if mc_count > 0 else "不要出 any 多項選擇題，甲部留空。"
            fill_instruction = f"必須剛好生成【{fill_count}】題。" if fill_count > 0 else "不要出 any 填充題，乙部留空。"
            calc_instruction = f"必須剛好生成【{calc_count}】題。" if calc_count > 0 else "不要出 any 列式計算題，丙部留空。"
            text_instruction = f"必須剛好生成【{text_count}】題。" if text_count > 0 else "不要出 any 長題目文字題，丁部留空。"
            
            text_prompt = f"""你是一位熟知香港小學課程、傳統名校考卷風格的資深老師。請為【香港小學{grade}】的學生，製作一份【{subject}】科測驗/考試卷。
            🎯【格式輸出命令 - 請嚴格回傳標準 JSON 物件】：
            {{
              "exam_body": "包含試卷大標題、班級姓名欄位、甲乙丙丁部副題目、題目。選擇題格式為 ○ A. 選項一 ○ B. 選項二...",
              "answer_body": "包含答案頁大標題、甲乙丙丁部、詳細計算過程及最終正確答案"
            }}
            數量要求：多項選擇題{mc_instruction}、填充題{fill_instruction}、列式計算題{calc_instruction}、長題目{text_instruction}。
            分數格式：優先用純文字如 3/5 或 2 1/4，如果寫中文必須寫成標準的「5又6分之1」格式。
            """
            if range_mode == "提供範圍":
                text_prompt += f"\n🎯【出題內容命令】：請完全根據以下文本內容出題：\n「{final_vault_text}」\n"
            else:
                text_prompt += f"\n🎯【出題內容命令】：請精準看懂提供之圖片工作紙考點，出一套相似且全新的題目！\n"
            
            # 🌟 僅呼叫 GitHub 綠色通道 GPT-4o
            parsed_json, used_model = call_pure_free_multiverse_ai(text_prompt)
            
            try:
                if parsed_json and ("exam_body" in parsed_json or "answer_body" in parsed_json):
                    # 🌟 透過安全展平防禦，確保絕不發生 dict attribute replace 崩潰
                    ex_raw = parsed_json.get("exam_body", "")
                    ans_raw = parsed_json.get("answer_body", "")
                    
                    ex_body = ensure_flat_string(ex_raw).replace("\\n", "\n").replace("\\\\n", "\n")
                    ans_body = ensure_flat_string(ans_raw).replace("\\n", "\n").replace("\\\\n", "\n")
                    
                    st.session_state['generated_exam'] = ex_body
                    st.session_state['generated_answers'] = ans_body
                    st.session_state['exam_text_editor'] = ex_body
                    st.session_state['ans_text_editor'] = ans_body
                    st.success(f"🎉 試卷由純免費通道生成成功！(最終調用功臣大腦: {used_model})")
                    st.rerun()
                else:
                    st.error("❌ GitHub 綠色通道今日配額已用盡或連線超時！請等候 Reset 重置後再試。")
            except Exception as e: 
                st.error(f"❌ 解析免費數據結構失敗。原因: {str(e)}")

# ==========================================
# 3. 獨立原始碼控制台 (雙區獨立)
# ==========================================
st.write("---")
st.header("📝 步驟三：獨立原始碼控制台 (雙區獨立)")
col_edit1, col_edit2 = st.columns(2)
with col_edit1:
    st.subheader("💻 題目原始碼暫存區")
    if 'exam_text_editor' not in st.session_state: st.session_state['exam_text_editor'] = st.session_state['generated_exam']
    def on_exam_change(): st.session_state['generated_exam'] = st.session_state['exam_text_editor']
    st.text_area("題目微調：", height=450, key="exam_text_editor", on_change=on_exam_change)
with col_edit2:
    st.subheader("🔑 答案原始碼暫存區")
    if 'ans_text_editor' not in st.session_state: st.session_state['ans_text_editor'] = st.session_state['generated_answers']
    def on_ans_change(): st.session_state['generated_answers'] = st.session_state['ans_text_editor']
    st.text_area("答案微調：", value=st.session_state['ans_text_editor'], height=450, key="ans_text_editor", on_change=on_ans_change)

# ==========================================
# 4. 視覺排版與控制台
# ==========================================
st.write("---")
st.header("🎨 步驟四：視覺排版與打印導出")

if st.session_state['generated_exam'] or st.session_state['generated_answers']:
    perfect_exam_html = python_layout_engine(st.session_state['generated_exam'], is_answer_key=False)
    perfect_ans_html = python_layout_engine(st.session_state['generated_answers'], is_answer_key=True)
    full_html_content = perfect_exam_html + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + perfect_ans_html
    
    # 建立電腦版即時打印呼叫，若在 iPad 上則提供專屬獨立 HTML 導出
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_render = st.button("🔄 點擊執行 Python 引擎，更新視覺排版", type="secondary", use_container_width=True)
    with col_btn2:
        trigger_print = st.button("🖨️ 手提電腦專用：立即列印 / 匯出 PDF", type="secondary", use_container_width=True)
        
    auto_print_js = "window.print();" if trigger_print else ""

    # 編譯完整 HTML 打印文檔架構 (已調校 3 倍長答題線)
    html_for_printing = f"""
    <!DOCTYPE html>
    <html style="background-color: white !important; color: black !important; color-scheme: light !important;">
    <head>
    <meta charset="utf-8">
    <meta name="color-scheme" content="light">
    <style>
        :root {{ color-scheme: light !important; }}
        html, body {{ background-color: white !important; color: #000000 !important; -webkit-text-fill-color: #000000 !important; }}
        #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; color: #000000 !important; padding: 20px; font-size: 16px; line-height: 2.3; }}
        .exam-title-main {{ font-size: 26px !important; font-weight: 800 !important; text-align: center !important; margin-top: 25px !important; margin-bottom: 15px !important; letter-spacing: 2px; color: #000000 !important; }}
        .exam-user-info {{ font-size: 18px !important; font-weight: bold !important; text-align: center !important; margin-bottom: 35px !important; word-spacing: 15px; color: #000000 !important; }}
        .exam-section-header {{ font-size: 20px !important; font-weight: 800 !important; color: #000000 !important; margin-top: 30px !important; margin-bottom: 12px !important; border-left: 5px solid #000 !important; padding-left: 10px; }}
        
        /* 🌟 完美的 3 倍長填充題印刷答題線 */
        .fill-blank-underline {{
            display: inline-block;
            width: 180px; /* 3倍超長設計，提供充足書寫空間 */
            border-bottom: 1.5px solid #000000 !important;
            margin: 0 10px;
            height: 18px;
            vertical-align: bottom;
        }}

        .v-frac {{ display: inline-flex; flex-direction: column; vertical-align: middle; text-align: center; line-height: 1.0; padding: 0 4px; font-size: 0.85em; position: relative; top: -0.15em; }}
        .v-frac .num {{ border-bottom: 1.5px solid #000000; padding-bottom: 2px; min-width: 14px; font-weight: 600; }}
        .v-frac .den {{ padding-top: 2px; min-width: 14px; font-weight: 600; }}
        .mc-option {{ margin-left: 20px; margin-top: 8px; margin-bottom: 8px; display: block !important; clear: both; color: #000000 !important; }}
        .question-text {{ font-weight: bold; margin-top: 25px; margin-bottom: 12px; color: #000000 !important; }}
        .fill-blank-row {{ margin-top: 14px; margin-bottom: 14px; color: #000000 !important; }}
        .write-zone {{ margin-top: 12px; margin-bottom: 25px; width: 100%; }}
        .row-line {{ width: 100%; height: 38px; border-bottom: 1px dashed #999 !important; }}
        .page-break {{ page-break-before: always; }}
        .ans-header {{ color: #ff4b4b !important; border-bottom: 2px solid #ff4b4b !important; padding-bottom: 10px; margin-top: 35px; font-size: 24px; text-align: center; }}
        @media print {{ html, body {{ background-color: white; color: #000000; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }} }}
    </style>
    </head>
    <body>
        <div id="exam-body">{full_html_content}</div>
        <script>{auto_print_js}</script>
    </body>
    </html>
    """

    # iPad 專屬一鍵破解 WebKit Iframe 打印缺陷之安全下載通道
    st.info("💡 **iPad / iPhone / 手機 Chrome 打印提示**：\niOS 系統（WebKit 內核限制）會強行鎖死網頁內嵌框架（Iframe），導致直接列印時只會出現 Page 1。\n\n請點擊下方**下載專屬 HTML 檔案**，在 iPad 下載點開後，即可進行完美的多頁列印與 PDF 匯出！")
    
    st.download_button(
        label="📲 iPad / 手提裝置專用：下載完整 HTML 列印檔",
        data=html_for_printing,
        file_name=f"香港小學{grade}_{subject}_試卷.html",
        mime="text/html",
        use_container_width=True,
        type="primary"
    )

    st.write("##")
    import streamlit.components.v1 as components
    components.html(html_for_printing, height=1200, scrolling=True)
else:
    st.info("💡 請先在上方的步驟二生成或提供題目數據。")
