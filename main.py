import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
import yt_dlp
from playwright.async_api import async_playwright

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Foydalanuvchilar topgan oqimlarini vaqtincha saqlash uchun lug'at
user_streams = {}

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

async def sniff_video_streams(webpage_url: str):
    """Sahifadagi barcha video oqimlarini (.m3u8, .mp4) ushlab qoluvchi sniffer"""
    found_streams = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            def intercept_request(request):
                req_url = request.url
                if any(ext in req_url for ext in ['.m3u8', '.mp4', '.ts', 'playlist.m3u8', 'index.m3u8']):
                    if req_url not in found_streams:
                        found_streams.append(req_url)

            page.on("request", intercept_request)
            
            try:
                await page.goto(webpage_url, timeout=60000, wait_until="domcontentloaded")
            except Exception:
                pass

            await page.wait_for_timeout(8000)
            await browser.close()
    except Exception as e:
        logging.error(f"Sniffer xatoligi: {e}")
    
    return found_streams

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
    await message.answer("Xush kelibsiz! Menga video havolasini yuboring, men barcha oqimlarni topib ro'yxat tuzib beraman.")

@dp.message(F.text.startswith("http://") | F.text.startswith("https://"))
async def handle_url(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("🔍 IDM sniffer yordamida sayt tahlil qilinmoqda, kuting...")
    
    streams = await sniff_video_streams(url)
    
    if not streams:
        # Agar sniffer topolmasa, yt-dlp ga urinib ko'ramiz
        streams = [url]

    user_streams[message.from_user.id] = streams

    # Tugmalar yaratamiz
    builder = InlineKeyboardBuilder()
    for idx, stream in enumerate(streams, 1):
        ext = "m3u8" if "m3u8" in stream else "mp4"
        builder.button(text=f"📥 Video oqimi #{idx} ({ext.upper()})", callback_data=f"dl_{idx-1}")
    
    builder.adjust(1)

    await status_msg.edit_text(
        f"✅ **Tahlil yakunlandi!**\n\n"
        f"🔍 Topilgan oqimlar soni: **{len(streams)} ta**\n"
        f"Quyidagi tugmalardan birini bosing va yuklab olishni boshlang:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_streams:
        await callback.answer("❌ Ma'lumot eskirgan. Iltimos, havolani qaytadan yuboring.", show_alert=True)
        return

    index = int(callback.data.split("_")[1])
    streams = user_streams[user_id]
    
    if index >= len(streams):
        await callback.answer("❌ Xatolik yuz berdi.", show_alert=True)
        return

    selected_url = streams[index]
    status_msg = callback.message
    
    await status_msg.edit_text("⏳ Yuklab olish boshlanmoqda...")

    file_prefix = f"downloads/vid_{user_id}_{callback.message.message_id}"
    os.makedirs("downloads", exist_ok=True)
    loop = asyncio.get_running_loop()

    file_path = None
    try:
        file_path = await loop.run_in_executor(None, download_video, selected_url, file_prefix, status_msg, loop)
        
        await status_msg.edit_text("📤 Video Telegram serveriga yuborilmoqda...")

        # Fayl hajmini tekshirish (Telegram limiti 2GB)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 2000:
            await status_msg.edit_text("❌ Fayl hajmi 2 GB dan katta, Telegram uni yubora olmaydi!")
            return

        video_file = types.FSInputFile(file_path)
        await callback.message.answer_video(
            video=video_file,
            caption="✅ Videongiz muvaffaqiyatli yuklab olindi!"
        )
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Yuklash/Yuborish xatosi: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi:\n`{str(e)}`", parse_mode="Markdown")

    finally:
        # Faylni faqat yuborib bo'lingandan keyin o'chiramiz
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

async def on_startup(bot: Bot):
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
        await bot.set_webhook(webhook_url)

def main():
    if RENDER_EXTERNAL_URL:
        dp.startup.register(on_startup)
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        
        port = int(os.environ.get("PORT", 10000))
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
