import time
import os
import re
import base64
import requests
import datetime
import json
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
    return f".tmp_text_{session_id}.txtpk"

def write_to_vault(text):
    with open(get_user_vault_path(), "w", encoding="utf-8") as f: 
        f.write(text)

def read_from_vault():
    path = get_user_vault_path()
    return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""

# ==========================================================
# 📊 全新扁平化動態模型計數器引擎
# ==========================================================
def get_hkt_date_str():
    tz_hkt = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_hkt).strftime("%Y-%m-%d")

def increment_github_counter(model_id):
    """全新架架：直接在 JSON 第一層建立真實模型名稱並累加"""
    if not GIT_TOKEN:
        return
    path = "usage_counter.json"
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GIT_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    today_str = get_hkt_date_str()
    
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                counter = json.loads(content)
                sha = data["sha"]
            else:
                counter = {"last_reset_date": today_str}
                sha = None
                
            # 跨日自動歸零重置
            if counter.get("last_reset_date") != today_str:
                counter = {"last_reset_date": today_str}
                
            # 動態為新模型建立欄位並累加
            if model_id not in counter:
                counter[model_id] = 0
            counter[model_id] += 1
            
            content_str = json.dumps(counter, indent=2)
            content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"Increment counter for {model_id} via Dictation [skip ci]",
                "content": content_b64
            }
            if sha:
                payload["sha"] = sha
                
            put_res = requests.put(url, headers=headers, json=payload)
            if put_res.status_code in [200, 201]:
                st.toast(f"📊 雲端配額同步成功！當前調用：【{model_id}】", icon="✅")
                break
            time.sleep(0.5)
        except Exception as e:
            st.toast(f"⚠️ 雲端計數器同步失敗: {str(e)}", icon="❌")
            time.sleep(0.5)

# ==========================================================
# 🧠 核心 OCR 與雙語文本清洗多通道穿透調用
# ==========================================================
def gemini_vision_extract_bilingual(image_bytes):
    models_to_try = ["gemini-2.5-flash", "gemini-2.5-pro"]
    
    prompt_text = (
        "你是一個精通香港小學教科書（課文、名言、優美段落）的 OCR 文字提取與整理專家。\n"
        "請仔細辨識圖片中的中文及英文文字，並按照以下極度嚴格的規則輸出，不要包含任何 markdown 程式碼區塊（如 ```json 等）或額外解釋：\n\n"
        "1. 完全保留原文的段落結構，不要漏掉任何標點符號。\n"
        "2. 如果整張圖片100%完全是純英文內容（例如英文故事、課文），請直接輸出純英文文本即可。\n"
        "3. 如果圖片中包含中文（或中英雙語），必須將其轉換為標準的雙語默書格式。格式規範如下：\n"
        "   - 每一個獨立的句子、詞彙或段落，必須單獨佔一行。\n"
        "   - 如果句子前有編號（例如 1.、2. 或 (1)、(2)），請務必完整保留在行首。\n"
        "   - 如果某一行是純中文句子，必須在該行文字的【最前方】加上標籤 `[CH]`（例如：[CH] 1. 今天天氣晴朗。）。\n"
        "   - 如果某一行是純英文句子，必須在該行文字的【最前方】加上標籤 `[EN]`（例如：[EN] 2. Good morning.）。\n"
        "   - 請逐行檢查，絕對不允許漏掉 `[CH]` 或 `[EN]` 標籤！\n"
        "4. 遇到冷僻字、繁簡體混雜時，一律修正為香港小學常用的標準常用繁體字。\n"
        "5. 再次強調：禁止輸出任何 ``` 標籤，直接輸出清洗後的純文字內容。"
    )
    
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    for model_id in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_TOKEN}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt_text},
                    {"inlineData": {"mimeType": "image/jpeg", "data": base64_image}}
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096
            }
        }
        
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                increment_github_counter(model_id)
                return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass
            
    if AI_TOKEN:
        try:
            url = "https://api.oneapi.sh/v1/chat/completions"
            headers = {"Authorization": f"Bearer {AI_TOKEN}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are an expert OCR assistant. Correct errors, layout text paragraph by paragraph line by line, output raw text directly without markdown tags."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                "temperature": 0.1
            }
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                increment_github_counter("gpt-4o-mini")
                return res.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
            
    return ""

