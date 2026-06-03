import streamlit as st
import requests
import json
import time
import re
import os
import datetime
import base64

# ==========================================
# 0. 網頁基本設定與【密碼鎖邏輯】
# ==========================================
st.set_page_config(page_title="香港小學測驗考試卷生成器", layout="wide")

# 🆕 升級 v1.10.1：終極修復！修正主分支為 main，徹底解決 404 Branch not found 儲存失敗問題
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.10.1"

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

st.title(APP_TITLE)

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
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
# 1. 安全金鑰與 GitHub 雲端知識庫對接底層
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GIT_TOKEN"]
    GEMINI_TOKEN = st.secrets["GEMINI_TOKEN"]
    AI_TOKEN = st.secrets.get("AI_TOKEN", "")
    GITHUB_REPO = "rlsw"
    GITHUB_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到基礎憑證 (GIT_TOKEN)。")
    st.stop()

if 'debug_logs' not in st.session_state: st.session_state['debug_logs'] = []
def add_log(msg):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state['debug_logs'].append(f"[{now}] {msg}")

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

# 🛠️ GitHub 雲端知識庫 CRUD 雙向強固函數組 (已更正為 main 分支)
def upload_knowledge_base_to_github(name, b64_images):
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    path = f"knowledge_base/{safe_name}.json"
    # 🔒 修正：強制鎖定 main 分支進行查詢與寫入
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    sha = None
    add_log(f"💾 準備儲存更新，正在向 GitHub 查詢舊有檔案的 SHA 標籤...")
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get("sha")
        add_log(f"✅ 成功獲取舊檔案 SHA: {sha}，本次將執行覆蓋覆寫 (Overwrite)。")
    else:
        add_log(f"💡 未找到舊檔案 SHA (狀態碼: {res.status_code})，本次將視為全新檔案建立。")
        
    payload_data = {
        "kb_name": name,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "images": b64_images
    }
    
    content_str = json.dumps(payload_data, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    
    put_payload = {
        "message": f"Save knowledge base: {name} [skip ci]",
        "content": content_b64,
        "branch": "main" # 🔒 修正：明確指示寫入 main 分支
    }
    if sha:
        put_payload["sha"] = sha
        
    write_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    add_log(f"🚀 正在推送最新數據至 GitHub (main 分支)...")
    put_res = requests.put(write_url, headers=headers, json=put_payload)
    
    add_log(f"🔔 GitHub 儲存回應狀態碼: {put_res.status_code}")
    if put_res.status_code not in [200, 201]:
        add_log(f"❌ 儲存失敗！GitHub 錯誤回應：{put_res.text}")
        
    return put_res.status_code in [200, 201]

def delete_knowledge_base_from_github(name):
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    path = f"knowledge_base/{safe_name}.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get("sha")
        delete_payload = {
            "message": f"Delete knowledge base: {name} [skip ci]",
            "sha": sha,
            "branch": "main"
        }
        del_res = requests.delete(f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}", headers=headers, json=delete_payload)
        return del_res.status_code == 200
    return False

def list_knowledge_bases_from_github():
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/knowledge_base?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return [item["name"].replace(".json", "") for item in res.json() if item["name"].endswith(".json")]
    except:
        pass
    return []

def get_knowledge_base_content(kb_name):
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', kb_name)
    # 🚀 修正：改走 main 分支的 Raw 通道
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/knowledge_base/{safe_name}.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }
    add_log(f"🚀 開啟大檔案 Raw 綠色通道抓取數據: {raw_url}")
    try:
        res = requests.get(raw_url, headers=headers)
        add_log(f"遠端 Raw 通道回應狀態碼: {res.status_code}")
        if res.status_code == 200:
            parsed_data = res.json()
            add_log(f"🎉 原始資料加載成功！知識庫名稱: {parsed_data.get('kb_name')}, 內含圖片張數: {len(parsed_data.get('images', []))}")
            return parsed_data
        else:
            add_log(f"❌ Raw 通道讀取失敗。狀態碼: {res.status_code}, 錯誤: {res.text}")
    except Exception as ex:
        add_log(f"❌ 發生異常崩潰: {str(ex)}")
    return None

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
# 🛡️ AI 核心生成與圖片分析通道
# ==========================================
def call_pure_free_multiverse_ai(messages, is_json=True):
    if AI_TOKEN:
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_TOKEN}",
            "Content-Type": "application/json"
        }
        github_payload = {
            "model": "gpt-4o",
            "messages": messages,
            "temperature": 0.4
        }
        if is_json:
            github_payload["response_format"] = {"type": "json_object"}
            
        try:
            res = requests.post(url, headers=headers, json=github_payload, timeout=120)
            if res.status_code == 200:
                raw_content = res.json()['choices'][0]['message']['content'].strip()
                if is_json:
                    raw_content = re.sub(r'^```json\s*', '', raw_content)
                    raw_content = re.sub(r'\s*```$', '', raw_content).strip()
                    return json.loads(raw_content)
                return raw_content
        except Exception as e:
            pass
    return None

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
                <text x="50" y="65" font-size="11" font-weight="bold" font-family="sans-serif">半徑/Radius {r1}</text>
                <text x="165" y="65" font-size="11" font-weight="bold" font-family="sans-serif">半徑/Radius {r3}</text>
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
                <text x="110" y="15" font-size="12" font-weight="bold" font-family="sans-serif">長/L = {w}</text>
                <text x="25" y="65" font-size="11" font-family="sans-serif" transform="rotate(-90 25,65)">闊/W = {h}</text>
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
                <text x="115" y="75" font-size="12" font-family="sans-serif">O (大圓心/Center)</text>
                <circle cx="110" cy="110" r="2" fill="black" />
                <line x1="110" y1="20" x2="110" y2="140" stroke="black" stroke-width="1" stroke-dasharray="3" />
                <text x="115" y="50" font-size="11" font-weight="bold" font-family="sans-serif">大圓直徑/Diameter = {d1}</text>
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
                <text x="100" y="135" font-size="12" font-weight="bold" font-family="sans-serif">底/Base = {b}</text>
                <text x="160" y="80" font-size="12" font-weight="bold" font-family="sans-serif">高/Height = {h}</text>
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
                <text x="80" y="138" font-size="12" font-weight="bold" font-family="sans-serif">長/L = {l}</text>
                <text x="185" y="110" font-size="12" font-weight="bold" font-family="sans-serif">闊/W = {w}</text>
                <text x="10" y="90" font-size="12" font-weight="bold" font-family="sans-serif">高/H = {h}</text>
            </svg>
            </div>
            """
        return svg_code
    except:
        return "📐 [幾何圖形加載錯誤] 📐"

# ==========================================
# 🚀 雙引擎排版核心 🚀
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
        if any(s in clean_line for s in ["部：", "部分：", "部", "部分", "Section:", "Part:"]):
            current_section = clean_line
            processed_lines.append(f'<div class="exam-section-header">{clean_line}</div>')
            continue
        if any(s in clean_line for s in ["測驗", "考試", "試卷", "Quiz", "Test", "Exam"]) and len(clean_line) < 45:
            processed_lines.append(f'<div class="exam-title-main">{clean_line}</div>')
            continue
        if any(s in clean_line for s in ["班級", "姓名", "學號", "班別", "Class", "Name", "No."]):
            processed_lines.append(f'<div class="exam-user-info">{clean_line}</div>')
            continue
            
        geo_match = re.search(r'(\[GEOMETRIC:[^\]]+\])', line)
        if geo_match:
            full_marker = geo_match.group(1)
            svg_html = draw_svg_geometry(full_marker)
            line = line.replace(full_marker, svg_html)
            processed_lines.append(f'<div>{line}</div>')
            continue

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

        line = re.sub(r'([_＿]{2,})', r'<span class="fill-blank-underline"></span>', line)
        line = re.sub(r'([\(（])\s{2,}([\)）])', r'\1 <span class="fill-blank-underline"></span> \2', line)
        line = convert_to_vertical_fractions(line)

        is_fill_section = any(s in current_section for s in ["第二", "填充", "填空", "FILL", "Fill", "Blanks"])
        if is_fill_section and not is_answer_key:
            if re.match(r'^[\(（][一二三四五六七八九十\da-zA-Z]+[\)）]', clean_line):
                if '<span class="fill-blank-underline">' not in line:
                    line = f'{line} <span class="fill-blank-underline"></span>'

        is_applied_or_calc_section = any(s in current_section for s in ["第三", "第四", "計算", "應用題", "文字題", "長題目", "Calculation", "Word", "Long Questions"])
        if re.match(r'^\d+\.', clean_line) and not is_answer_key and is_applied_or_calc_section:
            processed_lines.append(f'<div class="question-text">{line}</div>')
            processed_lines.append('<div class="write-zone">' + '<div class="row-line"></div>'*4 + '</div>')
            continue

        processed_lines.append(f'<div>{line}</div>')
        
    return "\n".join(processed_lines)

# ==========================================
# 🏠 Streamlit 分頁標籤 (TAB 佈局)
# ==========================================
tab_exam, tab_kb = st.tabs(["📝 試卷生成工具", "📂 雲端多圖知識庫管理"])

if 'kb_current_b64_list' not in st.session_state: st.session_state['kb_current_b64_list'] = []
if 'last_loaded_kb' not in st.session_state: st.session_state['last_loaded_kb'] = ""

# ------------------------------------------
# TAB 1: 試卷生成核心
# ------------------------------------------
with tab_exam:
    if 'generated_exam' not in st.session_state: st.session_state['generated_exam'] = ""
    if 'generated_answers' not in st.session_state: st.session_state['generated_answers'] = ""

    current_vault_ocr = read_from_exam_vault()

    st.header("📋 步驟一：基本資料與功能設定")
    col_meta1, col_meta2, col_meta3 = st.columns(3)
    with col_meta1: subject = st.selectbox("選擇科目", ["中文", "英文", "數學", "常識"])
    with col_meta2: grade = st.selectbox("選擇年級", ["小一", "小二", "小三", "小四", "小五", "小六"])
    with col_meta3: language = st.selectbox("語言模式 / Language", ["繁體中文", "English"])

    st.write("##")
    st.markdown("### 🔢 設定各題型生成數量 (只限 0, 5, 10, 15, 20, 25, 30)")
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1: mc_count = st.slider("多項選擇題", 0, 30, 5, step=5)
    with col_s2: fill_count = st.slider("填充題", 0, 30, 5, step=5)
    with col_s3: calc_count = st.slider("列式計算題", 0, 30, 0, step=5)
    with col_s4: text_count = st.slider("長題目文字題", 0, 30, 0, step=5)

    st.write("---")
    st.header("🎯 步驟二：設定出題範圍來源")
    
    scope_mode = st.radio("範圍模式選擇：", ["在此修改或輸入幾何範圍核心概念：", "選用先前存放的雲端知識庫"], horizontal=True)
    
    final_vault_text = ""
    chosen_kb_images = []
    
    if scope_mode == "在此修改或輸入幾何範圍核心概念：":
        text_input_val = st.text_area("✍️ 請輸入核心概念或課文範圍：", value=current_vault_ocr, height=150, key="ocr_box_editor")
        if text_input_val != current_vault_ocr:
            write_to_exam_vault(text_input_val)
            current_vault_ocr = text_input_val
        final_vault_text = current_vault_ocr
    else:
        available_kbs = list_knowledge_bases_from_github()
        if not available_kbs:
            st.warning("⚠️ 目前雲端沒有存放任何知識庫，請先到右側「📂 雲端多圖知識庫管理」上傳。")
            final_vault_text = ""
        else:
            selected_kb = st.selectbox("📂 選擇你要對接的知識庫資料：", available_kbs, key="tab1_kb_selector")
            if selected_kb:
                kb_data = get_knowledge_base_content(selected_kb)
                if kb_data:
                    st.success(f"✅ 已成功加載知識庫「{selected_kb}」，內含 {len(kb_data.get('images', []))} 張課本/工作紙檔案圖片。")
                    chosen_kb_images = kb_data.get('images', [])
                    final_vault_text = f"[使用雲端 GitHub 知識庫圖片庫: {selected_kb}]"

    st.write("##")
    btn_call_ai = st.button("🚀 呼叫「分批拼接不偷懶引擎」生成完整試卷 🤖", type="secondary", use_container_width=True)

    if btn_call_ai:
        if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
            st.error("❌ 請至少選擇一種題型的數量大於 0！")
        elif scope_mode == "選用先前存放的雲端知識庫" and not chosen_kb_images:
            st.error("❌ 所選知識庫無有效數據，無法建立試卷庫！")
        else:
            if scope_mode == "選用先前存放的雲端知識庫" and chosen_kb_images:
                st.toast("🔮 正在由 GPT-4o 深度解構所有知識庫圖片以建立精準試題庫...", icon="📦")
                
                analysis_messages = [
                    {"role": "system", "content": "You are a professional curriculum analyzer. Your task is to analyze multiple images from textbooks/worksheets and synthesize them into a highly concise but detailed blueprint of knowledge points, core concepts, formulas, and common exercise patterns for test item generation."}
                ]
                user_content = [{"type": "text", "text": "請深度分析這批由用戶上傳的工作紙與課本內容。提煉出裡面所有的考點、題型結構、幾何數字邏輯與公式，為稍後的出題做最萬全的知識儲備基礎。"}]
                for b64_img in chosen_kb_images:
                    clean_b64_data = re.sub(r'\s+', '', b64_img)
                    clean_b64 = clean_b64_data if clean_b64_data.startswith("data:image") else f"data:image/jpeg;base64,{clean_b64_data}"
                    user_content.append({"type": "image_url", "image_url": {"url": clean_b64}})
                    
                analysis_messages.append({"role": "user", "content": user_content})
                synthesized_knowledge = call_pure_free_multiverse_ai(analysis_messages, is_json=False)
                if synthesized_knowledge:
                    final_vault_text = synthesized_knowledge
                else:
                    st.error("❌ 雲端圖片庫深度分析失敗，請檢查網絡通道。")
                    st.stop()

            has_geometry = any(kw in final_vault_text.lower() for kw in ["圓", "三角", "面積", "體積", "長方體", "正方體", "circle", "triangle", "area", "volume", "cuboid"])
            geo_rule = ""
            if has_geometry:
                geo_rule = f"""
                ⚠️【核心幾何命令】：考量到本次範圍涉及幾何，你必須在題目中穿跨嵌入幾何圖形標記。
                - [GEOMETRIC:three_circles_linear:r1=大圓半徑;r2=中圓半徑;r3=小圓半徑]
                - [GEOMETRIC:circles_in_rectangle:w=長方形長;h=長方形闊]
                - [GEOMETRIC:concentric_overlap:d1=大圓直徑]
                - [GEOMETRIC:triangle:b=三角形底;h=三角形高]
                - [GEOMETRIC:cuboid_volume:l=長方體長;w=長方體闊;h=長方體高]
                """

            tasks = []
            if mc_count > 0: tasks.append((f"第一部分：多項選擇題（共 {mc_count} 題）", mc_count))
            if fill_count > 0: tasks.append((f"第二部分：填充題（共 {fill_count} 題）", fill_count))
            if calc_count > 0: tasks.append((f"第三部分：列式計算題（共 {calc_count} 題）", calc_count))
            if text_count > 0: tasks.append((f"第四部分：長題目文字題（共 {text_count} 題）", text_count))
            
            combined_exam = f"### 香港小學{grade}{subject}科測驗卷\n班別：__________  姓名：__________  學號：__________\n\n"
            combined_ans = "### 🔑 答案頁與幾何解題詳解 (Answer Key)\n\n"
            
            progress_bar = st.progress(0.0)
            task_step = 1.0 / len(tasks) if tasks else 1.0
            
            for idx, (t_title, t_num) in enumerate(tasks):
                sub_prompt = f"""你是一位香港名校【{subject}科】主任。請為【香港小學{grade}】編寫【{subject}科}】測驗卷的【{t_title}】。
                本次出題範圍與已提煉的知識庫考點為：「{final_vault_text}」
                要求寫出全部 {t_num} 題，不准使用省略號。
                {geo_rule}
                """
                res_json = call_pure_free_multiverse_ai([{"role": "user", "content": sub_prompt}], is_json=True)
                if res_json:
                    combined_exam += ensure_flat_string(res_json.get("exam_body", "")) + "\n\n"
                    combined_ans += ensure_flat_string(res_json.get("answer_body", "")) + "\n\n"
                progress_bar.progress((idx + 1) * task_step)

            st.session_state['generated_exam'] = combined_exam
            st.session_state['generated_answers'] = combined_ans
            st.rerun()

# ------------------------------------------
# TAB 2: 雲端多圖知識庫管理 (相容 main 分支終極版)
# ------------------------------------------
with tab_kb:
    st.header("📂 雲端課文/作業/工作紙知識庫管理")
    st.info("💡 你可以在這裡建立、追加修改或徹底刪除雲端檔案儲存庫，上傳的檔案將會永久保存。")
    
    kb_action = st.radio("⚙️ 請選擇操作模式：", ["🆕 建立全新知識庫", "✏️ 編輯 / 追加現有知識庫"], horizontal=True, key="kb_action_radio")
    current_kb_name = ""
    
    if kb_action == "🆕 建立全新知識庫":
        st.session_state['last_loaded_kb'] = ""
    
    if kb_action == "✏️ 編輯 / 追加現有知識庫":
        cloud_lists = list_knowledge_bases_from_github()
        if not cloud_lists:
            st.warning("⚠️ 目前雲端沒有任何知識庫，已為你自動切換為新建模式。")
            kb_action = "🆕 建立全新知識庫"
        else:
            st.markdown("### 📁 選擇與管理雲端庫")
            col_sel, col_del = st.columns([3, 1])
            with col_sel:
                selected_edit_kb = st.selectbox("請選擇要讀取的雲端知識庫：", cloud_lists, key="tab2_edit_kb_selector")
            with col_del:
                if selected_edit_kb:
                    if st.button(f"🗑️ 徹底刪除整個「{selected_edit_kb}」", type="primary", use_container_width=True, key="del_entire_kb_btn"):
                        if delete_knowledge_base_from_github(selected_edit_kb):
                            st.success(f"🔥 雲端知識庫「{selected_edit_kb}」已徹底抹除！")
                            st.session_state['last_loaded_kb'] = ""
                            st.session_state['kb_current_b64_list'] = []
                            time.sleep(0.5)
                            st.rerun()

            if selected_edit_kb:
                current_kb_name = selected_edit_kb
                if st.session_state['last_loaded_kb'] != selected_edit_kb:
                    add_log(f"🔄 偵測到選擇切換。開始抓取雲端知識庫：【{selected_edit_kb}】")
                    kb_payload = get_knowledge_base_content(selected_edit_kb)
                    if kb_payload:
                        st.session_state['kb_current_b64_list'] = kb_payload.get("images", [])
                        st.session_state['last_loaded_kb'] = selected_edit_kb

                st.write("##")
                st.markdown(f"### 📦 雲端已存檔案預覽（共 {len(st.session_state['kb_current_b64_list'])} 張）：")
                
                if len(st.session_state['kb_current_b64_list']) == 0:
                    st.info("💡 該知識庫內目前沒有任何檔案圖片。")
                else:
                    cols = st.columns(4)
                    keep_images = []
                    for img_idx, b64_data in enumerate(st.session_state['kb_current_b64_list']):
                        with cols[img_idx % 4]:
                            clean_pure_b64 = re.sub(r'\s+', '', str(b64_data))
                            clean_src = clean_pure_b64 if clean_pure_b64.startswith("data:image") else f"data:image/jpeg;base64,{clean_pure_b64}"
                            try:
                                st.image(clean_src, use_container_width=True)
                                if st.checkbox("❌ 刪除此檔案", key=f"del_img_check_{img_idx}"):
                                    st.caption("⚠️ 已剔除")
                                else:
                                    keep_images.append(b64_data)
                            except Exception:
                                st.error(f"⚠️ 圖片 {img_idx+1} 解碼渲染出錯")
                                
                    if len(keep_images) != len(st.session_state['kb_current_b64_list']):
                        st.session_state['kb_current_b64_list'] = keep_images

    st.write("---")
    st.markdown("### 📥 上傳與追加新檔案" if kb_action == "✏️ 編輯 / 追加現有知識庫" else "### 📥 建立全新檔案資料庫")
    
    if kb_action == "🆕 建立全新知識庫":
        current_kb_name = st.text_input("📝 請輸入全新知識庫名稱：", value="", key="new_kb_name_input")
        st.session_state['kb_current_b64_list'] = []
    
    uploaded_files = st.file_uploader("📸 請選擇或拖放上傳檔案：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="kb_file_uploader")
    if uploaded_files:
        temp_new_b64s = []
        for f in uploaded_files:
            f_bytes = f.read()
            b64_str = base64.b64encode(f_bytes).decode("utf-8")
            clean_new_b64 = re.sub(r'\s+', '', b64_str)
            if clean_new_b64 not in temp_new_b64s:
                temp_new_b64s.append(clean_new_b64)
        st.session_state['new_uploaded_cache'] = temp_new_b64s
    else:
        st.session_state['new_uploaded_cache'] = []

    if st.session_state['new_uploaded_cache']:
        st.markdown("#### 🔍 新上傳檔案即時預覽：")
        preview_cols = st.columns(5)
        for f_idx, b64_str in enumerate(st.session_state['new_uploaded_cache']):
            clean_new_src = b64_str if b64_str.startswith("data:image") else f"data:image/jpeg;base64,{b64_str}"
            with preview_cols[f_idx % 5]:
                st.image(clean_new_src, use_container_width=True, caption=f"新上傳 {f_idx+1}")

    st.write("##")
    if st.button("💾 儲存並同步至雲端知識庫", type="primary", use_container_width=True, key="save_kb_final_btn"):
        if not current_kb_name.strip():
            st.error("❌ 請輸入或選擇有效的知識庫名稱！")
        else:
            total_images = st.session_state['kb_current_b64_list'] + st.session_state['new_uploaded_cache']
            if not total_images:
                st.error("❌ 知識庫內不能沒有任何有效檔案！")
            else:
                with st.spinner("正在安全編碼並上傳同步至 GitHub 雲端..."):
                    success = upload_knowledge_base_to_github(current_kb_name.strip(), total_images)
                    if success:
                        st.success(f"🎉 雲端知識庫「{current_kb_name}」已成功保存並更新！正在清理本機快取...")
                        st.session_state['kb_current_b64_list'] = []
                        st.session_state['new_uploaded_cache'] = []
                        st.session_state['last_loaded_kb'] = ""
                        time.sleep(1.0)
                        st.rerun()
                    else:
                        st.error("❌ 同步失敗！請立刻查看下方黃色偵錯面板獲取 GitHub API 的具體拒絕原因。")

    # 日誌面板
    st.write("##")
    with st.expander("🛠️ 系統後台偵錯日誌面板 (Debug Logs)", expanded=True):
        if st.session_state['debug_logs']:
            log_text = "\n".join(st.session_state['debug_logs'][::-1])
            st.text_area("即時系統軌跡日誌：", value=log_text, height=200, key="system_debug_logs_view")
