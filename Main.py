import json
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import asyncio

API_TOKEN = "API TOKEN"
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ToDoStates(StatesGroup):
    adding_title = State()
    adding_description = State()
    editing_task = State()
    changing_status = State()
    deleting_task = State()
    setting_reminder = State()

STATUS_OPTIONS = {
    "not_started": "Не начата",
    "in_progress": "В процессе",
    "completed": "Выполнена"
}

DATA_FILE = "tasks.json"
to_do_lists = {}
user_to_list = {}

async def reminder_check():
    while True:
        now = datetime.now()
        next_check_time = None

        for list_id, data in to_do_lists.items():
            for task in data.get("tasks", []):
                if "reminder_time" in task and task["reminder_time"]:
                    reminder_time = datetime.strptime(task["reminder_time"], "%Y-%m-%d %H:%M:%S")
                    if now >= reminder_time and not task.get("reminded", False):
                        task["reminded"] = True
                        for user_id in data["users"]:
                            await bot.send_message(user_id, f"⏰ Напоминание: {task['task']}")
                    elif not task.get("reminded", False) and (not next_check_time or reminder_time < next_check_time):
                        next_check_time = reminder_time

        save_tasks()
        sleep_time = (next_check_time - datetime.now()).total_seconds() if next_check_time else 60
        await asyncio.sleep(max(sleep_time, 1))  # Динамическая пауза

def load_tasks():
    global to_do_lists, user_to_list
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            to_do_lists = data.get("to_do_lists", {})
            user_to_list = data.get("user_to_list", {})
    except FileNotFoundError:
        to_do_lists = {}
        user_to_list = {}

def save_tasks():
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump({
            "to_do_lists": to_do_lists,
            "user_to_list": user_to_list
        }, file, indent=4, ensure_ascii=False)

def create_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить")],
            [KeyboardButton(text="📋 Список")],
            [KeyboardButton(text="✅ Выполненные")]
        ],
        resize_keyboard=True
    )

def create_task_keyboard(list_id, task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏ Редактировать", callback_data=f"edit_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="⏰ Установить напоминание", callback_data=f"remind_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="🔄 Изменить статус", callback_data=f"status_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_task_{list_id}_{task_id}")]
    ])

def create_status_keyboard(list_id, task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Не начата", callback_data=f"set_status_{list_id}_{task_id}_not_started")],
        [InlineKeyboardButton(text="В процессе", callback_data=f"set_status_{list_id}_{task_id}_in_progress")],
        [InlineKeyboardButton(text="Выполнена", callback_data=f"done_{list_id}_{task_id}")]
    ], resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    if user_id not in user_to_list:
        list_id = str(uuid.uuid4())
        to_do_lists[list_id] = {"tasks": [], "completed": [], "users": [user_id]}
        user_to_list[user_id] = list_id
        save_tasks()
    await message.answer("Привет! Я бот для управления задачами. Выберите действие из меню:", reply_markup=create_main_menu())


@dp.message(lambda msg: msg.text == "➕ Добавить")
async def add_task(message: Message, state: FSMContext):
    await message.answer("Введите название задачи:")
    await state.set_state(ToDoStates.adding_title)


@dp.message(ToDoStates.adding_title)
async def process_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Теперь введите описание задачи (или нажмите /skip чтобы пропустить):")
    await state.set_state(ToDoStates.adding_description)


