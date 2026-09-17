import asyncio
import json
import os
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

BOT_TOKEN = "7074848184:AAEbKHXDuYofwtPeCZ5Tc9YHE8udULvsB5A"  # BotFather tokeningizni kiriting
ADMIN_ID = 1763787601  # Telegram ID-ingizni kiriting

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- FAYLLAR MANTIQI (JSON) ---
LESSONS_FILE = "lessons.json"
RESULTS_FILE = "results.json"


def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default
    return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


LESSONS_INFO = load_json(LESSONS_FILE, {
    "TEST 1": {"keys": {"1": "a", "2": "b", "3": "c", "4": "d", "5": "a"}}
})
STUDENT_RESULTS = load_json(RESULTS_FILE, [])


# --- HOLATLAR (FSM) ---
class QuizForm(StatesGroup):
    waiting_for_info = State()
    waiting_for_answers = State()
    waiting_for_new_test_name = State()
    waiting_for_new_test_keys = State()
    waiting_for_edit_keys = State()


# --- KLAVIATURALAR ---
def get_main_keyboard(user_id):
    kb = [
        [KeyboardButton(text="📝 Test yuborish"), KeyboardButton(text="📊 Natijalarim")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="🏆 Reyting")],
        [KeyboardButton(text="🗓 Davomat"), KeyboardButton(text="🪙 Tangalarim")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="👨‍🏫 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_admin_keyboard():
    kb = [
        [KeyboardButton(text="➕ Yangi test qo'shish"), KeyboardButton(text="✏️ Testni tahrirlash")],
        [KeyboardButton(text="📋 Barcha natijalarni ko'rish")],
        [KeyboardButton(text="⬅️ Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_tests_inline_keyboard(action="select_test"):
    buttons = []
    for test_name, data in LESSONS_INFO.items():
        q_count = len(data["keys"])
        buttons.append([InlineKeyboardButton(
            text=f"📚 {test_name} ({q_count} ta savol)",
            callback_data=f"{action}:{test_name}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- START VA BEKOR QILISH ---
@dp.message(Command("cancel"))
@dp.message(F.text == "⬅️ Bosh menyu")
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 **Bosh menyu**", reply_markup=get_main_keyboard(message.from_user.id),
                         parse_mode="Markdown")


@dp.message(CommandStart())
@dp.message(F.text == "👤 Profil")
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "👤 **Familiya va ismingizni kiriting:**\n*(Masalan: Mamadiyorov Yusuf)*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(QuizForm.waiting_for_info)


# PROFILNI TEKSHIRISH (FAMILIYA ISM)
@dp.message(QuizForm.waiting_for_info)
async def process_info(message: types.Message, state: FSMContext):
    text = message.text.strip()
    words = text.split()

    if len(words) < 2 or not all(w.isalpha() for w in words):
        await message.answer("❌ **Familiya ismingizni to'g'ri kiriting!**\n*(Masalan: Mamadiyorov Yusuf)*",
                             parse_mode="Markdown")
        return

    user_name = f"{words[0].capitalize()} {words[1].capitalize()}"
    await state.update_data(user_info=user_name)
    await message.answer(
        f"✅ **Ma'lumotlar saqlandi:** {user_name}\n\nKerakli bo'limni tanlang:",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(None)


# --- ADMIN PANEL ---
@dp.message(F.text == "👨‍🏫 Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⚠️ Siz admin emassiz!")
        return
    await message.answer("👨‍🏫 **Admin Panelga xush kelibsiz!**", reply_markup=get_admin_keyboard(),
                         parse_mode="Markdown")


@dp.message(F.text == "📋 Barcha natijalarni ko'rish")
async def view_all_results(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not STUDENT_RESULTS:
        await message.answer("📭 Hali hech kim test topshirmadi.")
        return

    text = "📊 **O'quvchilar Natijalari Ro'yxati:**\n\n"
    for idx, r in enumerate(reversed(STUDENT_RESULTS), 1):
        time_str = r.get("date", "Noma'lum vaqt")
        text += (
            f"{idx}. 👤 **{r['user']}**\n"
            f"   📘 Test: `{r['test']}` | 📊 Ball: **{r['score']}%** ({r['correct']}/{r['total']})\n"
            f"   🕒 Vaqt: `{time_str}`\n"
            f"   -------------------------------\n"
        )
        if len(text) > 3500:
            await message.answer(text, parse_mode="Markdown")
            text = ""
    if text:
        await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "➕ Yangi test qo'shish")
async def add_test_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("✏️ **Yangi test nomini kiriting** (Masalan: `TEST 3`):", reply_markup=ReplyKeyboardRemove(),
                         parse_mode="Markdown")
    await state.set_state(QuizForm.waiting_for_new_test_name)


@dp.message(QuizForm.waiting_for_new_test_name)
async def process_new_test_name(message: types.Message, state: FSMContext):
    test_name = message.text.strip().upper()
    await state.update_data(new_test_name=test_name)
    await message.answer(f"🗝 **{test_name}** uchun to'g'ri kalitlarni kiriting:\n\nMasalan: `1a2b3c4d5a`",
                         parse_mode="Markdown")
    await state.set_state(QuizForm.waiting_for_new_test_keys)


@dp.message(QuizForm.waiting_for_new_test_keys)
async def process_new_test_keys(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_name = data.get("new_test_name")
    raw_keys = message.text.strip().lower()

    parsed_keys = dict(re.findall(r'(\d+)\s*([a-z])', raw_keys))
    if not parsed_keys:
        await message.answer("❌ **Kalitlar noto'g'ri kiritildi!**\nIltimos, qayta kiriting (Masalan: `1a2b3c4d`):",
                             parse_mode="Markdown")
        return

    LESSONS_INFO[test_name] = {"keys": parsed_keys}
    save_json(LESSONS_FILE, LESSONS_INFO)

    await message.answer(f"✅ **{test_name}** saqlandi!\n❓ Savollar soni: **{len(parsed_keys)} ta**",
                         reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await state.set_state(None)


@dp.message(F.text == "✏️ Testni tahrirlash")
async def edit_test_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not LESSONS_INFO:
        await message.answer("📭 Tahrirlash uchun testlar yo'q.")
        return
    await message.answer("✏️ **Qaysi testning kalitlarini o'zgartirmoqchisiz?**",
                         reply_markup=get_tests_inline_keyboard("edit_test"), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("edit_test:"))
async def process_test_edit_select(callback: CallbackQuery, state: FSMContext):
    test_name = callback.data.split(":")[1]
    await state.update_data(editing_test=test_name)

    curr_keys = LESSONS_INFO[test_name]["keys"]
    keys_str = "".join([f"{k}{v}" for k, v in curr_keys.items()])

    await callback.message.edit_text(
        f"🛠 **{test_name} ni tahrirlash**\n\n"
        f"📌 Hozirgi kalitlar: `{keys_str}`\n\n"
        f"✍️ Yangi kalitlarni yuboring (Masalan: `1a2b3c4d...`):",
        parse_mode="Markdown"
    )
    await state.set_state(QuizForm.waiting_for_edit_keys)
    await callback.answer()


@dp.message(QuizForm.waiting_for_edit_keys)
async def process_edit_keys_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_name = data.get("editing_test")
    raw_keys = message.text.strip().lower()

    parsed_keys = dict(re.findall(r'(\d+)\s*([a-z])', raw_keys))
    if not parsed_keys:
        await message.answer("❌ Noto'g'ri format. Qayta kiriting (Masalan: `1a2b3c`):")
        return

    LESSONS_INFO[test_name]["keys"] = parsed_keys
    save_json(LESSONS_FILE, LESSONS_INFO)

    await message.answer(
        f"🔄 **{test_name}** kalitlari muvaffaqiyatli yangilandi!\n"
        f"❓ Yangi savollar soni: **{len(parsed_keys)} ta**",
        reply_markup=get_admin_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(None)


# --- TEST TOPSHIRISH ---
@dp.message(F.text == "📝 Test yuborish")
async def choose_test(message: types.Message):
    if not LESSONS_INFO:
        await message.answer("📭 Hozircha faol testlar yo'q.")
        return
    await message.answer("👇 **Topshirmoqchi bo'lgan testni tanlang:**",
                         reply_markup=get_tests_inline_keyboard("select_test"), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("select_test:"))
async def process_test_selection(callback: CallbackQuery, state: FSMContext):
    test_name = callback.data.split(":")[1]
    if test_name not in LESSONS_INFO:
        await callback.answer("❌ Bu test mavjud emas!", show_alert=True)
        return

    data = await state.get_data()
    user_info = data.get("user_info", "Noma'lum o'quvchi")

    await state.update_data(current_test=test_name)
    q_count = len(LESSONS_INFO[test_name]["keys"])

    await callback.message.edit_text(
        f"📚 **Test:** {test_name}\n"
        f"❓ **Savollar soni:** {q_count} ta\n"
        f"👤 **O'quvchi:** {user_info}\n\n"
        f"📝 **Javoblaringizni yuboring:**\n*(Masalan: `1a2b3c4d...`)*\n\n"
        f"❌ Bekor qilish: /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(QuizForm.waiting_for_answers)
    await callback.answer()


# --- JAVOBLARNI TEKSHIRISH VA BARCHA XATOLIKLAR NAZORATI ---
@dp.message(QuizForm.waiting_for_answers)
async def process_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_info = data.get("user_info", "Noma'lum")
    test_name = data.get("current_test")

    if not test_name or test_name not in LESSONS_INFO:
        await message.answer("⚠️ Test topilmadi. Qaytadan tanlang.",
                             reply_markup=get_main_keyboard(message.from_user.id))
        await state.clear()
        return

    keys = LESSONS_INFO[test_name]["keys"]
    total_q = len(keys)
    raw_text = message.text.strip().lower()

    raw_matches = re.findall(r'(\d+)\s*([a-z])', raw_text)

    if not raw_matches:
        await message.answer(
            "⚠️ **Test formatini yozishda xatolik ketgan!**\nJavoblaringizni `1a2b3c` formatida qayta kiriting.",
            parse_mode="Markdown")
        return

    # 1. Takroriy savollar nazorati (masalan: 2 marta 4-savolni yozsa)
    q_numbers = [m[0] for m in raw_matches]
    if len(q_numbers) != len(set(q_numbers)):
        await message.answer("⚠️ **Test formatini yozishda xatolik ketgan!**\n*(Bir savolga 2 marta javob yozilgan)*",
                             parse_mode="Markdown")
        return

    # 2. Savollar soni oshib ketgan bo'lsa
    if len(raw_matches) > total_q:
        await message.answer(
            f"⚠️ **Testlar soni oshib ketdi!**\n*(Ushbu testda {total_q} ta savol bor, siz {len(raw_matches)} ta javob yozdingiz)*",
            parse_mode="Markdown")
        return

    # 3. Faqat a, b, c, d, e variantlariga ruxsat
    allowed_options = {'a', 'b', 'c', 'd', 'e'}
    invalid_answers = [ans for _, ans in raw_matches if ans not in allowed_options]
    if invalid_answers:
        await message.answer(
            "⚠️ **Test formatini yozishda xatolik ketgan!**\n*(Testda faqat a, b, c, d, e javob variantlari mavjud)*",
            parse_mode="Markdown")
        return

    parsed_answers = dict(raw_matches)
    correct_count = 0
    details = []

    for q_num, correct_ans in keys.items():
        user_ans = parsed_answers.get(str(q_num), "-")
        if user_ans.lower() == str(correct_ans).lower():
            correct_count += 1
            details.append(f"  {q_num}-savol: ✅")
        else:
            details.append(f"  {q_num}-savol: ❌ (Siz: `{user_ans}`, To'g'ri: `{correct_ans}`)")

    score = int((correct_count / total_q) * 100) if total_q > 0 else 0
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    res = {
        "user": user_info,
        "test": test_name,
        "score": score,
        "correct": correct_count,
        "total": total_q,
        "date": now_time
    }
    STUDENT_RESULTS.append(res)
    save_json(RESULTS_FILE, STUDENT_RESULTS)

    report = (
            f"🎉 **Vazifa qabul qilindi!**\n\n"
            f"👤 **O'quvchi:** {user_info}\n"
            f"📘 **Test:** {test_name}\n"
            f"📊 **Natija:** {correct_count}/{total_q} ({score}%)\n"
            f"🕒 **Vaqt:** {now_time}\n\n"
            f"🔍 **Batafsil tahlil:**\n" + "\n".join(details)
    )

    await message.answer(report, reply_markup=get_main_keyboard(message.from_user.id), parse_mode="Markdown")
    await state.clear()


@dp.message(F.text == "📊 Natijalarim")
async def my_results(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_info = data.get("user_info")

    if not user_info:
        await message.answer("⚠️ Avval profil bo'limida familiya va ismingizni kiriting!")
        return

    my_res = [r for r in STUDENT_RESULTS if r["user"] == user_info]
    if not my_res:
        await message.answer("📭 Siz hali birorta ham test topshirmagansiz.")
        return

    text = f"📊 **{user_info}ning natijalari:**\n\n"
    for r in my_res:
        text += f"📘 **{r['test']}**: {r['score']}% ({r['correct']}/{r['total']}) — 🕒 `{r.get('date', '')}`\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text.in_({"🗓 Davomat", "🏆 Reyting", "🪙 Tangalarim"}))
async def coming_soon(message: types.Message):
    await message.answer(f"⏳ **{message.text}** bo'limi tez orada ishga tushadi!", parse_mode="Markdown")


# --- ISHGA TUSHIRISH ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())