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

# 🆕 升級 v1.6.5：幾何自動偵測特攻版 (關鍵字自動繪圖 + Step 5 滑桿機制 + iPad OS 列印優化)
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.6.5"

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
    AI_TOKEN = st.secrets.get("AI_TOKEN", "") # GitHub 免費 Models 綠色通道 Key
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
            if "exam_tool" not in counter: counter["exam_tool"] = {"main": 0, "backup": 0}
            if counter.get("last_reset_date") != today_str:
                counter["last_reset_date"] = today_str
                counter["exam_tool"] = {"main": 0, "backup": 0}
            counter["exam_tool"][counter_type] += 1
            content_str = json.dumps(counter, indent=2)
            content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
            payload = {"message": f"Increment exam {counter_type} counter [skip ci]", "content": content_b64}
            if sha: payload["sha"] = sha
            put_res = requests.put(url, headers=headers, json=payload)
            if put_res.status_code in [200, 201]:
                st.toast(f"📊 今日已用「{counter_type}」：{counter['exam_tool'][counter_type]} 次", icon="📝")
                break
            time.sleep(0.5)
        except:
            time.sleep(0.5)

def ensure_flat_string(val):
    if val is None: return ""
    if isinstance(val, str): return val
    if isinstance(val, list): return "\n".join(ensure_flat_string(item) for item in val)
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            k_clean = str(k).strip()
            if k_clean.lower() in ["title", "header", "name", "subject", "grade", "questions", "items", "choices", "options", "body", "content", "exam_body", "answer_body"]:
                lines.append(ensure_flat_string(v))
            else:
                lines.append(f"{k_clean}: {ensure_flat_string(v)}")
        return "\n".join(lines)
    return str(val)

# ==========================================
# 🛡️ AI 題目生成通道 (GitHub GPT-4o 綠色通道)
# ==========================================
def call_pure_free_multiverse_ai(text_prompt):
    if AI_TOKEN:
        st.toast("🚀 正在啟用 GitHub 綠色通道：GPT-4o 題目與幾何 SVG 建模生成...", icon="⚡")
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_TOKEN}",
            "Content-Type": "application/json"
        }
        github_payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a professional JSON output assistant. You must return a strict JSON object with fields 'exam_body' and 'answer_body'. You are allowed to embed geometric block markers like [GEOMETRIC:type:param1=val1;param2=val2] in exam_body to trigger custom drawing engines."},
                {"role": "user", "content": text_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }
        try:
            res = requests.post(url, headers=headers, json=github_payload, timeout=75)
            if res.status_code == 200:
                raw_content = res.json()['choices'][0]['message']['content'].strip()
                raw_content = re.sub(r'^```json\s*', '', raw_content)
                raw_content = re.sub(r'\s*```$', '', raw_content).strip()
                increment_github_counter("backup")
                return json.loads(raw_content), "github-gpt-4o"
        except Exception as e:
            st.toast(f"⚠️ GitHub 通道失敗: {str(e)}", icon="❌")
    return None, None

def do_gemini_ocr_with_fallback(b64_list, gemini_token):
    prompt = "你是一個100%精準的繁體中文與英文幾何工作紙打字掃描儀。請將圖片中的所有幾何圖形題目文字、數字、選項抄寫下來。直接輸出純文字，不要加入任何解釋。"
    parts = [{"text": prompt}]
    for b64 in b64_list: parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    payload = {"contents": [{"parts": parts}]}
    models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash"]
    for model_id in models:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_token}"
        try:
            res = requests.post(api_url, headers={"Content-Type": "application/json"}, json=payload, timeout=40)
            if res.status_code == 200:
                increment_github_counter("main")
                return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except: continue
    return "❌ 圖片辨識失敗，請稍候重試或手動輸入。"

