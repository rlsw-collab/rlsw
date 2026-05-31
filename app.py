import streamlit as st
import pytesseract
import os
import re
import base64
import requests
from PIL import Image
from azure.ai.inference import ChatCompletionsClient  
from azure.core.credentials import AzureKeyCredential
import edge_tts
import asyncio

# ==========================================================
# ⚙️ 雲端與本地自動適應設定專區
# ==========================================================
# 智能探測：如果是在本地 Windows 就指定路徑；如果在雲端 Linux 就直接調用系統內置命令
if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    # 雲端 Linux 環境下，系統會自動將 tesseract 加進環境變數，這裡不需手動指定
    pass

# 🔑 自動讀取本地或環境變數中的 GitHub Token
GITHUB_TOKEN = ""
LOCAL_TOKEN_PATH = r"C:\Users\roysw\Desktop\DictationBot\GitHubToken.txt"

if os.path.exists(LOCAL_TOKEN_PATH):
    with open(LOCAL_TOKEN_PATH, "r", encoding="utf-8") as f:
        GITHUB_TOKEN = f.read().strip()
elif "GITHUB_TOKEN" in os.environ:
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# 📂 填寫你的 GitHub 用戶名和儲存庫名稱（用於儲存和讀取課文 TXT）
# 請將下面修改為你實際的 GitHub 帳號資訊
GH_USER = "rlsw-collab"
GH_REPO = "rlsw"
GH_BRANCH = "main"

# ==========================================================
# 🧠 後台核心函數（Git 雲端讀寫、TTS、AI 修正）
# ==========================================================

def get_github_file_url(filename):
    return f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons/{filename}"

def save_to_github(title, content):
    """【黑科技】：直接將網頁 Text Box 的內容，打包 Push 回你的 GitHub 儲存庫"""
    if not GITHUB_TOKEN:
        return False, "未偵測到有效的 GitHub Token"
    
    filename = f"{title}.txt"
    url = get_github_file_url(filename)
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 檢查檔案是否已存在（若存在需要獲取 sha 才能進行覆蓋更新）
    res = requests.get(url, headers=headers)
    sha = None
    if res.status_code == 200:
        sha = res.json().get("sha")
        
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {
        "message": f"🤖 智能默書機：更新/儲存課文 {title}",
        "content": content_b64,
        "branch": GH_BRANCH
    }
    if sha:
        data["sha"] = sha
        
    put_res = requests.put(url, headers=headers, json=data)
    if put_res.status_code in [200, 201]:
        return True, "成功同步至 GitHub 雲端！"
    return False, f"Git 同步失敗碼: {put_res.status_code}"

def load_all_lessons_from_github():
    """從 GitHub 撈出所有已經儲存過的課文清單"""
    if not GITHUB_TOKEN:
        return []
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/lessons"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        files = res.json()
        return [f["name"].replace(".txt", "") for f in files if f["name"].endswith(".txt")]
    return []

def load_single_lesson(title):
    """讀取某篇特定課文的文字內容"""
    url = get_github_file_url(f"{title}.txt")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content_b64 = res.json().get("content", "")
        return base64.b64decode(content_b64).decode("utf-8")
    return ""

async def generate_edge_tts_audio(text):
    """調用微軟曉曉 Edge TTS 生成雲端串流語音"""
    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural", rate="+0%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def ai_correct_text(bad_text):
    if not GITHUB_TOKEN: return bad_text
    try:
        client = ChatCompletionsClient(endpoint="https://models.inference.ai.azure.com", credential=AzureKeyCredential(GITHUB_TOKEN))
        prompt = "你是一個專門修復小學課文 OCR 錯誤的專家。請將其100%還原成原本準確、通順的繁體中文課文原文。絕對不要夾帶任何 Markdown 語法、註解或額外解釋。"
        response = client.complete(messages=[{"role": "user", "content": prompt + "\n文本:\n" + bad_text}], model="gpt-4o")
        return response.choices[0].message.content.strip()
    except:
        return bad_text

def smart_split_sentence(text, target_len=10):
    strong_ends = ['。', '！', '？', '——', '……']
    split_chars = ['，', '、', '；', '：']
    sub_sentences = []
    current_chunk = ""
    current_char_count = 0
    for char in text:
        current_chunk += char
        if char not in (strong_ends + split_chars + ['「', '」', '《', '》', '“', '”', '·']):
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
# 🎨 Streamlit 前端網頁 UI 介面設計（手機/電腦自動適應）
# ==========================================================
st.set_page_config(page_title="智能雲端普通話默書機", page_icon="📖", layout="wide")

