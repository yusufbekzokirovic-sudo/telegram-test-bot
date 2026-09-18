import asyncio
import logging
import os
import json
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)

# -------------------------------------------------------------
# 1. BOT SOZLAMALARI VA TOKEN
# -------------------------------------------------------------
BOT_TOKEN = "7074848184:AAEbKHXDuYofwtPeCZ5Tc9YHE8udULvsB5A"  # BotFather'dan olingan tokeningiz
ADMIN_ID = 1763787601              # O'zingizning Telegram ID-ingizni kiriting

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Fayllar nomlari
LESSONS_FILE = "lessons.json"
RESULTS_FILE = "results.json"

# FSM Holatlari
class TestState(StatesGroup):
    waiting_for_answers = State()

class AdminState(StatesGroup):
    waiting_for_test_code = State()
    waiting_for_correct_answers = State()

# -------------------------------------------------------------
# 2. YORDAMCHI FAYL FUNKSIYALARI (JSON PERSISTENCE)
# -------------------------------------------------------------
def load_json(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Fayl o'qishda xatolik ({file_path}): {e}")
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Faylga saqlashda xatolik ({file_path}): {e}")

# -------------------------------------------------------------
# 3. BOT HANDLERLARI (FOYDALANUVCHI VA ADMIN FUNKSIYALARI)
# -------------------------------------------------------------

# /start buyrug'i
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        f"Salom, {message.from_user.full_name}!\n\n"
        "📖 Test javoblarini tekshirish botiga xush kelibsiz.\n"
        "Test topshirish uchun test kodini yuboring (masalan: `101`).\n\n"
        "Natijalarni ko'rish uchun: /results"
    )
    if message.from_user.id == ADMIN_ID:
        welcome_text += "\n\n👨‍💻 **Admin buyruqlari:**\n/addtest - Yangi test qo'shish"
    
    await message.answer(welcome_text, parse_mode="Markdown")

# Admin: Yangi test qo'shish (/addtest)
@dp.message(Command("addtest"))
async def cmd_add_test(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Bu buyruq faqat admin uchun!")
        return
    
    await message.answer("Yangi test kodini kiriting (masalan: `101`):")
    await state.set_state(AdminState.waiting_for_test_code)

@dp.message(AdminState.waiting_for_test_code)
async def process_test_code(message: types.Message, state: FSMContext):
    test_code = message.text.strip()
    await state.update_data(test_code=test_code)
    await message.answer(f"Test kodi `{test_code}` saqlandi.\nEndi to'g'ri javoblarni yuboring (masalan: `abcdabcd` yoki `1a2b3c`):")
    await state.set_state(AdminState.waiting_for_correct_answers)

@dp.message(AdminState.waiting_for_correct_answers)
async def process_correct_answers(message: types.Message, state: FSMContext):
    answers = message.text.strip().lower()
    data = await state.get_data()
    test_code = data.get("test_code")

    lessons = load_json(LESSONS_FILE)
    lessons[test_code] = answers
    save_json(LESSONS_FILE, lessons)

    await message.answer(f"✅ Test `{test_code}` muvaffaqiyatli saqlandi!\nJavoblar soni: {len(answers)} ta.")
    await state.clear()

# Natijalarni ko'rish (/results)
@dp.message(Command("results"))
async def cmd_results(message: types.Message):
    results = load_json(RESULTS_FILE)
    user_id = str(message.from_user.id)
    
    if user_id not in results or not results[user_id]:
        await message.answer("Sizda hali topshirilgan testlar natijalari yo'q.")
        return
    
    text = "📊 **Sizning test natijalaringiz:**\n\n"
    for res in results[user_id]:
        text += f"🔹 Test: `{res['test_code']}` | Ball: {res['score']}/{res['total']} ({res['percentage']}%)\n"
    
    await message.answer(text, parse_mode="Markdown")

# Test kodini qabul qilish va javoblarni tekshirish
@dp.message(F.text)
async def handle_test_submission(message: types.Message, state: FSMContext):
    text = message.text.strip()
    current_state = await state.get_state()

    # Agar foydalanuvchi test kodini kiritayotgan bo'lsa
    if current_state is None:
        lessons = load_json(LESSONS_FILE)
        
        # Kiritilgan matn test kodi sifatidami tekshiramiz
        parts = text.split()
        if len(parts) == 2:
            test_code, user_answers = parts[0], parts[1].lower()
            if test_code in lessons:
                await check_and_save_test(message, test_code, user_answers, lessons[test_code])
                return

        if text in lessons:
            await state.update_data(test_code=text)
            await message.answer(f"Test kodi: `{text}` topildi.\nEndi javoblaringizni bir qatorda yuboring (masalan: `abcdabcd`):")
            await state.set_state(TestState.waiting_for_answers)
        else:
            await message.answer("❌ Bunday koddagi test topilmadi. Qaytadan kiriting yoki adminga murojaat qiling.")

    elif current_state == TestState.waiting_for_answers:
        data = await state.get_data()
        test_code = data.get("test_code")
        lessons = load_json(LESSONS_FILE)
        
        correct_answers = lessons.get(test_code, "")
        user_answers = text.lower().strip()
        
        await check_and_save_test(message, test_code, user_answers, correct_answers)
        await state.clear()

async def check_and_save_test(message: types.Message, test_code: str, user_answers: str, correct_answers: str):
    total = len(correct_answers)
    score = 0
    
    for u, c in zip(user_answers, correct_answers):
        if u == c:
            score += 1
            
    percentage = round((score / total) * 100, 1) if total > 0 else 0

    # Natijani results.json ga saqlaymiz
    results = load_json(RESULTS_FILE)
    user_id = str(message.from_user.id)
    
    if user_id not in results:
        results[user_id] = []
        
    results[user_id].append({
        "test_code": test_code,
        "score": score,
        "total": total,
        "percentage": percentage
    })
    save_json(RESULTS_FILE, results)

    response = (
        f"✅ **Test tekshirildi!**\n\n"
        f"📋 Test kodi: `{test_code}`\n"
        f"🎯 To'g'ri javoblar: {score} / {total}\n"
        f"📈 Foiz: {percentage}%\n"
    )
    await message.answer(response, parse_mode="Markdown")

# -------------------------------------------------------------
# 4. RENDER UCHUN AIOHTTP WEB SERVER (PORT TIMEOUT UCHUN)
# -------------------------------------------------------------
async def handle_health_check(request):
    return web.Response(text="Bot 24/7 faol va sog'lom ishlamoqda!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"AIOHTTP Web-server {port}-portda ishga tushdi.")

# -------------------------------------------------------------
# 5. ASOSIY ISHGA TUSHIRISH (MAIN)
# -------------------------------------------------------------
async def main():
    # 1. Background web-serverni yurgizamiz (Render 90s timeout bermasligi uchun)
    await start_web_server()
    
    # 2. Bot pollingini boshlaymiz
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
