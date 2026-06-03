import time
import os
import re
import base64
import requests
import datetime
from PIL import Image
import io
import streamlit as st
import edge_tts
import asyncio

# ==========================================================
# ⚙️ 設定區
# ==========================================================
AI_TOKEN = st.secrets["AI_TOKEN"] if "AI_TOKEN" in st.secrets else ""
GIT_TOKEN = st.secrets["GIT_TOKEN"] if "GIT_TOKEN" in st.secrets else ""
GEMINI_TOKEN = st.secrets["GEMINI_TOKEN"] if "GEMINI_TOKEN" in st.secrets else ""

GH_USER = "rlsw-collab"
GH_REPO = "rlsw"
GH_BRANCH = "main"

# ==========================================================
# 💾 實體檔案保險箱 (多用戶隔離)
# ==========================================================
def get_user_vault_path():
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    ctx = get_script_run_ctx()
    session_id = ctx.session_id if ctx else "default"
    return f".tmp_text_{session_id}.txt"

def write_to_vault(text):
    with open(get_user_vault_path(), "w", encoding="utf-8") as f: 
        f.write(text)

def read_from_vault():
    path = get_user_vault_path()
    return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""

# ==========================================
# 🛡️ GitHub 雲端實時計數同步邏輯 (防衝突 ＆ 安全自癒修復)
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
        "Authorization": f"token {GIT_TOKEN}",
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
                
            # 🌟 核心修復：安全自癒 (Auto-Schema Patching)
            # 如果發現雲端舊 JSON 缺少 dictation_tool 或 exam_tool，自動在記憶體中補齊，防止 KeyError 崩潰
            if "exam_tool" not in counter:
                counter["exam_tool"] = {"main": 0, "backup": 0}
            if "dictation_tool" not in counter:
                counter["dictation_tool"] = {"main": 0, "backup": 0}
                
            # 檢查是否需要跨日重置
            if counter.get("last_reset_date") != today_str:
                counter["last_reset_date"] = today_str
                counter["exam_tool"] = {"main": 0, "backup": 0}
                counter["dictation_tool"] = {"main": 0, "backup": 0}
                
            # 累加默書工具計數器
            counter["dictation_tool"][counter_type] += 1
            
            content_str = json.dumps(counter, indent=2)
            content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"Increment dictation {counter_type} counter [skip ci]",
                "content": content_b64
            }
            if sha:
                payload["sha"] = sha
                
            put_res = requests.put(url, headers=headers, json=payload)
            if put_res.status_code in [200, 201]:
                st.toast(f"📊 默書雲端配額同步成功！今日已用「{counter_type}」：{counter['dictation_tool'][counter_type]} 次", icon="📝")
                break
            time.sleep(0.5)
        except Exception as e:
            st.toast(f"⚠️ 雲端計數器同步失敗: {str(e)}", icon="❌")
            time.sleep(0.5)

# ==========================================================
# 🧠 雙語核心功能函數
# ==========================================================
def save_to_github(title, content):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    data = {"message": f"🤖 智能默書機：更新課文 {title}", "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"), "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def save_audio_to_github(title, speed_value, audio_bytes):
    clean_title = title.replace(".mp3", "").strip()
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{clean_title}_speed_rate_{speed_value}.mp3"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    content_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    data = {"message": f"🎵 智能默書機：上傳課文聽寫軌 {clean_title} (rate_{speed_value}%)", "content": content_b64, "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def scan_lesson_cached_audios(title):
    clean_title = title.replace(".mp3", "").strip()
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    
    text_mapping = {
        "0": "快",
        "-20": "正常",
        "-30": "慢",
        "-40": "好慢"
    }
    
    found_tracks = [] 
    if res.status_code == 200:
        for f in res.json():
            name = f["name"]
            if name.startswith(f"{clean_title}_speed_rate_") and name.endswith(".mp3"):
                speed_match = re.search(r'_speed_rate_(-?\d+)', name)
                if speed_match:
                    pure_num = speed_match.group(1)
                    display_text = text_mapping.get(pure_num, f"{pure_num}%")
                    found_tracks.append((display_text, name, pure_num))
    try:
        found_tracks.sort(key=lambda x: int(x[2]), reverse=True)
    except:
        found_tracks.sort()
    return [(t[0], t[1]) for t in found_tracks]