st.title("📖 智能普通話默書機 (雲端網頁版)")
st.caption("📱 支援手機瀏覽器影相、修改課文及微軟曉曉高清讀默同步音軌")

# 初始化 Session 狀態，用來暫存當前正在編輯的課文
if "current_text" not in st.session_state:
    st.session_state["current_text"] = ""

# --- 側邊欄：雲端課本庫檔案管理 ---
st.sidebar.header("📁 雲端 Git 課本庫")
all_lessons = load_all_lessons_from_github()

if all_lessons:
    selected_lesson = st.sidebar.selectbox("開啓舊課文：", ["-- 請選擇 --"] + all_lessons)
    if selected_lesson != "-- 請選擇 --":
        if st.sidebar.button("確認載入課文"):
            st.session_state["current_text"] = load_single_lesson(selected_lesson)
            st.sidebar.success(f"已成功載入: {selected_lesson}")
else:
    st.sidebar.info("雲端暫無存檔，請在右側新增。")

# --- 主畫面：新增/影相獲取課文 ---
tab1, tab2 = st.tabs(["📸 手機影相/上傳圖片來源", "✍️ 手動直接輸入/修改"])

with tab1:
    uploaded_file = st.file_uploader("請選擇課文圖片（手機打開此網頁可直接啟用相機影相）：", type=["png", "jpg", "jpeg"])
    if uploaded_file is not None:
        img = Image.open(uploaded_file)
        st.image(img, caption="已上傳的課文圖片", width=300)
        
        if st.button("🚀 執行 AI OCR 智能識別與修復"):
            with st.spinner("PyTesseract 提取中 + GPT-4o 免費修正中..."):
                raw_text = pytesseract.image_to_string(img, config=r'-l chi_tra+chi_sim --psm 3')
                fixed_text = ai_correct_text(raw_text)
                st.session_state["current_text"] = fixed_text
                st.success("識別並修正完成！已填入下方的文字方塊。")

with tab2:
    st.write("您可以在下方直接打字，或者對剛剛影相辨識出來的內容進行最後校對：")

# 核心文字方塊：temp.txt 網頁化
lesson_content = st.text_area("課文內容 Text Box", value=st.session_state["current_text"], height=250)
st.session_state["current_text"] = lesson_content

# 雲端儲存區
st.subheader("💾 儲存課文到雲端")
col1, col2 = st.columns([2, 1])
with col1:
    lesson_title = st.text_input("請輸入課文標題（例如：小學三年級第二課）：", placeholder="未命名課文")
with col2:
    st.write(" ")
    st.write(" ")
    if st.button("💾 確認儲存至 Git"):
        if not lesson_title.strip():
            st.error("請輸入課文標題後再儲存！")
        elif not lesson_content.strip():
            st.error("課文內容不能為空！")
        else:
            with st.spinner("正在同步至 GitHub..."):
                success, msg = save_to_github(lesson_title.strip(), lesson_content)
                if success:
                    st.success(msg)
                    st.rerun() # 重新整理網頁，更新側邊欄清單
                else:
                    st.error(msg)

# --- 核心：正式開始讀默區 ---
if lesson_content.strip():
    st.markdown("---")
    st.subheader("📢 曉曉老師聽寫默書專區")
    
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', lesson_content) if p.strip()]
    
    if st.button("🏁 生成整篇課文的語音聽寫軌"):
        for p_idx, p_text in enumerate(paragraphs):
            st.markdown(f"#### 🔔 【第 {p_idx+1} 段】")
            sentences = smart_split_sentence(p_text)
            
            for s_idx, sentence in enumerate(sentences):
                st.write(f"👉 正在朗讀: `{sentence}`")
                
                # 呼叫 Edge TTS 生成語音二進位數據
                audio_bytes = asyncio.run(generate_edge_tts_audio(sentence))
                
                # 在網頁端渲染出微軟曉曉音訊組件
                st.audio(audio_bytes, format="audio/wav")
                
                # 提示家長：雲端網頁版可以由學生自行點選每句播放，或者跟隨進度。
                # 由於雲端無法直接控制客戶端的喇叭，Streamlit 的 st.audio 是最完美的解決方案。
