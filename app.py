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
# 🧠 後台核心函數（加入嚴格錯誤抓取機制）
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
    if put_res.status_code in [200, 201]:
        return True, "成功同步至 GitHub 雲端！"
    else:
        return False, f"Git 儲存失敗！GitHub 伺服器回應碼: {put_res.status_code}，詳情: {put_res.text}"

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
        if del_res.status_code == 200:
            return True, f"課文《{title}》已成功從雲端永久刪除！"
        return False, f"刪除失敗！GitHub 錯誤碼: {del_res.status_code}"
    return False, f"讀取指紋失敗，GitHub 回應碼: {res.status_code}"

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
        return base64.b64decode(res.json().get("content", "")).decode("utf-8"), None
    return "", f"下載失敗！GitHub 回應狀態碼: {res.status_code}，請檢查 Token 權限。"

def ai_correct_text_strict(bad_text):
    """🚨 嚴格除錯版 AI 修正：如果失敗，直接彈出紅框報錯，拒絕默默變空白"""
    if not AI_TOKEN: 
        return None, "錯誤：未偵測到有效的 AI_TOKEN，請檢查 Secrets 設定！"
    
    # 物理過濾拼音與英文字母
    cleaned_chars = []
    for char in bad_text:
        if '\u4e00' <= char <= '\u9fff' or char in '，。！？；：、「」『』《》·——……\n ':
            cleaned_chars.append(char)
    filtered_text = "".join(cleaned_chars)
    filtered_text = re.sub(r' +', ' ', filtered_text)

    try:
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(AI_TOKEN))
        prompt = """你是一個專門修復小學課文 OCR 錯誤的頂級專家。請根據傳進來的繁體中文殘卷，將其還原成 100% 通順、精準、符合小學課本邏輯的【繁體中文課文原文】。絕對不要包含任何拼音、Markdown 語法、註解或額外解釋，直接輸出修復後的純課文。"""
        
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n乾淨中文殘卷:\n" + filtered_text}], model="gpt-4o")
        return response.choices[0].message.content.strip(), None
    except Exception as e:
        return None, f"Azure AI 呼叫崩潰！錯誤原因: {e}"

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
# 🎨 UI 介面設計（換回你最愛的 3 大獨立功能 Tabs 佈局）
# ==========================================================
st.set_page_config(page_title="智能雲端普通話默書機", page_icon="📖", layout="wide")
st.title("📖 智能普通話默書機 (雲端除錯完全體)")

if "shared_text" not in st.session_state: st.session_state["shared_text"] = ""

tab1, tab2, tab3 = st.tabs([
    "📸 1. 批次影相 / 多圖上傳功能", 
    "✍️ 2. 手動輸入 / 課文修改功能", 
    "📢 3. 曉曉老師【聽寫專用】獨立功能"
])

