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

# 🆕 升級 v1.5.5：純免費特攻版 (Google 3路鏈條 + GitHub 綠色通道 GPT-4o 聯手，0成本封頂)
APP_TITLE = "📚 香港小學測驗/考試卷生成工具 v1.5.5"

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
    AI_TOKEN = st.secrets.get("AI_TOKEN", "") # 默書工具用的 GitHub Key 做綠色通道
    GH_REPO = "rlsw"
    GH_USER = "rlsw-collab"
except Exception as e:
    st.error("❌ 未能在 Streamlit Secrets 中找到必要的基礎憑證 (GIT_TOKEN 或 GEMINI_TOKEN)。")
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
# 🛡️ GitHub 雲端實時計數同步邏輯 (防衝突)
# ==========================================
def get_hkt_date_str():
    tz_hkt = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_hkt).strftime("%Y-%m-%d")

def increment_github_counter(counter_type):
    """
    counter_type: "main" (主攻) 或 "backup" (後備)
    """
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{path}"
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
                
            if counter.get("last_reset_date") != today_str:
                counter["last_reset_date"] = today_str
                counter["exam_tool"] = {"main": 0, "backup": 0}
                counter["dictation_tool"] = {"main": 0, "backup": 0}
                
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
        except:
            time.sleep(0.5)

# ==========================================
# 🛡️ 智慧全免費失敗故障輪替鏈 (Google 3路 + GitHub 綠色通道)
# ==========================================
def call_pure_free_multiverse_ai(payload_template, text_prompt):
    """
    大腦順序：Gemini 2.5 Flash (主攻) -> Gemini 2.5 Pro (後備) -> Gemini 3 Flash (後備) -> GitHub 綠色通道 GPT-4o (終極保險)
    """
    # 1. 第一階段：Google 三路免費通道
    gemini_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash"]
    
    for g_model in gemini_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={GEMINI_TOKEN}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload_template, timeout=60)
            if res.status_code == 200:
                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                # 累加計數
                c_type = "main" if g_model == "gemini-2.5-flash" else "backup"
                increment_github_counter(c_type)
                return json.loads(raw_text), g_model
        except:
            pass
        st.toast(f"⚠️ Google {g_model} 免費通道配額耗盡，無感切換中...", icon="🔄")

    # 2. 第二階段：GitHub Green 通道自由開闢 (GPT-4o 護航)
    if AI_TOKEN:
        st.toast("🚀 正在啟動終極防禦線：GitHub 綠色通道 GPT-4o...", icon="⚡")
        # 呼叫 GitHub Models API 接口
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_TOKEN}",
            "Content-Type": "application/json"
        }
        github_payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a professional JSON output assistant. You must return a strict JSON object with fields 'exam_body' and 'answer_body' without any markdown block formatting."},
                {"role": "user", "content": text_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }
        try:
            res = requests.post(url, headers=headers, json=github_payload, timeout=75)
            if res.status_code == 200:
                raw_content = res.json()['choices'][0]['message']['content'].strip()
                # 預防性清除 markdown 符號
                raw_content = re.sub(r'^```json\s*', '', raw_content)
                raw_content = re.sub(r'\s*```$', '', raw_content).strip()
                # 併入後備計數器統計中
                increment_github_counter("backup")
                return json.loads(raw_content), "github-gpt-4o"
        except:
            pass

    return None, None

# ==========================================
# 2. 輔助函式：圖片處理 & OCR 保底
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
        
        if "數學科測驗" in clean_line or "數學科考試" in clean_line or ("考試" in clean_line and "部" not in clean_line and "題" not in clean_line and len(clean_line) < 35):
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
st.markdown("### 🔢 設定各題型生成數量")
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
# 🚀 完美正名：移除大聯盟相關詞彙
btn_call_ai = st.button("🚀 呼叫 AI 免費多通道生成新題目 🤖", type="secondary", use_container_width=True)

if btn_call_ai:
    if mc_count == 0 and fill_count == 0 and calc_count == 0 and text_count == 0:
        st.error("❌ 請至少將一項題型的滑桿調大於 0！")
    else:
        with st.spinner("🚀 正在連動多路純免費大腦鏈條，全力出題中..."):
            contents = []
            final_vault_text = read_from_exam_vault()
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
            
            payload_template = {
                "contents": [{"parts": [{"text": text_prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "exam_body": {"type": "STRING"},
                            "answer_body": {"type": "STRING"}
                        },
                        "required": ["exam_body", "answer_body"]
                    }
                }
            }
            
            # 🌟 啟動 Google 免費鏈條 + GitHub 綠色通道聯手引擎
            parsed_json, used_model = call_pure_free_multiverse_ai(payload_template, text_prompt)
            
            try:
                if parsed_json and "exam_body" in parsed_json:
                    ex_body = parsed_json.get("exam_body", "").replace("\\n", "\n").replace("\\\\n", "\n")
                    ans_body = parsed_json.get("answer_body", "").replace("\\n", "\n").replace("\\\\n", "\n")
                    st.session_state['generated_exam'] = ex_body
                    st.session_state['generated_answers'] = ans_body
                    st.session_state['exam_text_editor'] = ex_body
                    st.session_state['ans_text_editor'] = ans_body
                    st.success(f"🎉 試卷純免費通道生成成功！(最終調用功臣大腦: {used_model})")
                    st.rerun()
                else:
                    st.error("❌ 全線 AI 純免費通道（Google 3路 ＆ GitHub 綠色通道）今日配額均已用盡！請等候 Reset 重置後再試。")
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

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    btn_render = st.button("🔄 點擊執行 Python 引擎，更新視覺排版", type="secondary", use_container_width=True)
with col_btn2:
    trigger_print = st.button("🖨️ 立即列印本試卷 / 匯出 PDF", type="secondary", use_container_width=True)

if st.session_state['generated_exam'] or st.session_state['generated_answers']:
    st.write("##")
    perfect_exam_html = python_layout_engine(st.session_state['generated_exam'], is_answer_key=False)
    perfect_ans_html = python_layout_engine(st.session_state['generated_answers'], is_answer_key=True)
    full_html_content = perfect_exam_html + '<div class="page-break"></div><h2 class="ans-header">🔑 答案頁 (Answer Key)</h2>' + perfect_ans_html
    auto_print_js = "window.print();" if trigger_print else ""
    
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
    import streamlit.components.v1 as components
    components.html(html_for_printing, height=1200, scrolling=True)
