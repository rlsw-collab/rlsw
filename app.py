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

def save_audio_to_github(title, audio_bytes):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.mp3"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    content_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    data = {"message": f"🎵 智能默書機：上傳課文聽寫軌 {title}.mp3", "content": content_b64, "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def load_audio_from_github(title):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.mp3"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return base64.b64decode(res.json()["content"])
    return None

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
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.mp3"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json()["sha"]
        data = {"message": f"💥 智能默書機：刪除聽寫軌 {title}.mp3", "sha": sha, "branch": GH_BRANCH}
        del_res = requests.delete(url, headers=headers, json=data)
        return del_res.status_code == 200
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

def ai_correct_text(bad_text):
    """🌟 終極重磅更新：極限鎖定原文字形，禁止任何白話文翻譯、意譯與改寫！"""
    try:
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(AI_TOKEN))
        prompt = """你是一個專門修復小學課文 OCR 錯誤的頂級嚴格專家。
        傳進來的文本可能夾雜了大量的拼音、英文字母、數字（如①、②）和無意義亂碼。

        【🔥 鐵獸級硬性任務——違者扣分】：
        1. 保持原文的「體裁」與「字詞」絕對不變！如果原文是古文（文言文），必須 100% 輸出古文，絕對禁止將古文翻譯成白話文！
        2. 徹底剔除所有拼音、英文字母及無意義的圓圈數字標號（例如刪除 ①、②、③ 等）。
        3. 根據 OCR 殘缺字進行字形修正，輸出 100% 精準的【繁體中文課文原文】。
        4. 嚴格做到「不新增任何課文沒有的句子、不重組段落、不作任何意譯與演繹」。
        5. 絕對不要包含任何 Markdown 語法標籤、註解或你的額外解釋，直接輸出修復後的純淨課文。"""
        
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n" + bad_text}], model="gpt-4o")
        return response.choices[0].message.content.strip()
    except: return bad_text

def convert_punctuation_to_words(text):
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

async def generate_audio_clean_raw(speak_text, custom_rate="-60%"):
    if not speak_text.strip(): return b""
    try:
        communicate = edge_tts.Communicate(speak_text, "zh-CN-XiaoxiaoNeural", rate=custom_rate)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return audio_data
    except:
        return b""

def generate_true_mp3_silence(seconds):
    frames_needed = int((seconds * 1000) / 24)
    single_frame = b"\xFF\xF3\x64\xC4" + (b"\x00" * 284)
    return single_frame * frames_needed

def smart_split_sentence(text, target_len=14):
    clean_text = text.replace("\r", "").replace("\n", "").strip()
    protected = clean_text.replace("：「", "【冒引】").replace("：“", "【冒引】")
    protected = protected.replace("。」", "【句引】").replace("」。", "【句引】")
    protected = protected.replace("！”", "【感引】").replace("！」", "【感引】")
    
    strong_ends = ['。', '！', '？', '；', '——']
    split_chars = ['，', '、']
    
    sub_sentences = []
    current_chunk = ""
    current_char_count = 0
    
    for char in protected:
        current_chunk += char
        if char not in (strong_ends + split_chars + ['《', '》', '·']):
            current_char_count += 1
            
        if char in strong_ends or (current_char_count >= target_len and char in split_chars):
            chunk_restore = current_chunk.replace("【冒引】", "：「").replace("【句引】", "結構。」").replace("【感引】", "！」")
            if chunk_restore.strip(): sub_sentences.append(chunk_restore.strip())
            current_chunk = ""
            current_char_count = 0
            
    if current_chunk.strip():
        chunk_restore = current_chunk.replace("【冒引】", "：「").replace("【句引】", "。」").replace("【感引】", "！」")
        sub_sentences.append(chunk_restore.strip())
        
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
st.title("📖 智能普通話默書機 v1.2.3-Final")

current_text = read_from_vault()
text_hash = str(len(current_text)) + "_" + str(hash(current_text))

tab1, tab2, tab3 = st.tabs(["📸 1. 批次影相", "✍️ 2. 載入與修改", "📢 3. 曉曉老師聽寫專區"])

with tab1:
    files = st.file_uploader("請上傳或拍攝課文圖片（可多選）：", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="up_t1")
    if files:
        cols = st.columns(min(len(files), 5))
        for i, f in enumerate(files): cols[i % 5].image(Image.open(f), use_container_width=True)
            
        if st.button("🚀 執行多圖聯合 AI OCR 識別與修復", key="ocr_btn_t1"):
            text = ""
            with st.spinner("GPT-4o 正在全速識別並修正課文..."):
                for f in files: text += pytesseract.image_to_string(Image.open(f), config=r'-l chi_tra+chi_sim --psm 3') + "\n"
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