# ==========================================================
# 🔊 語音合成組件 (Edge-TTS 異步引擎)
# ==========================================================
def convert_punctuation_to_words_bilingual(text, mode="中文"):
    if mode == "中文":
        mapping = [
            ('，', ' 逗號 '), ('。', ' 句號 '), ('！', ' 感嘆號 '), ('？', ' 問號 '),
            ('；', ' 分號 '), ('：', ' 冒號 '), ('、', ' 頓號 '), ('《', ' 開書名號 '),
            ('》', ' 關書名號 '), ('「', ' 開引號 '), ('」', ' 關引號 '), ('—', ' 破折號 ')
        ]
        for p, w in mapping: text = text.replace(p, w)
        return text
    else:
        mapping = [
            (',', ' comma '), ('.', ' period '), ('!', ' exclamation mark '), ('?', ' question mark '),
            (';', ' semicolon '), (':', ' colon '), ('"', ' quotes '), ("'", ' quote ')
        ]
        for p, w in mapping: text = text.replace(p, w)
        return text

async def generate_audio_clean_raw_bilingual(text, custom_rate="+0%", mode="中文"):
    if not text.strip(): return b""
    voice = "zh-HK-HiuMaanNeural" if mode == "中文" else "en-GB-SoniaNeural"
    try:
        communicate = edge_tts.Communicate(text, voice, rate=custom_rate)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return audio_data
    except Exception:
        return b""

def build_silence(duration_ms, sample_rate=24000):
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    return b"\x00" * (num_samples * 2)

# ==========================================================
# 🎨 UI 介面展示區
# ==========================================================
st.title("📝 智能默書語音生成與批改工具")
st.markdown("上傳默書範圍圖片（或手動輸入文字），一鍵生成符合香港小學標準（每句朗讀兩次、附帶標點提示及完美停頓）的優質默書配套！")

tabs = st.tabs(["📸 步驟一：提取與清洗默書文本", "🎧 步驟二：生成全功能朗讀音頻"])