@dp.message(ToDoStates.adding_description)
async def process_task_description(message: Message, state: FSMContext):
    user_data = await state.get_data()
    title = user_data.get('title')
    description = message.text.strip() if message.text != "/skip" else ""

    user_id = str(message.from_user.id)
    list_id = user_to_list.get(user_id)

    task = {
        "task": title,
        "description": description,  # Добавляем описание
        "status": STATUS_OPTIONS["not_started"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reminder_time": None,
        "reminded": False
    }

    to_do_lists[list_id]["tasks"].append(task)
    save_tasks()
    await message.answer(f"✅ Задача добавлена: {title}", reply_markup=create_main_menu())
    await state.clear()

@dp.message(lambda msg: msg.text == "📋 Список")
async def list_tasks(message: Message):
    user_id = str(message.from_user.id)
    list_id = user_to_list.get(user_id)
    if not to_do_lists[list_id]["tasks"]:
        await message.answer("📭 Список пуст или не найден. Добавьте новую задачу.", reply_markup=create_main_menu())
        return

    tasks = to_do_lists[list_id].get("tasks", [])
    for idx, task in enumerate(tasks):
        task_text = f"📌 {task['task']}\nСтатус: {task['status']}"

        if task["reminder_time"]:
            task_text += f"\nНапоминание: {task['reminder_time']}"

        if task["reminded"]:
            task_text += " ✅"

        if task['description']:
            task_text += f"\nОписание: {task['description']}"

        await message.answer(
            task_text,
            reply_markup=create_task_keyboard(list_id, idx)
        )

@dp.callback_query(lambda call: call.data.startswith("edit_"))
async def edit_task(callback: types.CallbackQuery, state: FSMContext):
    _, list_id, task_id = callback.data.split("_")

    await state.set_state(ToDoStates.editing_task)

    await state.update_data(list_id=list_id, task_id=int(task_id))

    await callback.message.answer("Введите новый текст задачи:")

@dp.message(ToDoStates.editing_task)
async def process_edit_task(message: Message, state: FSMContext):
    data = await state.get_data()
    list_id = data.get("list_id")
    task_id = data.get("task_id")
    new_task_text = message.text.strip()

    if list_id not in to_do_lists:
        await message.answer("❌ Список задач не найден. Пожалуйста, перезапустите бота командой /start.", reply_markup=create_main_menu())
        await state.clear()
        return

    tasks = to_do_lists[list_id].get("tasks", [])
    if 0 <= task_id < len(tasks):
        to_do_lists[list_id]["tasks"][task_id]["task"] = new_task_text
        save_tasks()

        await message.answer("✅ Задача обновлена.", reply_markup=create_main_menu())
    else:
        await message.answer("❌ Задача не найдена. Попробуйте снова.", reply_markup=create_main_menu())
    await state.clear()

@dp.callback_query(lambda call: call.data.startswith("remind_"))
async def set_reminder(callback_query: types.CallbackQuery, state: FSMContext):
    _, list_id, task_id = callback_query.data.split("_")

    await state.update_data(list_id=list_id, task_id=int(task_id))

    await callback_query.message.answer("Введите время для напоминания в формате `DD-MM-YYYY HH:MM`:")

    await state.set_state(ToDoStates.setting_reminder)

@dp.message(ToDoStates.setting_reminder)
async def process_reminder_time(message: Message, state: FSMContext):
    user_data = await state.get_data()
    list_id = user_data.get("list_id")
    task_id = user_data.get("task_id")

    try:
        reminder_time = datetime.strptime(message.text.strip(), "%d-%m-%Y %H:%M")
    except ValueError:
        await message.answer("❌ Некорректный формат времени. Попробуйте снова:")
        return

    task = to_do_lists[list_id]["tasks"][task_id]
    task["reminder_time"] = reminder_time.strftime("%Y-%m-%d %H:%M:%S")
    task["reminded"] = False
    save_tasks()

    await message.answer(f"✅ Напоминание для задачи \"{task['task']}\" установлено на {reminder_time}.", reply_markup=create_main_menu())
    await state.clear()

@dp.callback_query(lambda call: call.data.startswith("status_"))
async def change_status(callback: types.CallbackQuery, state: FSMContext):
    _, list_id, task_id = callback.data.split("_")
    task_id = int(task_id)

    if list_id in to_do_lists:
        tasks = to_do_lists[list_id].get("tasks", [])
        if 0 <= task_id < len(tasks):
            await state.set_state(ToDoStates.changing_status)

            await state.update_data(list_id=list_id, task_id=task_id)

            await callback.message.answer("Выберите новый статус задачи:", reply_markup=create_status_keyboard(list_id, task_id))
        else:
            await callback.message.answer("❌ Задача не найдена.")
    else:
        await callback.message.answer("❌ Список задач не найден.")

@dp.callback_query(lambda call: call.data.startswith("set_status_"))
async def set_status(callback: types.CallbackQuery):
    _, _, list_id, task_id, status_key = callback.data.split("_", 4)
    task_id = int(task_id)

    if list_id in to_do_lists and status_key in STATUS_OPTIONS:
        tasks = to_do_lists[list_id].get("tasks", [])
        if 0 <= task_id < len(tasks):
            to_do_lists[list_id]["tasks"][task_id]["status"] = STATUS_OPTIONS[status_key]
            save_tasks()

            await callback.message.edit_text(
                f"📌 {to_do_lists[list_id]['tasks'][task_id]['task']}\nСтатус: {STATUS_OPTIONS[status_key]}")
        else:
            await callback.message.answer("❌ Задача не найдена.")
    else:
        await callback.message.answer("❌ Некорректный статус.")

@dp.callback_query(lambda call: call.data.startswith("done_"))
async def mark_done(callback: types.CallbackQuery):
    _, list_id, task_id = callback.data.split("_")
    task_id = int(task_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data=f"confirm_done_{list_id}_{task_id}"),
         InlineKeyboardButton(text="Нет", callback_data=f"cancel_done_{list_id}_{task_id}")]
    ])
    await callback.message.answer("Вы уверены, что хотите завершить эту задачу?", reply_markup=keyboard)


