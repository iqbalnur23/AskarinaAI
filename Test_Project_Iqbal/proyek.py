# Impor pustaka (library) yang diperlukan
from openai import OpenAI
import google.generativeai as genai
import streamlit as st
import os
from dotenv import load_dotenv
import pandas as pd
import tabulate
from io import BytesIO

# Muat variabel lingkungan dari file .env (untuk menyimpan kunci API)
load_dotenv()

st.set_page_config(layout="wide")
st.title("🇮🇩 ASKARINA - Asisten Kawal B2B Telkom Indonesia")

# --- Definisi Persona dalam Bahasa Indonesia ---
ASKARINA_INTERNAL_PROMPT = """Anda adalah ASKARINA, 'Asisten Kawal B2B Telkom Indonesia'. Fungsi utama Anda adalah membantu peran striker Telkom Indonesia (Account Manager, Sales Assistant, Account Representative) dengan memberikan informasi yang cepat dan akurat dari database pelanggan B2B.

Aturan Anda:
- Nada bicara Anda harus profesional, efisien, dan suportif.
- Saat ditanya, temukan jawaban langsung dari data pelanggan relevan yang disediakan di bawah ini.
- Jika data tidak ditemukan dalam database, Anda harus menyatakan: "Maaf, data yang Anda cari tidak ditemukan dalam database."
- Jangan mengarang informasi atau menjawab pertanyaan di luar lingkup data yang disediakan.

Berikut adalah data pelanggan yang relevan untuk permintaan pengguna:
"""

ASKARINA_RESEARCH_PROMPT = """Anda adalah ASKARINA, seorang Asisten Riset B2B industri telekomunikasi. Peran Anda adalah untuk menjawab pertanyaan pengetahuan umum dan melakukan pencarian di internet untuk menemukan informasi, seperti analisis pasar, profil perusahaan, atau tren industri untuk mencari prospek pelanggan baru di sektor pelayanan digital dan Telekomunikasi.
- Jawaban harus informatif, membantu, dan jika memungkinkan, sebutkan sumbernya.
- Selalu berkomunikasi dalam Bahasa Indonesia.
"""

# --- Konfigurasi API dan Database ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR7b41aChFNSZ9CXvQV5ILKH7J3cUTJDqcvT48tl-EAT---7g0m9K17fgvXAn7diXdm0jMPmAScT1Jl/pub?output=xlsx"

# --- Inisialisasi Klien API ---
@st.cache_resource
def get_telkom_client():
    api_key = os.getenv("TELKOM_API_KEY")
    if not api_key: return None
    try:
        return OpenAI(api_key=api_key, base_url="https://telkom-ai-dag-api.apilogy.id/Telkom-LLM/0.0.4/llm", default_headers={"x-api-key": api_key})
    except Exception: return None

@st.cache_resource
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except Exception: return None

# --- Fungsi Pemuatan dan Pencarian Database ---
@st.cache_data
def load_database_as_df(url):
    try:
        return pd.read_excel(url, engine="openpyxl")
    except Exception: return None

def find_relevant_context(prompt, df):
    if df is None or df.empty: return "Database tidak dimuat atau kosong."
    prompt_keywords = set(prompt.lower().split())
    df_searchable = df.astype(str).apply(lambda x: ' '.join(x).lower(), axis=1)
    mask = df_searchable.str.contains('|'.join(prompt_keywords), na=False)
    relevant_df = df[mask]
    if relevant_df.empty: return "Tidak ada data spesifik yang ditemukan untuk permintaan Anda di database."
    return tabulate.tabulate(relevant_df, headers="keys", tablefmt="github", showindex=False)

# --- Fungsi Pembuatan SPH ---
def generate_sph_content(data):
    prompt = f"""
    Berdasarkan informasi berikut, buat draf dokumen SPH (Surat Penawaran Harga) yang profesional dalam Bahasa Indonesia.
    
    - Nama Pelanggan: {data['customer_name']}
    - Alamat Pelanggan: {data['customer_address']}
    - Produk/Layanan: {data['product']}
    - Harga: {data['price']}
    - Catatan Tambahan: {data['notes']}

    Dokumen harus memiliki header yang jelas, pendahuluan, detail penawaran, harga, syarat dan ketentuan, serta penutup.
    """
    try:
        gemini_client = get_gemini_client()
        response = gemini_client.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Terjadi kesalahan saat membuat SPH: {e}"