# ==========================================
# 🎨 🛠️ 核心：幾何圖形 SVG 印刷級動態渲染器 🛠️ 🎨
# ==========================================
def draw_svg_geometry(marker_str):
    """
    解析語法：[GEOMETRIC:type:param1=val1;param2=val2]
    並動態回傳黑白高對比、印刷級幾何向量圖
    """
    try:
        marker_str = marker_str.replace("[", "").replace("]", "")
        parts = marker_str.split(":")
        if len(parts) < 3: return ""
        g_type = parts[1].strip()
        param_pairs = parts[2].split(";")
        params = {}
        for pair in param_pairs:
            if "=" in pair:
                k, v = pair.split("=")
                params[k.strip()] = v.strip()
                
        svg_code = ""
        
        # 題型一：三圓連心切點題 (模擬工作紙第3, 5題)
        if g_type == "three_circles_linear":
            r1 = params.get("r1", "6")
            r2 = params.get("r2", "4")
            r3 = params.get("r3", "3")
            svg_code = f"""
            <div style="text-align:center; margin:15px 0;">
            <svg width="280" height="150" style="background:white;">
                <!-- 大圓 -->
                <circle cx="100" cy="75" r="55" stroke="black" stroke-width="1.8" fill="none" />
                <!-- 中圓 -->
                <circle cx="85" cy="75" r="40" stroke="black" stroke-width="1.5" fill="none" stroke-dasharray="2 2" />
                <!-- 小圓 -->
                <circle cx="180" cy="75" r="25" stroke="black" stroke-width="1.8" fill="none" />
                <!-- 連心輔助虛線 -->
                <line x1="45" y1="75" x2="205" y2="75" stroke="black" stroke-width="1" stroke-dasharray="4" />
                <!-- 圓心標記 -->
                <circle cx="45" cy="75" r="2.5" fill="black"/><text x="40" y="95" font-size="13" font-family="sans-serif">P</text>
                <circle cx="85" cy="75" r="2.5" fill="black"/><text x="80" y="95" font-size="13" font-family="sans-serif">Q</text>
                <circle cx="180" cy="75" r="2.5" fill="black"/><text x="175" y="95" font-size="13" font-family="sans-serif">R</text>
                <!-- 數據標註 -->
                <text x="50" y="65" font-size="11" font-weight="bold" font-family="sans-serif">半徑 {r1}cm</text>
                <text x="170" y="65" font-size="11" font-weight="bold" font-family="sans-serif">半徑 {r3}cm</text>
            </svg>
            </div>
            """
            
        # 題型二：長方形內切雙圓題 (模擬工作紙第2題)
        elif g_type == "circles_in_rectangle":
            w = params.get("w", "20")
            h = params.get("h", "10")
            svg_code = f"""
            <div style="text-align:center; margin:15px 0;">
            <svg width="260" height="140" style="background:white;">
                <!-- 外框長方形 -->
                <rect x="20" y="20" width="220" height="100" stroke="black" stroke-width="2" fill="none" />
                <!-- 內切左圓 -->
                <circle cx="70" cy="70" r="50" stroke="black" stroke-width="1.5" fill="none" />
                <!-- 內切右圓 -->
                <circle cx="170" cy="70" r="50" stroke="black" stroke-width="1.5" fill="none" />
                <!-- 直徑/半徑箭頭標註 -->
                <line x1="70" y1="70" x2="120" y2="70" stroke="black" stroke-width="1.2" />
                <circle cx="70" cy="70" r="2" fill="black" />
                <!-- 長方形長寬標註 -->
                <text x="110" y="15" font-size="12" font-weight="bold" font-family="sans-serif">長方形長 = {w} cm</text>
                <text x="25" y="65" font-size="11" font-family="sans-serif" transform="rotate(-90 25,65)">闊 = {h} cm</text>
            </svg>
            </div>
            """
            
        # 題型三：大小圓重疊 / 半徑同心圓組合 (模擬工作紙第1, 4題)
        elif g_type == "concentric_overlap":
            d1 = params.get("d1", "14")
            svg_code = f"""
            <div style="text-align:center; margin:15px 0;">
            <svg width="220" height="160" style="background:white;">
                <!-- 大圓 -->
                <circle cx="110" cy="80" r="60" stroke="black" stroke-width="1.8" fill="none" />
                <!-- 內切小圓（過大圓圓心） -->
                <circle cx="110" cy="110" r="30" stroke="black" stroke-width="1.5" fill="none" />
                <!-- 圓心 -->
                <circle cx="110" cy="80" r="2.5" fill="black" />
                <text x="115" y="75" font-size="12" font-family="sans-serif">O (大圓心)</text>
                <circle cx="110" cy="110" r="2" fill="black" />
                <!-- 標註長度 -->
                <line x1="110" y1="20" x2="110" y2="140" stroke="black" stroke-width="1" stroke-dasharray="3" />
                <text x="115" y="50" font-size="11" font-weight="bold" font-family="sans-serif">大圓直徑 = {d1}cm</text>
            </svg>
            </div>
            """
        return svg_code
    except:
        return "📐 [幾何圖形加載錯誤] 📐"

