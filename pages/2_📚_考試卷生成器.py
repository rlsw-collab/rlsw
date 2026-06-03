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

APP_TITLE = "📚 香港小學測驗/考試卷生成工具"

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

st.markdown("""
    <style>
        @media print {
            .no-print { display: none !important; }
            .stButton { display: none !important; }
            div[data-testid="stSidebar"] { display: none !important; }
            body { background-color: #fff !important; font-size: 14pt !important; color: #000 !important; }
            @page { size: A4; margin: 20mm 18mm 20mm 18mm; }
            h1, h2, h3, h4 { color: #000 !important; page-break-after: avoid; }
            .exam-container { border: none !important; padding: 0 !important; box-shadow: none !important; }
        }
        .exam-container {
            background-color: #ffffff;
            padding: 40px 50px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
            font-family: 'Times New Roman', "MingLiU", "Microsoft JhengHei", sans-serif;
            line-height: 1.8;
            color: #000000;
        }
        .v-frac { display: inline-table; vertical-align: middle; text-align: center; line-height: 1.0; padding: 0 4px; font-size: 0.85em; }
        .v-frac .num { border-bottom: 1.5px solid #000; padding-bottom: 2px; min-width: 14px; }
        .v-frac .den { padding-top: 2px; min-width: 14px; }
        .mc-option { 
            margin-left: 20px; 
            margin-top: 6px; 
            margin-bottom: 6px; 
            display: block !important; 
            clear: both;
        }
        .mc-circle { font-size: 16px; font-weight: normal; margin-right: 4px; font-family: sans-serif; }
        .mc-ans { color: #ff4b4b; font-weight: bold; margin-right: 4px; font-family: sans-serif; }
        .write-zone { margin-top: 15px; margin-bottom: 30px; width: 100%; }
        .row-line { width: 100%; height: 38px; border-bottom: 1px dashed #999 !important; }
        .page-break { page-break-before: always; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 📊 試卷生成器專屬：扁平化真實模型計數器
# ==========================================
def increment_github_counter_for_exam(model_id="gpt-4o"):
    """當試卷生成成功時，直接在 JSON 第一層對指定的模型進行 +1"""
    GIT_TOKEN = st.secrets["GIT_TOKEN"] if "GIT_TOKEN" in st.secrets else ""
    GH_USER = "rlsw-collab"
    GH_REPO = "rlsw"
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GIT_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    tz_hkt = datetime.timezone(datetime.timedelta(hours=8))
    today_str = datetime.datetime.now(tz_hkt).strftime("%Y-%m-%d")
    
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                counter = json.loads(content)
                sha = data["sha"]
            else:
                counter = {"last_reset_date": today_str}
                sha = None
                
            if counter.get("last_reset_date") != today_str:
                counter = {"last_reset_date": today_str}
                
            if model_id not in counter:
                counter[model_id] = 0
            counter[model_id] += 1
            
            content_str = json.dumps(counter, indent=2)
            content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"Increment counter for {model_id} via Exam Tool [skip ci]",
                "content": content_b64
            }
            if sha:
                payload["sha"] = sha
                
            put_res = requests.put(url, headers=headers, json=payload)
            if put_res.status_code in [200, 201]:
                st.toast(f"📊 試卷生成配額同步成功！當前調用：【{model_id}】", icon="📝")
                break
            time.sleep(0.5)
        except Exception as e:
            st.toast(f"⚠️ 試卷計數器同步失敗: {str(e)}", icon="❌")
            time.sleep(0.5)

# ==========================================
# 🛠️ 輔助渲染工具：幾何圖形生成與直式分數轉換
# ==========================================
def inject_dynamic_geometry_and_fractions(html_content, slider_vals):
    for i, val in enumerate(slider_vals):
        html_content = html_content.replace(f"[SLIDER_{i+1}]", str(val))
        
    frac_pattern = r'\[FRAC:\s*([0-9\-\+\*a-zA-Z]+)\s*/\s*([0-9\-\+\*a-zA-Z]+)\]'
    def frac_repl(match):
        num = match.group(1)
        den = match.group(2)
        return f'<table class="v-frac"><tr><td class="num">{num}</td></tr><tr><td class="den">{den}</td></tr></table>'
    html_content = re.sub(frac_pattern, frac_repl, html_content)
    
    if "平面幾何" in html_content or "面積" in html_content or "圓" in html_content or "三角形" in html_content:
        if "圓" in html_content and "</svg>" not in html_content:
            r_val = slider_vals[0] if len(slider_vals) > 0 else 7
            circle_svg = f"""
            <div style='text-align:center; margin:15px 0;'>
                <svg width='160' height='160' viewBox='0 0 160 160' style='background:transparent;'>
                    <circle cx='80' cy='80' r='60' stroke='#000' stroke-width='2' fill='none' />
                    <line x1='80' y1='80' x2='140' y2='80' stroke='#000' stroke-width='1.5' stroke-dasharray='4,4' />
                    <circle cx='80' cy='80' r='3' fill='#000' />
                    <text x='74' y='73' font-size='14'>O</text>
                    <text x='105' y='98' font-size='13'>r = {r_val} cm</text>
                </svg>
            </div>
            """
            html_content = html_content.replace("</div>\n<div class='mc-option'", f"{circle_svg}</div>\n<div class='mc-option'")
            
        if ("三角形" in html_content or "面積" in html_content) and "圓" not in html_content and "</svg>" not in html_content:
            b_val = slider_vals[0] if len(slider_vals) > 0 else 10
            h_val = slider_vals[1] if len(slider_vals) > 1 else 15
            triangle_svg = f"""
            <div style='text-align:center; margin:15px 0;'>
                <svg width='180' height='130' viewBox='0 0 180 130' style='background:transparent;'>
                    <polygon points='30,110 150,110 150,20' stroke='#000' stroke-width='2' fill='none' />
                    <path d='M 140,110 L 140,100 L 150,100' stroke='#000' stroke-width='1.5' fill='none' />
                    <text x='90' y='125' font-size='13'>底 = {b_val} cm</text>
                    <text x='158' y='70' font-size='13'>高 = {h_val} cm</text>
                </svg>
            </div>
            """
            html_content = html_content.replace("</div>\n<div class='mc-option'", f"{triangle_svg}</div>\n<div class='mc-option'")
            
    return html_content

# ==========================================
# 🤖 試卷生成核心 API 呼叫區 (Azure GPT-4o 端)
# ==========================================
def generate_exam_paper_api(prompt_payload):
    AI_TOKEN = st.secrets["AI_TOKEN"] if "AI_TOKEN" in st.secrets else ""
    if not AI_TOKEN:
        st.error("❌ 未能在 Secrets 中配置完整的 AI_TOKEN，無法發起 AI 請求。")
        return None
        
    url = "https://api.oneapi.sh/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_TOKEN}",
        "Content-Type": "application/json"
    }
    
    system_instruction = (
        "你是一位專門對接香港教育局小學課程指引（包含主流教材如：常識科、數學科樂思/大眾/現代、中文科科利/啟思）的資深出題專家。\n"
        "請根據用戶指定的年級、科目及主題，生成一份結構嚴謹、排版完美的香港小學標準風格測驗試卷。\n\n"
        "【⚠️ 核心出題及排版技術規範 - 務必嚴格執行】\n"
        "1. 必須完全使用正體中文（香港慣用詞彙，例如：次數、配額、厘米、角柱、乘方），絕對不能出現簡體字或內地術語（如：厘米不能寫成公分）。\n"
        "2. 如果題目涉及分數，請【務必】使用 `[FRAC: 分子/分母]` 格式包裹（例如：`[FRAC: 3/5]`），系統會自動將其轉化為考卷專用的高精度直式分數。\n"
        "3. 如果是【選擇題】，每一個選項必須使用單獨的獨立 DIV 包裹，並加上專門的樣式類別（格式必須為：`<div class='mc-option'><span class='mc-circle'>①</span> 選項內容</div>`），序號統一使用帶圈數字 ① ② ③ ④，嚴禁將多個選項並排在同一行！\n"
        "4. 試卷結構需包含：\n"
        "   - 精美考卷標頭（學校名稱留空括號、學生姓名、班別、學號、得分）。\n"
        "   - 第一部分：多項選擇題（每題需明確標出分值，如：(2分)）。\n"
        "   - 第二部分：語文基礎 / 填充或短答題（下方需預留答題橫線區：`<div class='write-zone'><div class='row-line'></div></div>`）。\n"
        "5. 為了配合動態幾何圖形與數字參數變更，如果題目有具體數字，請【優先使用】`[SLIDER_1]`、`[SLIDER_2]`、`[SLIDER_3]` 標籤來代替死數字（例如：若提及半徑或底高，可寫：半徑為 `[SLIDER_1]` 厘米）。\n"
        "6. 不要包含任何 ```html 程式碼包裹區塊，直接輸出最純淨、可由 <body> 直接渲染的 HTML 內容。"
    )
    
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt_payload}
        ],
        "temperature": 0.4,
        "max_tokens": 4000
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            increment_github_counter_for_exam("gpt-4o")
            return res.json()["choices"][0]["message"]["content"].strip()
        else:
            st.error(f"❌ API 伺服器回傳錯誤代碼: {res.status_code}，請稍後再試。")
            return None
    except Exception as e:
        st.error(f"⚠️ 網絡連線超時或異常: {str(e)}")
        return None

# ==========================================
# 🎨 老師友善控制面板 (Sidebar 控制區)
# ==========================================
with st.sidebar:
    st.header("🛠️ 考卷參數配置面板")
    
    grade = st.selectbox("1. 選擇學生年級：", ["小一 (Primary 1)", "小二 (Primary 2)", "小三 (Primary 3)", "小四 (Primary 4)", "小五 (Primary 5)", "小六 (Primary 6)"])
    subject = st.selectbox("2. 選擇學科：", ["數學科 (Mathematics)", "中文科 (Chinese)", "常識科 / 綜合科學 (General Studies)"])
    
    st.write("---")
    st.subheader("📐 幾何與數字動態調控滑桿")
    
    s1 = st.select_slider("動態參數 1 (如半徑/底/填充數)：", options=[0, 5, 10, 15, 20, 25, 30], value=10)
    s2 = st.select_slider("動態參數 2 (如高/次數/核心值)：", options=[0, 5, 10, 15, 20, 25, 30], value=15)
    s3 = st.select_slider("動態參數 3 (額外輔助參數)：", options=[0, 5, 10, 15, 20, 25, 30], value=5)
    slider_vals = [s1, s2, s3]
    
    st.write("---")
    topic = st.text_input("3. 輸入考試特定主題範疇：", value="平面圓形組合題 / 分數運算與應用題")
    question_count = st.slider("4. 題目數量設定：", min_value=2, max_value=12, value=4, step=1)
    
    st.write("---")
    submit_btn = st.button("🚀 開始動態生成專業試卷", use_container_width=True)

# ==========================================
# 📄 試卷即時渲染與打印預覽區
# ==========================================
if 'current_paper' not in st.session_state:
    st.session_state['current_paper'] = None

if submit_btn:
    user_prompt = f"請為{grade}的{subject}生成一份主題為「{topic}」的專業測驗卷。總題目數量要求為 {question_count} 題。請確保完美嵌入 [SLIDER_1]、[SLIDER_2] 等幾何控制標籤，並使用香港本地考卷標準格式。"
    
    with st.spinner("🔮 AI 專家出題系統正在高速編排題目..."):
        raw_html = generate_exam_paper_api(user_prompt)
        if raw_html:
            st.session_state['current_paper'] = raw_html
            st.success("🎉 試卷動態生成成功！您可以在下方查看、動態調整參數，或直接進行列印。")

if st.session_state['current_paper']:
    st.markdown("### 📄 考卷動態實時預覽 (A4 標準排版)")
    final_rendered_html = inject_dynamic_geometry_and_fractions(st.session_state['current_paper'], slider_vals)
    st.markdown(f"<div class='exam-container'>{final_rendered_html}</div>", unsafe_allow_html=True)
else:
    st.info("👈 請先在左側控制面板中配置您的年級與主題，然後點擊「開始動態生成專業試卷」按鈕。")
