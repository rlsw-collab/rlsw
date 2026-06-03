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

# 🆕 升級 v1.7.9：動態幾何圖形參數 (修復 GPT-4o 照抄死數字與出錯圖形範圍問題)
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.7.9"

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
# 🛡️ GitHub 雲端實時計數同步邏輯
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
# 🛡️ AI 題目生成通道
# ==========================================
def call_pure_free_multiverse_ai(text_prompt):
    if AI_TOKEN:
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_TOKEN}",
            "Content-Type": "application/json"
        }
        github_payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a professional JSON output assistant. You must return a strict JSON object with fields 'exam_body' and 'answer_body'. DO NOT OMIT ANY QUESTIONS. Write out every single item explicitly without using '...' ellipses."},
                {"role": "user", "content": text_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.4
        }
        try:
            res = requests.post(url, headers=headers, json=github_payload, timeout=90)
            if res.status_code == 200:
                raw_content = res.json()['choices'][0]['message']['content'].strip()
                raw_content = re.sub(r'^```json\s*', '', raw_content)
                raw_content = re.sub(r'\s*```$', '', raw_content).strip()
                increment_github_counter("backup")
                return json.loads(raw_content)
        except Exception as e:
            pass
    return None

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
# 🎨 🛠️ 幾何圖形 SVG 印刷級動態渲染器 🛠️ 🎨
# ==========================================
def draw_svg_geometry(marker_str):
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
        
        if g_type == "three_circles_linear":
            r1 = params.get("r1", "10")
            r3 = params.get("r3", "7")
            svg_code = f"""
            <div class="geo-container" style="text-align:center; margin:15px 0;">
            <svg width="280" height="150" style="background:white; border:1px solid #ddd; border-radius:6px; display:inline-block;">
                <circle cx="100" cy="75" r="55" stroke="black" stroke-width="1.8" fill="none" />
                <circle cx="85" cy="75" r="40" stroke="black" stroke-width="1.5" fill="none" stroke-dasharray="2 2" />
                <circle cx="180" cy="75" r="25" stroke="black" stroke-width="1.8" fill="none" />
                <line x1="45" y1="75" x2="205" y2="75" stroke="black" stroke-width="1" stroke-dasharray="4" />
                <circle cx="45" cy="75" r="2.5" fill="black"/><text x="40" y="95" font-size="13" font-family="sans-serif">P</text>
                <circle cx="85" cy="75" r="2.5" fill="black"/><text x="80" y="95" font-size="13" font-family="sans-serif">Q</text>
                <circle cx="180" cy="75" r="2.5" fill="black"/><text x="175" y="95" font-size="13" font-family="sans-serif">R</text>
                <text x="50" y="65" font-size="11" font-weight="bold" font-family="sans-serif">半徑 {r1}</text>
                <text x="165" y="65" font-size="11" font-weight="bold" font-family="sans-serif">半徑 {r3}</text>
            </svg>
            </div>
            """
            
        elif g_type == "circles_in_rectangle":
            w = params.get("w", "24")
            h = params.get("h", "12")
            svg_code = f"""
            <div class="geo-container" style="text-align:center; margin:15px 0;">
            <svg width="260" height="140" style="background:white; border:1px solid #ddd; border-radius:6px; display:inline-block;">
                <rect x="20" y="20" width="220" height="100" stroke="black" stroke-width="2" fill="none" />
                <circle cx="70" cy="70" r="50" stroke="black" stroke-width="1.5" fill="none" />
                <circle cx="170" cy="70" r="50" stroke="black" stroke-width="1.5" fill="none" />
                <line x1="70" y1="70" x2="120" y2="70" stroke="black" stroke-width="1.2" />
                <circle cx="70" cy="70" r="2" fill="black" />
                <text x="110" y="15" font-size="12" font-weight="bold" font-family="sans-serif">長 = {w}</text>
                <text x="25" y="65" font-size="11" font-family="sans-serif" transform="rotate(-90 25,65)">闊 = {h}</text>
            </svg>
            </div>
            """
            
        elif g_type == "concentric_overlap":
            d1 = params.get("d1", "16")
            svg_code = f"""
            <div class="geo-container" style="text-align:center; margin:15px 0;">
            <svg width="220" height="160" style="background:white; border:1px solid #ddd; border-radius:6px; display:inline-block;">
                <circle cx="110" cy="80" r="60" stroke="black" stroke-width="1.8" fill="none" />
                <circle cx="110" cy="110" r="30" stroke="black" stroke-width="1.5" fill="none" />
                <circle cx="110" cy="80" r="2.5" fill="black" />
                <text x="115" y="75" font-size="12" font-family="sans-serif">O (大圓心)</text>
                <circle cx="110" cy="110" r="2" fill="black" />
                <line x1="110" y1="20" x2="110" y2="140" stroke="black" stroke-width="1" stroke-dasharray="3" />
                <text x="115" y="50" font-size="11" font-weight="bold" font-family="sans-serif">大圓直徑 = {d1}</text>
            </svg>
            </div>
            """
            
        elif g_type == "triangle":
            b = params.get("b", "15")
            h = params.get("h", "10")
            svg_code = f"""
            <div class="geo-container" style="text-align:center; margin:15px 0;">
            <svg width="240" height="150" style="background:white; border:1px solid #ddd; border-radius:6px; display:inline-block;">
                <polygon points="40,120 200,120 150,30" stroke="black" stroke-width="1.8" fill="none" />
                <line x1="150" y1="30" x2="150" y2="120" stroke="black" stroke-width="1.2" stroke-dasharray="3" />
                <rect x="145" y="115" width="5" height="5" stroke="black" stroke-width="1" fill="none" />
                <text x="100" y="135" font-size="12" font-weight="bold" font-family="sans-serif">底 = {b}</text>
                <text x="160" y="80" font-size="12" font-weight="bold" font-family="sans-serif">高 = {h}</text>
            </svg>
            </div>
            """

        elif g_type == "cuboid_volume":
            l = params.get("l", "12")
            w = params.get("w", "8")
            h = params.get("h", "5")
            svg_code = f"""
            <div class="geo-container" style="text-align:center; margin:15px 0;">
            <svg width="260" height="160" style="background:white; border:1px solid #ddd; border-radius:6px; display:inline-block;">
                <polygon points="40,120 160,120 160,60 40,60" stroke="black" stroke-width="1.8" fill="none" />
                <polygon points="40,60 160,60 210,30 90,30" stroke="black" stroke-width="1.5" fill="none" />
                <polygon points="160,120 210,90 210,30 160,60" stroke="black" stroke-width="1.8" fill="none" />
                <line x1="40" y1="120" x2="90" y2="90" stroke="black" stroke-width="1.2" stroke-dasharray="3" />
                <line x1="90" y1="90" x2="210" y2="90" stroke="black" stroke-width="1.2" stroke-dasharray="3" />
                <line x1="90" y1="90" x2="90" y2="30" stroke="black" stroke-dasharray="3" stroke-width="1.2" />
                <text x="80" y="138" font-size="12" font-weight="bold" font-family="sans-serif">長 = {l}</text>
                <text x="185" y="110" font-size="12" font-weight="bold" font-family="sans-serif">闊 = {w}</text>
                <text x="10" y="90" font-size="12" font-weight="bold" font-family="sans-serif">高 = {h}</text>
            </svg>
            </div>
            """
        return svg_code
    except:
        return "📐 [幾何圖形加載錯誤] 📐"

