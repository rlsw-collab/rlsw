import pytesseract
import time
import os
import re
import base64
import requests
from PIL import Image
import streamlit as st
from azure.ai.inference import ChatCompletionsClient  
from azure.core.credentials import AzureKeyCredential
import edge_tts
import asyncio

# ==========================================================
# ⚙️ 雲端與本地自動適應設定專區
# ==========================================================
if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

AI_TOKEN = ""
GIT_TOKEN = ""

if "AI_TOKEN" in st.secrets and "GIT_TOKEN" in st.secrets:
    AI_TOKEN = st.secrets["AI_TOKEN"]
    GIT_TOKEN = st.secrets["GIT_TOKEN"]
else:
    TOKEN_PATH = r"C:\Users\roysw\Desktop\DictationBot\GitHubToken.txt"
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            local_tok = f.read().strip()
            AI_TOKEN = local_tok
            GIT_TOKEN = local_tok

GH_USER = "rlsw-collab"
GH_REPO = "rlsw"
GH_BRANCH = "main"

# ==========================================================
# 💾 多用戶「Session 簽名級」實體檔案保險箱
# ==========================================================
def get_user_vault_path():
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    ctx = get_script_run_ctx()
    session_id = ctx.session_id if ctx else "default_user"
    return f".tmp_text_{session_id}.txt"

def write_to_vault(text):
    vault_path = get_user_vault_path()
    with open(vault_path, "w", encoding="utf-8") as f:
        f.write(text)

