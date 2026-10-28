import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL") # Render beradigan tashqi URL

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def make_progress_hook(status_msg, loop):
    last_percent = [""]
    def hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()
            
            if percent != last_percent[0]:
                last_percent[0] = percent
                text = f"📥 **Yuklab olinmoqda...**\n\n📊 Foiz: {percent}\n🚀 Tezlik: {speed}\n⏳ Qolgan vaqt: {eta}"
                asyncio.run_coroutine_threadsafe(safe_edit_text(status_msg, text), loop)
    return hook

async def safe_edit_text(msg, text):
    try:
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception:
        pass

def download_video(url: str, output_path: str, status_msg, loop) -> str:
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
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
    await message.answer("Xush kelibsiz! Menga video havolasini yuboring, IDM kabi yuklab beraman.")

@dp.message(F.text.startswith("http://") | F.text.startswith("https://"))
async def handle_url(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("🔍 Havola tahlil qilinmoqda...")
    
    file_prefix = f"downloads/vid_{message.from_user.id}_{message.message_id}"
    os.makedirs("downloads", exist_ok=True)
    loop = asyncio.get_running_loop()

    try:
        file_path = await loop.run_in_executor(None, download_video, url, file_prefix, status_msg, loop)
        await status_msg.edit_text("📤 Telegramga yuborilmoqda...")

        video_file = types.FSInputFile(file_path)
        await message.answer_video(video=video_file, caption="✅ Videongiz tayyor!")
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await status_msg.edit_text("❌ Videoni yuklab bo'lmadi. Havola yaroqsiz yoki himoyalangan.")
    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def on_startup(bot: Bot):
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
        await bot.set_webhook(webhook_url)
        logging.info(f"Webhook o'rnatildi: {webhook_url}")

def main():
    if RENDER_EXTERNAL_URL:
        # Render serverida ishlasa - Webhook rejimi
        dp.startup.register(on_startup)
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        
        port = int(os.environ.get("PORT", 10000))
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        # Kompyuterda ishlasa - Oddiy Polling rejimi
        asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