# ==========================================
# 🚀 分數與幾何雙引擎渲染核心 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
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
        
        # 🌟 攔截幾何標記並進行 SVG 實時動態渲染 🌟
        geo_match = re.search(r'(\[GEOMETRIC:[^\]]+\])', line)
        if geo_match:
            full_marker = geo_match.group(1)
            svg_html = draw_svg_geometry(full_marker)
            line = line.replace(full_marker, svg_html)
        
        line = re.sub(r'([_＿]{2,})', r'<span class="fill-blank-underline"></span>', line)
        line = re.sub(r'([\(（])\s{2,}([\)）])', r'\1 <span class="fill-blank-underline"></span> \2', line)
        
        if "測驗" in clean_line or "考試" in clean_line or ("試卷" in clean_line and len(clean_line) < 35):
            processed_lines.append(f'<div class="exam-title-main">{clean_line}</div>')
            continue
        if "班級" in clean_line or "姓名" in clean_line or "學號" in clean_line:
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
with col_meta1: subject = st.selectbox("選擇科目", ["數學", "中文", "英文", "常識"])
with col_meta2: grade = st.selectbox("選擇年級", ["小五", "小六", "小四", "小三", "小二", "小一"])

st.write("##")
st.markdown("### 🔢 設定各題型生成數量 (可調成 0 關閉該題型)")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
# 🌟 所有滑桿值限制在 0, 5, 10, 15, 20, 25, 30 並移除了幾何專屬滑桿
with col_s1: mc_count = st.slider("多項選擇題", 0, 30, 5, step=5)
with col_s2: fill_count = st.slider("填充題", 0, 30, 5, step=5)
with col_s3: calc_count = st.slider("列式計算題", 0, 30, 0, step=5)
with col_s4: text_count = st.slider("長題目文字題", 0, 30, 0, step=5)

st.write("---")
st.header("🎯 步驟二：設定出題範圍來源")
range_mode = st.radio("範圍模式選擇：", ["提供範圍", "提供幾何工作紙模板"], horizontal=True)

uploaded_files = st.file_uploader("上傳工作紙進行智慧辨識", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)

st.write("##")
if range_mode == "提供範圍":
    if uploaded_files and st.button("🔍 點擊執行 Gemini 幾何字元提取 (OCR)", use_container_width=True):
        with st.spinner("正在辨識幾何工作紙文字並存入保險箱..."):
            b64_list = [convert_image_to_base64(f.getvalue()) for f in uploaded_files if f.name.lower().endswith(('png', 'jpg', 'jpeg'))]
            extracted_txt = do_gemini_ocr_with_fallback(b64_list, GEMINI_TOKEN)
            write_to_exam_vault(extracted_txt)
            st.success("✅ 文字解鎖成功！")
            st.rerun()
    text_input_val = st.text_area("📝 在此修改或輸入幾何範圍核心概念：", value=current_vault_ocr, height=200, key=f"ocr_box_{vault_hash}")
    if text_input_val != current_vault_ocr:
        write_to_exam_vault(text_input_val)
        current_vault_ocr = text_input_val
else:
    static_notice = "根據平面圓形組合幾何圖形工作紙考點"
    write_to_exam_vault(static_notice)
    st.text_area("📝 範圍狀態（已鎖定）：", value=static_notice, height=70, disabled=True)

st.write("##")
btn_call_ai = st.button("🚀 呼叫 AI 幾何引擎 + 綠色通道生成圖形試卷 🤖", type="secondary", use_container_width=True)

