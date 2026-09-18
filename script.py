import asyncio
import logging
import os
import json
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# -------------------------------------------------------------
# 1. BOT SOZLAMALARI
# -------------------------------------------------------------
BOT_TOKEN = "7074848184:AAEbKHXDuYofwtPeCZ5Tc9YHE8udULvsB5A"  # BotFather'dan olingan tokeningizni kiriting
ADMIN_ID = 1763787601              # O'zingizning Telegram ID-ingizni kiriting

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

LESSONS_FILE = "lessons.json"
RESULTS_FILE = "results.json"
USERS_FILE = "users.json"

class UserRegisterState(StatesGroup):
    waiting_for_full_name = State()

class AdminState(StatesGroup):
    waiting_for_test_code = State()
    waiting_for_answers = State()
    waiting_for_edit_code = State()
    waiting_for_new_answers = State()

class TestState(StatesGroup):
    waiting_for_user_answers = State()

# -------------------------------------------------------------
# 2. JSON FAYLLAR BILAN ISHLASH VA YORDAMChI FUNKSIYALAR
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
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def extract_answers(text):
    return "".join(re.findall(r'[a-zA-Z]', text)).lower()

def add_user_coins(user_id, coins_to_add):
    users = load_json(USERS_FILE)
    str_user_id = str(user_id)
    if str_user_id in users:
        users[str_user_id]["coins"] = users[str_user_id].get("coins", 0) + coins_to_add
        users[str_user_id]["tests_count"] = users[str_user_id].get("tests_count", 0) + 1
        save_json(USERS_FILE, users)
        return users[str_user_id]["coins"]
    return 0

def get_user_data(user_id):
    users = load_json(USERS_FILE)
    return users.get(str(user_id), {"name": "Noma'lum", "coins": 0, "tests_count": 0})

