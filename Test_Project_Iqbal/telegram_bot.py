# Impor pustaka yang diperlukan
import os
import logging
from dotenv import load_dotenv
import pandas as pd
import tabulate
from openai import OpenAI
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
# NEW: Impor untuk menangani file Word dan file di memori
import docx
from io import BytesIO

# Muat variabel lingkungan dari file .env
load_dotenv()

# --- Pengaturan Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Persona dan Logika Inti ASKARINA ---
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

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR7b41aChFNSZ9CXvQV5ILKH7J3cUTJDqcvT48tl-EAT---7g0m9K17fgvXAn7diXdm0jMPmAScT1Jl/pub?output=xlsx"

# --- Fungsi ---
def load_database_as_df(url):
    try:
        df = pd.read_excel(url, engine="openpyxl")
        logger.info("Database berhasil dimuat ke dalam DataFrame.")
        return df
    except Exception as e:
        logger.error(f"Error memuat spreadsheet: {e}")
        return None

def find_relevant_context(prompt, df):
    if df is None or df.empty:
        return "Database tidak dimuat atau kosong."
    prompt_keywords = set(prompt.lower().split())
    df_searchable = df.astype(str).apply(lambda x: ' '.join(x).lower(), axis=1)
    mask = df_searchable.str.contains('|'.join(prompt_keywords), na=False)
    relevant_df = df[mask]
    if relevant_df.empty:
        return "Tidak ada data spesifik yang ditemukan untuk permintaan Anda di database."
    return tabulate.tabulate(relevant_df, headers="keys", tablefmt="github", showindex=False)

def generate_sph_text(data):
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
        response = GEMINI_CLIENT.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error saat membuat SPH: {e}")
        return "Maaf, terjadi kesalahan saat membuat draf SPH."