if btn_call_ai:
    if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
        st.error("❌ 請至少選擇一種題型的數量大於 0！")
    else:
        with st.spinner("🚀 幾何圖形引擎正在與 GitHub GPT-4o 進行多維度建模出題..."):
            final_vault_text = read_from_exam_vault()
            
            # 🌟 自動偵測幾何圖形關鍵字
            has_geometry_keywords = any(kw in final_vault_text for kw in ["圓", "三角", "面積", "體積"])
            
            geo_prompt_addon = ""
            if has_geometry_keywords:
                geo_prompt_addon = """
                ⚠️【幾何圖形自動繪圖出題命令】：
                由於目前設定的考試範圍內包含「圓、三角、面積、體積」等幾何概念，請你必須在適當的題目（特別是填充題或選擇題）中融入幾何圖案。
                每當需要為題目配上圖形時，請在該題目文字下方單獨佔一行，並精準嵌入以下格式的幾何標記（參數數值可根據你的出題數據自由調整，但格式必須100%精準）：
                - [GEOMETRIC:three_circles_linear:r1=6;r2=4;r3=3] (用於多圓重疊、圓心與切點連線題)
                - [GEOMETRIC:circles_in_rectangle:w=24;h=12] (用於長方形或正方形內切雙圓題)
                - [GEOMETRIC:concentric_overlap:d1=16] (用於大小圓重疊、同心圓或過圓心切圓題)
                """
            else:
                geo_prompt_addon = "\n（本次範圍不包含幾何概念，請以普通純文字題目為主。）"
            
            # 精細的幾何出題提示詞，命令 AI 必須正確嵌入圖形觸發標記
            text_prompt = f"""你是一位香港傳統小學（如喇沙、拔萃）的資深數學組組長。請為【香港小學{grade}】製作一份【{subject}科：圓形的性質與幾何組合測驗卷】。
            
            🎯【必須回傳的標準 JSON 物件格式】：
            {{
              "exam_body": "包含大標題、班級姓名欄、各部題目。",
              "answer_body": "包含答案頁大標題、每題的詳細計算公式、幾何關係、以及最終正確答案"
            }}

            🔢【題型數量嚴格命令】：
            1. 多項選擇題：生成 {mc_count} 題。
            2. 填充題：生成 {fill_count} 題。
            3. 列式計算題：生成 {calc_count} 題。
            4. 長題目文字題：生成 {text_count} 題。
            
            幾何出題考點範例參考：
            - 在長方形內有兩個相同的圓形緊貼內切，已知長方形長，求圓形半徑或長方形闊。
            - 三個圓心 P, Q, R 在同一條直線上，大圓半徑為 X cm，小圓半徑為 Y cm，求中間圓或最大外切範圍直徑。
            
            {geo_prompt_addon}
            """
            
            parsed_json, used_model = call_pure_free_multiverse_ai(text_prompt)
            
            if parsed_json and ("exam_body" in parsed_json or "answer_body" in parsed_json):
                ex_body = ensure_flat_string(parsed_json.get("exam_body", ""))
                ans_body = ensure_flat_string(parsed_json.get("answer_body", ""))
                st.session_state['generated_exam'] = ex_body
                st.session_state['generated_answers'] = ans_body
                st.session_state['exam_text_editor'] = ex_body
                st.session_state['ans_text_editor'] = ans_body
                st.success(f"🎉 幾何圖形試卷生成成功！(大腦功臣: {used_model})")
                st.rerun()
            else:
                st.error("❌ 出題超時或配額限制，請重試。")

# ==========================================
# 4. 獨立原始碼控制台 (雙區獨立)
# ==========================================
st.write("---")
st.header("📝 步驟三：幾何源碼調校控制台")
col_edit1, col_edit2 = st.columns(2)
with col_edit1:
    if 'exam_text_editor' not in st.session_state: st.session_state['exam_text_editor'] = st.session_state['generated_exam']
    def on_exam_change(): st.session_state['generated_exam'] = st.session_state['exam_text_editor']
    st.text_area("題目微調（可在這裏手動增刪 [GEOMETRIC:...] 標記變更圖形）：", height=400, key="exam_text_editor", on_change=on_exam_change)