# ==========================================================
# 功能一：批次影相 / 多圖上傳功能
# ==========================================================
with tab1:
    st.subheader("📸 拍攝/上傳新課文")
    uploaded_files = st.file_uploader("請上傳或拍攝課文圖片（可多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="uploader_t1")
    
    if uploaded_files:
        st.write("🖼️ 圖片預覽：")
        cols = st.columns(min(len(uploaded_files), 5))
        for i, f in enumerate(uploaded_files):
            with cols[i % 5]: st.image(Image.open(f), use_container_width=True, caption=f"第 {i+1} 張")
                
        if st.button("🚀 執行多圖聯合 AI OCR 識別與修復", key="ocr_btn_t1"):
            full_raw_text = ""
            with st.spinner("正在合併提取並交給 GPT-4o 修正中..."):
                for f in uploaded_files:
                    img = Image.open(f)
                    raw = pytesseract.image_to_string(img, config=r'-l chi_tra+chi_sim --psm 3')
                    full_raw_text += f"\n{raw}\n"
                
                # 🚨 呼叫嚴格除錯函數
                fixed_text, error_msg = ai_correct_text_strict(full_raw_text)
                if error_msg:
                    st.error(error_msg) # 🔴 如果失敗，直接把紅色警報印出來！
                else:
                    st.session_state["shared_text"] = fixed_text
                    st.success("✨ 識別並修正成功！")

    # 綁定
    lesson_content_t1 = st.text_area("課文內容 Text Box (可在此進行修改)", value=st.session_state["shared_text"], height=250, key="txt_t1")
    st.session_state["shared_text"] = lesson_content_t1

    st.subheader("💾 儲存新課文到雲端")
    c1, c2 = st.columns([2, 1])
    with c1:
        title_t1 = st.text_input("請輸入課文標題：", placeholder="例如：堅持與成功", key="title_t1")
    with c2:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t1"):
            if not title_t1.strip() or not lesson_content_t1.strip():
                st.error("標題和內容不能為空！")
            else:
                with st.spinner("正在同步至 GitHub..."):
                    success, msg = save_to_github(title_t1.strip(), lesson_content_t1)
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
            selected_lesson = st.selectbox("📂 雲端 Git 課本庫：", ["-- 請選擇課文 --"] + all_lessons, key="select_t2")
            if selected_lesson != "-- 請選擇課文 --" and st.button("確認載入選取課文", key="load_btn_t2"):
                loaded_txt, err = load_single_lesson(selected_lesson)
                if err:
                    st.error(err) # 🔴 如果載入失敗，亮出紅框！
                else:
                    st.session_state["shared_text"] = loaded_txt
                    st.success(f"已成功載入: {selected_lesson}")
                    st.rerun()
                
        with col_delete:
            st.write(" ") 
            st.write(" ")
            if selected_lesson != "-- 請選擇課文 --":
                if st.button(f"🗑️ 永久刪除《{selected_lesson}》", key="delete_btn_t2", type="primary"):
                    with st.spinner("正在從 GitHub 雲端抹殺檔案..."):
                        success, msg = delete_from_github(selected_lesson)
                        if success:
                            st.success(msg)
                            st.session_state["shared_text"] = ""
                            time.sleep(0.5)
                            st.rerun()
                        else: st.error(msg)
    else:
        st.info("雲端目前沒有已儲存的課文檔。")

    lesson_content_t2 = st.text_area("課文內容 Text Box", value=st.session_state["shared_text"], height=250, key="txt_t2")
    st.session_state["shared_text"] = lesson_content_t2

    st.subheader("💾 重新儲存/覆蓋課文到雲端")
    c3, c4 = st.columns([2, 1])
    with c3:
        default_title = selected_lesson if (all_lessons and selected_lesson != "-- 請選擇課文 --") else ""
        title_t2 = st.text_input("請輸入課文標題（相同標題將會直接覆蓋更新）：", value=default_title, key="title_t2")
    with c4:
        st.write(" ")
        st.write(" ")
        if st.button("💾 確認儲存至 Git", key="save_btn_t2"):
            if not title_t2.strip() or not lesson_content_t2.strip():
                st.error("標題和內容不能為空！")
            else:
                with st.spinner("正在同步至 GitHub..."):
                    success, msg = save_to_github(title_t2.strip(), lesson_content_t2)
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
            lesson_text_t3, err3 = load_single_lesson(selected_lesson_t3)
            if err3:
                st.error(err3)
            else:
                paragraphs_t3 = [p.strip() for p in re.split(r'\n\s*\n', lesson_text_t3) if p.strip()]
                all_sentences = []
                for p_text in paragraphs_t3:
                    all_sentences.extend(smart_split_sentence(p_text))
                
                st.markdown(f"### 📖 當前準備默書：《{selected_lesson_t3}》")
                
                st.markdown("---")
                st.markdown("#### 🚀 終極連播功能")
                if st.button("🏁 一鍵產生【整篇連續默書】音軌", key="play_all_btn"):
                    with st.spinner("曉曉老師正在打包音軌..."):
                        pcm_list = []
                        for sentence in all_sentences:
                            if sentence.strip():
                                base_audio = asyncio.run(generate_single_audio(sentence))
                                if base_audio:
                                    dictation_wav = build_dictation_wav(base_audio)
                                    pcm_list.append(dictation_wav)
                        full_lesson_audio = build_full_lesson_wav(pcm_list)
                        if full_lesson_audio:
                            st.success("🎉 合成完畢！")
                            st.audio(full_lesson_audio, format="audio/wav")
                
                st.markdown("---")
                st.markdown("#### 🎯 自由單句選播區")
                for idx, sentence in enumerate(all_sentences):
                    col_text, col_audio = st.columns([4, 2])
                    with col_text: st.write(f"第 {idx+1} 句： `{sentence}`")
                    with col_audio:
                        if st.button(f"📢 聽寫第 {idx+1} 句", key=f"single_btn_{idx}"):
                            with st.spinner("合成中..."):
                                base_audio = asyncio.run(generate_single_audio(sentence))
                                if base_audio:
                                    dictation_audio = build_dictation_wav(base_audio)
                                    st.audio(dictation_audio, format="audio/wav")
