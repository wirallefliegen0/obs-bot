"""
Telegram Bot Module.
Handles sending notifications for new grades.
"""

import asyncio
from telegram import Bot
from telegram.error import TelegramError
import config


async def send_message_async(text: str) -> bool:
    
    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML"
        )
        return True
    except TelegramError as e:
        print(f"[!] Telegram error: {e}")
        return False


def send_message(text: str) -> bool:

    return asyncio.run(send_message_async(text))


def format_grade_message(grade: dict) -> str:
  
    course_code = grade.get("course_code", "N/A")
    course_name = grade.get("course_name", "N/A")
    grade_value = grade.get("grade", "N/A")
    status = grade.get("status", "")
    
    message = (
        "🎓 <b>Yeni Sınav Sonucu!</b>\n\n"
        f"📚 <b>Ders:</b> {course_code}\n"
        f"📖 <b>Ders Adı:</b> {course_name}\n"
        f"📊 <b>Not:</b> <code>{grade_value}</code>\n"
    )
    
    if status:
        message += f"📋 <b>Durum:</b> {status}\n"
    
    message += "\n✨ Tebrikler! Başarılar dilerim."
    
    return message


def send_grade_notification(grade: dict) -> bool:
   
    message = format_grade_message(grade)
    return send_message(message)


def send_multiple_grades_notification(grades: list[dict]) -> bool:

    if not grades:
        return False
    
    if len(grades) == 1:
        return send_grade_notification(grades[0])
    
    message = f"🎓 <b>{len(grades)} Yeni Sınav Sonucu!</b>\n\n"
    
    for i, grade in enumerate(grades, 1):
        course_code = grade.get("course_code", "N/A")
        course_name = grade.get("course_name", "N/A")
        grade_value = grade.get("grade", "N/A")
        
        message += f"{i}. <b>{course_code}</b> - {course_name}: <code>{grade_value}</code>\n"
    
    message += "\n✨ Tebrikler! Başarılar dilerim."
    
    return send_message(message)


def send_startup_message() -> bool:

    message = (
        "🤖 <b>OBS Bildirim Botu Aktif!</b>\n\n"
        f"⏰ Kontrol sıklığı: {config.CHECK_INTERVAL} dakika\n"
        "📝 Yeni sonuçlar açıklandığında bildirim alacaksınız."
    )
    return send_message(message)


def send_error_notification(error_msg: str) -> bool:

    message = f"⚠️ <b>OBS Bot Hatası</b>\n\n{error_msg}"
    return send_message(message)
