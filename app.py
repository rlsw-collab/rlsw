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

# 🔑 雙 Token 雲端/本地自動配對
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
        "message": f"🤖 智能默書機：儲儲/更新課文 {title}",
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
        prompt = """你是一個專門修復小學課文 OCR 錯誤的頂級專家。請將文本中所有的普通話拼音和英文字母徹底刪除，將中文字 100% 還原成精準、通順、符合小學課本邏輯的【繁體中文課文原文】。絕對不要包含任何拼音、Markdown 語法標籤、註解或額外解釋，直接輸出修復後的純課文。"""
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
    strong_ends = ['。', '！', '？', '——', '……']
    split_chars = ['，', '、', '；', '：']
    sub_sentences = []
    current_chunk = ""
    current_char_count = 0
    for char in text:
        current_chunk += char
        if char not in (strong_ends + split_chars + ['「', '」', '《', '裝', '“', '”', '·']):
            current_char_count += 1
        if char in strong_ends or (current_char_count >= target_len and char in split_chars):
            if current_chunk.strip(): sub_sentences.append(current_chunk.strip())
            current_chunk = ""
            current_char_count = 0
    if current_chunk.strip(): sub_sentences.append(current_chunk.strip())
    return sub_sentences

# ==========================================================
# 🎨 經典回歸：單一文字框不打架核心 UI
# ==========================================================
st.set_page_config(page_title="智能雲端普通話默書機", page_icon="📖", layout="wide")
st.title("📖 智能普通話默書機 (雲端回歸初心版)")

if "stable_text" not in st.session_state: 
    st.session_state["stable_text"] = ""

# --- 🚀 第一層：雲端課本庫與上傳區並排 ---
col_left, col_right = st.columns([1, 1])

with col_left:
    st.markdown("### 📁 1. 雲端 Git 課本庫")
    all_lessons = load_all_lessons_from_github()
    if all_lessons:
        c_sel, c_del = st.columns([3, 1])
        with c_sel:
            selected_lesson = st.selectbox("選取舊課文：", ["-- 請選擇 --"] + all_lessons, key="sel_box")
        with c_del:
            st.write(" ")
            st.write(" ")
            if selected_lesson != "-- 請選擇 --" and st.button("🗑️ 刪除", type="primary"):
                with st.spinner("正在刪除..."):
                    success, msg = delete_from_github(selected_lesson)
                    st.session_state["stable_text"] = ""
                    st.rerun()
                    
        if selected_lesson != "-- 請選擇 --" and st.button("📥 確認載入選取課文"):
            st.session_state["stable_text"] = load_single_lesson(selected_lesson)
            st.rerun()
    else:
        st.info("雲端目前沒有已儲存的課文檔。")

with col_right:
    st.markdown("### 📸 2. 批次影相 / 多圖上傳")
    uploaded_files = st.file_uploader("請上傳或拍攝課文圖片（可多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="up_core")
    
    if uploaded_files:
        st.write("🖼️ 圖片預覽：")
        cols = st.columns(min(len(uploaded_files), 5))
        for i, f in enumerate(uploaded_files):
            with cols[i % 5]: st.image(Image.open(f), use_container_width=True)
                
        if st.button("🚀 執行多圖聯合 AI OCR 識別與修復"):
            full_raw_text = ""
            with st.spinner("GPT-4o 正在全速修復中..."):
                for f in uploaded_files:
                    img = Image.open(f)
                    raw = pytesseract.image_to_string(img, config=r'-l chi_tra+chi_sim --psm 3')
                    full_raw_text += f"\n{raw}\n"
                st.session_state["stable_text"] = ai_correct_text_strict(full_raw_text)
                st.rerun()

# --- 🚀 第二層：唯一的、絕對不會消失的 Text Box 專區 ---
st.markdown("---")
st.markdown("### ✍️ 3. 課文內容中心 (打字/AI辨識/載入皆匯聚於此)")
lesson_content = st.text_area("課文內容 (可在此進行最後修改)", value=st.session_state["stable_text"], height=250, key="one_and_only_textarea")
st.session_state["stable_text"] = lesson_content

# 儲存按鈕
c_title, c_save = st.columns([3, 1])
with c_title:
    default_name = selected_lesson if (all_lessons and selected_lesson != "-- 請選擇 --") else ""
    title_input = st.text_input("請輸入課文標題（相同標題會直接覆蓋更新）：", value=default_name, key="save_title")
with c_save:
    st.write(" ")
    st.write(" ")
    if st.button("💾 儲存/更新課文到雲端 Git"):
        if not title_input.strip() or not lesson_content.strip():
            st.error("標題和內容不能為空！")
        else:
            with st.spinner("同步中..."):
                success, msg = save_to_github(title_input.strip(), lesson_content)
                st.success(msg) if success else st.error(msg)
                time.sleep(0.5)
                st.rerun()

# --- 🚀 第三層：曉曉老師【聽寫專用】標準音軌 ---
if lesson_content.strip():
    st.markdown("---")
    st.markdown("### 📢 4. 曉曉老師【聽寫專用】標準聽寫音軌")
    
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', lesson_content) if p.strip()]
    all_sentences = []
    for p_text in paragraphs:
        all_sentences.extend(smart_split_sentence(p_text))
        
    col_all, _ = st.columns([2, 2])
    with col_all:
        if st.button("🏁 一鍵產生【整篇連續默書】音軌 (每句兩次，自動停8秒)"):
            with st.spinner("曉曉老師正在打包整篇音軌..."):
                pcm_list = []
                for sentence in all_sentences:
                    if sentence.strip():
                        base_audio = asyncio.run(generate_single_audio(sentence))
                        if base_audio:
                            pcm_list.append(build_dictation_wav(base_audio))
                full_audio = build_full_lesson_wav(pcm_list)
                if full_audio:
                    st.success("🎉 整篇連續音軌合成成功！點擊下方 Play 開始默書：")
                    st.audio(full_audio, format="audio/wav")
                    
    st.markdown("#### 🎯 單句加操區")
    for idx, sentence in enumerate(all_sentences):
        if sentence.strip():
            c_txt, c_aud = st.columns([4, 2])
            with c_txt: st.write(f"第 {idx+1} 句： `{sentence}`")
            with c_aud:
                if st.button(f"📢 聽寫第 {idx+1} 句", key=f"btn_{idx}"):
                    with st.spinner("合成中..."):
                        base_audio = asyncio.run(generate_single_audio(sentence))
                        if base_audio: st.audio(build_dictation_wav(base_audio), format="audio/wav")
