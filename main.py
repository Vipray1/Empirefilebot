import os
import json
from dotenv import load_dotenv
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = ("7662000357")
FILES = {
    "admins": "admins.json",
    "tools": "tools.json",
    "combos": "combos.json"
}
USERS_FILE = "users.json"
LOGS_FILE = "logs.json"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- JSON Helpers ---
def load_json(filename, default=None):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(default if default is not None else [], f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

def is_admin(user_id):
    admins = load_json(FILES["admins"], [OWNER_ID])
    return user_id in admins

def log_activity(text):
    logs = load_json(LOGS_FILE, [])
    logs.insert(0, text)
    if len(logs) > 100:
        logs = logs[:100]
    save_json(LOGS_FILE, logs)

def add_user(user_id):
    users = load_json(USERS_FILE, [])
    if user_id not in users:
        users.append(user_id)
        save_json(USERS_FILE, users)

# --- Bot Handlers ---

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    add_user(user_id)
    log_activity(f"User {user_id} started bot")

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Tools", callback_data="view_tools"),
        InlineKeyboardButton("Combos", callback_data="view_combos"),
    )
    if is_admin(user_id):
        markup.add(InlineKeyboardButton("Upload File", callback_data="upload_file"))
    if user_id == OWNER_ID:
        markup.add(
            InlineKeyboardButton("Add Admin", callback_data="add_admin"),
            InlineKeyboardButton("Remove Admin", callback_data="remove_admin"),
            InlineKeyboardButton("Delete All Files", callback_data="delete_all"),
            InlineKeyboardButton("Broadcast", callback_data="broadcast"),
            InlineKeyboardButton("Activity Logs", callback_data="activity_logs"),
        )
    bot.send_message(message.chat.id, "Welcome to Empire File Manager.\nPlease choose a section.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_"))