def generate_raw_github_url(filename):
    import urllib.parse
    encoded_filename = urllib.parse.quote(filename.strip())
    return f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/{GH_BRANCH}/lessons/{encoded_filename}"

def delete_from_github(title):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json()["sha"]
        data = {"message": f"💥 智能默書機：刪除課文 {title}", "sha": sha, "branch": GH_BRANCH}
        del_res = requests.delete(url, headers=headers, json=data)
        return del_res.status_code == 200
    return False

def delete_audio_from_github(title):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        for f in res.json():
            if f["name"].startswith(title) and f["name"].endswith(".mp3"):
                del_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{f['name']}"
                requests.delete(del_url, headers=headers, json={"message": f"💥 刪除快取軌 {f['name']}", "sha": f["sha"], "branch": GH_BRANCH})
    return True

def load_all_lessons():
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    return [f["name"].replace(".txt", "") for f in res.json() if f["name"].endswith(".txt")] if res.status_code == 200 else []

def load_single_lesson(title):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    res = requests.get(url, headers={"Authorization": f"token {GIT_TOKEN}"})
    return base64.b64decode(res.json()["content"]).decode("utf-8") if res.status_code == 200 else ""

def convert_image_to_base64(uploaded_file):
    image = Image.open(uploaded_file)
    if image.mode != "RGB":
        image = image.convert("RGB")
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# 🆕 升級為 Google 三路純免費高可用 OCR 鏈條 (完美對接 Counter)
def gemini_vision_extract_bilingual(base64_images_list, mode="中文"):
    if not base64_images_list: return ""
    if not GEMINI_TOKEN: return "錯誤：未在 Secrets 中設定 GEMINI_TOKEN！"
    
    if mode == "中文":
        prompt_text = """你現在是一個100%精準、只會看圖抄寫的繁體中文打字掃描儀。
        圖片是小學課本，漢字正上方疊加了密密麻麻的普通話拼音。
        【🚫 鋼鐵死命令】：
        1. 完全無視所有拼音字母、英文字元和小圓圈數字標號。
        2. 盯緊【大字漢字】，一字不漏、按照自然段落順序將漢字抄寫下來，保持全形標點符號與原本換行。直接輸出純文字。"""
    else:
        prompt_text = """You are now a 100% accurate, literal English text scanner for school textbooks.
        【🚫 Strict Commands】:
        1. Transcribe the English prose text from the image word for word with absolute accuracy.
        2. Maintain all original capitalization, words, paragraphs, and punctuation (commas, periods, question marks).
        3. Ignore background illustrations, page numbers, and footnote definitions at the bottom. 
        4. Output ONLY clean English text. Do not include any explanations or markdown tags."""

    parts = [{"text": prompt_text}]
    for b64 in base64_images_list:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    payload = {"contents": [{"parts": parts}]}
    
    free_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash"]
    
    for model_id in free_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_TOKEN}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=50)
            if res.status_code == 200:
                # 🌟 識別成功：同步雲端計數器至對應的主攻（Flash）或後備（Pro/v3）欄位
                c_type = "main" if model_id == "gemini-2.5-flash" else "backup"
                increment_github_counter(c_type)
                return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except:
            continue
            
    return "❌ 所有 Google 免費通道今日辨識配額已用盡，請手動複製或明天再試。"

