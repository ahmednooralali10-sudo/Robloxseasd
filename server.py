import os
import json
import threading
import requests
import datetime
from flask import Flask
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from user_agent import generate_user_agent

# ---عدادات ---
TOKEN = "8807194549:AAGcUNewT82vYW7rxdngAdSYOTlvCvYUOo8"
CHANNEL_ID = "@vaul3t" # تقدر تغيره أو تشيله

# --- Flask للسيرفر ---
app = Flask(__name__)

@app.route("/")
def index():
    return "TikTok Bot is running!"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000))
    t.daemon = True
    t.start()

# --- دالة جلب معلومات التيك توك ---
class TiktokUserScraper:
    URI_BASE = 'https://www.tiktok.com/'

    def get_user_details(self, username):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": generate_user_agent(),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            })
            # طلب الصفحة لتخطي الحماية
            session.get(f"https://www.tiktok.com/@{username}", timeout=10)
            
            url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}&aid=1988"
            r = session.get(url, timeout=15)
            
            if r.status_code != 200:
                return {"error": f"فشل الاتصال، كود: {r.status_code}"}
                
            data = r.json()
            if "userInfo" not in data or "user" not in data["userInfo"]:
                return {"error": "🚨 الحساب غير موجود أو محظور."}
                
            user = data["userInfo"]["user"]
            stats = data["userInfo"]["stats"]
            
            create_time = user.get("createTime", 0)
            try:
                created_date = datetime.datetime.utcfromtimestamp(create_time).strftime('%Y-%m-%d')
            except:
                created_date = "Unknown"
                
            result = {
                "Username": f"@{user.get('uniqueId', username)}",
                "Nickname": user.get("nickname", "N/A"),
                "User ID": user.get("id", "N/A"),
                "Region": user.get("region", "N/A"),
                "Followers": f"{stats.get('followerCount', 0):,}",
                "Following": f"{stats.get('followingCount', 0):,}",
                "Likes": f"{stats.get('heartCount', 0):,}",
                "Videos": f"{stats.get('videoCount', 0):,}",
                "Verified": "✅ Yes" if user.get("verified", False) else "❌ No",
                "Private": "🔒 Yes" if user.get("privateAccount", False) else "🔓 No",
                "Bio": user.get("signature", "N/A"),
                "Created": created_date,
                "Profile Picture": user.get("avatarLarger", "N/A"),
                "_raw_user": user
            }
            return result
        except Exception as e:
            return {"error": f"حدث خطأ: {str(e)}"}

scraper = TiktokUserScraper()

USERNAME, USER_ID = range(2)

# --- أوامر البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "👋 أرسل لي اسم مستخدم تيك توك (بدون @) عشان أجيب لك كل المعلومات.\n/cancel للإلغاء.",
        parse_mode=ParseMode.MARKDOWN
    )
    return USERNAME

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip().replace("@", "")
    result = scraper.get_user_details(user_input)

    if 'error' in result:
        await update.message.reply_text(result['error'])
        return ConversationHandler.END
        
    profile_pic = result.pop('Profile Picture', None)
    if profile_pic and profile_pic != 'N/A':
        try:
            await update.message.reply_photo(photo=profile_pic)
        except Exception:
            pass

    result.pop('_raw_user', None)
    response = "📋 *TikTok Account Details*\n\n"
    for key, value in result.items():
        safe_key = escape_markdown(key, version=2)
        safe_value = escape_markdown(str(value), version=2)
        response += f"*{safe_key}*: {safe_value}\n"

    keyboard = [[InlineKeyboardButton("🔄 Refresh Information", callback_data=f"refresh:{user_input}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        response,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('❌ Operation cancelled')
    return ConversationHandler.END

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    identifier = query.data.split(':', 1)[1]

    try:
        result = scraper.get_user_details(identifier)

        if 'error' in result:
            await query.edit_message_text(text=result['error'])
            return

        result.pop('_raw_user', None)
        result.pop('Profile Picture', None)
        
        response = "📋 *TikTok Account Details*\n\n"
        for key, value in result.items():
            safe_key = escape_markdown(key, version=2)
            safe_value = escape_markdown(str(value), version=2)
            response += f"*{safe_key}*: {safe_value}\n"

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Information", callback_data=f"refresh:{identifier}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                text=response,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
                reply_markup=reply_markup
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                await query.answer("✅ المعلومات محدثة بالفعل.")
    except Exception as e:
        await query.message.reply_text(f"⚠️ فشل التحديث: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Error found: {context.error}")
    try:
        if update.message:
            await update.message.reply_text("⚠️ حدث خطأ، جرب مرة ثانية.")
        elif update.callback_query:
            await update.callback_query.message.reply_text("⚠️ حدث خطأ، جرب مرة ثانية.")
    except Exception:
        pass

def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(refresh_callback, pattern="^refresh:"))

    print("Bot running...")
    application.run_polling()

if __name__ == '__main__':
    keep_alive()
    main()