@dp.callback_query(lambda call: call.data.startswith("confirm_done_"))
async def process_confirm_done(callback: types.CallbackQuery):
    _, _, list_id, task_id = callback.data.split("_")
    task_id = int(task_id)

    if list_id in to_do_lists:
        tasks = to_do_lists[list_id].get("tasks", [])
        if 0 <= task_id < len(tasks):
            task = tasks.pop(task_id)
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task["status"] = STATUS_OPTIONS["completed"]
            to_do_lists[list_id]["completed"].append(task)
            save_tasks()

            await callback.message.edit_text(f"✅ Задача завершена: {task['task']}")
        else:
            await callback.answer("❌ Задача не найдена.")
    else:
        await callback.answer("❌ Список задач не найден.")


@dp.callback_query(lambda call: call.data.startswith("cancel_done_"))
async def process_cancel_done(callback: types.CallbackQuery):
    await callback.message.edit_text("Завершение задачи отменено.")


@dp.message(lambda msg: msg.text == "✅ Выполненные")
async def show_completed(message: Message):
    user_id = str(message.from_user.id)
    list_id = user_to_list.get(user_id)
    if not list_id or list_id not in to_do_lists:
        await message.answer("📭 Нет выполненных задач или список задач не найден.", reply_markup=create_main_menu())
        return

    completed_tasks = to_do_lists[list_id].get("completed", [])

    if not completed_tasks:
        await message.answer("📭 В этом списке нет выполненных задач.")
        return

    for idx, task in enumerate(completed_tasks):
        task_text = f"✅ {idx + 1}. {task['task']}"

        if task['description']:
            task_text += f"\nОписание: {task['description']}"

        task_text += f"\n🕒 Завершено: {task['completed_at']}"

        await message.answer(task_text)


@dp.callback_query(lambda call: call.data.startswith("delete_task_"))
async def confirm_delete_task(callback: types.CallbackQuery):
    _, _, list_id, task_id = callback.data.split("_")
    task_id = int(task_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_{list_id}_{task_id}"),
         InlineKeyboardButton(text="❌ Нет", callback_data="cancel_delete")]
    ])
    await callback.message.answer("Вы уверены, что хотите удалить эту задачу?", reply_markup=keyboard)

@dp.callback_query(lambda call: call.data.startswith("confirm_delete_"))
async def process_delete_task(callback: types.CallbackQuery):
    _, _, list_id, task_id = callback.data.split("_")
    task_id = int(task_id)
    if list_id in to_do_lists:
        tasks = to_do_lists[list_id].get("tasks", [])
        if 0 <= task_id < len(tasks):
            deleted_task = tasks.pop(task_id)
            save_tasks()
            await callback.message.edit_text(f"❌ Задача удалена: {deleted_task['task']}")
        else:
            await callback.message.answer("❌ Задача не найдена.")
    else:
        await callback.message.answer("❌ Список задач не найден.")

@dp.callback_query(lambda call: call.data == "cancel_delete")
async def cancel_delete_task(callback: types.CallbackQuery):
    await callback.message.edit_text("Удаление отменено.")

load_tasks()

async def main():
    asyncio.create_task(reminder_check())  # Запускаем проверку напоминаний
    try:
        await dp.start_polling(bot)
    finally:
        save_tasks()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())