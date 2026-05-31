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
    if not AI_TOKEN: 
        print("❌ AI_TOKEN 缺失")
        return "【除錯】未讀取到 AI_TOKEN"
    try:
        print(f" LOG: 準備發送給 Azure AI 的原始字數: {len(bad_text)}")
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(AI_TOKEN))
        prompt = """你是一個專門修復小學課文 OCR 錯誤的頂級專家。請將文本中所有的普通話拼音和英文字母徹底刪除，將中文字 100% 還原成精準、通順、符合小學課本邏輯的【繁體中文課文原文】。絕對不要包含任何拼音、Markdown 語法標籤、註解或額外解釋，直接輸出修復後的純課文。"""
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n文本:\n" + bad_text}], model="gpt-4o")
        res_text = response.choices[0].message.content.strip()
        print(f" LOG: Azure AI 成功返回！字數: {len(res_text)}")
        return res_text
    except Exception as e:
        print(f"❌ Azure AI 呼叫崩潰原因: {e}")
        return f"【AI 呼叫失敗】原因: {e}"

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
# 🎨 數據追蹤監聽區
# ==========================================================
def handle_t1_change():
    print(f"📝 [監聽日誌] Tab 1 打字更新！新內容長度: {len(st.session_state['t1_field'])}")
    st.session_state["stable_vault"] = st.session_state["t1_field"]

def handle_t2_change():
    print(f"📝 [監聽日誌] Tab 2 打字更新！新內容長度: {len(st.session_state['t2_field'])}")
    st.session_state["stable_vault"] = st.session_state["t2_field"]

# 初始化唯一不滅保險箱
if "stable_vault" not in st.session_state: 
    print("🆕 [系統初始化] 建立核心保險箱 stable_vault")
    st.session_state["stable_vault"] = ""

# ==========================================================
# 📊 【除錯專用】前端頂部雷達（直接印在網頁最頂端，一目了然）
# ==========================================================
st.set_page_config(page_title="智能雲端普通話默書機", page_icon="📖", layout="wide")
st.title("📖 智能普通話默書機 (日誌除錯版)")

with st.expander("🔍 系統實時全域狀態雷達 (Debug Log Dashboard)", expanded=True):
    st.warning(f"目前後台保險箱 `stable_vault` 內文字長度： {len(st.session_state['stable_vault'])} 字")
    st.text(f"【保險箱目前文字快照】\n{st.session_state['stable_vault']}")

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
                    raw = pytesseract.image_to_string(img, config=r'-l chi_tra+chi_sim --ps