with tab2:
    lessons = load_all_lessons()
    sel = st.selectbox("📂 選取雲端舊課文：", ["-- 請選擇課文 --"] + lessons, key="select_t2")
    
    c_load, c_del = st.columns([1, 1])
    with c_load:
        if st.button("📥 確認載入選取課文", key="load_btn_t2"):
            if sel != "-- 請選擇課文 --":
                write_to_vault(load_single_lesson(sel))
                st.rerun()
                
    with c_del:
        if sel != "-- 請選擇課文 --":
            if st.button("🗑️ 徹底刪除雲端課文及音軌快取", key="del_btn_t2", type="primary"):
                with st.spinner(f"💥 正在從雲端徹底剷除《{sel}》的文字與 MP3 檔..."):
                    txt_ok = delete_from_github(sel)
                    mp3_ok = delete_audio_from_github(sel)
                    if txt_ok:
                        write_to_vault("") 
                        st.success(f"✨ 剷除成功！《{sel}》的文字檔及雲端聲帶快取已被永久消滅！")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("⚠️ 刪除失敗，請檢查 GitHub 權限。")
            
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
    else: st.info("目前保險箱內沒有課文數據。")
    
    if current_text.strip():
        raw_paragraphs = [p.strip() for p in re.split(r'\n+', current_text) if p.strip()]
        
        dictation_units = []
        for p_idx, p_text in enumerate(raw_paragraphs):
            p_sentences = smart_split_sentence(p_text)
            for s_idx, s_text in enumerate(p_sentences):
                if s_text.strip():
                    p_label = f"第{p_idx + 1}段" if s_idx == 0 else ""
                    dictation_units.append((p_label, s_text))
        
        st.markdown("---")
        st.markdown("#### 🚀 終極連播：全篇自動連續聽寫（-60%最慢、重覆間停4秒、寫字定格8秒）")
        
        cached_audio = None
        if sel_t3 != "-- 請選擇課文 --":
            with st.spinner("🔍 正在檢測雲端是否有現成音軌快取..."):
                cached_audio = load_audio_from_github(sel_t3)
        
        if cached_audio:
            st.success("⚡ 偵測到雲端已有完美的快取音軌！一秒解鎖直接開播，無需重新等待生成！")
            st.audio(cached_audio, format="audio/mp3")
        else:
            if sel_t3 != "-- 請選擇課文 --":
                st.info("💡 這課書目前尚未在 GitHub 儲存音軌，首次默書請點擊下方按鈕進行【全新生成與自動備份】。")
            
            if st.button("🏁 一鍵產生【整篇連續默書】音軌", key="play_all_btn"):
                progress_text = "曉曉老師正在全速封裝【物理防壓縮】最高規格聽寫音軌中，請稍候..."
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
                    my_bar.progress(pct, text=f"⏳ 正在合成第 {idx+1}/{total_lines} 句：{s_text[:10]}...")
                    
                    text_with_breathes = convert_punctuation_to_words(s_text)
                    blocks = [b.strip() for b in re.split(r'(逗號|句號|感嘆號|問號|分號|冒號|頓號|開書名號|關書名號|開引號|關引號|破折號)', text_with_breathes) if b.strip()]
                    
                    sentence_audio_stream = b""
                    for blk in blocks:
                        blk_clean = re.sub(r'[\s·\裝]', '', blk)
                        blk_audio = loop.run_until_complete(generate_audio_clean_raw(blk_clean, custom_rate="-60%"))
                        if blk_audio:
                            sentence_audio_stream += blk_audio + silence_0_5s
                    
                    if sentence_audio_stream:
                        unit_stream = b""
                        if p_label:
                            label_audio = loop.run_until_complete(generate_audio_clean_raw(p_label, custom_rate="-30%"))
                            if label_audio: unit_stream += label_audio + silence_0_5s
                        
                        unit_stream += sentence_audio_stream + silence_4_0s + sentence_audio_stream + silence_8_0s
                        mp3_final_list.append(unit_stream)
                        
                loop.close()
                
                if mp3_final_list:
                    full_mp3 = b"".join(mp3_final_list)
                    my_bar.progress(100, text="🎉 音軌全面合成完畢！")
                    
                    if sel_t3 != "-- 請選擇課文 --":
                        with st.spinner("💾 正在自動將此完美音軌永久同步備份至 GitHub 雲端..."):
                            if save_audio_to_github(sel_t3, full_mp3):
                                st.success(f"✨ 商業級優化成功！《{sel_t3}》的音軌已成功在 GitHub 備份存檔！")
                    
                    st.audio(full_mp3, format="audio/mp3")
                else: 
                    st.error("⚠️ 音軌生成失敗。")
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
                        
                        text_with_breathes = convert_punctuation_to_words(s_text)
                        blocks = [b.strip() for b in re.split(r'(逗號|句號|感嘆號|問號|分號|冒號|頓號|開書名號|關書名號|開引號|關引號|破折號)', text_with_breathes) if b.strip()]
                        
                        sentence_audio_stream = b""
                        for blk in blocks:
                            blk_clean = re.sub(r'[\s·\裝]', '', blk)
                            blk_audio = loop.run_until_complete(generate_audio_clean_raw(blk_clean, custom_rate="-60%"))
                            if blk_audio: sentence_audio_stream += blk_audio + silence_0_5s
                        
                        unit_stream = b""
                        if p_label:
                            label_audio = loop.run_until_complete(generate_audio_clean_raw(p_label, custom_rate="-30%"))
                            if label_audio: unit_stream += label_audio + silence_0_5s
                        
                        if sentence_audio_stream:
                            unit_stream += sentence_audio_stream + silence_4_0s + sentence_audio_stream + silence_8_0s
                            st.audio(unit_stream, format="audio/mp3")
                        loop.close()
