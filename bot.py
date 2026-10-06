import os
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import cv2
import numpy as np
from PIL import Image
import qrcode
import requests

# 1. Получение токена из настроек Render
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    print("ВНИМАНИЕ: Переменная BOT_TOKEN не найдена в Environment Variables!")

bot = telebot.TeleBot(TOKEN)


# 2. Микро HTTP-сервер для Render (не даёт серверу упасть)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return  # Отключаем спам логами HTTP-запросов в консоль


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()


# 3. Обработчики команд бота

@bot.message_handler(commands=['start'])
def start_command(message):
    # Обычный текст без parse_mode, чтобы не было ошибок форматирования
    bot.send_message(
        message.chat.id,
        "Привет! Бот успешно запущен и работает 24/7!\n\n"
        "• Отправь /qr [текст] — чтобы сгенерировать QR-код.\n"
        "• Отправь картинку — бот обработает её через OpenCV."
    )


@bot.message_handler(commands=['qr'])
def generate_qr(message):
    # Получаем текст после команды /qr
    text = message.text.replace('/qr', '').strip()
    
    if not text:
        bot.reply_to(message, "Укажи текст после команды! Пример: /qr Привет")
        return

    # Создание QR-кода
    qr_img = qrcode.make(text)
    
    # Сохранение в буфер памяти
    bio = io.BytesIO()
    bio.name = 'qrcode.png'
    qr_img.save(bio, 'PNG')
    bio.seek(0)
    
    bot.send_photo(message.chat.id, photo=bio)


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "Обрабатываю фото...")
    
    try:
        # Скачивание изображения из Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Открытие через Pillow
        pil_image = Image.open(io.BytesIO(downloaded_file))
        
        # Преобразование PIL -> OpenCV
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        # Пример обработки OpenCV (перевод в оттенки серого)
        gray_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        
        # Преобразование обратно в PIL и отправка
        result_pil = Image.fromarray(gray_image)
        bio = io.BytesIO()
        bio.name = 'result.jpg'
        result_pil.save(bio, 'JPEG')
        bio.seek(0)
        
        bot.send_photo(message.chat.id, photo=bio)
    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке фото: {e}")


@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"Вы написали: {message.text}")


# 4. Запуск сервера и бота
if __name__ == '__main__':
    # Запускаем HTTP-сервер в отдельном фоновом потоке
    threading.Thread(target=run_web_server, daemon=True).start()
    
    print("Сервер запущен. Старт polling...")
    
    # Бесконечный цикл ожидания сообщений
    bot.infinity_polling(skip_pending=True)
