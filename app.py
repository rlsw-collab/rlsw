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
    # 如果在本地測試，先用回原來的單一檔案
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
    # 📝 儲存檔案使用具備寫入權限的 GIT_TOKEN
    if not GIT_TOKEN:
        return False, "未偵測到有效的 GIT_TOKEN"
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
    if sha:
        data["sha"] = sha
    put_res = requests.put(url, headers=headers, json=data)
    return (True, "成功同步至 GitHub 雲端！") if put_res.status_code in [200, 201] else (False, f"Git 錯誤: {put_res.status_code}")

def load_all_lessons_from_github():
    if not GIT_TOKEN: return []
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return [f["name"].replace(".txt", "") for f in res.json() if f["name"].endswith(".txt")]
    return []

def load_single_lesson(title):
    url = get_github_file_url(f"{title}.txt")
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return base64.b64decode(res.json().get("content", "")).decode("utf-8")
    return ""

def ai_correct_text(bad_text):
    # 🧠 呼叫 AI 使用當初完美的 AI_TOKEN
    if not AI_TOKEN: 
        return bad_text
    try:
        # 第一層：物理過濾英文字母與數字（彻底消滅任何拼音干擾）
        cleaned_chars = []
        for char in bad_text:
            if '\u4e00' <= char <= '\u9fff' or char in '，。！？；：、「」『』《》·——……\n ':
                cleaned_chars.append(char)
        filtered_text = "".join(cleaned_chars)
        filtered_text = re.sub(r' +', ' ', filtered_text)

        client = ChatCompletionsClient(
            endpoint="https://models.inference.ai.azure.com", 
            credential=AzureKeyCredential(AI_TOKEN)
        )
        
        prompt = """
        你是一個專門修復小學課文 OCR 錯誤的頂級專家。
        請根據傳進來的繁體中文殘卷，將其還原成 100% 通順、精準、符合小學課本邏輯的【繁體中文課文原文】。
        修復重點字詞：
        - 修正錯字（例如將 "決地" 修正為 "決定"、"要微" 修正為 "要我們"）。
        - 完美還原人名和品牌："美國蘋果公司"、"史提夫·喬布斯"、"愛德華·詹納"。
        - 還原古語名言：「鍥而不捨，金石可鏤。」
        絕對不要包含任何拼音、Markdown 語法、註解或額外解釋，直接輸出修復後的純課文。
        """
        
        response = client.complete(
            messages=[{"role": "user", "content": prompt + "\n乾淨中文殘卷:\n" + filtered_text}], 
            model="gpt-4o"
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return bad_text

async def generate_single_audio(text):
    clean_text = re.sub(r'[，。！？；：、「」『』《》·——……]', ' ', text)
    communicate = edge_tts.Communicate(clean_text, "zh-CN-XiaoxiaoNeural", rate="-5%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def build_dictation_wav(audio_bytes, sample_rate=24000):
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
            if current_chunk.strip():
                sub_sentences.append(current_chunk.strip())
            current_chunk = ""
            current_char_count = 0
    if current_chunk.strip():
        sub_sentences.append(current_chunk.strip())
    return sub_sentences

# ==========================================================
# 🎨 UI 介面設計
# ==========================================================
st.set_page_config(page_title="智能雲端普通話默書機", page_icon="📖", layout="wide")
st.title("📖 智能普通話默書機 (雲端網頁版)")

if "current_text" not in st.session_state:
    st.session_state["current_text"] = ""

st.sidebar.header("📁 雲端 Git 課本庫")
all_lessons = load_all_lessons_from_github()
if all_lessons:
    selected_lesson = st.sidebar.selectbox("開啓舊課文：", ["-- 請選擇 --"] + all_lessons)
    if selected_lesson != "-- 請選擇 --":
        if st.sidebar.button("確認載入課文"):
            st.session_state["current_text"] = load_single_lesson(selected_lesson)
            st.sidebar.success(f"已成功載入: {selected_lesson}")
            st.rerun()

tab1, tab2 = st.tabs(["📸 批次影相 / 多圖上傳來源", "✍️ 手動輸入 / 課文修改"])

with tab1:
    uploaded_files = st.file_uploader("請上傳或拍攝課文圖片（可多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if uploaded_files:
        if st.button("🚀 執行多圖聯合 AI OCR 識別與修復"):
            full_raw_text = ""
            with st.spinner("正在合併提取並交給 GPT-4o 修正中..."):
                for f in uploaded_files:
                    img = Image.open(f)
                    raw = pytesseract.image_to_string(img, config=r'-l chi_tra+chi_sim --psm 3')
                    full_raw_text += f"\n{raw}\n"
                fixed_text = ai_correct_text(full_raw_text)
                st.session_state["current_text"] = fixed_text
                st.success("✨ 識別並修正成功！請切換至『手動輸入 / 課文修改』標籤查看。")

with tab2:
    lesson_content = st.text_area("課文內容 Text Box", value=st.session_state["current_text"], height=250)
    st.session_state["current_text"] = lesson_content

st.subheader("💾 儲存課文到雲端")
col1, col2 = st.columns([2, 1])
with col1:
    lesson_title = st.text_input("請輸入課文標題：", placeholder="未命名課文")
with col2:
    st.write(" ")
    st.write(" ")
    if st.button("💾 確認儲存至 Git"):
        if not lesson_title.strip() or not lesson_content.strip():
            st.error("標題和內容不能為空！")
        else:
            with st.spinner("正在同步至 GitHub..."):
                success, msg = save_to_github(lesson_title.strip(), lesson_content)
                if success:
                    st.success(msg)
                    time.sleep(1)
                    st.rerun()
                else: st.error(msg)

if lesson_content.strip():
    st.markdown("---")
    st.subheader("📢 曉曉老師【聽寫專用】標準音軌")
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', lesson_content) if p.strip()]
    for p_idx, p_text in enumerate(paragraphs):
        st.markdown(f"### 🔔 第 {p_idx+1} 段")
        sentences = smart_split_sentence(p_text)
        for s_idx, sentence in enumerate(sentences):
            col_text, col_audio = st.columns([3, 2])
            with col_text:
                st.write(f"📖 `{sentence}`")
            with col_audio:
                base_audio = asyncio.run(generate_single_audio(sentence))
                dictation_audio = build_dictation_wav(base_audio)
                st.audio(dictation_audio, format="audio/wav")