def convert_punctuation_to_words_bilingual(text, mode="中文"):
    if mode == "中文":
        text = text.replace("——", "破折號")
        text = text.replace("《", "開書名號").replace("》", "關書名號")
        text = text.replace("，", "逗號").replace(",", "逗號")
        text = text.replace("。", "句號").replace(".", "句號")
        text = text.replace("！", "感嘆號").replace("!", "感嘆號")
        text = text.replace("？", "問號").replace("?", "問號")
        text = text.replace("；", "分號").replace(";", "分號")
        text = text.replace("：", "冒號").replace(":", "冒號")
        text = text.replace("、", "頓號")
        
        text = text.replace("「", "開引號").replace("」", "關引號")
        text = text.replace("『", "開引號").replace("』", "關引號")
        text = text.replace("“", "開引號").replace("”", "關引號")
        text = text.replace("‘", "開引號").replace("’", "關引號")
    else:
        text = text.replace(".", " full stop ").replace("。", " full stop ")
        text = text.replace(",", " comma ").replace("，", " comma ")
        text = text.replace("!", " exclamation mark ").replace("！", " exclamation mark ")
        text = text.replace("?", " question mark ").replace("？", " question mark ")
        text = text.replace(";", " semicolon ").replace("；", " semicolon ")
        text = text.replace(":", " colon ").replace("：", " colon ")
        
        text = re.sub(r"([a-zA-Z])[’']([a-zA-Z])", r"\1【APOS】\2", text)
        
        text = text.replace("“", " open quotation mark ")
        text = text.replace("”", " close quotation mark ")
        text = text.replace("‘", " open quotation mark ")
        text = text.replace("’", " close quotation mark ")
        
        quote_count = 0
        def replace_quote(match):
            nonlocal quote_count
            quote_count += 1
            return " open quotation mark " if quote_count % 2 != 0 else " close quotation mark "
        
        text = re.sub(r'["\']', replace_quote, text)
        text = text.replace("【APOS】", "'")
        
    return text

async def generate_audio_clean_raw_bilingual(speak_text, custom_rate="-20%", mode="中文"):
    if not speak_text.strip(): return b""
    try:
        if str(custom_rate).strip() == "0%":
            custom_rate = "+0%"
            
        voice_model = "zh-CN-XiaoxiaoNeural" if mode == "中文" else "en-US-AriaNeural"
        communicate = edge_tts.Communicate(speak_text, voice_model, rate=custom_rate)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        print(f"TTS 發音生成報慢: {str(e)}") 
        return b""

def generate_true_mp3_silence(seconds):
    frames_needed = int((seconds * 1000) / 24)
    single_frame = b"\xFF\xF3\x64\xC4" + (b"\x00" * 284)
    return single_frame * frames_needed