# ==========================================
# 🚀 雙引擎渲染核心 🚀
# ==========================================
def convert_to_vertical_fractions(text_content):
    text_content = re.sub(r'(\d+)\s*又\s*(\d+)\s*分之\s*(\d+)', r'\1<span class="v-frac"><span class="num">\3</span><span class="den">\2</span></span>', text_content)
    text_content = re.sub(r'(\d+)\s*又\s*(\d+)/(\d+)', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', text_content)
    text_content = re.sub(r'(?<!\d)(\d+)\s*分之\s*(\d+)(?!\d)', r'<span class="v-frac"><span class="num">\2</span><span class="den">\1</span></span>', text_content)
    text_content = re.sub(r'(\d+)\s*[\(\[]?(\d+)/(\d+)[\)\]]?', r'\1<span class="v-frac"><span class="num">\2</span><span class="den">\3</span></span>', text_content)
    text_content = re.sub(r'(?<!/)(?<!<)(?<!\d)(\d+)/(\d+)(?!\d)(?!>)', r'<span class="v-frac"><span class="num">\1</span><span class="den">\2</span></span>', text_content)
    return text_content

def python_layout_engine(raw_text, is_answer_key=False):
    if not raw_text: return ""
    raw_text = raw_text.replace("\\n", "\n").replace("\\\\n", "\n")
    
    raw_text = raw_text.replace("**", "").replace("###", "")
    lines = raw_text.split('\n')
    processed_lines = []
    current_section = ""
    
    for line in lines:
        if not line.strip(): continue
        clean_line = line.strip()
        
        # 1. 識別大題目部別與主題
        if "部：" in clean_line or "部分：" in clean_line or "部" in clean_line or "部分" in clean_line:
            current_section = clean_line
            processed_lines.append(f'<div class="exam-section-header">{clean_line}</div>')
            continue
            
        # 2. 識別試卷主副標題
        if "測驗" in clean_line or "考試" in clean_line or ("試卷" in clean_line and len(clean_line) < 35):
            processed_lines.append(f'<div class="exam-title-main">{clean_line}</div>')
            continue
        if "班級" in clean_line or "姓名" in clean_line or "學號" in clean_line or "班別" in clean_line:
            processed_lines.append(f'<div class="exam-user-info">{clean_line}</div>')
            continue
            
        # 3. 幾何 SVG 標籤拦截與繪製
        geo_match = re.search(r'(\[GEOMETRIC:[^\]]+\])', line)
        if geo_match:
            full_marker = geo_match.group(1)
            svg_html = draw_svg_geometry(full_marker)
            line = line.replace(full_marker, svg_html)
            processed_lines.append(f'<div>{line}</div>')
            continue

        # 4. 🌟 多項選擇題（MC）人人有圓圈引擎
        opt_starts = list(re.finditer(r'[○●]?\s*[A-D]\.\s+', line))
        
        if opt_starts:
            first_idx = opt_starts[0].start()
            question_part = line[:first_idx].strip()
            
            if question_part:
                processed_lines.append(f'<div class="question-text">{question_part}</div>')
            
            options_text = line[first_idx:]
            options = re.findall(r'([○●]?\s*[A-D]\.\s+.*?(?=\s*[○●]?\s*[A-D]\.\s+|$))', options_text)
            
            for opt in options:
                opt_str = opt.strip()
                is_correct = "●" in opt
                opt_str = re.sub(r'^[○●]\s*', '', opt_str).strip()
                
                if is_correct or (is_answer_key and "●" in line):
                    processed_lines.append(f'<div class="mc-option"><span class="mc-ans">●</span> {opt_str}</div>')
                else:
                    processed_lines.append(f'<div class="mc-option"><span class="mc-circle">○</span> {opt_str}</div>')
            continue

        # 5. 底線與空括號長度美化
        line = re.sub(r'([_＿]{2,})', r'<span class="fill-blank-underline"></span>', line)
        line = re.sub(r'([\(（])\s{2,}([\)）])', r'\1 <span class="fill-blank-underline"></span> \2', line)
        line = convert_to_vertical_fractions(line)

        # 6. 手寫答題紙 (列式與長題目)
        is_applied_or_calc_section = any(s in current_section for s in ["第三", "第四", "計算", "應用題", "文字題", "長題目"])
        
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
with col_meta1: subject = st.selectbox("選擇科目", ["數學", "中文", "英文", "常識"])
with col_meta2: grade = st.selectbox("選擇年級", ["小五", "小六", "小四", "小三", "小二", "小一"])

st.write("##")
st.markdown("### 🔢 設定各題型生成數量 (只限 0, 5, 10, 15, 20, 25, 30)")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1: mc_count = st.slider("多項選擇題", 0, 30, 5, step=5)
with col_s2: fill_count = st.slider("填充題", 0, 30, 5, step=5)
with col_s3: calc_count = st.slider("列式計算題", 0, 30, 0, step=5)
with col_s4: text_count = st.slider("長題目文字題", 0, 30, 0, step=5)

st.write("---")
st.header("🎯 步驟二：設定出題範圍來源")
range_mode = st.radio("範圍模式選擇：", ["提供範圍", "提供幾何工作紙模板"], horizontal=True)
uploaded_files = st.file_uploader("上傳工作紙進行幾何智慧辨識", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if range_mode == "提供範圍":
    text_input_val = st.text_area("📝 在此修改或輸入幾何範圍核心概念：", value=current_vault_ocr, height=150, key=f"ocr_box_{vault_hash}")
    if text_input_val != current_vault_ocr:
        write_to_exam_vault(text_input_val)
        current_vault_ocr = text_input_val
else:
    static_notice = "根據平面圓形與幾何圖形工作紙考點，計算圓心、切點、多圓重疊、長方形內切圓、三角形與長方體體積的關係。"
    write_to_exam_vault(static_notice)
    st.text_area("📝 範圍狀態（已鎖定）：", value=static_notice, height=70, disabled=True)

st.write("##")
btn_call_ai = st.button("🚀 呼叫「分批拼接不偷懶引擎」生成完整試卷 🤖", type="secondary", use_container_width=True)

if btn_call_ai:
    if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
        st.error("❌ 請至少選擇一種題型的數量大於 0！")
    else:
        final_vault_text = read_from_exam_vault()
        
        has_geometry = any(kw in final_vault_text for kw in ["圓", "三角", "面積", "體積", "長方體", "正方體"])
        
        geo_rule = ""
        if has_geometry:
            geo_rule = f"""
            ⚠️【核心幾何命令】：考量到本次範圍涉及幾何，你必須在題目中穿插嵌入幾何圖形標記。
            🔥【絕對指令 1 - 範圍匹配】：請「嚴格限制」只選用與給定範圍概念相關的圖形！例如範圍只寫了「三角形」，就絕對不准出「圓形」或「長方體」題目！
            🔥【絕對指令 2 - 動態參數】：標記中的參數數值 (如 w, h, r1, b, l 等) 必須根據你當前出題的實際數字「動態填入」，絕對不能照抄下方範例的死數字！
            
            可選用的標記格式 (請將中文描述替換成你出題時的實際數字，例如題目三角形底是20，高是8，則輸出 [GEOMETRIC:triangle:b=20;h=8])：
            - [GEOMETRIC:three_circles_linear:r1=大圓半徑;r2=中圓半徑;r3=小圓半徑] (僅限範圍含圓形性質時使用)
            - [GEOMETRIC:circles_in_rectangle:w=長方形長;h=長方形闊] (僅限範圍含長方形與圓時使用)
            - [GEOMETRIC:concentric_overlap:d1=大圓直徑] (僅限範圍含同心圓時使用)
            - [GEOMETRIC:triangle:b=三角形底;h=三角形高] (僅限範圍含三角形時使用)
            - [GEOMETRIC:cuboid_volume:l=長方體長;w=長方體闊;h=長方體高] (僅限範圍含立體體積時使用)
            """

        tasks = []
        if mc_count > 0: tasks.append(("MC", f"第一部分：多項選擇題（共 {mc_count} 題，題號由 1 開始到 {mc_count}）", mc_count))
        if fill_count > 0: tasks.append(("FILL", f"第二部分：填充題（共 {fill_count} 題，題號由 {mc_count+1} 開始到 {mc_count+fill_count}）", fill_count))
        if calc_count > 0: tasks.append(("CALC", f"第三部分：列式計算題（共 {calc_count} 題，題號由 {mc_count+fill_count+1} 開始到 {mc_count+fill_count+calc_count}）", calc_count))
        if text_count > 0: tasks.append(("TEXT", f"第四部分：長題目文字題（共 {text_count} 題，題號由 {mc_count+fill_count+calc_count+1} 開始到 {mc_count+fill_count+calc_count+text_count}）", text_count))

        combined_exam = f"### 香港小學{grade}{subject}科測驗卷\n班別：__________  姓名：__________  學號：__________\n\n"
        combined_ans = "### 🔑 答案頁與幾何解題詳解 (Answer Key)\n\n"
        
        progress_bar = st.progress(0.0)
        task_step = 1.0 / len(tasks) if tasks else 1.0
        
        for idx, (t_type, t_title, t_num) in enumerate(tasks):
            st.toast(f"⏳ 正在生成{t_title}... 拒絕任何省略號！", icon="📝")
            
            sub_prompt = f"""你是一位香港名校數學科組長。請為【香港小學{grade}】編寫【{subject}科】測驗卷的【{t_title}】。
            本次出題範圍/重點為：「{final_vault_text}」
            
            要求：
            1. 必須完整地生成全部 {t_num} 道題目，每一題都要寫出具體文字。
            2. ❌ 絕對不允許使用任何 '...' 省略號，亦不准寫出簡寫字。
            3. 繁體中文香港小學標準。
            {geo_rule}
            
            🎯【必須回傳的 JSON 格式】：
            {{
              "exam_body": "### {t_title}\\n\\n這裡依序寫出第1題到第{t_num}題的題目內容...",
              "answer_body": "### {t_title} 答案詳解\\n\\n這裡寫出對應的詳細公式與答案..."
            }}
            """
            
            res_json = call_pure_free_multiverse_ai(sub_prompt)
            if res_json:
                combined_exam += ensure_flat_string(res_json.get("exam_body", "")) + "\n\n"
                combined_ans += ensure_flat_string(res_json.get("answer_body", "")) + "\n\n"
            else:
                st.error(f"❌ {t_title} 生成失敗，請重試。")
                st.stop()
                
            progress_bar.progress((idx + 1) * task_step)
            time.sleep(0.5)

        st.session_state['generated_exam'] = combined_exam
        st.session_state['generated_answers'] = combined_ans
        st.session_state['exam_text_editor'] = combined_exam
        st.session_state['ans_text_editor'] = combined_ans
        st.success("🎉 全套完整題目生成完畢！")
        st.rerun()

# ==========================================
# 4. 原始碼控制台
# ==========================================
st.write("---")
st.header("📝 步驟三：幾何源碼調校控制台")
col_edit1, col_edit2 = st.columns(2)
with col_edit1:
    if 'exam_text_editor' not in st.session_state: st.session_state['exam_text_editor'] = st.session_state['generated_exam']
    def on_exam_change(): st.session_state['generated_exam'] = st.session_state['exam_text_editor']
    st.text_area("題目微調（拒絕省略號）：", value=st.session_state['exam_text_editor'], height=350, key="exam_text_editor", on_change=on_exam_change)
with col_edit2:
    if 'ans_text_editor' not in st.session_state: st.session_state['ans_text_editor'] = st.session_state['generated_answers']
    def on_ans_change(): st.session_state['generated_answers'] = st.session_state['ans_text_editor']
    st.text_area("答案與詳解微調：", value=st.session_state['ans_text_editor'], height=350, key="ans_text_editor", on_change=on_ans_change)

# ==========================================
# 5. 視覺排版與 iPad 完美打印
# ==========================================
st.write("---")
st.header("🎨 步驟四：印刷級幾何排版與打印導出")

if st.session_state['generated_exam'] or st.session_state['generated_answers']:
    perfect_exam_html = python_layout_engine(st.session_state['generated_exam'], is_answer_key=False)
    perfect_ans_html = python_layout_engine(st.session_state['generated_answers'], is_answer_key=True)
    full_html_content = perfect_exam_html + '<div class="page-break"></div>' + perfect_ans_html
    
    trigger_print = st.button("🖨️ 立即啟動手提電腦列印", type="secondary", use_container_width=True)
    auto_print_js = "window.print();" if trigger_print else ""

    html_for_printing = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        html, body {{ background-color: white !important; color: #000000 !important; -webkit-text-fill-color: #000000 !important; }}
        #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; padding: 20px; font-size: 16px; line-height: 2.3; }}
        .exam-title-main {{ font-size: 26px !important; font-weight: 800 !important; text-align: center !important; margin-top: 20px !important; margin-bottom: 15px !important; }}
        .exam-user-info {{ font-size: 17px !important; font-weight: bold !important; text-align: center !important; margin-bottom: 30px !important; word-spacing: 12px; }}
        .exam-section-header {{ font-size: 19px !important; font-weight: 800 !important; margin-top: 25px !important; margin-bottom: 12px !important; border-left: 5px solid #000 !important; padding-left: 10px; }}
        .fill-blank-underline {{ display: inline-block; width: 150px; border-bottom: 1.5px solid #000 !important; margin: 0 10px; height: 18px; vertical-align: bottom; }}
        .v-frac {{ display: inline-flex; flex-direction: column; vertical-align: middle; text-align: center; line-height: 1.0; padding: 0 4px; font-size: 0.85em; }}
        .v-frac .num {{ border-bottom: 1.5px solid #000; padding-bottom: 2px; min-width: 14px; }}
        .v-frac .den {{ padding-top: 2px; min-width: 14px; }}
        
        /* 選擇題每行獨立包裹與對齊 */
        .mc-option {{ 
            margin-left: 20px; 
            margin-top: 6px; 
            margin-bottom: 6px; 
            display: block !important; 
            clear: both;
        }}
        .mc-circle {{ font-size: 16px; font-weight: normal; margin-right: 4px; font-family: sans-serif; }}
        .mc-ans {{ color: #ff4b4b; font-weight: bold; margin-right: 4px; font-family: sans-serif; }}
        
        /* 答題紙橫線區域 */
        .write-zone {{ margin-top: 15px; margin-bottom: 30px; width: 100%; }}
        .row-line {{ width: 100%; height: 38px; border-bottom: 1px dashed #999 !important; }}
        
        .page-break {{ page-break-before: always; }}
    </style>
    </head>
    <body>
        <div id="exam-body">{full_html_content}</div>
        <script>{auto_print_js}</script>
    </body>
    </html>
    """

    st.download_button(
        label="📲 iPad 專用：下載完美全圓圈選項幾何 HTML 列印檔",
        data=html_for_printing,
        file_name=f"香港小學{grade}_完美圓圈幾何試卷.html",
        mime="text/html",
        use_container_width=True,
        type="primary"
    )

    st.write("##")
    import streamlit.components.v1 as components
    components.html(html_for_printing, height=1200, scrolling=True)
