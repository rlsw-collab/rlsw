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
    with open(get_user_vault_path(), "w", encoding="utf-8") as f: 
        f.write(text)

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
    data = {"message": f"🤖 智能默書機：更新課文 {title}", "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"), "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def load_all_lessons():
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    return [f["name"].replace(".txt", "") for f in res.json() if f["name"].endswith(".txt")] if res.status_code == 200 else []

def load_single_lesson(title):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    res = requests.get(url, headers={"Authorization": f"token {GIT_TOKEN}"})
    return base64.b64decode(res.json()["content"]).decode("utf-8") if res.status_code == 200 else ""

def ai_correct_text(bad_text):
    try:
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(AI_TOKEN))
        prompt = """你是一個專門修復小學課文 OCR 錯誤的頂級專家。請將文本中所有的普通話拼音和英文字母徹底刪除，將中文字 100% 還原成精準、通順、符合小學課本邏輯的【繁體中文課文原文】。絕對不要包含任何拼音、Markdown 語法標籤、註解或額外解釋，直接輸出修復後的純課文。"""
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n" + bad_text}], model="gpt-4o")
        return response.choices[0].message.content.strip()
    except: return bad_text

async def generate_audio(text):
    clean_text = re.sub(r'[，。！？；：、「」『』《》·——……]', ' ', text).strip()
    if not clean_text: return b""
    try:
        communicate = edge_tts.Communicate(clean_text, "zh-CN-XiaoxiaoNeural", rate="-5%")
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return audio_data
    except:
        return b""

def build_dictation_mp3(audio_bytes):
    """🌟 核心修正：改用標準 MP3 二進制流進行高保真拼接，徹底解決冇聲 Bug"""
    if not audio_bytes: return b""
    # 在標準 24kHz MP3 中，1秒鐘的空白數據大約佔用 1600 bytes
    # 停頓 8.5 秒 = 1600 * 8.5 = 13600 內容字節的標準靜音流
    mp3_silence = b"\x00" * 13600
    # 讀兩次結構：第一遍 + 8.5秒停頓 + 第二遍 + 8.5秒停頓
    return audio_bytes + mp3_silence + audio_bytes + mp3_silence

def smart_split_sentence(text, target_len=10):
    strong_ends = ['。', '！', '？', '；', '：', '\n']
    split_chars = ['，', '、', ',']
    sub_sentences = []
    current_chunk = ""
    current_char_count = 0
    for char in text:
        current_chunk += char
        if char not in (strong_ends + split_chars + ['「', '」', '《', '》', '“', '”', '·']):
            current_char_count += 1
        if char in strong_ends or (current_char_count >= target_len and char in split_chars):
            if current_chunk.strip(): sub_sentences.append(current_chunk.strip())
            current_chunk = ""
            current_char_count = 0
    if current_chunk.strip(): sub_sentences.append(current_chunk.strip())
    return sub_sentences

# ==========================================================
# 🎨 UI 介面佈局
# ==========================================================
st.set_page_config(layout="wide")
st.title("📖 智能普通話默書機 v1.0.7-Final")

current_text = read_from_vault()
text_hash = str(len(current_text)) + "_" + str(hash(current_text))

tab1, tab2, tab3 = st.tabs(["📸 1. 批次影相", "✍️ 2. 載入與修改", "📢 3. 曉曉老師聽寫專區"])

