import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Данные бота
TOKEN = "8523980313:AAHQEXsScQr-YP7-3C9kWsFfW5Jkb39B5os"
BOT_USERNAME = "aaa"
GROUP_CHAT_ID = -1003330565829  # ID группы (где будут тегаться все)
CHANNEL_CHAT_ID = -1003777568283  # ID канала (куда будут отправляться посты)

# ID администраторов (добавьте свои ID)
ADMIN_IDS = [1802596753]  # Добавьте сюда ID администраторов

# Хранилище для отслеживания нажатий
user_responses = {}  # {message_id: {user_id: user_info}}
scheduled_posts = []  # Список запланированных постов

# Инициализация бота и диспетчера с хранилищем состояний
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# Состояния для создания поста
class CreatePost(StatesGroup):
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_confirm = State()
    waiting_for_schedule = State()

# Проверка является ли пользователь админом
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# Главное меню админа
def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать пост")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📋 Список постов")],
            [KeyboardButton(text="⏰ Запланированные"), KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# Клавиатура подтверждения
def get_confirm_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Отправить сейчас"), KeyboardButton(text="⏰ Запланировать")],
            [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# Клавиатура для планирования
def get_schedule_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1 мин"), KeyboardButton(text="5 мин"), KeyboardButton(text="15 мин")],
            [KeyboardButton(text="30 мин"), KeyboardButton(text("1 час"), KeyboardButton(text="⏰ Ввести время"))],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# Функция для создания клавиатуры с кнопкой "Готово"
def create_ready_keyboard(message_id=None):
    if message_id:
        callback_data = f"post_ready_{message_id}"
    else:
        callback_data = "post_ready_new"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Готово", 
                    callback_data=callback_data
                )
            ]
        ]
    )
    return keyboard

# Функция для создания обновленной клавиатуры
def create_updated_keyboard(count, message_id):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Готово ({count})", 
                    callback_data=f"post_ready_{message_id}"
                )
            ]
        ]
    )
    return keyboard

# Функция для отправки поста в канал
async def send_post_to_channel(title: str, text: str, scheduled=False):
    try:
        # Формируем текст поста
        current_time = datetime.now().strftime("%H:%M:%S %d.%m.%Y")
        
        if scheduled:
            post_text = f"📅 Запланированный пост\n\n"
        else:
            post_text = ""
            
        post_text += f"📌 {title}\n\n"
        post_text += f"{text}\n\n"
        post_text += f"⏰ Время отправки: {current_time}"
        
        # Отправляем пост в канал БЕЗ клавиатуры сначала
        message = await bot.send_message(
            chat_id=CHANNEL_CHAT_ID,
            text=post_text
        )
        
        # Теперь добавляем клавиатуру с правильным message_id
        keyboard = create_ready_keyboard(message.message_id)
        await message.edit_reply_markup(reply_markup=keyboard)
        
        # Инициализируем хранилище для этого сообщения
        user_responses[message.message_id] = {}
        
        logger.info(f"Пост '{title}' отправлен в канал в {current_time}")
        return message.message_id
        
    except Exception as e:
        logger.error(f"Ошибка при отправке поста: {e}")
        return None

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if is_admin(message.from_user.id):
        await message.answer(
            "👋 Добро пожаловать в панель администратора!\n"
            "Выберите действие:",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "👋 Привет! Я бот для отправки постов в канал.\n"
            "Вы не являетесь администратором."
        )

