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

# 🆕 升級 v1.9.0：將系統版本標題改為 CSS 固定置頂懸浮（Sticky Header），確保滾動時不消失
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.9.0"

# 注入全域樣式：包含打印控制與固定置頂標題（Fixed Header）的排版
st.markdown("""
<style>
/* 1. 固定置頂標題樣式 */
.sticky-header {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    background-color: #f0f2f6; /* 跟 Streamlit 默認底色接近，也可改 white */
    padding: 15px 30px;
    font-size: 28px;
    font-weight: bold;
    color: #31333F;
    border-bottom: 2px solid #e0e0e0;
    z-index: 999999;
}

/* 2. 為主體內容留出頂部空間，避免被置頂標題擋住 */
.main-content-padding {
    padding-top: 75px;
}

/* 3. @media print 打印專用樣式 */
@media print {
    .sticky-header,
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

# 顯示置頂標題
st.markdown(f'<div class="sticky-header">{APP_TITLE}</div>', unsafe_allow_html=True)

# 密碼鎖邏輯
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    # 密碼界面同樣套用主體 Padding
    st.markdown('<div class="main-content-padding"></div>', unsafe_allow_html=True)
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
        res = requests.get(url, headers=headers)
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