# -------------------------------------------------------------
# 3. TUGMALAR (KEYBOARDS)
# -------------------------------------------------------------
def get_main_keyboard(user_id):
    # Admin uchun faqat admin menyusi chiqariladi
    if user_id == ADMIN_ID:
        return get_admin_keyboard()
    
    # O'quvchilar uchun asosiy menyu
    kb = [
        [KeyboardButton(text="📝 Test yuborish"), KeyboardButton(text="🗓 Davomat")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="🏆 Reyting")],
        [KeyboardButton(text="📊 Natijalarim"), KeyboardButton(text="🪙 Tangalarim")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    kb = [
        [KeyboardButton(text="➕ Yangi test qo'shish"), KeyboardButton(text="✏️ Testni tahrirlash")],
        [KeyboardButton(text="📋 Barcha natijalarni ko'rish")],
        [KeyboardButton(text="⬅️ Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_tests_inline_keyboard(user_id=None, is_admin=False):
    lessons = load_json(LESSONS_FILE)
    results = load_json(RESULTS_FILE)
    
    completed_tests = set()
    if user_id and not is_admin:
        user_results = results.get(str(user_id), [])
        for res in user_results:
            completed_tests.add(res.get("test_code"))

    builder = []
    for code, ans in lessons.items():
        if is_admin or code not in completed_tests:
            builder.append([InlineKeyboardButton(text=f"📚 TEST {code} ({len(ans)} ta savol)", callback_data=f"select_test_{code}")])
            
    return InlineKeyboardMarkup(inline_keyboard=builder)

# -------------------------------------------------------------
# 4. HANDLERLAR
# -------------------------------------------------------------
@dp.message(CommandStart())
@dp.message(F.text == "⬅️ Bosh menyu")
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Admin kirganida
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "👨‍💼 **Xush kelibsiz, Admin!**\n\nBoshqaruv panelidan kerakli bo'limni tanlang:",
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown"
        )
        return

    # Oddiy foydalanuvchini tekshirish va ro'yxatdan o'tkazish
    users = load_json(USERS_FILE)
    user_id = str(message.from_user.id)
    
    if user_id not in users or "name" not in users[user_id]:
        await message.answer("Assalomu alaykum! Botdan foydalanish uchun **Ism va Familiyangizni** kiriting:\n\n*Masalan: Ali Valiyev*", parse_mode="Markdown")
        await state.set_state(UserRegisterState.waiting_for_full_name)
        return

    await message.answer(
        f"Xush kelibsiz, {users[user_id]['name']}! Kerakli bo'limni tanlang:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(UserRegisterState.waiting_for_full_name)
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    words = full_name.split()
    
    # Ism va familiyani kamida 2 ta so'zdan iboratligini tekshirish
    if len(words) < 2 or not all(w.isalpha() for w in words):
        await message.answer("⚠️ **Iltimos, ism va familiyangizni to'liq kiriting!**\n\nMasalan: `Ali Valiyev`", parse_mode="Markdown")
        return

    users = load_json(USERS_FILE)
    user_id = str(message.from_user.id)
    
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["name"] = full_name
    users[user_id]["coins"] = users[user_id].get("coins", 0)
    users[user_id]["tests_count"] = users[user_id].get("tests_count", 0)
    save_json(USERS_FILE, users)
    
    await state.clear()
    await message.answer(f"✅ Rahmat, **{full_name}**! Muvaffaqiyatli ro'yxatdan o'tdingiz.", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "👤 Profil")
async def show_profile(message: types.Message):
    data = get_user_data(message.from_user.id)
    await message.answer(
        f"👤 **Foydalanuvchi profili:**\n\n"
        f"👤 Ism: {data.get('name', 'Kiritilmagan')}\n"
        f"🪙 Tangalar: {data.get('coins', 0)} ta\n"
        f"📝 Ishlangan testlar: {data.get('tests_count', 0)} ta",
        parse_mode="Markdown"
    )

@dp.message(F.text == "🪙 Tangalarim")
async def show_coins(message: types.Message):
    data = get_user_data(message.from_user.id)
    await message.answer(f"🪙 Sizning jami tangalaringiz: **{data.get('coins', 0)} ta**\n\nHar bir to'g'ri javob uchun 1 ta tanga beriladi!", parse_mode="Markdown")

@dp.message(F.text == "🗓 Davomat")
async def show_attendance(message: types.Message):
    await message.answer("🗓 Davomat tizimi faollashtirilmoqda. Tez orada ushbu bo'lim ishga tushadi!")

@dp.message(F.text == "🏆 Reyting")
async def show_leaderboard(message: types.Message):
    users = load_json(USERS_FILE)
    if not users:
        await message.answer("Hozircha reyting ma'lumotlari mavjud emas.")
        return
    
    sorted_users = sorted(users.items(), key=lambda x: x[1].get('coins', 0), reverse=True)
    
    user_id_str = str(message.from_user.id)
    user_rank = None
    user_coins = 0
    
    for rank, (u_id, u_data) in enumerate(sorted_users, 1):
        if u_id == user_id_str:
            user_rank = rank
            user_coins = u_data.get('coins', 0)
            break

    text = "🏆 **Top-10 eng ko'p tangaga ega o'quvchilar:**\n\n"
    for idx, (u_id, u_data) in enumerate(sorted_users[:10], 1):
        name = u_data.get('name', 'Noma\'lum')
        text += f"{idx}. **{name}** — 🪙 {u_data.get('coins', 0)} ta tanga\n"
    
    text += "\n" + "─" * 25 + "\n"
    if user_rank:
        text += f"📊 **Sizning o'rningiz:** {user_rank}-o'rin ({user_coins} ta tanga)"
    else:
        text += "📊 **Sizning o'rningiz:** Hali ro'yxatda yo'qsiz."

    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 Natijalarim")
async def show_results(message: types.Message):
    results = load_json(RESULTS_FILE)
    user_id = str(message.from_user.id)
    
    if user_id not in results or not results[user_id]:
        await message.answer("Siz hali test topshirmadingiz.")
        return
    
    text = "📊 **Sizning test natijalaringiz:**\n\n"
    for res in results[user_id]:
        text += f"🔹 TEST `{res['test_code']}`: {res['score']}/{res['total']} ({res['percentage']}%)\n"
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN PANEL ---
@dp.message(F.text == "🧑‍💻 Admin Panel")
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("🧑‍💻 Admin Panelga xush kelibsiz!", reply_markup=get_admin_keyboard())

@dp.message(F.text == "📋 Barcha natijalarni ko'rish")
async def show_all_results(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    results = load_json(RESULTS_FILE)
    users = load_json(USERS_FILE)
    
    if not results:
        await message.answer("Hozircha hech kim test topshirmadi.")
        return
    
    text = "📋 **O'quvchilarning barcha test natijalari:**\n\n"
    for u_id, u_results in results.items():
        u_name = users.get(u_id, {}).get("name", f"ID: {u_id}")
        text += f"👤 **{u_name}:**\n"
        for res in u_results:
            text += f"   ▫️ TEST {res['test_code']}: {res['score']}/{res['total']} ({res['percentage']}%)\n"
        text += "\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "➕ Yangi test qo'shish")
async def add_test_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Yangi test kodi/raqamini kiriting (masalan: `1`):")
    await state.set_state(AdminState.waiting_for_test_code)

@dp.message(AdminState.waiting_for_test_code)
async def add_test_code(message: types.Message, state: FSMContext):
    await state.update_data(test_code=message.text.strip())
    await message.answer("To'g'ri javoblarni kiriting (masalan: `abcd...` yoki `1a2b3c...`):")
    await state.set_state(AdminState.waiting_for_answers)

@dp.message(AdminState.waiting_for_answers)
async def add_test_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_code = data['test_code']
    clean_answers = extract_answers(message.text)
    
    if not clean_answers:
        await message.answer("⚠️ **Kalitlar kiritilmadi!** Iltimos, to'g'ri kalitlarni kiriting (masalan: `abcd...`):", parse_mode="Markdown")
        return

    lessons = load_json(LESSONS_FILE)
    lessons[test_code] = clean_answers
    save_json(LESSONS_FILE, lessons)
    
    await message.answer(f"✅ TEST {test_code} saqlandi! Savollar soni: **{len(clean_answers)} ta**", reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "✏️ Testni tahrirlash")
async def edit_test_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    keyboard = get_tests_inline_keyboard(is_admin=True)
    if not keyboard.inline_keyboard:
        await message.answer("Tahrirlash uchun hech qanday test mavjud emas.")
        return
    
    await state.set_state(AdminState.waiting_for_edit_code)
    await message.answer("✏️ Qaysi testning kalitlarini o'zgartirmoqchisiz?", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("select_test_"))
async def process_test_select(callback: types.CallbackQuery, state: FSMContext):
    test_code = callback.data.split("select_test_")[1]
    current_state = await state.get_state()
    
    if current_state == AdminState.waiting_for_edit_code:
        await state.update_data(edit_test_code=test_code)
        await callback.message.answer(f"✏️ TEST {test_code} uchun yangi to'g'ri javoblarni kiriting:")
        await state.set_state(AdminState.waiting_for_new_answers)
    else:
        await state.update_data(user_test_code=test_code)
        await callback.message.answer(
            f"👇 **TEST {test_code} tanlandi.**\n\n"
            f"Javoblaringizni bir qatorda yuboring:\n"
            f"👉 Masalan: `abcd...` yoki `1a2b3c...`",
            parse_mode="Markdown"
        )
        await state.set_state(TestState.waiting_for_user_answers)
        
    await callback.answer()

@dp.message(AdminState.waiting_for_new_answers)
async def save_new_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_code = data['edit_test_code']
    clean_answers = extract_answers(message.text)
    
    if not clean_answers:
        await message.answer("⚠️ **Yangi kalitlar kiritilmadi!** Qaytadan kiriting:", parse_mode="Markdown")
        return

    lessons = load_json(LESSONS_FILE)
    lessons[test_code] = clean_answers
    save_json(LESSONS_FILE, lessons)
    
    await message.answer(f"✅ TEST {test_code} kalitlari yangilandi! Savollar soni: **{len(clean_answers)} ta**", reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await state.clear()

# --- TEST YUBORISH VA JAVOBLARNI TEKSHIRISH ---
@dp.message(F.text == "📝 Test yuborish")
async def user_start_test(message: types.Message, state: FSMContext):
    keyboard = get_tests_inline_keyboard(user_id=message.from_user.id)
    if not keyboard.inline_keyboard:
        await message.answer("🎉 Siz barcha faol testlarni topshirib bo'lgansiz!")
        return
    await message.answer("👇 Topshirmoqchi bo'lgan testni tanlang:", reply_markup=keyboard)

@dp.message(TestState.waiting_for_user_answers)
async def check_user_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_code = data['user_test_code']
    
    user_ans = extract_answers(message.text)
    lessons = load_json(LESSONS_FILE)
    correct_ans = lessons.get(test_code, "")
    
    if not user_ans:
        await message.answer("⚠️ **Javoblar aniqlanmadi!** Iltimos, javoblarni to'g'ri shaklda yuboring.\n\nMasalan: `1a2b3c...` yoki `abcd...`", parse_mode="Markdown")
        return
    
    if len(user_ans) != len(correct_ans):
        await message.answer(
            f"⚠️ **Javoblar soni mos kelmadi!**\n\n"
            f"Ushbu testda **{len(correct_ans)} ta** savol bor, siz esa **{len(user_ans)} ta** javob yubordingiz.\n"
            f"Iltimos, qaytadan tekshirib yuboring.",
            parse_mode="Markdown"
        )
        return

    score = sum(1 for u, c in zip(user_ans, correct_ans) if u == c)
    total = len(correct_ans)
    percentage = round((score / total) * 100, 1) if total > 0 else 0
    
    total_coins = add_user_coins(message.from_user.id, score)
    
    results = load_json(RESULTS_FILE)
    u_id = str(message.from_user.id)
    if u_id not in results:
        results[u_id] = []
    results[u_id].append({
        "test_code": test_code,
        "score": score,
        "total": total,
        "percentage": percentage
    })
    save_json(RESULTS_FILE, results)
    
    await message.answer(
        f"🎯 **Test natijasi:**\n\n"
        f"📚 TEST {test_code}\n"
        f"✅ To'g'ri javoblar: {score}/{total}\n"
        f"📈 Foiz: {percentage}%\n\n"
        f"🎉 **+{score} ta tanga** ishlandingiz!\n"
        f"🪙 Jami tangalaringiz: **{total_coins} ta**",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.clear()

# -------------------------------------------------------------
# 5. RENDER WEB SERVER VA MAIN
# -------------------------------------------------------------
async def handle_health_check(request):
    return web.Response(text="Bot faol ishlamoqda!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