def smart_split_sentence_bilingual(text, target_len=14, mode="中文"):
    clean_text = text.replace("\r", "").strip()
    
    if mode == "中文":
        protected = clean_text.replace("：「", "【冒引】").replace("：“", "【冒引】")
        protected = protected.replace("。」", "【句引】").replace("'].", "【句引】")
        protected = protected.replace("《", "【開書名】").replace("》", "【關書名】")
        protected = protected.replace("——", "【破折】")
        
        strong_ends = ['。', '！', '？', '；']
        split_chars = ['，', '、']
        
        sub_sentences = []
        current_chunk = ""
        current_char_count = 0
        
        for char in protected:
            current_chunk += char
            if char not in (strong_ends + split_chars + ['·']):
                current_char_count += 1
            if char in strong_ends or (current_char_count >= target_len and char in split_chars):
                chunk_restore = current_chunk.replace("【冒引】", "：「").replace("【句引】", "。」")
                chunk_restore = chunk_restore.replace("【開書名】", "《").replace("【關書名】", "》")
                chunk_restore = chunk_restore.replace("【破折】", "——")
                if chunk_restore.strip(): sub_sentences.append(chunk_restore.strip())
                current_chunk = ""
                current_char_count = 0
        if current_chunk.strip():
            chunk_restore = current_chunk.replace("【冒引】", "：「").replace("【句引】", "。」")
            chunk_restore = chunk_restore.replace("【開書名】", "《").replace("【關書名】", "》")
            chunk_restore = chunk_restore.replace("【破折】", "——")
            sub_sentences.append(chunk_restore)
            
        final_sentences = []
        for s in sub_sentences:
            if not s.strip(): continue
            if final_sentences and s[0] in ['，', '、', '。', '！', '？', '；', '：', '」', '裝', ',', '.', '!', '?', ';', ':']:
                final_sentences[-1] = final_sentences[-1] + s
            else:
                final_sentences.append(s)
        return final_sentences
        
    else:
        protected = clean_text.replace("e.g.", "【EG】").replace("i.e.", "【IE】")
        conjunctions = ['that', 'when', 'because', 'if', 'which', 'and']
        tokens_raw = re.split(r'(?<=[\.!\?;\s,])', protected)
        
        sub_sentences = []
        current_chunk = ""
        
        for token in tokens_raw:
            if not token: continue
            current_words = current_chunk.split()
            token_clean = token.strip().lower()
            
            if len(current_words) >= 8 and token_clean in conjunctions and current_chunk.strip()[-1] not in ['.', '!', '?', ';', ',']:
                if current_chunk.strip():
                    sub_sentences.append(current_chunk.strip().replace("【EG】", "e.g.").replace("【IE】", "i.e."))
                current_chunk = token
            else:
                current_chunk += token
                
            clean_chunk = current_chunk.strip()
            if clean_chunk:
                last_char = clean_chunk[-1]
                if last_char in ['"', '裝', '’', "'"] and len(clean_chunk) > 1:
                    last_char = clean_chunk[-2]
                
                if last_char in ['.', '!', '?', ';'] or (last_char == ',' and len(current_chunk.split()) >= 5):
                    sub_sentences.append(current_chunk.strip().replace("【EG】", "e.g.").replace("【IE】", "i.e."))
                    current_chunk = ""
                    
        if current_chunk.strip():
            sub_sentences.append(current_chunk.strip().replace("【EG】", "e.g.").replace("【IE】", "i.e."))
            
        merged_sentences = []
        for s in sub_sentences:
            if not merged_sentences:
                merged_sentences.append(s)
            else:
                if len(s.split()) < 3 and not merged_sentences[-1].endswith(('.', '!', '?')): 
                    merged_sentences[-1] = merged_sentences[-1] + " " + s
                else:
                    merged_sentences.append(s)
                    
        return merged_sentences

# ==========================================================
# 🎨 UI & 安全防護鎖
# ==========================================================
st.set_page_config(layout="wide")
st.title("📖 智能中英雙語默書聽寫機 v1.11.2")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "current_lesson_title" not in st.session_state:
    st.session_state["current_lesson_title"] = ""
if "instant_audio_bytes" not in st.session_state:
    st.session_state["instant_audio_bytes"] = None

if not st.session_state["authenticated"]:
    st.subheader("🔐 安全密碼驗證")
    pwd_input = st.text_input("請輸入專屬訪問密碼：", type="password")
    if st.button("確認登入"):
        if pwd_input == "royroy":
            st.session_state["authenticated"] = True
            st.success("🔓 驗證成功！正在解鎖雙語默書機...")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("❌ 密碼錯誤，拒絕訪問！")
    st.stop()

# ==========================================================
# 🔓 解鎖後的雙語介面
# ==========================================================
current_text = read_from_vault()
text_hash = str(len(current_text)) + "_" + str(hash(current_text))

tab1, tab2, tab3 = st.tabs(["📸 1. Gemini 雙語影相辨識", "✍️ 2. 雲端舊課文載入與修改", "📢 3. 曉曉/Aria老師聽寫專區"])