def read_from_vault():
    vault_path = get_user_vault_path()
    if os.path.exists(vault_path):
        with open(vault_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# ==========================================================
# 🧠 後台核心函數
# ==========================================================

def get_github_file_url(filename):
    return f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{filename}"

def save_to_github(title, content):
    if not GIT_TOKEN: return False, "錯誤：未偵測到有效的 GIT_TOKEN！"
    filename = f"{title}.txt"
    url = get_github_file_url(filename)
    headers = {
        "Authorization": f"token {GIT_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    res = requests.get(url, headers=headers)
    sha = None
    if res.status_code == 200:
        sha = res.json().get("sha")
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {
        "message": f"🤖 智能默書機：儲存/更新課文 {title}",
        "content": content_b64,
        "branch": GH_BRANCH
    }
    if sha: data["sha"] = sha
    put_res = requests.put(url, headers=headers, json=data)
    return (True, "成功同步至 GitHub 雲端！") if put_res.status_code in [200, 201] else (False, f"Git 錯誤代碼: {put_res.status_code}")

def delete_from_github(title):
    if not GIT_TOKEN: return False, "錯誤：未偵測到有效的 GIT_TOKEN！"
    filename = f"{title}.txt"
    url = get_github_file_url(filename)
    headers = {
        "Authorization": f"token {GIT_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get("sha")
        data = {
            "message": f"🗑️ 智能默書機：刪除課文 {title}",
            "sha": sha,
            "branch": GH_BRANCH
        }
        del_res = requests.delete(url, headers=headers, json=data)
        return (True, f"課文《{title}》已成功從雲端永久刪除！") if del_res.status_code == 200 else (False, "刪除失敗")
    return False, "找不到檔案指紋"

def load_all_lessons_from_github():
    if not GIT_TOKEN: return []
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return [f["name"].replace(".txt", "") for f in res.json() if f["name"].endswith(".txt")]
    except: pass
    return []

def load_single_lesson(title):
    url = get_github_file_url(f"{title}.txt")
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return base64.b64decode(res.json().get("content", "")).decode("utf-8")
    return ""

def ai_correct_text_strict(bad_text):
    if not AI_TOKEN: return bad_text
    try:
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(AI_TOKEN))
        prompt = """你是一個專門修復小學課文 OCR 錯誤的頂級專家。請將文本中所有的普通話拼音和英文字母徹底刪除，將中文字 100% 還原成精準、通順、符合小學課本邏輯的【繁體中文課文原文】。絕對不要包含 any 拼音、Markdown 語法標籤、註解或額外解釋，直接輸出修復後的純課文。"""
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n文本:\n" + bad_text}], model="gpt-4o")
        return response.choices[0].message.content.strip()
    except:
        return bad_text

async def generate_single_audio(text):
    clean_text = re.sub(r'[，。！？；：、「」『』《》·——……]', ' ', text).strip()
    if not clean_text: return b""
    communicate = edge_tts.Communicate(clean_text, "zh-CN-XiaoxiaoNeural", rate="-5%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    return audio_data

def build_dictation_wav(audio_bytes, sample_rate=24000):
    if not audio_bytes: return b""
    raw_pcm = audio_bytes[100:] if len(audio_bytes) > 100 else audio_bytes
    bytes_per_sec = sample_rate * 2 
    padding_breath = b"\x00" * int(bytes_per_sec * 2.5) 
    padding_write = b"\x00" * int(bytes_per_sec * 8.0)   
    combined_pcm = raw_pcm + padding_breath + raw_pcm + padding_write
    
    header = b"RIFF"
    header += (len(combined_pcm) + 36).to_bytes(4, "little")
    header += b"WAVEfmt "
    header += (16).to_bytes(4, "little")
    header += (1).to_bytes(2, "little")       
    header += (sample_rate).to_bytes(4, "little") 
    header += (bytes_per_sec).to_bytes(4, "little")
    header += (2).to_bytes(2, "little")
    header += (16).to_bytes(2, "little")      
    header += b"data"
    header += (len(combined_pcm)).to_bytes(4, "little")
    return header + combined_pcm

def build_full_lesson_wav(pcm_list, sample_rate=24000):
    full_pcm = b""
    for pcm in pcm_list:
        if len(pcm) > 44: full_pcm += pcm[44:] 
    if not full_pcm: return b""
    header = b"RIFF"
    header += (len(full_pcm) + 36).to_bytes(4, "little")
    header += b"WAVEfmt "
    header += (16).to_bytes(4, "little")
    header += (1).to_bytes(2, "little")       
    header += (sample_rate).to_bytes(4, "little") 
    header += (sample_rate * 2).to_bytes(4, "little")
    header += (2).to_bytes(2, "little")
    header += (16).to_bytes(2, "little")      
    header += b"data"
    header += (len(full_pcm)).to_bytes(4, "little")
    return header + full_pcm

def smart_split_sentence(text, target_len=10):
    # 將所有常見的繁網全形標點統統納入切割雷達，確保每句長度適中，微軟引擎絕對不罷工
    strong_ends = ['。', '！', '？', '；', '：', '\n']
    split_chars = ['，', '、', ',']
    sub_sentences = []
    current_chunk = ""
    current_char_count = 0
    
    for char in text:
        current_chunk += char
        if char not in (strong_ends + split_chars + ['「', '」', '《', '》', '“', '”', '·']):
            current_char_count += 1
            
        # 只要遇到強句尾，或者字數夠長遇到逗號，就立刻切斷成獨立短句
        if char in strong_ends or (current_char_count >= target_len and char in split_chars):
            if current_chunk.strip():
                sub_sentences.append(current_chunk.strip())
            current_chunk = ""
            current_char_count = 0
            
    if current_chunk.strip():
        sub_sentences.append(current_chunk.strip())
    return sub_sentences

# ==========================================================
# 🎨 介面啟動與大標題版本號
# ==========================================================
st.set_page_config(page_title="智能雲端普通話默書機", page_icon="📖", layout="wide")
st.title("📖 智能普通話默書機　v1.0.５")

# 讀取現有實體暫存
current_vault_text = read_from_vault()
text_hash = str(len(current_vault_text)) + "_" + str(hash(current_vault_text))

# 📡 重新裝回：DEBUG 雷達快照
with st.expander("🔍 實時保險箱核心快照 (DEBUG 雷達)", expanded=True):
    if current_vault_text:
        st.success(f"⚡ 後台實實安全暫存檔目前鎖定： **{len(current_vault_text)}** 字")
        st.info(current_vault_text)
    else:
        st.warning("⚠️ 後台實時暫存目前為空。")

tab1, tab2, tab3 = st.tabs([
    "📸 1. 批次影相 / 多圖上傳功能", 
    "✍️ 2. 載入與手動修改功能", 
    "📢 3. 曉曉老師聽寫專區"
])

# ==========================================================
# 功能一：批次影相 / 多圖上傳功能
# ==========================================================
with tab1:
    st.subheader("📸 拍攝/上傳新課文")
    uploaded_files = st.file_uploader("請上傳或拍攝課文圖片（可多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="up_t1")
    
    if uploaded_files:
        st.write(f"📂 已選取 {len(uploaded_files)} 張相片。")
        if st.button("🚀 執行多圖聯合 AI OCR 識別與修復", key="ocr_btn_t1"):
            full_raw_text = ""
            with st.spinner("GPT-4o 正在全速識別並修正課文..."):
                for f in uploaded_files:
                    img = Image.open(f)
                    raw = pytesseract.image_to_string(img, config=r'-l chi_tra+chi_sim --psm 3')
                    full_raw_text += f"\n{raw}\n"
                
                ai_out = ai_correct_text_strict(full_raw_text)
                write_to_vault(ai_out)
                st.success("✨ 文字已成功寫入底層保險箱！")
                st.rerun()

    # 🔥 核心降維打擊：利用動態 key=text_hash，當文字有變動時，強制 Streamlit 銷毀並重新生成全新文字框，徹底消滅空白 Bug
    t1_input = st.text_area("課文內容 Text Box (可在此進行手動調整)", value=current_vault_text, height=250, key=f"t1_widget_{text_hash}")
    if t1_input != current_vault_text:
        write_to_vault(t1_input)

    st.subheader("💾 儲存新課文到雲端")
    c1, c2 = st.columns([3, 1])
    with c1:
        title_t1 = st.text_input("請輸入課文標題：", placeholder="例如：堅持與成功", key="title_t1")
    with c2:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t1"):
            latest_text = read_from_vault()
            if not title_t1.strip() or not latest_text.strip():
                st.error("標題和內容不能為空！")
            else:
                with st.spinner("同步中..."):
                    success, msg = save_to_github(title_t1.strip(), latest_text)
                    st.success(msg) if success else st.error(msg)

# ==========================================================
# 功能二：手動輸入 / 課文修改功能
# ==========================================================
with tab2:
    st.subheader("✍️ 載入、修改與編寫課文")
    all_lessons = load_all_lessons_from_github()
    selected_lesson = "-- 請選擇課文 --"
    
    if all_lessons:
        col_select, col_delete = st.columns([4, 2])
        with col_select:
            selected_lesson = st.selectbox("📂 選取雲端舊課文：", ["-- 請選擇課文 --"] + all_lessons, key="select_t2")
            if selected_lesson != "-- 請選擇課文 --" and st.button("📥 確認載入選取課文", key="load_btn_t2"):
                loaded_text = load_single_lesson(selected_lesson)
                write_to_vault(loaded_text)
                st.success(f"已成功載入: {selected_lesson}")
                st.rerun()
                
        with col_delete:
            st.write(" ") 
            st.write(" ")
            if selected_lesson != "-- 請選擇課文 --":
                if st.button(f"🗑️ 永久刪除《{selected_lesson}》", key="delete_btn_t2", type="primary"):
                    with st.spinner("正在刪除..."):
                        success, msg = delete_from_github(selected_lesson)
                        if success:
                            st.success(msg)
                            write_to_vault("")
                            time.sleep(0.5)
                            st.rerun()
                        else: st.error(msg)
    else:
        st.info("雲端目前沒有已儲存的課文檔。")

    # 🔥 同步強刷機制
    t2_input = st.text_area("課文內容 Text Box", value=current_vault_text, height=250, key=f"t2_widget_{text_hash}")
    if t2_input != current_vault_text:
        write_to_vault(t2_input)

    st.subheader("💾 重新儲存/覆蓋課文到雲端")
    c3, c4 = st.columns([3, 1])
    with c3:
        default_name = selected_lesson if (all_lessons and selected_lesson != "-- 請選擇課文 --") else ""
        title_t2 = st.text_input("請輸入課文標題：", value=default_name, key="title_t2")
    with c4:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t2"):
            latest_text_t2 = read_from_vault()
            if not title_t2.strip() or not latest_text_t2.strip():
                st.error("標題和內容不能為空！")
            else:
                with st.spinner("同步中..."):
                    success, msg = save_to_github(title_t2.strip(), latest_text_t2)
                    if success:
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error(msg)

# ==========================================================
# 功能三：曉曉老師【聽寫專用】獨立功能
# ==========================================================
with tab3:
    st.subheader("📢 曉曉老師聽寫默書專區")
    all_lessons_t3 = load_all_lessons_from_github()
    
    if all_lessons_t3:
        selected_lesson_t3 = st.selectbox("🎯 請選擇今天要默書的課文：", ["-- 請選擇課文 --"] + all_lessons_t3, key="select_t3")
        
        if selected_lesson_t3 != "-- 請選擇課文 --":
            lesson_text_t3 = load_single_lesson(selected_lesson_t3)
            
            if lesson_text_t3 and lesson_text_t3.strip():
                paragraphs_t3 = [p.strip() for p in re.split(r'\n\s*\n', lesson_text_t3) if p.strip()]
                all_sentences = []
                for p_text in paragraphs_t3:
                    all_sentences.extend(smart_split_sentence(p_text))
                
                st.markdown(f"### 📖 當前準備默書：《{selected_lesson_t3}》")
                
                st.markdown("---")
                st.markdown("#### 🚀 終極懶人包：全篇自動連續聽寫")
                if st.button("🏁 一鍵產生【整篇連續默書】音軌", key="play_all_btn"):
                    with st.spinner("曉曉老師正在全速為整篇課文打包音軌，請稍候..."):
                        pcm_list = []
                        for sentence in all_sentences:
                            if sentence.strip():
                                base_audio = asyncio.run(generate_single_audio(sentence))
                                if base_audio:
                                    pcm_list.append(build_dictation_wav(base_audio))
                        
                        full_lesson_audio = build_full_lesson_wav(pcm_list)
                        if full_lesson_audio:
                            st.success("🎉 整篇課文聽寫軌合成完畢！")
                            st.audio(full_lesson_audio, format="audio/wav")
                        else:
                            st.error("⚠️ 音軌拼接失敗。")
                
                st.markdown("---")
                st.markdown("#### 🎯 自由控速區：一句句單獨選播")
                for idx, sentence in enumerate(all_sentences):
                    if sentence.strip():
                        col_text, col_audio = st.columns([4, 2])
                        with col_text: st.write(f"第 {idx+1} 句： `{sentence}`")
                        with col_audio:
                            if st.button(f"📢 聽寫第 {idx+1} 句", key=f"single_btn_{idx}"):
                                with st.spinner("合成中..."):
                                    base_audio = asyncio.run(generate_single_audio(sentence))
                                    if base_audio: st.audio(build_dictation_wav(base_audio), format="audio/wav")
            else:
                st.warning("⚠️ 該雲端課文內容為空。")
    else:
        st.info("雲端目前沒有課文，請先去功能一或功能二儲存課文。")
