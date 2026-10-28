import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
import yt_dlp

# Server muhitidan BOT_TOKEN ni o'qib olamiz
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Agar token topilmasa, dastur xatolik berib to'xtashi uchun himoya
if not BOT_TOKEN:
    raise ValueError("Xatolik: BOT_TOKEN muhit o'zgaruvchisida (Environment Variables) topilmadi!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# yt-dlp yuklanish holatini ushlab turuvchi funksiya
def make_progress_hook(status_msg, loop):
    last_percent = [""]
    def hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()
            
            # Har safar foiz o'zgarganda xabarni yangilash (spamlarni oldini olish uchun)
            if percent != last_percent[0]:
                last_percent[0] = percent
                text = f"📥 **Yuklab olinmoqda...**\n\n📊 Foiz: {percent}\n🚀 Tezlik: {speed}\n⏳ Qolgan vaqt: {eta}"
                asyncio.run_coroutine_threadsafe(
                    safe_edit_text(status_msg, text), loop
                )
    return hook

async def safe_edit_text(msg, text):
    try:
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception:
        pass # Telegram tezlik cheklovi (flood) tufayli xatolik bersa e'tiborsiz qoldiramiz

def download_video(url: str, output_path: str, status_msg, loop) -> str:
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'progress_hooks': [make_progress_hook(status_msg, loop)],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(filename)
        expected_mp4 = f"{base}.mp4"
        if os.path.exists(expected_mp4):
            return expected_mp4
        return filename

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Xush kelibsiz! Menga video havolasini yuboring, uni yuklab beraman va jarayonni ko'rsatib turaman."
    )

@dp.message(F.text.startswith("http://") | F.text.startswith("https://"))
async def handle_url(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("🔍 Havola tahlil qilinmoqda...")
    
    file_prefix = f"downloads/vid_{message.from_user.id}_{message.message_id}"
    os.makedirs("downloads", exist_ok=True)
    loop = asyncio.get_running_loop()

    try:
        # Videoni yuklab olish
        file_path = await loop.run_in_executor(
            None, download_video, url, file_prefix, status_msg, loop
        )

        await status_msg.edit_text("📤 **Video Telegram serveriga yuborilmoqda... Kuting.**", parse_mode="Markdown")

        video_file = types.FSInputFile(file_path)
        await message.answer_video(
            video=video_file,
            caption="✅ Videongiz tayyor!"
        )
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi.\nSababi: Havola yaroqsiz yoki video juda katta.")

    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.main(main()) if hasattr(asyncio, 'main') else asyncio.run(main())