# Обработчик команды /admin (альтернативный вход)
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if is_admin(message.from_user.id):
        await message.answer(
            "👋 Панель администратора\nВыберите действие:",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer("❌ У вас нет прав администратора!")

# Обработчик кнопки "Создать пост"
@dp.message(F.text == "📝 Создать пост")
async def create_post_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return
    
    await message.answer(
        "📝 Создание нового поста\n\n"
        "Введите заголовок поста:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CreatePost.waiting_for_title)

# Обработчик ввода заголовка
@dp.message(CreatePost.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("❌ Заголовок слишком длинный (макс. 100 символов). Введите снова:")
        return
    
    await state.update_data(title=message.text)
    await message.answer(
        "📝 Теперь введите текст поста:\n\n"
        "Вы можете использовать форматирование Markdown:\n"
        "*жирный*\n"
        "_курсив_\n"
        "`моноширинный`\n"
        "[ссылка](https://example.com)"
    )
    await state.set_state(CreatePost.waiting_for_text)

# Обработчик ввода текста
@dp.message(CreatePost.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    if len(message.text) > 4000:
        await message.answer("❌ Текст слишком длинный (макс. 4000 символов). Введите снова:")
        return
    
    await state.update_data(text=message.text)
    
    # Получаем данные
    data = await state.get_data()
    
    # Показываем предпросмотр
    preview_text = (
        "📋 Предпросмотр поста:\n\n"
        f"📌 Заголовок: {data['title']}\n\n"
        f"📝 Текст:\n{data['text']}\n\n"
        "Выберите действие:"
    )
    
    await message.answer(
        preview_text,
        reply_markup=get_confirm_keyboard()
    )
    await state.set_state(CreatePost.waiting_for_confirm)

# Обработчик подтверждения
@dp.message(CreatePost.waiting_for_confirm)
async def process_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text == "✅ Отправить сейчас":
        # Отправляем пост сразу
        post_id = await send_post_to_channel(data['title'], data['text'])
        if post_id:
            await message.answer(
                f"✅ Пост успешно отправлен в канал!\nID поста: {post_id}",
                reply_markup=get_admin_keyboard()
            )
        else:
            await message.answer(
                "❌ Ошибка при отправке поста!",
                reply_markup=get_admin_keyboard()
            )
        await state.clear()
        
    elif message.text == "⏰ Запланировать":
        # Переходим к планированию
        await message.answer(
            "⏰ Выберите время отправки поста:",
            reply_markup=get_schedule_keyboard()
        )
        await state.set_state(CreatePost.waiting_for_schedule)
        
    elif message.text == "✏️ Редактировать":
        # Возвращаемся к редактированию заголовка
        await message.answer(
            "Введите новый заголовок поста:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(CreatePost.waiting_for_title)
        
    elif message.text == "❌ Отменить":
        await message.answer(
            "❌ Создание поста отменено.",
            reply_markup=get_admin_keyboard()
        )
        await state.clear()
    else:
        await message.answer("Пожалуйста, выберите действие из клавиатуры:")

# Обработчик планирования
@dp.message(CreatePost.waiting_for_schedule)
async def process_schedule(message: Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text == "🔙 Назад":
        # Возвращаемся к подтверждению
        preview_text = (
            "📋 Предпросмотр поста:\n\n"
            f"📌 Заголовок: {data['title']}\n\n"
            f"📝 Текст:\n{data['text']}\n\n"
            "Выберите действие:"
        )
        await message.answer(
            preview_text,
            reply_markup=get_confirm_keyboard()
        )
        await state.set_state(CreatePost.waiting_for_confirm)
        return
    
    # Обработка выбора времени
    delay_seconds = 0
    
    if message.text == "1 мин":
        delay_seconds = 60
    elif message.text == "5 мин":
        delay_seconds = 300
    elif message.text == "15 мин":
        delay_seconds = 900
    elif message.text == "30 мин":
        delay_seconds = 1800
    elif message.text == "1 час":
        delay_seconds = 3600
    elif message.text == "⏰ Ввести время":
        await message.answer(
            "Введите время в минутах (например: 10 для 10 минут):",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    else:
        # Проверяем, введено ли число
        try:
            minutes = int(message.text)
            delay_seconds = minutes * 60
        except ValueError:
            await message.answer("Пожалуйста, введите число или выберите вариант из клавиатуры:")
            return
    
    # Сохраняем запланированный пост
    schedule_time = datetime.now().timestamp() + delay_seconds
    scheduled_posts.append({
        'title': data['title'],
        'text': data['text'],
        'schedule_time': schedule_time,
        'admin_id': message.from_user.id
    })
    
    schedule_time_str = datetime.fromtimestamp(schedule_time).strftime("%H:%M:%S %d.%m.%Y")
    
    await message.answer(
        f"✅ Пост запланирован на {schedule_time_str}\n"
        f"Заголовок: {data['title']}\n\n"
        "Пост будет отправлен автоматически.",
        reply_markup=get_admin_keyboard()
    )
    
    # Запускаем задачу для отправки
    asyncio.create_task(send_scheduled_post(data['title'], data['text'], delay_seconds, message.from_user.id))
    
    await state.clear()

# Функция для отправки запланированного поста
async def send_scheduled_post(title: str, text: str, delay: int, admin_id: int):
    await asyncio.sleep(delay)
    
    post_id = await send_post_to_channel(title, text, scheduled=True)
    
    if post_id:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"✅ Запланированный пост отправлен!\n"
                     f"Заголовок: {title}\n"
                     f"ID поста: {post_id}"
            )
        except:
            pass  # Не отправляем уведомление, если админ заблокировал бота

# Обработчик кнопки "Статистика"
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return
    
    total_responses = sum(len(users) for users in user_responses.values())
    active_posts = len(user_responses)
    scheduled_count = len(scheduled_posts)
    
    stats_text = (
        f"📊 Статистика бота:\n\n"
        f"📨 Активных постов: {active_posts}\n"
        f"👤 Всего отметок 'Готово': {total_responses}\n"
        f"⏰ Запланированных постов: {scheduled_count}\n"
        f"🕒 Текущее время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
    )
    
    await message.answer(stats_text)

# Обработчик кнопки "Список постов"
@dp.message(F.text == "📋 Список постов")
async def show_posts_list(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return
    
    if not user_responses:
        await message.answer("📭 Нет активных постов.")
        return
    
    posts_text = "📋 Активные посты:\n\n"
    
    for i, (message_id, users) in enumerate(user_responses.items(), 1):
        posts_text += f"{i}. ID: {message_id}\n"
        posts_text += f"   👤 Отметок: {len(users)}\n"
        
        # Показываем последних 3 пользователей
        if users:
            user_list = list(users.items())[-3:]  # Последние 3
            for user_id, user_info in user_list:
                mention = f"@{user_info['username']}" if user_info['username'] else user_info['name']
                posts_text += f"   • {mention}\n"
        
        posts_text += "\n"
    
    # Если текст слишком длинный
    if len(posts_text) > 4000:
        parts = [posts_text[i:i+4000] for i in range(0, len(posts_text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(posts_text)

# Обработчик кнопки "Запланированные"
@dp.message(F.text == "⏰ Запланированные")
async def show_scheduled_posts(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return
    
    if not scheduled_posts:
        await message.answer("📭 Нет запланированных постов.")
        return
    
    scheduled_text = "⏰ Запланированные посты:\n\n"
    
    for i, post in enumerate(scheduled_posts, 1):
        time_str = datetime.fromtimestamp(post['schedule_time']).strftime("%H:%M:%S %d.%m.%Y")
        time_left = post['schedule_time'] - datetime.now().timestamp()
        
        if time_left > 0:
            hours = int(time_left // 3600)
            minutes = int((time_left % 3600) // 60)
            
            scheduled_text += f"{i}. {post['title']}\n"
            scheduled_text += f"   ⏰ Время: {time_str}\n"
            scheduled_text += f"   🕒 Осталось: {hours}ч {minutes}мин\n\n"
    
    if len(scheduled_text) > 4000:
        parts = [scheduled_text[i:i+4000] for i in range(0, len(scheduled_text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(scheduled_text)

# Обработчик кнопки "Отмена"
@dp.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            "❌ Действие отменено.",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "Нет активных действий для отмены.",
            reply_markup=get_admin_keyboard()
        )

# Обработчик нажатия на кнопку "Готово" в постах
@dp.callback_query(lambda c: c.data.startswith("post_ready"))
async def process_ready_button(callback_query: CallbackQuery):
    try:
        # Получаем информацию о пользователе
        user_id = callback_query.from_user.id
        user_name = callback_query.from_user.full_name
        username = callback_query.from_user.username
        
        # Получаем ID сообщения в канале
        message_id = callback_query.message.message_id
        
        # Определяем message_id из callback_data
        callback_data = callback_query.data
        
        if callback_data == "post_ready_new":
            target_message_id = message_id
        else:
            try:
                target_message_id = int(callback_data.split("_")[2])
            except (IndexError, ValueError):
                target_message_id = message_id
        
        # Проверяем, нажимал ли уже этот пользователь
        if target_message_id in user_responses and user_id in user_responses[target_message_id]:
            users_count = len(user_responses[target_message_id])
            await callback_query.answer(
                text=f"Вы уже отметились! Всего отметилось: {users_count}",
                show_alert=False
            )
            return
        
        # Сохраняем информацию о пользователе
        if target_message_id not in user_responses:
            user_responses[target_message_id] = {}
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        user_responses[target_message_id][user_id] = {
            "name": user_name,
            "username": username,
            "timestamp": timestamp
        }
        
        # Отправляем уведомление в группу
        user_mention = f"@{username}" if username else f"{user_name}"
        try:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"👤 {user_mention} отметил, что готов!\n"
                     f"📅 Время: {timestamp}\n"
                     f"🆔 ID: {user_id}"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке в группу: {e}")
        
        # Обновляем пост в канале
        users_count = len(user_responses[target_message_id])
        current_text = callback_query.message.text
        
        # Убираем старый список пользователей
        if "👥 Отметили готовность:" in current_text:
            lines = current_text.split("\n")
            new_text_lines = []
            for line in lines:
                if "👥 Отметили готовность:" in line:
                    break
                new_text_lines.append(line)
            current_text = "\n".join(new_text_lines).strip()
        
        # Добавляем новый список
        users_list = "\n\n👥 Отметили готовность:\n"
        for uid, uinfo in user_responses[target_message_id].items():
            mention = f"@{uinfo['username']}" if uinfo['username'] else uinfo['name']
            users_list += f"• {mention} ({uinfo['timestamp']})\n"
        
        try:
            await callback_query.message.edit_text(
                text=current_text + users_list,
                reply_markup=create_updated_keyboard(users_count, target_message_id)
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании: {e}")
        
        await callback_query.answer(
            text=f"Спасибо, {user_name}! Вы отметились как готовый.",
            show_alert=False
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки: {e}")
        await callback_query.answer(
            text="Произошла ошибка.",
            show_alert=True
        )

# Функция для автоматической отправки постов каждую минуту (оставим как опцию)
async def auto_scheduled_posts():
    while True:
        # Здесь можно оставить автоматическую отправку, если нужно
        # await send_post_to_channel("Автоматический пост", "Как дела?")
        await asyncio.sleep(60)

# Основная функция запуска бота
async def main():
    logger.info("Бот запускается...")
    
    try:
        bot_info = await bot.get_me()
        logger.info(f"Бот @{bot_info.username} успешно запущен")
        
        # Запускаем авто-посты, если нужно
        # asyncio.create_task(auto_scheduled_posts())
        
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
