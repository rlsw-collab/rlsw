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
# ⚙️ 設定區
# ==========================================================
if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

AI_TOKEN = st.secrets["AI_TOKEN"] if "AI_TOKEN" in st.secrets else ""
GIT_TOKEN = st.secrets["GIT_TOKEN"] if "GIT_TOKEN" in st.secrets else ""
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
    with open(get_user_vault_path(), "w", encoding="utf-8") as f: f.write(text)

def read_from_vault():
    path = get_user_vault_path()
    return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""

# ==========================================================
# 🧠 核心功能函數
# ==========================================================
def save_to_github(title, content):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    data = {"message": f"update {title}", "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"), "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def load_all_lessons():
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    return [f["name"].replace(".txt", "") for f in res.json()] if res.status_code == 200 else []

def load_single_lesson(title):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    res = requests.get(url, headers={"Authorization": f"token {GIT_TOKEN}"})
    return base64.b64decode(res.json()["content"]).decode("utf-8") if res.status_code == 200 else ""

def ai_correct_text(bad_text):
    try:
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(AI_TOKEN))
        prompt = "修復 OCR 錯字，刪除拼音，輸出純繁體中文課文。"
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n" + bad_text}], model="gpt-4o")
        return response.choices[0].message.content.strip()
    except: return bad_text

async def generate_audio(text):
    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural", rate="-5%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    return audio_data

def build_dictation_wav(audio_bytes):
    # 音訊數據跳過 100 字節頭部
    raw_pcm = audio_bytes[100:]
    # 靜音 8 秒 (24000Hz * 2bytes * 8s = 384000)
    silence = b"\x00" * 384000
    # 讀兩次結構
    combined = raw_pcm + silence + raw_pcm + silence
    # 重建 WAV 頭
    header = b"RIFF" + (len(combined) + 36).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (24000).to_bytes(4, "little") + (48000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") + b"data" + (len(combined)).to_bytes(4, "little")
    return header + combined

def smart_split(text):
    return [s.strip() for s in re.split(r'[。！？；：\n]', text) if s.strip()]

# ==========================================================
# 🎨 UI
# ==========================================================
st.set_page_config(layout="wide")
st.title("📖 智能普通話默書機 v1.0.6-Final")

current_text = read_from_vault()
text_hash = str(len(current_text)) + "_" + str(hash(current_text))

tab1, tab2, tab3 = st.tabs(["📸 1. 批次影相", "✍️ 2. 載入與修改", "📢 3. 曉曉老師聽寫專區"])

with tab1:
    files = st.file_uploader("上傳圖片", accept_multiple_files=True)
    if files:
        cols = st.columns(min(len(files), 5))
        for i, f in enumerate(files): cols[i % 5].image(Image.open(f))
        if st.button("🚀 執行 OCR"):
            text = ""
            for f in files: text += pytesseract.image_to_string(Image.open(f), config=r'-l chi_tra+chi_sim --psm 3')
            write_to_vault(ai_correct_text(text))
            st.rerun()
    t1 = st.text_area("課文內容", value=current_text, height=250, key=f"t1_{text_hash}")
    if t1 != current_text: write_to_vault(t1)

with tab2:
    lessons = load_all_lessons()
    sel = st.selectbox("選課文", ["--"] + lessons)
    if st.button("📥 載入"):
        write_to_vault(load_single_lesson(sel))
        st.rerun()
    t2 = st.text_area("課文內容", value=current_text, height=250, key=f"t2_{text_hash}")
    if t2 != current_vault_text: write_to_vault(t2)
    if st.button("💾 儲存"): save_to_github(sel, current_text)

with tab3:
    st.text_area("當前默書課文", value=current_text, height=200, disabled=True)
    if st.button("🏁 產生【讀兩次、停8秒】自動音軌"):
        pcm_list = []
        for s in smart_split(current_text):
            audio = asyncio.run(generate_audio(s))
            if audio: pcm_list.append(build_dictation_wav(audio))
        
        full_pcm = b"".join([p[44:] for p in pcm_list])
        header = b"RIFF" + (len(full_pcm) + 36).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (24000).to_bytes(4, "little") + (48000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") + b"data" + (len(full_pcm)).to_bytes(4, "little")
        st.audio(header + full_pcm, format="audio/wav")
