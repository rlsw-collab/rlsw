import time
import os
import re
import base64
import requests
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
    return f".tmp_text_{session_id}.txt"

def write_to_vault(text):
    with open(get_user_vault_path(), "w", encoding="utf-8") as f: 
        f.write(text)

def read_from_vault():
    path = get_user_vault_path()
    return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""

# ==========================================================
# 🧠 核心功能函數 (修正：% 號網址路徑地雷物理拔除)
# ==========================================================
def save_to_github(title, content):
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{title}.txt"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    data = {"message": f"🤖 智能默書機：更新課文 {title}", "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"), "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def save_audio_to_github(title, speed_value, audio_bytes):
    """🌟 修正：speed_value 只傳入純數字（如 -30），檔名絕對不帶敏感的 % 號"""
    clean_title = title.replace(".mp3", "").strip()
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{clean_title}_speed_rate_{speed_value}.mp3"
    headers = {"Authorization": f"token {GIT_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    content_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    data = {"message": f"🎵 智能默書機：上傳課文聽寫軌 {clean_title} (rate_{speed_value}%)", "content": content_b64, "branch": GH_BRANCH}
    if res.status_code == 200: data["sha"] = res.json()["sha"]
    put_res = requests.put(url, headers=headers, json=data)
    return put_res.status_code in [200, 201]

def scan_lesson_cached_audios(title):
    """🌟 修正：精準匹配純數字檔名，並在畫面上漂亮還原 % 顯示"""
    clean_title = title.replace(".mp3", "").strip()
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    
    found_tracks = [] 
    if res.status_code == 200:
        for f in res.json():
            name = f["name"]
            if name.startswith(f"{clean_title}_speed_rate_") and name.endswith(".mp3"):
                # 提取純數字（包括負號）
                speed_match = re.search(r'_speed_rate_(-?\d+)\.mp3$', name)
                if speed_match:
                    pure_num = speed_match.group(1)
                    display_text = f"{pure_num}%" # 還原百分比給網頁看
                    found_tracks.append((display_text, name))
    return sorted(found_tracks)

def load_specific_audio_by_filename(filename):
    # 🌟 核心修正：對網址檔名進行標準安全轉碼，防止特殊中文字元造成加載崩潰
    import urllib.parse
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{encoded_filename}"
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
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GIT_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        for f in res.json():
            if f["name"].startswith(title) and f["name"].endswith(".mp3"):
                del_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{f['name']}"
                requests.delete(del_url, headers=headers, json={"message": f"💥 刪除快取軌 {f['name']}", "sha": f["sha"], "branch": GH_BRANCH})
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

def convert_image_to_base64(uploaded_file):
    image = Image.open(uploaded_file)
    if image.mode != "RGB":
        image = image.convert("RGB")
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def gemini_vision_extract(base64_images_list):
    if not base64_images_list: return ""
    if not GEMINI_TOKEN: return "錯誤：未在 Secrets 中設定 GEMINI_TOKEN！"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_TOKEN}"
        headers = {"Content-Type": "application/json"}
        
        prompt_text = """你現在是一個100%精準、只會看圖抄寫的繁體中文打字掃描儀。
        你看到的圖片是小學課本。漢字的正上方疊加了密密麻麻的普通話拼音。

        【🚫 鋼鐵死命令】：
        1. 你的眼睛必須完全無視所有拼音字母、英文字元和小圓圈數字標號。
        2. 盯緊圖片中的【大字漢字】，一字不漏、按照自然段落順序將漢字抄寫下來。
        3. 絕對禁止任何二次創作、聯想或編造！原圖有甚麼字就寫甚麼字，絕對不准加入任何網上的企業招聘面試故事、愛爾蘭哲人或蘇格拉底的故事！
        4. 保持全形標點符號與自然段落換行。直接輸出最純淨的繁體中文，不要包含 any Markdown 標籤或你的合理解釋。"""

        parts = [{"text": prompt_text}]
        for b64 in base64_images_list:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
            
        payload = {"contents": [{"parts": parts}]}
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return f"Gemini API 報錯: {res.text}"
    except Exception as e:
        return f"Gemini 辨識發生異常: {str(e)}"

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