# --- Tata Letak Aplikasi Utama ---
col1, col2 = st.columns([2, 1])

with col1:
    st.header("Asisten Chat")
    
    # --- Pemilihan Mode untuk ASKARINA ---
    selected_mode = st.radio(
        "Pilih Mode ASKARINA:",
        ["Data Internal (Telkom LLM)", "Riset Prospek & Umum (Google Gemini)"],
        horizontal=True,
        key="mode_selection"
    )

    # Inisialisasi riwayat chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Tampilkan riwayat chat
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Terima input pengguna
    if prompt := st.chat_input("Tanyakan sesuatu pada ASKARINA..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            response_container = st.empty()
            full_response = ""

            # --- Logika untuk mengarahkan prompt ke AI yang benar ---
            if selected_mode == "Data Internal (Telkom LLM)":
                telkom_client = get_telkom_client()
                db_df = st.session_state.get("database_df")
                if not telkom_client or db_df is None:
                    full_response = "Error: ASKARINA mode internal tidak terkonfigurasi dengan benar. Periksa kunci API dan tautan spreadsheet."
                else:
                    relevant_knowledge = find_relevant_context(prompt, db_df)
                    final_system_prompt = ASKARINA_INTERNAL_PROMPT + "\n" + relevant_knowledge
                    api_messages = [{"role": "system", "content": final_system_prompt}, {"role": "user", "content": prompt}]
                    try:
                        stream = telkom_client.chat.completions.create(model="telkom-ai", messages=api_messages, stream=True)
                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                full_response += chunk.choices[0].delta.content
                                response_container.markdown(full_response + "▌")
                    except Exception as e:
                        full_response = f"Error saat memanggil Telkom API: {e}"

            elif selected_mode == "Riset Prospek & Umum (Google Gemini)":
                gemini_client = get_gemini_client()
                if not gemini_client:
                    full_response = "Error: ASKARINA mode riset tidak terkonfigurasi. Periksa kunci API Gemini Anda."
                else:
                    final_prompt = ASKARINA_RESEARCH_PROMPT + "\n\nPertanyaan Pengguna: " + prompt
                    try:
                        stream = gemini_client.generate_content(final_prompt, stream=True)
                        for chunk in stream:
                            full_response += chunk.text
                            response_container.markdown(full_response + "▌")
                    except Exception as e:
                        full_response = f"Error saat memanggil Gemini API: {e}"
            
            response_container.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

with col2:
    st.header("Generator SPH")
    st.markdown("Buat draf Surat Penawaran Harga (SPH) dengan cepat.")

    with st.form("sph_form"):
        customer_name = st.text_input("Nama Pelanggan")
        customer_address = st.text_area("Alamat Pelanggan")
        product = st.text_input("Produk/Layanan yang Ditawarkan")
        price = st.text_input("Harga Penawaran (misal: Rp 1.000.000 / bulan)")
        notes = st.text_area("Catatan Tambahan (opsional)")
        submitted = st.form_submit_button("Buat Draf SPH")

    if submitted:
        if not all([customer_name, customer_address, product, price]):
            st.warning("Mohon lengkapi semua kolom yang wajib diisi.")
        else:
            with st.spinner("ASKARINA sedang membuat draf SPH..."):
                sph_data = {
                    "customer_name": customer_name,
                    "customer_address": customer_address,
                    "product": product,
                    "price": price,
                    "notes": notes,
                }
                generated_content = generate_sph_content(sph_data)
                st.session_state.sph_content = generated_content

    if "sph_content" in st.session_state:
        st.text_area("Draf SPH", st.session_state.sph_content, height=300)
        sph_bytes = st.session_state.sph_content.encode('utf-8')
        st.download_button(
            label="Download SPH (.txt)",
            data=BytesIO(sph_bytes),
            file_name=f"SPH_{customer_name.replace(' ', '_')}.txt",
            mime="text/plain"
        )

# --- Pengaturan Awal Saat Aplikasi Dimuat ---
if "database_df" not in st.session_state:
    st.session_state.database_df = load_database_as_df(SPREADSHEET_URL)