def view_section(call):
    section = call.data.split("_")[1]
    files = load_json(FILES[section], [])
    if not files:
        return bot.send_message(call.message.chat.id, f"No files found in {section} section.")
    for file in files:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton(f"Download: {file['button']}", callback_data=f"get_{section}_{file['filename']}"))
        if is_admin(call.from_user.id):
            markup.add(InlineKeyboardButton(f"Delete: {file['button']}", callback_data=f"del_{section}_{file['filename']}"))
        bot.send_message(call.message.chat.id, f"File: {file['filename']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("get_"))
def send_file(call):
    _, section, filename = call.data.split("_", 2)
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            bot.send_document(call.message.chat.id, f)
        log_activity(f"{call.from_user.id} downloaded {filename}")
    else:
        bot.send_message(call.message.chat.id, "File not found.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def delete_file(call):
    if not is_admin(call.from_user.id):
        return bot.send_message(call.message.chat.id, "Only admins can delete files.")
    _, section, filename = call.data.split("_", 2)
    try:
        os.remove(filename)
    except:
        pass
    files = load_json(FILES[section], [])
    files = [f for f in files if f["filename"] != filename]
    save_json(FILES[section], files)
    bot.send_message(call.message.chat.id, f"The file '{filename}' was deleted.")
    log_activity(f"{call.from_user.id} deleted {filename}")

@bot.callback_query_handler(func=lambda call: call.data == "upload_file")
def upload_start(call):
    if is_admin(call.from_user.id):
        bot.send_message(call.message.chat.id, "Send a .py or .txt file with a short caption (button name).")
    else:
        bot.send_message(call.message.chat.id, "You are not allowed to upload files.")

@bot.message_handler(content_types=["document"])
def handle_upload(message):
    if not is_admin(message.from_user.id):
        return bot.send_message(message.chat.id, "You are not allowed to upload files.")
    if message.document.file_size > 50 * 1024 * 1024:
        return bot.send_message(message.chat.id, "File too big (max 50MB).")
    if not message.caption:
        return bot.send_message(message.chat.id, "Please add a caption for the button name.")
    filename = message.document.file_name
    if not (filename.endswith(".py") or filename.endswith(".txt")):
        return bot.send_message(message.chat.id, "Only .py and .txt files allowed.")
    filetype = "tools" if filename.endswith(".py") else "combos"
    file_info = bot.get_file(message.document.file_id)
    content = bot.download_file(file_info.file_path)
    with open(filename, "wb") as f:
        f.write(content)
    files = load_json(FILES[filetype], [])
    files = [f for f in files if f["filename"] != filename]
    files.append({"filename": filename, "button": message.caption.strip()})
    save_json(FILES[filetype], files)
    bot.send_message(message.chat.id, f"File uploaded and button added in {filetype}.")
    log_activity(f"{message.from_user.id} uploaded {filename}")

@bot.callback_query_handler(func=lambda call: call.data in ["add_admin", "remove_admin"])
def handle_admin_action(call):
    if call.from_user.id != OWNER_ID:
        return bot.send_message(call.message.chat.id, "Only the owner can manage admins.")
    bot.send_message(call.message.chat.id, "Send the user ID to " + ("add" if call.data == "add_admin" else "remove") + ".")

@bot.message_handler(func=lambda m: m.from_user.id == OWNER_ID and m.text and m.text.strip().isdigit())
def admin_id_input(message):
    user_id = int(message.text.strip())
    admins = load_json(FILES["admins"], [OWNER_ID])
    if user_id == OWNER_ID:
        return bot.send_message(message.chat.id, "You are already the owner.")
    if user_id in admins:
        admins.remove(user_id)
        save_json(FILES["admins"], admins)
        bot.send_message(message.chat.id, f"Admin {user_id} removed.")
        log_activity(f"Admin {user_id} removed by owner")
    else:
        admins.append(user_id)
        save_json(FILES["admins"], admins)
        bot.send_message(message.chat.id, f"Admin {user_id} added.")
        log_activity(f"Admin {user_id} added by owner")

@bot.callback_query_handler(func=lambda call: call.data == "delete_all")
def delete_all_files(call):
    if call.from_user.id != OWNER_ID:
        return bot.send_message(call.message.chat.id, "Only the owner can delete all files.")
    for section in ["tools", "combos"]:
        for file in load_json(FILES[section], []):
            try:
                os.remove(file["filename"])
            except:
                pass
        save_json(FILES[section], [])
    bot.send_message(call.message.chat.id, "All files deleted.")
    log_activity("All files deleted by owner")

@bot.callback_query_handler(func=lambda call: call.data == "broadcast")
def broadcast_start(call):
    if call.from_user.id != OWNER_ID:
        return
    bot.send_message(call.message.chat.id, "Send the broadcast message text.")

@bot.message_handler(func=lambda m: m.from_user.id == OWNER_ID and m.text and not m.text.strip().isdigit())
def broadcast_send(message):
    users = load_json(USERS_FILE, [])
    count = 0
    for uid in users:
        try:
            bot.send_message(uid, message.text)
            count += 1
        except:
            pass
    bot.send_message(message.chat.id, f"Broadcast sent to {count} users.")
    log_activity(f"Broadcast sent by owner to {count} users")

@bot.callback_query_handler(func=lambda call: call.data == "activity_logs")
def show_logs(call):
    if call.from_user.id != OWNER_ID:
        return
    users = load_json(USERS_FILE, [])
    admins = load_json(FILES["admins"], [OWNER_ID])
    logs = load_json(LOGS_FILE, [])
    text = f"Users: {len(users)}\nAdmins: {len(admins)}\n\nLast Activities:\n"
    text += "\n".join(logs[:5]) if logs else "No activity yet."
    bot.send_message(call.message.chat.id, text)

# --- Flask Webhook ---

@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

@app.route('/')
def index():
    return "Empire File Manager Bot läuft."

if __name__ == '__main__':
    # Wichtig: Ersetze DEINE_DOMAIN hier mit deiner Render-/Hosting-Domain (ohne https://)
    YOUR_DOMAIN = "empirefilebot.onrender.com"
    WEBHOOK_URL = f"https://{YOUR_DOMAIN}/{TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=5000)
