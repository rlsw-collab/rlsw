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

# 🆕 升級 v1.9.1：移除強制懸浮置頂，回歸自然網頁流，確保標題完美待在 Tabs 上方不擋畫面
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.9.1"

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

# 採用標準的 st.title，確保永遠自然排在最頂部
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
    AI_TOKEN = st.secrets.get("AI_TOKEN", "") # GitHub 免費 Models 綠色通道 Key
    GITHUB_REPO = "rlsw"
    GITHUB_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到基礎憑證 (GIT_TOKEN)。")
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

# 🛠️ GitHub 雲端知識庫讀寫函數組
def upload_knowledge_base_to_github(name, b64_images):
    safe_name = re.sub(r'[\\/*?:"<>| ]', '_', name)
    path = f"knowledge_base/{safe_name}.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    sha = None
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get("sha")
        
    payload_data = {
        "kb_name": name,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "images": b64_images
    }
    
    content_str = json.dumps(payload_data, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    
    put_payload = {
        "message": f"Upload knowledge base: {name} [skip ci]",
        "content": content_b64
    }
    if sha:
        put_payload["sha"] = sha
        
    put_res = requests.put(url, headers=headers, json=put_payload)
    return put_res.status_code in [200, 201]

def list_knowledge_bases_from_github():
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/knowledge_base"
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
    path = f"knowledge_base/{kb_name}.json"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res =requests.get(url, headers=headers)
        if res.status_code == 200:
            content = base64.b64decode(res.json()["content"]).decode("utf-8")
            return json.loads(content)
    except:
        pass
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
# Tabs 直接緊跟在 st.title 標題正下方，結構乾淨自然
tab_exam, tab_kb = st.tabs(["📝 試卷生成工具", "📂 雲端多圖知識庫管理"])

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
            selected_kb = st.selectbox("📂 選擇你要對接的知識庫資料：", available_kbs)
            if selected_kb:
                kb_data = get_knowledge_base_content(selected_kb)
                if kb_data:
                    st.success(f"✅ 已成功加載知識庫「{selected_kb}」，內含 {len(kb_data.get('images', []))} 張課本/工作紙圖片。")
                    chosen_kb_images = kb_data.get('images', [])
                    final_vault_text = f"[使用雲端 GitHub 知識庫圖片庫: {selected_kb}]"

    st.write("##")
    btn_call_ai = st.button("🚀 呼叫「分批拼接不偷懶引擎」生成完整試卷 🤖", type="secondary", use_container_width=True)

    if btn_call_ai:
        if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
            st.error("❌ 請至少選擇一種題型的數量大於 0！" if language == "繁體中文" else "❌ Please select at least one question type with a quantity greater than 0!")
        elif scope_mode == "選用先前存放的雲端知識庫" and not chosen_kb_images:
            st.error("❌ 所選知識庫無有效數據，無法建立試卷庫！")
        else:
            if scope_mode == "選用先前存放的雲端知識庫" and chosen_kb_images:
                st.toast("🔮 正在由 GPT-4o 深度解構所有知識庫圖片以建立精準試題庫...", icon="📦")
                
                analysis_messages = [
                    {"role": "system", "content": "You are a professional curriculum analyzer. Your task is to analyze multiple images from textbooks/worksheets and synthesize them into a highly concise but detailed blueprint of knowledge points, core concepts, formulas, and common exercise patterns for test item generation. Output purely in Chinese if requested, or English."}
                ]
                
                user_content = [{"type": "text", "text": "請深度分析這批由學生 iPad 拍攝上傳的工作紙與課本內容。提煉出裡面所有的考點、題型結構、幾何數字邏輯與公式，為稍後的出題做最萬全的知識儲備基礎。"}]
                for b64_img in chosen_kb_images:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                    })
                    
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
                if language == "繁體中文":
                    geo_rule = f"""
                    ⚠️【核心幾何命令】：考量到本次範圍涉及幾何，你必須在題目中穿插嵌入幾何圖形標記。
                    🔥【絕對指令 1 - 範圍匹配】：請「嚴格限制」只選用與給定範圍概念相關的圖形！
                    🔥【絕對指令 2 - 動態參數】：標記中的參數數值 (如 w, h, r1, b, l 等) 必須根據你當前出題的實際數字「動態填入」，絕對不能照抄下方範例的死數字！
                    
                    可選用的標記格式：
                    - [GEOMETRIC:three_circles_linear:r1=大圓半徑;r2=中圓半徑;r3=小圓半徑]
                    - [GEOMETRIC:circles_in_rectangle:w=長方形長;h=長方形闊]
                    - [GEOMETRIC:concentric_overlap:d1=大圓直徑]
                    - [GEOMETRIC:triangle:b=三角形底;h=三角形高]
                    - [GEOMETRIC:cuboid_volume:l=長方體長;w=長方體闊;h=長方體高]
                    """
                else:
                    geo_rule = f"""
                    ⚠️ [Geometric Image Rules]: Since the scope involves geometry, you must embed geometry diagram markers into the questions.
                    🔥 [Rule 1 - Strict Scope Match]: Only use shapes strictly mentioned in the scope! 
                    🔥 [Rule 2 - Dynamic Parameters]: Replace the parameters (w, h, r1, b, l, etc.) with the actual random numbers you use for the questions. Never use placeholder texts.
                    
                    Available Marker Formats:
                    - [GEOMETRIC:three_circles_linear:r1=large_radius;r2=mid_radius;r3=small_radius]
                    - [GEOMETRIC:circles_in_rectangle:w=length;h=width]
                    - [GEOMETRIC:concentric_overlap:d1=large_diameter]
                    - [GEOMETRIC:triangle:b=base;h=height]
                    - [GEOMETRIC:cuboid_volume:l=length;w=width;h=height]
                    """

            tasks = []
            if language == "繁體中文":
                if mc_count > 0: tasks.append((f"第一部分：多項選擇題（共 {mc_count} 題，題號由 1 開始到 {mc_count}）", mc_count))
                if fill_count > 0: tasks.append((f"第二部分：填充題（共 {fill_count} 題，題號由 {mc_count+1} 開始到 {mc_count+fill_count}）", fill_count))
                if calc_count > 0: tasks.append((f"第三部分：列式計算題（共 {calc_count} 題，題號由 {mc_count+fill_count+1} 開始到 {mc_count+fill_count+calc_count}）", calc_count))
                if text_count > 0: tasks.append((f"第四部分：長題目文字題（共 {text_count} 題，題號由 {mc_count+fill_count+calc_count+1} 開始到 {mc_count+fill_count+calc_count+text_count}）", text_count))
                
                combined_exam = f"### 香港小學{grade}{subject}科測驗卷\n班別：__________  姓名：__________  學號：__________\n\n"
                combined_ans = "### 🔑 答案頁與幾何解題詳解 (Answer Key)\n\n"
            else:
                if mc_count > 0: tasks.append((f"Part I: Multiple Choice Questions (Total {mc_count} questions, from Q1 to Q{mc_count})", mc_count))
                if fill_count > 0: tasks.append((f"Part II: Fill in the Blanks (Total {fill_count} questions, from Q{mc_count+1} to Q{mc_count+fill_count})", fill_count))
                if calc_count > 0: tasks.append((f"Part III: Calculation Questions (Total {calc_count} questions, from Q{mc_count+fill_count+1} to Q{mc_count+fill_count+calc_count})", calc_count))
                if text_count > 0: tasks.append((f"Part IV: Long/Word Questions (Total {text_count} questions, from Q{mc_count+fill_count+calc_count+1} to Q{mc_count+fill_count+calc_count+text_count})", text_count))
                
                grade_map = {"小一":"Primary 1", "小二":"Primary 2", "小三":"Primary 3", "小四":"Primary 4", "小五":"Primary 5", "小六":"Primary 6"}
                subject_map = {"中文":"Chinese", "英文":"English", "數學":"Mathematics", "常識":"General Studies"}
                en_grade = grade_map.get(grade, grade)
                en_subject = subject_map.get(subject, subject)
                
                combined_exam = f"### Hong Kong {en_grade} {en_subject} Quiz/Exam Paper\nClass: __________  Name: __________  No.: __________\n\n"
                combined_ans = "### 🔑 Answer Key & Detailed Solutions\n\n"
            
            progress_bar = st.progress(0.0)
            task_step = 1.0 / len(tasks) if tasks else 1.0
            
            for idx, (t_title, t_num) in enumerate(tasks):
                st.toast(f"⏳ 正在生成 {t_title}" if language == "繁體中文" else f"⏳ Generating {t_title}", icon="📝")
                
                if language == "繁體中文":
                    sub_prompt = f"""你是一位香港名校【{subject}科】主任。請為【香港小學{grade}】編寫【{subject}科】測驗卷的【{t_title}】。
                    本次出題範圍與已提煉的知識庫考點為：「{final_vault_text}」
                    
                    要求：
                    1. 必須完整地生成全部 {t_num} 道題目，每一題都要寫出具體文字。
                    2. ❌ 絕對不允許使用 any '...' 省略號，亦不准寫出簡寫字。
                    3. 繁體中文香港小學標準。
                    {geo_rule}
                    
                    🎯【必須回傳的 JSON 格式】：
                    {{
                      "exam_body": "### {t_title}\\n\\n這裡依序寫出第1題到第{t_num}題的題目內容...",
                      "answer_body": "### {t_title} 答案詳解\\n\\n這裡寫出對應的詳細公式與答案..."
                    }}
                    """
                else:
                    grade_map = {"小一":"Primary 1", "小二":"Primary 2", "小三":"Primary 3", "小四":"Primary 4", "小五":"Primary 5", "小六":"Primary 6"}
                    subject_map = {"中文":"Chinese", "英文":"English", "數學":"Mathematics", "常識":"General Studies"}
                    en_grade = grade_map.get(grade, grade)
                    en_subject = subject_map.get(subject, subject)
                    
                    sub_prompt = f"""You are a professional Subject Head of [{en_subject}] in a prestigious Hong Kong primary school. 
                    Please draft [{t_title}] for a Hong Kong [{en_grade}] [{en_subject}] exam paper.
                    The exam topics/analyzed knowledge bases are: "{final_vault_text}"
                    
                    Requirements:
                    1. You must completely generate all {t_num} questions. Write out each question explicitly.
                    2. ❌ Strictly NO abbreviations or ellipses like '...' allowed. 
                    3. Use standard British English / Hong Kong primary school English textbook standards.
                    {geo_rule}
                    
                    🎯 [REQUIRED JSON FORMAT]:
                    {{
                      "exam_body": "### {t_title}\\n\\nList question 1 to question {t_num} sequentially here...",
                      "answer_body": "### {t_title} Answer Key & Explanations\\n\\nProvide step-by-step solutions and final answers here..."
                    }}
                    """
                
                res_json = call_pure_free_multiverse_ai([{"role": "user", "content": sub_prompt}], is_json=True)
                if res_json:
                    combined_exam += ensure_flat_string(res_json.get("exam_body", "")) + "\n\n"
                    combined_ans += ensure_flat_string(res_json.get("answer_body", "")) + "\n\n"
                else:
                    st.error(f"❌ {t_title} 生成失敗，請重試。" if language == "繁體中文" else f"❌ Failed to generate {t_title}, please try again.")
                    st.stop()
                    
                progress_bar.progress((idx + 1) * task_step)
                time.sleep(0.5)

            st.session_state['generated_exam'] = combined_exam
            st.session_state['generated_answers'] = combined_ans
            st.session_state['exam_text_editor'] = combined_exam
            st.session_state['ans_text_editor'] = combined_ans
            st.success("🎉 全套完整題目生成完畢！" if language == "繁體中文" else "🎉 Full exam paper generated successfully!")
            st.rerun()

    # 原始碼控制台
    st.write("---")
    st.header("📝 步驟三：幾何源碼調校控制台" if language == "繁體中文" else "📝 Step 3: Source Code Fine-tuning Console")
    col_edit1, col_edit2 = st.columns(2)
    with col_edit1:
        if 'exam_text_editor' not in st.session_state: st.session_state['exam_text_editor'] = st.session_state['generated_exam']
        def on_exam_change(): st.session_state['generated_exam'] = st.session_state['exam_text_editor']
        st.text_area("題目微調：" if language == "繁體中文" else "Edit Questions:", value=st.session_state['exam_text_editor'], height=350, key="exam_text_editor", on_change=on_exam_change)
    with col_edit2:
        if 'ans_text_editor' not in st.session_state: st.session_state['ans_text_editor'] = st.session_state['generated_answers']
        def on_ans_change(): st.session_state['generated_answers'] = st.session_state['ans_text_editor']
        st.text_area("答案與詳解微調：" if language == "繁體中文" else "Edit Answer Key:", value=st.session_state['ans_text_editor'], height=350, key="ans_text_editor", on_change=on_ans_change)

    # 排版與 iPad 導出
    st.write("---")
    st.header("🎨 步驟四：印刷級幾何排版與打印導出" if language == "繁體中文" else "🎨 Step 4: Print-ready Layout & Export")

    if st.session_state['generated_exam'] or st.session_state['generated_answers']:
        perfect_exam_html = python_layout_engine(st.session_state['generated_exam'], is_answer_key=False)
        perfect_ans_html = python_layout_engine(st.session_state['generated_answers'], is_answer_key=True)
        full_html_content = perfect_exam_html + '<div class="page-break"></div>' + perfect_ans_html
        
        trigger_print = st.button("🖨️ 立即啟動手提電腦列印" if language == "繁體中文" else "🖨️ Print Now", type="secondary", use_container_width=True)
        auto_print_js = "window.print();" if trigger_print else ""

        html_for_printing = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            html, body {{ background-color: white !important; color: #000000 !important; -webkit-text-fill-color: #000000 !important; }}
            #exam-body {{ font-family: "Microsoft JhengHei", "微軟正黑體", Arial, sans-serif; padding: 20px; font-size: 16px; line-height: 2.3; }}
            .exam-title-main {{ font-size: 26px !important; font-weight: 800 !important; text-align: center !important; margin-top: 20px !important; margin-bottom: 15px !important; }}
            .exam-user-info {{ font-size: 17px !important; font-weight: bold !important; text-align: center !important; margin-bottom: 30px !important; word-spacing: 12px; }}
            .exam-section-header {{ font-size: 19px !important; font-weight: 800 !important; margin-top: 25px !important; margin-bottom: 12px !important; border-left: 5px solid #000 !important; padding-left: 10px; }}
            .fill-blank-underline {{ display: inline-block; width: 150px; border-bottom: 1.5px solid #000 !important; margin: 0 10px; height: 18px; vertical-align: bottom; }}
            .v-frac {{ display: inline-flex; flex-direction: column; vertical-align: middle; text-align: center; line-height: 1.0; padding: 0 4px; font-size: 0.85em; }}
            .v-frac .num {{ border-bottom: 1.5px solid #000; padding-bottom: 2px; min-width: 14px; }}
            .v-frac .den {{ padding-top: 2px; min-width: 14px; }}
            .mc-option {{ margin-left: 20px; margin-top: 6px; margin-bottom: 6px; display: block !important; clear: both; }}
            .mc-circle {{ font-size: 16px; font-weight: normal; margin-right: 4px; font-family: sans-serif; }}
            .mc-ans {{ color: #ff4b4b; font-weight: bold; margin-right: 4px; font-family: sans-serif; }}
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
            label="📲 iPad 專用：下載完美全圓圈選項幾何 HTML 列印檔" if language == "繁體中文" else "📲 Download Print-ready HTML File for iPad",
            data=html_for_printing,
            file_name=f"香港小學{grade}_試卷.html" if language == "繁體中文" else f"HK_Primary_{grade}_Exam.html",
            mime="text/html",
            use_container_width=True,
            type="primary"
        )

        st.write("##")
        import streamlit.components.v1 as components
        components.html(html_for_printing, height=1200, scrolling=True)

# ------------------------------------------
# TAB 2: 雲端多圖知識庫管理
# ------------------------------------------
with tab_kb:
    st.header("📂 iPad 雲端課文/作業/工作紙知識庫上傳")
    st.info("💡 你可以在這裡上傳多張由 iPad 拍攝的課文或工作紙相片，打包儲存至 GitHub，日後即可在生成考卷時直接調用！")
    
    uploaded_files = st.file_uploader("📸 請選擇或拖放上傳相片：", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"📎 已加載 {len(uploaded_files)} 個相片檔案。")
        kb_name_input = st.text_input("📝 請為這組資料庫命名（例如：小六常識第二單元、小五數學圓形面積）：", value="")
        
        if st.button("💾 打包並上傳至雲端儲存庫", type="primary", use_container_width=True):
            if not kb_name_input.strip():
                st.error("❌ 請輸入此資料組的儲存名稱！")
            else:
                with st.spinner("正在將 iPad 相片安全編碼並同步至 GitHub 雲端..."):
                    b64_list = []
                    for f in uploaded_files:
                        f_bytes = f.read()
                        b64_str = base64.b64encode(f_bytes).decode("utf-8")
                        b64_list.append(b64_str)
                    
                    success = upload_knowledge_base_to_github(kb_name_input.strip(), b64_list)
                    if success:
                        st.success(f"🎉 資料庫「{kb_name_input}」已完美同步到 GitHub！日後可在 Tab 1 步驟二中直接讀取調用。")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ 上傳失敗，請確認你的 GitHub Key 權限與倉庫配置是否正確。")
