from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import os
import threading
import cv2
import numpy as np
from PIL import Image
import qrcode
import telebot
from telebot import types

TOKEN = "8924199543:AAFqVR4oL-_dTZrcfVxLrBzYbiA3MgDEPyo"
bot = telebot.TeleBot(TOKEN)

# =============================================================
# 1. МИКРО HTTP-СЕРВЕР (Health Check / Keep-Alive)
# =============================================================


class HealthCheckHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    """Ответ на GET-запросы для прохождения Health Check."""
    self.send_response(200)
    self.send_header("Content-type", "application/json; charset=utf-8")
    self.end_headers()
    self.wfile.write(b'{"status": "ok", "bot": "running"}')

  def log_message(self, format, *args):
    """Отключаем лишние логи HTTP-запросов в консоли."""
    return


def start_http_server():
  # Берем порт из переменной окружения PORT (для Render/Railway) или 8080 по умолчанию
  port = int(os.environ.get("PORT", 8080))
  server_address = ("0.0.0.0", port)
  httpd = HTTPServer(server_address, HealthCheckHandler)
  print(f"🌐 Микро HTTP-сервер запущен на порту {port}")
  httpd.serve_forever()


# Запускаем HTTP-сервер в отдельном фоновом (daemon) потоке
threading.Thread(target=start_http_server, daemon=True).start()


# =============================================================
# 2. ОСНОВНАЯ ЛОГИКА ТЕЛЕГРАМ-БОТА
# =============================================================

user_settings = {}


def get_user_config(chat_id):
  if chat_id not in user_settings:
    user_settings[chat_id] = {
        "fill_color": "black",
        "back_color": "white",
        "logo": None,
    }
  return user_settings[chat_id]


COLOR_PRESETS = {
    "black": ("#000000", "Черный ⬛"),
    "blue": ("#1E40AF", "Синий 🟦"),
    "red": ("#DC2626", "Красный 🟥"),
    "green": ("#15803D", "Зеленый 🟩"),
    "purple": ("#6B21A8", "Фиолетовый 🟪"),
}


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
  text = (
      "👋 *Универсальный QR-бот*\n\n"
      "🔹 **Возможности:**\n"
      "1. **Генерация**: отправь любой текст или ссылку.\n"
      "2. **Сканирование**: отправь фото с QR-кодом для его расшифровки.\n"
      "3. **Логотип**: отправь обычное фото (без QR), чтобы сделать его"
      " логотипом.\n"
      "4. **Цвет**: выбирай цвета QR-кода с помощью кнопок.\n\n"
      "🗑 /clear_logo — сбросить текущий логотип"
  )

  markup = types.InlineKeyboardMarkup(row_width=2)
  buttons = [
      types.InlineKeyboardButton(text=name, callback_data=f"color_{key}")
      for key, (_, name) in COLOR_PRESETS.items()
  ]
  markup.add(*buttons)

  bot.send_message(
      message.chat.id, text, parse_mode="Markdown", reply_markup=markup
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("color_"))
def handle_color_change(call):
  color_key = call.data.split("_")[1]
  if color_key in COLOR_PRESETS:
    config = get_user_config(call.message.chat.id)
    config["fill_color"] = COLOR_PRESETS[color_key][0]
    color_name = COLOR_PRESETS[color_key][1]

    bot.answer_callback_query(call.id, f"Выбран цвет: {color_name}")
    bot.send_message(
        call.message.chat.id,
        f"✅ Цвет QR-кода изменён на **{color_name}**.",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["clear_logo"])
def clear_logo(message):
  config = get_user_config(message.chat.id)
  config["logo"] = None
  bot.reply_to(message, "🗑 Логотип удалён.")


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
  try:
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # Декодирование QR-кода через OpenCV
    np_arr = np.frombuffer(downloaded_file, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    if data:
      reply_text = f"🔎 **Расшифрованный QR-код:**\n\n`{data}`"
      markup = types.InlineKeyboardMarkup()

      if data.startswith(("http://", "https://")):
        markup.add(
            types.InlineKeyboardButton(text="🔗 Перейти по ссылке", url=data)
        )

      bot.reply_to(
          message, reply_text, parse_mode="Markdown", reply_markup=markup
      )
    else:
      config = get_user_config(message.chat.id)
      config["logo"] = downloaded_file
      bot.reply_to(
          message,
          "🖼 QR-код на фото не обнаружен.\nКартинка сохранена как **логотип**"
          " для новых QR-кодов!",
          parse_mode="Markdown",
      )

  except Exception:
    bot.reply_to(message, "⚠️ Произошла ошибка при обработке изображения.")


@bot.message_handler(func=lambda message: True)
def generate_qr(message):
  try:
    config = get_user_config(message.chat.id)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(message.text)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color=config["fill_color"], back_color=config["back_color"]
    ).convert("RGBA")

    if config["logo"]:
      logo = Image.open(io.BytesIO(config["logo"])).convert("RGBA")
      qr_w, qr_h = qr_img.size
      max_logo_size = int(qr_w * 0.20)
      logo.thumbnail((max_logo_size, max_logo_size), Image.Resampling.LANCZOS)

      pos_x = (qr_w - logo.width) // 2
      pos_y = (qr_h - logo.height) // 2

      pad = 6
      bg_rect = Image.new(
          "RGBA", (logo.width + pad * 2, logo.height + pad * 2), "white"
      )
      qr_img.paste(bg_rect, (pos_x - pad, pos_y - pad))
      qr_img.paste(logo, (pos_x, pos_y), logo)

    bio = io.BytesIO()
    bio.name = "qrcode.png"
    qr_img.save(bio, "PNG")
    bio.seek(0)

    bot.send_photo(
        message.chat.id,
        photo=bio,
        caption=f"Ваш QR-код для: `{message.text}`",
        parse_mode="Markdown",
    )

  except Exception:
    bot.reply_to(message, "Произошла ошибка при генерации QR-кода.")


if __name__ == "__main__":
  print("🤖 Бот запущен...")
  bot.infinity_polling()