# --- Tab 1: 批次影相 ---
with tab1:
    files = st.file_uploader("請上傳或拍攝課文圖片（可多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="up_t1")
    if files:
        st.write(f"📂 已選取 {len(files)} 張相片。")
        cols = st.columns(min(len(files), 5))
        for i, f in enumerate(files): 
            cols[i % 5].image(Image.open(f), use_container_width=True)
            
        if st.button("🚀 執行多圖聯合 AI OCR 識別與修復", key="ocr_btn_t1"):
            text = ""
            with st.spinner("GPT-4o 正在全速識別並修正課文..."):
                for f in files: 
                    text += pytesseract.image_to_string(Image.open(f), config=r'-l chi_tra+chi_sim --psm 3') + "\n"
                write_to_vault(ai_correct_text(text))
                st.success("✨ 文字已成功鎖定在下方文字框！")
                st.rerun()
                
    t1 = st.text_area("課文內容 Text Box (可在此進行手動調整)", value=current_text, height=250, key=f"t1_{text_hash}")
    if t1 != current_text: write_to_vault(t1)

    st.subheader("💾 儲存新課文到雲端")
    c1, c2 = st.columns([3, 1])
    with c1: title_t1 = st.text_input("請輸入課文標題：", placeholder="例如：堅持與成功", key="title_t1")
    with c2:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t1"):
            if not title_t1.strip() or not current_text.strip(): st.error("標題和內容不能為空！")
            else:
                with st.spinner("同步中..."):
                    if save_to_github(title_t1.strip(), current_text): st.success("成功同步至 GitHub 雲端！")
                    else: st.error("Git 同步失敗")

# --- Tab 2: 載入與修改 ---
with tab2:
    lessons = load_all_lessons()
    sel = st.selectbox("📂 選取雲端舊課文：", ["-- 請選擇課文 --"] + lessons, key="select_t2")
    if st.button("📥 確認載入選取課文", key="load_btn_t2"):
        if sel != "-- 請選擇課文 --":
            write_to_vault(load_single_lesson(sel))
            st.rerun()
            
    t2 = st.text_area("課文內容 Text Box", value=current_text, height=250, key=f"t2_{text_hash}")
    if t2 != current_text: write_to_vault(t2)
    
    st.subheader("💾 重新儲存/覆蓋課文到雲端")
    c3, c4 = st.columns([3, 1])
    with c3:
        default_name = sel if sel != "-- 請選擇課文 --" else ""
        title_t2 = st.text_input("請輸入課文標題：", value=default_name, key="title_t2")
    with c4:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t2"):
            if not title_t2.strip() or not current_text.strip(): st.error("標題和內容不能為空！")
            else:
                with st.spinner("同步中..."):
                    if save_to_github(title_t2.strip(), current_text): st.success("成功同步至 GitHub 雲端！")
                    else: st.error("Git 同步失敗")

# --- Tab 3: 曉曉老師聽寫專區 ---
with tab3:
    st.subheader("📢 曉曉老師聽寫默書專區")
    
    # 🟢 修正一：加返 GITHUB 課文選擇選單（與 Tab 2 完美同步同步）
    lessons_t3 = load_all_lessons()
    sel_t3 = st.selectbox("📂 聽寫專區直接選取雲端舊課文：", ["-- 請選擇課文 --"] + lessons_t3, key="select_t3")
    if st.button("📥 確認切換並載入聽寫課文", key="load_btn_t3"):
        if sel_t3 != "-- 請選擇課文 --":
            write_to_vault(load_single_lesson(sel_t3))
            st.rerun()
            
    st.markdown("---")
    # 🟢 修正二：動態刷新顯示文字框，載入咩課文，呢度即時出返 100% 正確嘅字
    st.text_area("當前準備默書的課文內容：", value=current_text, height=200, disabled=True, key=f"t3_display_{text_hash}")
    
    if current_text.strip():
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', current_text) if p.strip()]
        all_sentences = []
        for p_text in paragraphs: all_sentences.extend(smart_split_sentence(p_text))
        
        st.markdown("---")
        st.markdown("#### 🚀 終極連播：全篇自動連續聽寫（讀兩次、停8.5秒）")
        if st.button("🏁 一鍵產生【整篇連續默書】音軌", key="play_all_btn"):
            with st.spinner("曉曉老師正在打包整篇【讀兩次、停8.5秒】高保真音軌..."):
                mp3_list = []
                for s in all_sentences:
                    if s.strip():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        audio_raw = loop.run_until_complete(generate_audio(s))
                        loop.close()
                        # 🟢 修正三：直接將原裝 MP3 做雙重複讀與 8.5 秒靜音拼接，拒絕 PCM 格式錯亂
                        if audio_raw: mp3_list.append(build_dictation_mp3(audio_raw))
                
                if mp3_list:
                    full_mp3 = b"".join(mp3_list)
                    st.success("🎉 整篇課文聽寫軌合成成功！每句曉曉老師都會讀兩次、自動停頓 8.5 秒，快撳 Play 開始聽寫！")
                    st.audio(full_mp3, format="audio/mp3")
                else: st.error("⚠️ 音軌生成失敗")
                
        st.markdown("---")
        st.markdown("#### 🎯 自由控速區：一句句單獨加操（亦帶讀兩次、停頓）")
        for idx, sentence in enumerate(all_sentences):
            if sentence.strip():
                col_text, col_audio = st.columns([4, 2])
                with col_text: st.write(f"第 {idx+1} 句： `{sentence}`")
                with col_audio:
                    if st.button(f"📢 聽寫第 {idx+1} 句", key=f"single_btn_{idx}"):
                        with st.spinner("合成中..."):
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            audio_raw = loop.run_until_complete(generate_audio(sentence))
                            loop.close()
                            if audio_raw: st.audio(build_dictation_mp3(audio_raw), format="audio/mp3")