with tabs[0]:
    st.markdown("### 1. 來源數據匯入")
    src_mode = st.radio("選擇匯入方式：", ["手機拍照 / 上傳圖片檔案", "直接手動輸入/貼上文本內容"], horizontal=True)
    
    raw_extracted_text = ""
    if src_mode == "手機拍照 / 上傳圖片檔案":
        uploaded_file = st.file_uploader("請上傳或拍攝課文圖片 (支援 JPG/PNG)：", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            st.image(uploaded_file, caption="📸 已成功載入的圖片", width=350)
            if st.button("🚀 開始智能 OCR 辨識與格式清洗", use_container_width=True):
                with st.spinner("AI 正在進行高精度文字提取與雙語分行清洗，請稍候..."):
                    img_bytes = uploaded_file.read()
                    raw_extracted_text = gemini_vision_extract_bilingual(img_bytes)
                    if raw_extracted_text:
                        write_to_vault(raw_extracted_text)
                        st.success("🎉 辨識並清洗成功！已自動填入下方編輯區。")
                    else:
                        st.error("❌ 文字提取失敗，請確保圖片清晰或切換為手動輸入。")
                        
    vault_content = read_from_vault()
    st.markdown("### 2. 默書內容校對與編輯區")
    edited_text = st.text_area("編輯最終默書文本：", value=vault_content, height=280)
    
    if edited_text != vault_content:
        write_to_vault(edited_text)

with tabs[1]:
    st.markdown("### 3. 高級音頻生成控制面板")
    final_text = read_from_vault()
    
    if not final_text.strip():
        st.warning("⚠️ 請先在第一個標籤頁成功提取或輸入默書文本。")
    else:
        col1, col2 = st.columns(2)
        with col1:
            speed_slider = st.slider("🐢 調整朗讀速度 (相較於標準速度)：", min_value=-50, max_value=10, value=-20, step=5)
            custom_rate_str = f"{speed_slider}%"
        with col2:
            st.write("")
            st.write("")
            st.info(f"當前朗讀語速設定：`{custom_rate_str}` (建議減速 -20% 配合小學生聽寫)")
            
        st.write("---")
        st.markdown("#### 🎧 線上試聽與下載專區")
        
        lines = [line.strip() for line in final_text.split('\n') if line.strip()]
        
        silence_0_5s = build_silence(500)
        silence_4_0s = build_silence(4000)
        silence_8_0s = build_silence(8000)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for idx, line in enumerate(lines):
            if line.startswith("[CH]"):
                active_lang = "中文"
                clean_line = line.replace("[CH]", "").strip()
            elif line.startswith("[EN]"):
                active_lang = "英文"
                clean_line = line.replace("[EN]", "").strip()
            else:
                active_lang = "中文"
                clean_line = line
                
            match = re.match(r'^((?:\d+\.|[A-Za-z]\.|\(\d+\))\s*)(.*)$', clean_line)
            if match:
                p_label = match.group(1).strip()
                s_text = match.group(2).strip()
            else:
                p_label = ""
                s_text = clean_line
                
            with st.container():
                st.markdown(f"**第 {idx+1} 句 ({active_lang})** : `{clean_line}`")
                btn_cols = st.columns([1, 2, 2])
                
                # 1. 課堂標準版朗讀 (🌟 已徹底修復語音拼接內置語法碎屑錯誤)
                with btn_cols[0]:
                    if st.button(f"🔊 課堂朗讀版", key=f"std_{idx}"):
                        with st.spinner("合成中..."):
                            text_with_breathes = convert_punctuation_to_words_bilingual(s_text, mode=active_lang)
                            if active_lang == "中文":
                                blocks = [b.strip() for b in re.split(r'(開書名號|關書名號|逗號|句號|感嘆號|問號|分號|冒號|頓號|開引號|關引號|破折號)', text_with_breathes) if b.strip()]
                            else:
                                blocks = [text_with_breathes.strip()]
                            
                            sentence_audio_stream = b""
                            for blk in blocks:
                                blk_clean = re.sub(r'[\s·\\]', '', blk) if active_lang == "中文" else blk.strip()
                                blk_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(blk_clean, custom_rate=custom_rate_str, mode=active_lang))
                                if blk_audio: 
                                    sentence_audio_stream += blk_audio + silence_0_5s
                            
                            unit_stream = b""
                            if p_label:
                                label_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(p_label, custom_rate="-30%", mode=active_lang))
                                if label_audio: 
                                    unit_stream += label_audio + silence_0_5s
                            if sentence_audio_stream:
                                unit_stream += sentence_audio_stream + silence_4_0s + sentence_audio_stream + silence_8_0s
                                
                            if unit_stream:
                                st.audio(unit_stream, format="audio/mp3")
                                
                # 2. 單句全句下載
                with btn_cols[1]:
                    if st.button(f"⬇️ 生成全句導出音頻", key=f"dl_{idx}"):
                        with st.spinner("打包音頻中..."):
                            full_text = s_text
                            full_audio = loop.run_until_complete(generate_audio_clean_raw_bilingual(full_text, custom_rate=custom_rate_str, mode=active_lang))
                            if full_audio:
                                st.audio(full_audio, format="audio/mp3")
                                b64 = base64.b64encode(full_audio).decode()
                                st.markdown(f'<a href="data:audio/mp3;base64,{b64}" download="sentence_{idx+1}.mp3">📥 點擊下載 MP3</a>', unsafe_allow_html=True)
