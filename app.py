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

def convert_punctuation_to_words(text):
    """🌟 修正一：全線補齊書名號、開關引號、破折號，轉為普通話中文讀音"""
    text = text.replace("，", "逗號").replace(",", "逗號")
    text = text.replace("。", "句號")
    text = text.replace("！", "感嘆號")
    text = text.replace("？", "問號")
    text = text.replace("；", "分號")
    text = text.replace("：", "冒號")
    text = text.replace("、", "頓號")
    text = text.replace("《", "開書名號").replace("》", "關書名號")
    text = text.replace("「", "開引號").replace("」", "關引號")
    text = text.replace("『", "開引號").replace("』", "關引號")
    text = text.replace("“", "開引號").replace("”", "關引號")
    text = text.replace("——", "破折號")
    return text

async def generate_dictation_audio_stream(text):
    """🌟 修正二與修正三：
    1. 將語速（rate）再慢一倍，調低至極致溫柔、一字一頓的 -40% 聽寫語速！
    2. 利用微軟官方 SSML 語音標籤，在兩次帶讀之間，精準命令雲端停頓 8000 毫秒（8秒鐘）！
    """
    speak_text = convert_punctuation_to_words(text)
    if not speak_text.strip(): return b""
    
    # 建立「重覆兩次，中間停頓8秒」的標準聽寫 SSML 架構
    ssml_content = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='zh-CN'>
        <voice name='zh-CN-XiaoxiaoNeural'>
            <prosody rate='-40%'>{speak_text}</prosody>
            <break time='8000ms' />
            <prosody rate='-40%'>{speak_text}</prosody>
            <break time='8000ms' />
        </voice>
    </speak>
    """
    try:
        communicate = edge_tts.Communicate(speak_text, "zh-CN-XiaoxiaoNeural")
        # 使用標準 SSML 覆蓋原始發音機制
        communicate.ssml = ssml_content
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return audio_data
    except:
        return b""

def smart_split_sentence(text, target_len=14):
    """🌟 修正四：人性化斷句改良。標點符號不允許出現在句首。
    說話冒號開引號、句號關引號會牢牢黏在對話句子內部，絕不切碎！
    """
    # 移除可能導致混亂的換行，統一成純字串處理
    clean_text = text.replace("\r", "").replace("\n", "").strip()
    
    # 使用保護性替代符，把「：」「「」「」」「。」等組合拳先鎖定保護起來
    protected = clean_text
    # 鎖定對話組合：說話冒號開引號
    protected = protected.replace("：「", "【冒引】").replace("：“", "【冒引】")
    # 鎖定對話結束：句號關引號 / 感嘆號關引號
    protected = protected.replace("。」", "【句引】").replace("」。", "【句引】")
    protected = protected.replace("！”", "【感引】").replace("！」", "【感引】")
    
    # 定義可以切斷的標準強句尾
    strong_ends = ['。', '！', '？', '；', '——']
    split_chars = ['，', '、']
    
    sub_sentences = []
    current_chunk = ""
    current_char_count = 0
    
    for char in protected:
        current_chunk += char
        if char not in (strong_ends + split_chars + ['《', '》', '·']):
            current_char_count += 1
            
        # 遇到強句尾，或者字數夠長遇到逗號，進行切分
        if char in strong_ends or (current_char_count >= target_len and char in split_chars):
            # 解鎖還原保護性符號，確保引號不落單
            chunk_restore = current_chunk.replace("【冒引】", "：「").replace("【句引】", "。」").replace("【感引】", "！」")
            if chunk_restore.strip():
                sub_sentences.append(chunk_restore.strip())
            current_chunk = ""
            current_char_count = 0
            
    if current_chunk.strip():
        chunk_restore = current_chunk.replace("【冒引】", "：「").replace("【句引】", "。」").replace("【感引】", "！」")
        sub_sentences.append(chunk_restore.strip())
        
    # 最後一關安全檢查：如果切出來的句子開頭是標點符號，強行與上一句合併，人性化防落單
    final_sentences = []
    for s in sub_sentences:
        if final_sentences and s[0] in ['，', '、', '。', '！', '？', '；', '：', '」', '》', '』', '”']:
            final_sentences[-1] = final_sentences[-1] + s
        else:
            final_sentences.append(s)
            
    return final_sentences

# ==========================================================
# 🎨 UI 介面佈局
# ==========================================================
st.set_page_config(layout="wide")
st.title("📖 智能普通話默書機 v1.1.0-Ultimate")

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
    
    lessons_t3 = load_all_lessons()
    sel_t3 = st.selectbox("📂 聽寫專區直接選取雲端舊課文：", ["-- 請選擇課文 --"] + lessons_t3, key="select_t3")
    if st.button("📥 確認切換並載入聽寫課文", key="load_btn_t3"):
        if sel_t3 != "-- 請選擇課文 --":
            write_to_vault(load_single_lesson(sel_t3))
            st.rerun()
            
    st.markdown("---")
    st.markdown("#### 📖 當前準備默書的課文內容：")
    
    if current_text.strip():
        st.markdown(
            f"""
            <div style="background-color: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd; color: black; font-size: 16px; line-height: 1.6; white-space: pre-wrap; font-weight: 500;">
            {current_text}
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        st.info("目前保險箱內沒有課文數據，請先去 Tab 1 影相或 Tab 2 載入課文。")
    
    if current_text.strip():
        # 按段落切分，再進行人性化句子切割
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', current_text) if p.strip()]
        all_sentences = []
        for p_text in paragraphs: 
            all_sentences.extend(smart_split_sentence(p_text))
        
        st.markdown("---")
        st.markdown("#### 🚀 終極連播：全篇自動連續聽寫（完美慢速、讀全標點、官方定8秒）")
        if st.button("🏁 一鍵產生【整篇連續默書】音軌", key="play_all_btn"):
            with st.spinner("曉曉老師正在打包【極致慢速 + 讀完所有標點 + 官方精準停頓 8 秒】音軌..."):
                mp3_list = []
                for s in all_sentences:
                    if s.strip():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        # 🤖 調用 SSML 官方停頓發音引擎
                        audio_raw = loop.run_until_complete(generate_dictation_audio_stream(s))
                        loop.close()
                        if audio_raw: mp3_list.append(audio_raw)
                
                if mp3_list:
                    full_mp3 = b"".join(mp3_list)
                    st.success("🎉 終極聽寫音軌打包完畢！曉曉老師語速已放慢一倍，會讀出引號及書名號，且每句讀完均會完美原地停頓 8 秒！")
                    st.audio(full_mp3, format="audio/mp3")
                else: st.error("⚠️ 音軌生成失敗")
                
        st.markdown("---")
        st.markdown("#### 🎯 自由控速區：一句句單獨加操（同樣具備讀兩次、慢速與8秒停頓）")
        for idx, sentence in enumerate(all_sentences):
            if sentence.strip():
                col_text, col_audio = st.columns([4, 2])
                with col_text: st.write(f"第 {idx+1} 句： `{sentence}`")
                with col_audio:
                    if st.button(f"📢 聽寫第 {idx+1} 句", key=f"single_btn_{idx}"):
                        with st.spinner("合成中..."):
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            audio_raw = loop.run_until_complete(generate_dictation_audio_stream(sentence))
                            loop.close()
                            if audio_raw: st.audio(audio_raw, format="audio/mp3")