with col_edit2:
    if 'ans_text_editor' not in st.session_state: st.session_state['ans_text_editor'] = st.session_state['generated_answers']
    def on_ans_change(): st.session_state['generated_answers'] = st.session_state['ans_text_editor']
    st.text_area("答案與詳解微調：", value=st.session_state['ans_text_editor'], height=400, key="ans_text_editor", on_change=on_ans_change)

# ==========================================
# 5. 視覺排版與 iPad 完美打印
# ==========================================
st.write("---")
st.header("🎨 步驟四：印刷級幾何排版與打印導出")

if st.session_state['generated_exam'] or st.session_state['generated_answers']:
    perfect_exam_html = python_layout_engine(st.session_state['generated_exam'], is_answer_key=False)
    perfect_ans_html = python_layout_engine(st.session_state['generated_answers'], is_answer_key=True)
    full_html_content = perfect_exam_html + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁與幾何解題詳解 (Answer Key)</h2>' + perfect_ans_html
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1: st.button("🔄 同步更新幾何視覺排版", type="secondary", use_container_width=True)
    with col_btn2: trigger_print = st.button("🖨️ 手提電腦：立即列印 / 匯出", type="secondary", use_container_width=True)
        
    auto_print_js = "window.print();" if trigger_print else ""

    html_for_printing = f"""
    <!DOCTYPE html>
    <html style="background-color: white !important; color: black !important;">
    <head>
    <meta charset="utf-8">
    <style>
        html, body {{ background-color: white !important; color: #000000 !important; -webkit-text-fill-color: #000000 !important; }}
        #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; padding: 20px; font-size: 16px; line-height: 2.3; }}
        .exam-title-main {{ font-size: 26px !important; font-weight: 800 !important; text-align: center !important; margin-top: 20px !important; margin-bottom: 15px !important; color: #000000 !important; }}
        .exam-user-info {{ font-size: 17px !important; font-weight: bold !important; text-align: center !important; margin-bottom: 30px !important; word-spacing: 12px; color: #000000 !important; }}
        .exam-section-header {{ font-size: 19px !important; font-weight: 800 !important; color: #000000 !important; margin-top: 25px !important; margin-bottom: 12px !important; border-left: 5px solid #000 !important; padding-left: 10px; }}
        
        .fill-blank-underline {{
            display: inline-block;
            width: 180px;
            border-bottom: 1.5px solid #000000 !important;
            margin: 0 10px;
            height: 18px;
            vertical-align: bottom;
        }}
        .v-frac {{ display: inline-flex; flex-direction: column; vertical-align: middle; text-align: center; line-height: 1.0; padding: 0 4px; font-size: 0.85em; }}
        .v-frac .num {{ border-bottom: 1.5px solid #000000; padding-bottom: 2px; min-width: 14px; }}
        .v-frac .den {{ padding-top: 2px; min-width: 14px; }}
        .mc-option {{ margin-left: 20px; margin-top: 6px; margin-bottom: 6px; display: block !important; color: #000000 !important; }}
        .page-break {{ page-break-before: always; }}
        .ans-header {{ color: #ff4b4b !important; border-bottom: 2px solid #ff4b4b !important; padding-bottom: 10px; margin-top: 35px; font-size: 23px; text-align: center; }}
        @media print {{ html, body {{ background-color: white; color: #000000; -webkit-print-color-adjust: exact !important; }} }}
    </style>
    </head>
    <body>
        <div id="exam-body">{full_html_content}</div>
        <script>{auto_print_js}</script>
    </body>
    </html>
    """

    st.info("💡 **iPad / iPhone 完美跨頁打印提示**：\n請點擊下方大按鈕將包含【精準 SVG 幾何圖】的考卷下載至 iPad。點開檔案後即可完美分頁列印或導出 PDF，圖形線條絕對清晰不模糊！")
    
    st.download_button(
        label="📲 iPad 專用：下載完整 HTML 幾何圖形列印檔",
        data=html_for_printing,
        file_name=f"香港小學{grade}_幾何組合試卷.html",
        mime="text/html",
        use_container_width=True,
        type="primary"
    )

    st.write("##")
    import streamlit.components.v1 as components
    components.html(html_for_printing, height=1400, scrolling=True)
else:
    st.info("💡 請先在上方的步驟二生成或提供題目數據。")
