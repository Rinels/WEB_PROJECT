import sqlite3
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import asyncio

API_TOKEN = "API_KEY"
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def init_db():
    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        list_id TEXT
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS task_lists (
        list_id TEXT PRIMARY KEY
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_id TEXT,
        task TEXT,
        description TEXT,
        status TEXT,
        created_at TEXT,
        reminder_time TEXT,
        reminded INTEGER DEFAULT 0,
        completed_at TEXT,
        FOREIGN KEY (list_id) REFERENCES task_lists(list_id)
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS list_members (
        list_id TEXT,
        user_id TEXT,
        PRIMARY KEY (list_id, user_id),
        FOREIGN KEY (list_id) REFERENCES task_lists(list_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )''')

    conn.commit()
    conn.close()


init_db()


class ToDoStates(StatesGroup):
    adding_title = State()
    adding_description = State()
    editing_task = State()
    editing_description = State()
    changing_status = State()
    deleting_task = State()
    setting_reminder = State()


STATUS_OPTIONS = {
    "not_started": "Не начата",
    "in_progress": "В процессе",
    "completed": "Выполнена"
}


async def reminder_check():
    while True:
        now = datetime.now()
        next_check_time = None

        conn = sqlite3.connect('ToDo.db')
        cursor = conn.cursor()

        cursor.execute('''
        SELECT task_id, list_id, task, reminder_time, reminded 
        FROM tasks 
        WHERE reminder_time IS NOT NULL 
          AND reminded = 0
          AND status != ?
        ''', (STATUS_OPTIONS["completed"],))

        tasks = cursor.fetchall()

        for task_id, list_id, task_text, reminder_time_str, reminded in tasks:
            reminder_time = datetime.strptime(reminder_time_str, "%Y-%m-%d %H:%M:%S")

            if now >= reminder_time and not reminded:
                cursor.execute('''
                UPDATE tasks SET reminded = 1 WHERE task_id = ?
                ''', (task_id,))

                cursor.execute('''
                SELECT user_id FROM list_members WHERE list_id = ?
                ''', (list_id,))

                users = cursor.fetchall()

                for (user_id,) in users:
                    try:
                        await bot.send_message(user_id, f"⏰ Напоминание: {task_text}")
                    except Exception as e:
                        print(f"Ошибка при отправке напоминания: {e}")

            elif not reminded and (not next_check_time or reminder_time < next_check_time):
                next_check_time = reminder_time

        conn.commit()
        conn.close()

        sleep_time = (next_check_time - datetime.now()).total_seconds() if next_check_time else 60
        await asyncio.sleep(max(sleep_time, 1))


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
        [InlineKeyboardButton(text="✏ Редактировать", callback_data=f"edit_menu_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="⏰ Установить напоминание", callback_data=f"remind_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="🔄 Изменить статус", callback_data=f"status_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_task_{list_id}_{task_id}")]
    ])


def create_edit_menu_keyboard(list_id, task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Редактировать название", callback_data=f"edit_name_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="📝 Редактировать описание", callback_data=f"edit_desc_{list_id}_{task_id}")],
        [InlineKeyboardButton(text="↩ Назад", callback_data=f"back_{list_id}_{task_id}")]
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

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('SELECT list_id FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        list_id = str(uuid.uuid4())

        cursor.execute('INSERT INTO task_lists (list_id) VALUES (?)', (list_id,))
        cursor.execute('INSERT INTO users (user_id, list_id) VALUES (?, ?)', (user_id, list_id))
        cursor.execute('INSERT INTO list_members (list_id, user_id) VALUES (?, ?)', (list_id, user_id))

        conn.commit()

    conn.close()

    await message.answer("Привет! Я бот для управления задачами. Выберите действие из меню:",
                         reply_markup=create_main_menu())


@dp.message(lambda msg: msg.text == "➕ Добавить")
async def add_task(message: Message, state: FSMContext):
    await message.answer("Введите название задачи:")
    await state.set_state(ToDoStates.adding_title)


@dp.message(ToDoStates.adding_title)
async def process_task_title(message: Message, state: FSMContext):
    if message.text.strip() in ["➕ Добавить", "📋 Список", "✅ Выполненные"]:
        await message.answer(
            "Текст не может совпадать с текстом кнопки. Пожалуйста, введите другое название:")
        return

    await state.update_data(title=message.text.strip())
    await message.answer("Теперь введите описание задачи (или нажмите /skip чтобы пропустить):")
    await state.set_state(ToDoStates.adding_description)


@dp.message(ToDoStates.adding_description)
async def process_task_description(message: Message, state: FSMContext):
    if message.text.strip() in ["➕ Добавить", "📋 Список", "✅ Выполненные"]:
        await message.answer(
            "Текст не может совпадать с текстом кнопки. Пожалуйста, введите другое название:")
        return

    user_data = await state.get_data()
    title = user_data.get('title')
    description = message.text.strip() if message.text != "/skip" else ""

    user_id = str(message.from_user.id)

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('SELECT list_id FROM users WHERE user_id = ?', (user_id,))
    list_id = cursor.fetchone()[0]

    cursor.execute('''
    INSERT INTO tasks (list_id, task, description, status, created_at, reminder_time, reminded)
    VALUES (?, ?, ?, ?, ?, NULL, 0)
    ''', (list_id, title, description, STATUS_OPTIONS["not_started"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

    await message.answer(f"✅ Задача добавлена: {title}", reply_markup=create_main_menu())
    await state.clear()


@dp.message(lambda msg: msg.text == "📋 Список")
async def list_tasks(message: Message):
    user_id = str(message.from_user.id)

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('SELECT list_id FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await message.answer("📭 Список пуст или не найден. Добавьте новую задачу.", reply_markup=create_main_menu())
        conn.close()
        return

    list_id = user_data[0]

    cursor.execute('''
    SELECT task_id, task, description, status, reminder_time, reminded 
    FROM tasks 
    WHERE list_id = ? AND status != ? 
    ORDER BY 
        CASE WHEN status = ? THEN 0 ELSE 1 END,
        created_at
    ''', (list_id, STATUS_OPTIONS["completed"], STATUS_OPTIONS["in_progress"]))

    tasks = cursor.fetchall()

    if not tasks:
        await message.answer("📭 Список пуст. Добавьте новую задачу.", reply_markup=create_main_menu())
        conn.close()
        return

    for task in tasks:
        task_id, task_text, description, status, reminder_time, reminded = task

        message_text = f"📌 {task_text}\nСтатус: {status}"

        if reminder_time:
            message_text += f"\nНапоминание: {reminder_time}"
            if reminded:
                message_text += " ✅"

        if description:
            message_text += f"\nОписание: {description}"

        await message.answer(
            message_text,
            reply_markup=create_task_keyboard(list_id, task_id)
        )

    conn.close()


@dp.callback_query(lambda call: call.data.startswith("edit_menu_"))
async def edit_task_menu(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) == 4:
        _, _, list_id, task_id = parts
        await callback.message.answer("Выберите, что хотите изменить:",
                                      reply_markup=create_edit_menu_keyboard(list_id, task_id))


@dp.callback_query(lambda call: call.data.startswith("edit_name_"))
async def edit_task_name(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) == 4:
        _, _, list_id, task_id = parts
        await state.set_state(ToDoStates.editing_task)
        await state.update_data(list_id=list_id, task_id=task_id)
        await callback.message.answer("Введите новое название задачи:")


@dp.callback_query(lambda call: call.data.startswith("edit_desc_"))
async def edit_task_description(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) == 4:
        _, _, list_id, task_id = parts
        await state.set_state(ToDoStates.editing_description)
        await state.update_data(list_id=list_id, task_id=task_id)
        await callback.message.answer("Введите новое описание задачи (или /delete чтобы удалить описание):")


@dp.callback_query(lambda call: call.data.startswith("back_"))
async def back_to_task(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) == 3:
        _, list_id, task_id = parts

        conn = sqlite3.connect('ToDo.db')
        cursor = conn.cursor()

        cursor.execute('''
        SELECT task, description, status, reminder_time, reminded 
        FROM tasks 
        WHERE task_id = ? AND list_id = ?
        ''', (task_id, list_id))

        task = cursor.fetchone()
        conn.close()

        if task:
            task_text, description, status, reminder_time, reminded = task
            message_text = f"📌 {task_text}\nСтатус: {status}"

            if reminder_time:
                message_text += f"\nНапоминание: {reminder_time}"
                if reminded:
                    message_text += " ✅"

            if description:
                message_text += f"\nОписание: {description}"

            await callback.message.answer(
                message_text,
                reply_markup=create_task_keyboard(list_id, task_id)
            )
        else:
            await callback.answer("❌ Задача не найдена")


@dp.message(ToDoStates.editing_task)
async def process_edit_task(message: Message, state: FSMContext):
    data = await state.get_data()
    list_id = data.get("list_id")
    task_id = data.get("task_id")
    new_task_text = message.text.strip()

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('''
    UPDATE tasks 
    SET task = ? 
    WHERE task_id = ? AND list_id = ?
    ''', (new_task_text, task_id, list_id))

    conn.commit()
    conn.close()

    await message.answer("✅ Название задачи обновлено.", reply_markup=create_main_menu())
    await state.clear()


@dp.message(ToDoStates.editing_description)
async def process_edit_description(message: Message, state: FSMContext):
    data = await state.get_data()
    list_id = data.get("list_id")
    task_id = data.get("task_id")
    new_description = message.text.strip() if message.text != "/delete" else ""

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('''
    UPDATE tasks 
    SET description = ? 
    WHERE task_id = ? AND list_id = ?
    ''', (new_description, task_id, list_id))

    conn.commit()
    conn.close()

    await message.answer("✅ Описание задачи обновлено.", reply_markup=create_main_menu())
    await state.clear()


@dp.callback_query(lambda call: call.data.startswith("remind_"))
async def set_reminder(callback_query: types.CallbackQuery, state: FSMContext):
    _, list_id, task_id = callback_query.data.split("_")

    await state.update_data(list_id=list_id, task_id=task_id)
    await callback_query.message.answer("Введите время для напоминания в формате `DD-MM-YYYY HH:MM`:")
    await state.set_state(ToDoStates.setting_reminder)


@dp.message(ToDoStates.setting_reminder)
async def process_reminder_time(message: Message, state: FSMContext):
    user_data = await state.get_data()
    list_id = user_data.get("list_id")
    task_id = user_data.get("task_id")

    try:
        reminder_time = datetime.strptime(message.text.strip(), "%d-%m-%Y %H:%M")
        if reminder_time <= datetime.now():
            await message.answer("❌ Напоминание должно быть установлено на будущее время. Попробуйте снова:")
            return

        reminder_time_str = reminder_time.strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect('ToDo.db')
        cursor = conn.cursor()

        cursor.execute('SELECT task FROM tasks WHERE task_id = ?', (task_id,))
        task_text = cursor.fetchone()[0]

        cursor.execute('''
        UPDATE tasks 
        SET reminder_time = ?, reminded = 0 
        WHERE task_id = ? AND list_id = ?
        ''', (reminder_time_str, task_id, list_id))

        conn.commit()
        conn.close()

        formatted_time = reminder_time.strftime("%d.%m.%Y в %H:%M")
        await message.answer(
            f"✅ Напоминание для задачи \"{task_text}\" установлено на {formatted_time}.",
            reply_markup=create_main_menu()
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ Некорректный формат времени. Используйте формат ДД-ММ-ГГГГ ЧЧ:ММ\nПопробуйте снова:")


@dp.callback_query(lambda call: call.data.startswith("status_"))
async def change_status(callback: types.CallbackQuery, state: FSMContext):
    _, list_id, task_id = callback.data.split("_")

    await state.update_data(list_id=list_id, task_id=task_id)
    await callback.message.answer("Выберите новый статус задачи:",
                                  reply_markup=create_status_keyboard(list_id, task_id))
    await state.set_state(ToDoStates.changing_status)


@dp.callback_query(lambda call: call.data.startswith("set_status_"))
async def set_status(callback: types.CallbackQuery):
    _, _, list_id, task_id, status_key = callback.data.split("_", 4)

    if status_key in STATUS_OPTIONS:
        new_status = STATUS_OPTIONS[status_key]

        conn = sqlite3.connect('ToDo.db')
        cursor = conn.cursor()

        cursor.execute('''
        UPDATE tasks 
        SET status = ? 
        WHERE task_id = ? AND list_id = ?
        ''', (new_status, task_id, list_id))

        cursor.execute('''
        SELECT task, description, status, reminder_time, reminded 
        FROM tasks 
        WHERE task_id = ? AND list_id = ?
        ''', (task_id, list_id))

        task = cursor.fetchone()
        conn.commit()
        conn.close()

        if task:
            task_text, description, status, reminder_time, reminded = task
            message_text = f"📌 {task_text}\nСтатус: {status}"

            await callback.message.edit_text(message_text)
        else:
            await callback.message.answer("❌ Задача не найдена.")
    else:
        await callback.message.answer("❌ Некорректный статус.")


@dp.callback_query(lambda call: call.data.startswith("done_"))
async def mark_done(callback: types.CallbackQuery):
    _, list_id, task_id = callback.data.split("_")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data=f"confirm_done_{list_id}_{task_id}"),
         InlineKeyboardButton(text="Нет", callback_data=f"cancel_done_{list_id}_{task_id}")]
    ])
    await callback.message.answer("Вы уверены, что хотите завершить эту задачу?", reply_markup=keyboard)


@dp.callback_query(lambda call: call.data.startswith("confirm_done_"))
async def process_confirm_done(callback: types.CallbackQuery):
    _, _, list_id, task_id = callback.data.split("_")

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('''
    UPDATE tasks 
    SET status = ?, completed_at = ? 
    WHERE task_id = ? AND list_id = ?
    ''', (STATUS_OPTIONS["completed"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id, list_id))

    cursor.execute('SELECT task FROM tasks WHERE task_id = ?', (task_id,))
    task_text = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    await callback.message.edit_text(f"✅ Задача завершена: {task_text}")


@dp.callback_query(lambda call: call.data.startswith("cancel_done_"))
async def process_cancel_done(callback: types.CallbackQuery):
    await callback.message.edit_text("Завершение задачи отменено.")


@dp.message(lambda msg: msg.text == "✅ Выполненные")
async def show_completed(message: Message):
    user_id = str(message.from_user.id)

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('SELECT list_id FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await message.answer("📭 Нет выполненных задач или список задач не найден.", reply_markup=create_main_menu())
        conn.close()
        return

    list_id = user_data[0]

    cursor.execute('''
    SELECT task, description, completed_at 
    FROM tasks 
    WHERE list_id = ? AND status = ? 
    ORDER BY completed_at DESC
    ''', (list_id, STATUS_OPTIONS["completed"]))

    completed_tasks = cursor.fetchall()
    conn.close()

    if not completed_tasks:
        await message.answer("📭 В этом списке нет выполненных задач.")
        return

    for idx, task in enumerate(completed_tasks, 1):
        task_text, description, completed_at = task
        message_text = f"✅ {idx}. {task_text}"

        if description:
            message_text += f"\nОписание: {description}"

        message_text += f"\n🕒 Завершено: {completed_at}"

        await message.answer(message_text)


@dp.callback_query(lambda call: call.data.startswith("delete_task_"))
async def confirm_delete_task(callback: types.CallbackQuery):
    _, _, list_id, task_id = callback.data.split("_")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data=f"confirm_delete_{list_id}_{task_id}"),
         InlineKeyboardButton(text="Нет", callback_data="cancel_delete")]
    ])
    await callback.message.answer("Вы уверены, что хотите удалить эту задачу?", reply_markup=keyboard)


@dp.callback_query(lambda call: call.data.startswith("confirm_delete_"))
async def process_delete_task(callback: types.CallbackQuery):
    _, _, list_id, task_id = callback.data.split("_")

    conn = sqlite3.connect('ToDo.db')
    cursor = conn.cursor()

    cursor.execute('SELECT task FROM tasks WHERE task_id = ?', (task_id,))
    task_text = cursor.fetchone()[0]

    cursor.execute('DELETE FROM tasks WHERE task_id = ? AND list_id = ?', (task_id, list_id))

    conn.commit()
    conn.close()

    await callback.message.edit_text(f"❌ Задача удалена: {task_text}")


@dp.callback_query(lambda call: call.data == "cancel_delete")
async def cancel_delete_task(callback: types.CallbackQuery):
    await callback.message.edit_text("Удаление отменено.")


async def main():
    asyncio.create_task(reminder_check())
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())