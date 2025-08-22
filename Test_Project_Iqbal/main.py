import streamlit as st
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Muat environment variables dari file .env
load_dotenv()

# Konfigurasi API key Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

st.title("My First AI Chatbot")

# Inisialisasi model
model = genai.GenerativeModel('gemini-2.5-pro')

# Input chat dari pengguna
if prompt := st.chat_input("Tanya sesuatu..."):
    st.chat_message("user").markdown(prompt)

    response = model.generate_content(prompt)

    with st.chat_message("assistant"):
        st.markdown(response.text)

# --- Bagian Sidebar untuk Konfigurasi ---
with st.sidebar:
    st.header("⚙ Configuration")
    st.subheader("🎭 Select Role")
# Placeholder untuk pilihan peran 
    st.subheader("📚 Knowledge Base") 
# Placeholder untuk unggah file

# --- Inisialisasi Session State ---

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Antarmuka Chat Utama ---
# Tampilkan riwayat percakapan
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Daftar peran (ROLES dictionary) ditempatkan di atas
ROLES = {
    "General Assistant": { #...
    },
    # ... (definisi peran lainnya)
}
with st.sidebar:
    # ...
    selected_role = st.selectbox(
        "Choose assistant role:",
options=list(ROLES.keys())
    )
# ...
# ... Di dalam logika `if prompt:`
# Bangun prompt sistem dengan instruksi peran
system_prompt = ROLES[selected_role]["system_prompt"]
# ... Kirim prompt ini ke Gemini ...