with tab1:
    st.subheader("📸 拍下課本圖片（自動偵測中英文）")
    
    lang_mode = st.radio("請選擇當前默書科目：", ["🇨🇳 繁體中文普通話", "🇬🇧 英語 English"], horizontal=True)
    mode_label = "中文" if "中文" in lang_mode else "英文"
    
    files = st.file_uploader("請上傳或拍攝課文圖片（支援多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="up_t1")
    if files:
        cols = st.columns(min(len(files), 5))
        for i, f in enumerate(files): cols[i % 5].image(Image.open(f), use_container_width=True)
            
        if st.button("🚀 啟動 Gemini 視覺大腦識別", key="ocr_btn_t1"):
            with st.spinner(f"🔮 Gemini 視覺中樞正以【{lang_mode}】規格透視課文中..."):
                b64_list = [convert_image_to_base64(f) for f in files]
                clean_extracted_text = gemini_vision_extract_bilingual(b64_list, mode=mode_label)
                write_to_vault(clean_extracted_text)
                st.session_state["instant_audio_bytes"] = None
                st.success("✨ 原文課文已成功完美解鎖！")
                st.rerun()
                
    t1 = st.text_area("課文內容 Text Box (AI 識別後可在此進行檢查微調)", value=current_text, height=250, key=f"t1_{text_hash}")
    if t1 != current_text: 
        write_to_vault(t1)
        current_text = t1

    st.subheader("💾 將新識別的課文儲存到雲端")
    c1, c2 = st.columns([3, 1])
    with c1: title_t1 = st.text_input("請輸入課文標題：", placeholder="例如：The_Crocodile_Hunter", key="title_t1")
    with c2:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t1"):
            if not title_t1.strip() or not t1.strip(): st.error("標題和內容不能為空！")
            else:
                with st.spinner("同步中..."):
                    if save_to_github(title_t1.strip(), t1): 
                        st.session_state["current_lesson_title"] = title_t1.strip()
                        st.session_state["instant_audio_bytes"] = None
                        st.success("成功同步至 GitHub 雲端！")

with tab2:
    lessons = load_all_lessons()
    sel = st.selectbox("📂 選取雲端舊課文：", ["-- 請選擇課文 --"] + lessons, key="select_t2")
    
    c_load, c_del = st.columns([1, 1])
    with c_load:
        if st.button("📥 確認載入選取課文", key="load_btn_t2"):
            if sel != "-- 請選擇課文 --":
                write_to_vault(load_single_lesson(sel))
                st.session_state["current_lesson_title"] = sel
                st.session_state["instant_audio_bytes"] = None
                st.rerun()
                
    with c_del:
        if sel != "-- 請選擇課文 --":
            if st.button("🗑️ 徹底刪除雲端課文及音軌快取", key="del_btn_t2", type="primary"):
                with st.spinner(f"💥 正在從雲端徹底剷除《{sel}》的文字與 MP3 檔..."):
                    txt_ok = delete_from_github(sel)
                    mp3_ok = delete_audio_from_github(sel)
                    if txt_ok:
                        write_to_vault("") 
                        st.session_state["current_lesson_title"] = ""
                        st.session_state["instant_audio_bytes"] = None
                        st.success(f"✨ 剷除成功！《{sel}》的文字檔檔已被永久消滅！")
                        time.sleep(1)
                        st.rerun()
            
    t2 = st.text_area("課文內容 Text Box", value=current_text, height=250, key=f"t2_{text_hash}")
    if t2 != current_text: 
        write_to_vault(t2)
        current_text = t2
    
    st.subheader("💾 重新儲存/覆蓋課文到雲端")
    c3, c4 = st.columns([3, 1])
    with c3:
        default_name = sel if sel != "-- 請選擇課文 --" else ""
        title_t2 = st.text_input("請輸入課文標題：", value=default_name, key="title_t2")
    if st.button("💾 確認儲存至 Git", key="save_btn_t2"):
        if not title_t2.strip() or not t2.strip(): st.error("標題和內容不能為空！")
        else:
            with st.spinner("同步中..."):
                if save_to_github(title_t2.strip(), t2): 
                    st.session_state["current_lesson_title"] = title_t2.strip()
                    st.session_state["instant_audio_bytes"] = None
                    st.success("成功同步至 GitHub 雲端！")

with tab3:
    st.subheader("📢 智能雙語聽寫默書專區")
    
    play_mode = st.radio("請指定本課發音語系規格：", ["🇨🇳 普通話模式 (曉曉老師)", "🇬🇧 英語模式 (Aria老師)"], horizontal=True)
    active_lang = "中文" if "普通話" in play_mode else "英文"
    
    lessons_t3 = load_all_lessons()
    sel_t3 = st.selectbox("📂 直接選取雲端舊課文：", ["-- 請選擇課文 --"] + lessons_t3, key="select_t3")
    if st.button("📥 確認切換並載入聽寫課文", key="load_btn_t3"):
        if sel_t3 != "-- 請選擇課文 --":
            write_to_vault(load_single_lesson(sel_t3))
            st.session_state["current_lesson_title"] = sel_t3 
            st.session_state["instant_audio_bytes"] = None 
            st.rerun()
            
    st.markdown("---")
    st.markdown("#### ⚙️ 老師發音參數調節面板")
    
    speed_level = st.radio(
        "請調較老師的聽寫語速：",
        ["快", "正常", "慢", "好慢"],
        index=1, 
        horizontal=True
    )
    
    speed_mapping = {
        "快": ("0%", 0),
        "正常": ("-20%", -20),
        "慢": ("-30%", -30),
        "好慢": ("-40%", -40)
    }
    custom_rate_str, speed_percent = speed_mapping[speed_level]
    
    st.markdown("---")
    st.markdown("#### 📖 當前準備默書的課文內容：")
    active_title = st.session_state["current_lesson_title"]
    if active_title:
        st.markdown(f"**當前載入課文：** 🏆 `{active_title}`" )
    
    if current_text.strip():
        st.markdown(
            f"""
            <div style="background-color: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd; color: black; font-size: 16px; line-height: 1.6; white-space: pre-wrap; font-weight: 500;">
            {current_text}
            </div>
            """, 
            unsafe_allow_html=True
        )
    else: st.info("目前保險箱內沒有課文數據。")
    
    if current_text.strip():
        raw_paragraphs = [p.strip() for p in re.split(r'\n+', current_text) if p.strip()]
        
        dictation_units = []
        for p_idx, p_text in enumerate(raw_paragraphs):
            p_sentences = smart_split_sentence_bilingual(p_text, mode=active_lang)
            for s_idx, s_text in enumerate(p_sentences):
                if s_text.strip():
                    p_label = f"Paragraph {p_idx + 1}" if active_lang == "英文" else f"第{p_idx + 1}段"
                    dictation_units.append((p_label if s_idx == 0 else "", s_text))
        
        st.markdown("---")
        st.markdown("### 🎵 雲端已存音軌快取庫 (多速度點播面板)")
        
        if active_title:
            with st.spinner(f"🔍 正在盤點雲端《{active_title}》的所有語速音軌..."):
                cached_tracks = scan_lesson_cached_audios(active_title)
            
            if cached_tracks:
                st.success(f"✨ 成功在雲端搵到 {len(cached_tracks)} 個不同語速的版本！想播邊個直接撳 Play：")
                for speed_text, filename in cached_tracks:
                    with st.expander(f"▶️ 點擊展開點播：【語速：{speed_text}】完整聽寫連續軌", expanded=True):
                        raw_stream_url = generate_raw_github_url(filename)
                        st.audio(raw_stream_url, format="audio/mp3")
            else:
                st.info("💡 雲端目前尚未有任何語速的音軌快取。請在下方進行【全新生成】。")
        else:
            st.info("💡 請先在上方選取並確認載入課文，即可透視雲端快取庫。")
            
        st.markdown("---")
        st.markdown(f"#### 🚀 產生新快取：全篇自動連續聽寫（當前設定：{speed_level}）")
        
        if st.session_state["instant_audio_bytes"] is not None:
            st.warning(f"🔥 剛生成完畢！下方為【{speed_level}】即時緩衝音軌（已同步至雲端，稍後刷新即可收入上方快取庫）：")
            st.audio(st.session_state["instant_audio_bytes"], format="audio/mp3")

        if st.button("🏁 一鍵產生【整篇連續默書】音軌", key="play_all_btn"):
            progress_text = f"正在以【{speed_level}】語速全速封裝最高規格【{active_lang}】聽寫軌中..."
            my_bar = st.progress(0, text=progress_text)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            silence_0_5s = generate_true_mp3_silence(0.5) 
            silence_4_0s = generate_true_mp3_silence(4.0) 
            silence_8_0s = generate_true_mp3_silence(8.0) 
            
            mp3_final_list = []
            total_lines = len(dictation_units)
            
            for idx, (p_label, s_text) in enumerate(dictation_units):
                pct = int(((idx) / total_lines) * 100)
                my_bar.progress(pct, text=f"⏳ 正在合成第 {idx+1}/{total_lines} 句...")
                
                text_with_breathes = convert_punctuation_to_words_bilingual(s_text, mode=active_lang)
                
                if active_lang == "中文":
                    blocks = [b.strip() for b in re.split(r'(開書名號|關書名號|逗號|句號|感嘆號|問號|分號|冒號|頓號|開引號|關引號|破折號)', text_with_breathes) if b.strip()]
                else:
                    blocks = [text_with_breathes.strip()]
                
                sentence_audio_stream = b""
                for blk in blocks:
                    blk_clean = re.sub(r'[\s·\裝]', '', blk) if active_lang == "中文" else blk.strip()
                    blk_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(blk_clean, custom_rate=custom_rate_str, mode=active_lang))
                    if blk_audio:
                        sentence_audio_stream += blk_audio + silence_0_5s
                
                if sentence_audio_stream:
                    unit_stream = b""
                    if p_label:
                        label_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(p_label, custom_rate="-30%", mode=active_lang))
                        if label_audio: unit_stream += label_audio + silence_0_5s
                    
                    unit_stream += sentence_audio_stream + silence_4_0s + sentence_audio_stream + silence_8_0s
                    mp3_final_list.append(unit_stream)
                    
            loop.close()
            
            if mp3_final_list:
                full_mp3 = b"".join(mp3_final_list)
                my_bar.progress(100, text="🎉 音軌全面合成完畢！")
                
                st.session_state["instant_audio_bytes"] = full_mp3
                
                if active_title:
                    with st.spinner(f"💾 正在自動將完美音軌上傳為雲端快取..."):
                        save_audio_to_github(active_title, str(speed_percent), full_mp3)
                
                st.success(f"✨ 備份成功！【{speed_level}】語速音軌已送往雲端，請等待 2 秒後重新整理網頁！")
                time.sleep(2)
                st.rerun()
            else: 
                st.error("⚠️ 音軌生成失敗。發音介面可能被拒絕連線。")
                my_bar.empty()
            
        st.markdown("---")
        st.markdown("#### 🎯 自由控速區：一句句單獨加操")
        for idx, (p_label, s_text) in enumerate(dictation_units):
            display_text = f"【{p_label}】{s_text}" if p_label else s_text
            col_text, col_audio = st.columns([4, 2])
            with col_text: st.write(f"第 {idx+1} 句： `{display_text}`")
            with col_audio:
                if st.button(f"📢 聽寫第 {idx+1} 句", key=f"single_btn_{idx}"):
                    with st.spinner("合成中..."):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        silence_0_5s = generate_true_mp3_silence(0.5)
                        silence_4_0s = generate_true_mp3_silence(4.0)
                        silence_8_0s = generate_true_mp3_silence(8.0)
                        
                        text_with_breathes = convert_punctuation_to_words_bilingual(s_text, mode=active_lang)
                        if active_lang == "中文":
                            blocks = [b.strip() for b in re.split(r'(開書名號|關書名號|逗號|句號|感嘆號|問號|分號|冒號|頓號|開引號|關引號|破折號)', text_with_breathes) if b.strip()]
                        else:
                            blocks = [text_with_breathes.strip()]
                        
                        sentence_audio_stream = b""
                        for blk in blocks:
                            blk_clean = re.sub(r'[\s·\裝]', '', blk) if active_lang == "中文" else blk.strip()
                            blk_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(blk_clean, custom_rate=custom_rate_str, mode=active_lang))
                            if blk_audio: sentence_audio_stream += blk_audio + silence_0_5s
                        
                        unit_stream = b""
                        if p_label:
                            label_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(p_label, custom_rate="-30%", mode=active_lang))
                            if label_audio: unit_stream += label_audio + silence_0_5s
                        
                        if sentence_audio_stream:
                            unit_stream += sentence_audio_stream + silence_4_0s + sentence_audio_stream + silence_8_0s
                            st.audio(unit_stream, format="audio/mp3")
                        loop.close()