# --- Variabel global dan Klien API ---
TELKOM_API_KEY = os.getenv("TELKOM_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELKOM_CLIENT = OpenAI(api_key=TELKOM_API_KEY, base_url="https://telkom-ai-dag-api.apilogy.id/Telkom-LLM/0.0.4/llm", default_headers={"x-api-key": TELKOM_API_KEY})
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_CLIENT = genai.GenerativeModel('gemini-1.5-flash')
DATABASE_DF = load_database_as_df(SPREADSHEET_URL)

# --- State untuk ConversationHandler ---
MAIN_MENU, CHOOSE_MODE, SPH_CUSTOMER, SPH_ADDRESS, SPH_PRODUCT, SPH_PRICE, SPH_NOTES, HANDLE_QUERY = range(8)

# --- Fungsi Menu dan Navigasi ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"Pengguna {update.effective_user.first_name} memulai percakapan.")
    context.user_data.clear()
    keyboard = [["Pilih Mode", "Buat SPH"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Halo! Saya ASKARINA, Asisten Kawal B2B Anda. Silakan pilih opsi dari menu di bawah:",
        reply_markup=reply_markup,
    )
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_choice = update.message.text
    logger.info(f"Pilihan menu utama: {user_choice}")
    if user_choice == "Pilih Mode":
        keyboard = [["Data Internal", "Riset Prospek & Umum"], ["Kembali ke Menu Utama"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Silakan pilih mode:", reply_markup=reply_markup)
        return CHOOSE_MODE
    elif user_choice == "Buat SPH":
        keyboard = [["Batal"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Baik, mari kita mulai membuat SPH. Siapa nama pelanggannya?", reply_markup=reply_markup)
        return SPH_CUSTOMER
    else:
        return await start(update, context)

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Pengguna kembali ke menu utama.")
    return await start(update, context)

# --- Fungsi Penangan Mode Chat ---
async def set_mode_and_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mode = update.message.text
    context.user_data['mode'] = mode
    logger.info(f"Mode diatur ke: {mode}")
    await update.message.reply_text(f"Mode diatur ke: {mode}. Silakan ajukan pertanyaan Anda.", reply_markup=ReplyKeyboardRemove())
    return HANDLE_QUERY

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mode = context.user_data.get('mode')
    prompt = update.message.text
    logger.info(f"Menerima pesan dari {update.effective_user.first_name} dalam mode {mode}: {prompt}")

    if mode == "Data Internal":
        if DATABASE_DF is None:
            await update.message.reply_text("Maaf, database tidak dapat diakses saat ini.")
        else:
            relevant_knowledge = find_relevant_context(prompt, DATABASE_DF)
            final_system_prompt = ASKARINA_INTERNAL_PROMPT + "\n" + relevant_knowledge
            api_messages = [{"role": "system", "content": final_system_prompt}, {"role": "user", "content": prompt}]
            try:
                response = TELKOM_CLIENT.chat.completions.create(model="telkom-ai", messages=api_messages)
                await update.message.reply_text(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"Error memanggil Telkom API: {e}")
                await update.message.reply_text("Maaf, terjadi kesalahan saat menghubungi layanan internal.")
    
    elif mode == "Riset Prospek & Umum":
        final_prompt = ASKARINA_RESEARCH_PROMPT + "\n\nPertanyaan Pengguna: " + prompt
        try:
            response = GEMINI_CLIENT.generate_content(final_prompt)
            await update.message.reply_text(response.text)
        except Exception as e:
            logger.error(f"Error memanggil Gemini API: {e}")
            await update.message.reply_text("Maaf, terjadi kesalahan saat melakukan riset.")
    
    return await start(update, context)

# --- Fungsi Penangan Generator SPH ---
async def sph_get_customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sph'] = {'customer_name': update.message.text}
    await update.message.reply_text("Baik. Apa alamat lengkap pelanggan?")
    return SPH_ADDRESS

async def sph_get_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sph']['customer_address'] = update.message.text
    await update.message.reply_text("Oke. Produk/layanan apa yang ditawarkan?")
    return SPH_PRODUCT

async def sph_get_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sph']['product'] = update.message.text
    await update.message.reply_text("Dicatat. Berapa harga penawarannya?")
    return SPH_PRICE

async def sph_get_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sph']['price'] = update.message.text
    await update.message.reply_text("Hampir selesai. Apakah ada catatan tambahan? (Ketik '-' jika tidak ada)")
    return SPH_NOTES

async def sph_get_notes_and_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sph']['notes'] = update.message.text
    await update.message.reply_text("Terima kasih. Saya sedang membuat draf SPH...", reply_markup=ReplyKeyboardRemove())
    
    sph_data = context.user_data['sph']
    sph_text = generate_sph_text(sph_data)
    
    # --- REVISED: Membuat dan mengirim file Word ---
    try:
        # Membuat dokumen Word di memori
        document = docx.Document()
        document.add_paragraph(sph_text)
        
        # Menyimpan dokumen ke buffer BytesIO
        doc_io = BytesIO()
        document.save(doc_io)
        doc_io.seek(0) # Kembali ke awal file
        
        # Membuat nama file yang dinamis
        customer_name = sph_data.get('customer_name', 'customer').replace(' ', '_')
        file_name = f"SPH_{customer_name}.docx"
        
        # Mengirim dokumen ke pengguna
        await update.message.reply_document(document=doc_io, filename=file_name)
        logger.info(f"File SPH '{file_name}' berhasil dikirim.")

    except Exception as e:
        logger.error(f"Gagal membuat atau mengirim file docx: {e}")
        await update.message.reply_text("Maaf, terjadi kesalahan saat membuat file Word. Berikut adalah draf dalam bentuk teks:")
        await update.message.reply_text(sph_text) # Fallback ke teks biasa jika gagal
    
    context.user_data.pop('sph', None)
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Pengguna membatalkan operasi.")
    context.user_data.clear()
    await update.message.reply_text("Proses dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

# --- Fungsi Utama ---
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN tidak ditemukan di file .env!")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.Regex(r'^(Pilih Mode|Buat SPH)$'), main_menu_handler)],
            CHOOSE_MODE: [
                MessageHandler(filters.Regex(r'^(Data Internal|Riset Prospek & Umum)$'), set_mode_and_prompt),
                MessageHandler(filters.Regex(r'^Kembali ke Menu Utama$'), back_to_main_menu),
            ],
            HANDLE_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query)],
            SPH_CUSTOMER: [MessageHandler(filters.TEXT & ~filters.COMMAND, sph_get_customer)],
            SPH_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sph_get_address)],
            SPH_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sph_get_product)],
            SPH_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sph_get_price)],
            SPH_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, sph_get_notes_and_generate)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r'^(Batal|Kembali ke Menu Utama)$'), cancel)
        ],
    )

    application.add_handler(conv_handler)
    
    logger.info("Bot sedang berjalan...")
    application.run_polling()

if __name__ == "__main__":
    main()
