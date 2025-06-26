# import os
# import logging
# import uuid
# import tempfile
# import re
# import sys
# from datetime import datetime, timedelta
# from dotenv import load_dotenv
# from telegram import (
#     Update,
#     InlineKeyboardButton,
#     InlineKeyboardMarkup,
#     ReplyKeyboardMarkup,
#     ReplyKeyboardRemove,
#     InlineQueryResultArticle,
#     InputTextMessageContent,
# )
# from telegram.ext import (
#     Application,
#     CommandHandler,
#     MessageHandler,
#     CallbackQueryHandler,
#     ConversationHandler,
#     InlineQueryHandler,
#     filters,
#     ContextTypes,
# )
# from telegram import error as telegram_error
# from werkzeug.utils import secure_filename
# from firebase_admin import firestore
# from models import User, File, UserRepository
# from file_manager import FileManager
# from ai_agent import AIAgent
# from auth import AuthManager
# import mimetypes
# import aiohttp
# from PIL import Image
# import io
# from cachetools import TTLCache

# # Setup logging
# logging.basicConfig(
#     level=logging.DEBUG,  # Changed to DEBUG for detailed tracing
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.FileHandler("bot.log", mode="a", encoding="utf-8"),
#         logging.StreamHandler(stream=sys.stdout),
#     ],
# )
# logger = logging.getLogger(__name__)

# # Load environment variables
# load_dotenv()
# TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# FLASK_APP_URL = os.getenv("FLASK_APP_URL", "http://localhost:5000")
# if not TELEGRAM_BOT_TOKEN:
#     raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")

# # Initialize Firestore
# db = firestore.client()

# # Initialize AI Agent
# ai_agent = AIAgent()

# # Conversation states
# (
#     REGISTRATION,
#     REGISTRATION_OTP,
#     LOGIN,
#     LOGIN_OTP,
#     UPLOAD_FILE,
#     ADD_STORAGE,
#     ADD_STORAGE_EMAIL,
#     AI_QUERY,
#     DELETE_FILE,
#     SEARCH_FILES,
# ) = range(10)

# # Rate limiting
# RATE_LIMIT = 30  # Max commands per minute
# USER_REQUESTS = {}  # Track requests per user
# SESSION_CACHE = TTLCache(maxsize=1000, ttl=86400)  # 24-hour session cache


# def rate_limit_exceeded(user_id: str) -> bool:
#     now = datetime.utcnow()
#     if user_id not in USER_REQUESTS:
#         USER_REQUESTS[user_id] = []
#     USER_REQUESTS[user_id] = [
#         t for t in USER_REQUESTS[user_id] if now - t < timedelta(minutes=1)
#     ]
#     if len(USER_REQUESTS[user_id]) >= RATE_LIMIT:
#         return True
#     USER_REQUESTS[user_id].append(now)
#     return False


# # Session management
# def get_user_session(telegram_id: str) -> dict:
#     if telegram_id in SESSION_CACHE:
#         logger.debug(f"Retrieved session from cache for {telegram_id}: {SESSION_CACHE[telegram_id]}")
#         return SESSION_CACHE[telegram_id]
#     try:
#         doc_ref = db.collection("telegram_sessions").document(str(telegram_id))
#         doc = doc_ref.get()
#         session = doc.to_dict() if doc.exists else {}
#         SESSION_CACHE[telegram_id] = session
#         logger.debug(f"Retrieved session from Firestore for {telegram_id}: {session}")
#         return session
#     except Exception as e:
#         logger.error(f"Failed to get session for {telegram_id}: {str(e)}")
#         return {}


# def save_user_session(telegram_id: str, data: dict):
#     data["last_updated"] = datetime.utcnow().timestamp()
#     SESSION_CACHE[telegram_id] = data
#     logger.debug(f"Saved session to cache for {telegram_id}: {data}")
#     try:
#         db.collection("telegram_sessions").document(str(telegram_id)).set(data)
#         logger.debug(f"Saved session to Firestore for {telegram_id}")
#     except Exception as e:
#         logger.error(f"Failed to save session to Firestore for {telegram_id}: {str(e)}")


# def clear_user_session(telegram_id: str):
#     if telegram_id in SESSION_CACHE:
#         del SESSION_CACHE[telegram_id]
#         logger.debug(f"Cleared session cache for {telegram_id}")
#     try:
#         db.collection("telegram_sessions").document(str(telegram_id)).delete()
#         logger.debug(f"Cleared session from Firestore for {telegram_id}")
#     except Exception as e:
#         logger.error(f"Failed to clear session for {telegram_id}: {str(e)}")


# # Helper functions
# def validate_email(email: str) -> bool:
#     pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
#     return bool(re.match(pattern, email))


# def build_main_menu():
#     keyboard = [
#         [
#             InlineKeyboardButton("📤 Quick Upload", callback_data="upload_file"),
#             InlineKeyboardButton("📂 Recent Files", callback_data="recent_files"),
#         ],
#         [
#             InlineKeyboardButton("🤖 Ask AI", callback_data="ai_ask"),
#             InlineKeyboardButton("🔍 Search Files", callback_data="search_files"),
#         ],
#         [
#             InlineKeyboardButton(
#                 "☁️ Storage Accounts", callback_data="storage_accounts"
#             ),
#             InlineKeyboardButton("📊 Stats", callback_data="stats"),
#         ],
#         [InlineKeyboardButton("🚪 Logout", callback_data="logout")],
#     ]
#     return InlineKeyboardMarkup(keyboard)


# def build_quick_actions():
#     keyboard = [
#         [InlineKeyboardButton("📤 Upload File", callback_data="upload_file")],
#         [InlineKeyboardButton("📂 My Files", callback_data="list_files")],
#         [InlineKeyboardButton("🤖 Ask AI", callback_data="ai_ask")],
#         [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#     ]
#     return InlineKeyboardMarkup(keyboard)


# def build_file_category_menu():
#     keyboard = [
#         [InlineKeyboardButton("📚 All Files", callback_data="category_all_1")],
#         [InlineKeyboardButton("🖼️ Images", callback_data="category_images_1")],
#         [InlineKeyboardButton("📄 Documents", callback_data="category_documents_1")],
#         [InlineKeyboardButton("🎥 Videos", callback_data="category_videos_1")],
#         [InlineKeyboardButton("🎵 Audio", callback_data="category_audio_1")],
#         [InlineKeyboardButton("🔢 Other", callback_data="category_other_1")],
#         [InlineKeyboardButton("📅 Sort by Date", callback_data="sort_date_1")],
#         [InlineKeyboardButton("📏 Sort by Size", callback_data="sort_size_1")],
#         [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#     ]
#     return InlineKeyboardMarkup(keyboard)


# def build_file_actions(file_id: str):
#     keyboard = [
#         [
#             InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{file_id}"),
#             InlineKeyboardButton("📥 Download", callback_data=f"download_{file_id}"),
#         ],
#         [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{file_id}")],
#         [InlineKeyboardButton("🔙 Back", callback_data="list_files")],
#     ]
#     return InlineKeyboardMarkup(keyboard)


# def build_pagination_buttons(page: int, total_pages: int, category: str):
#     keyboard = []
#     row = []
#     if page > 1:
#         row.append(
#             InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{category}_{page-1}")
#         )
#     if page < total_pages:
#         row.append(
#             InlineKeyboardButton("Next ➡️", callback_data=f"page_{category}_{page+1}")
#         )
#     if row:
#         keyboard.append(row)
#     return keyboard


# async def send_notification(telegram_id: str, message: str):
#     async with Application.builder().token(TELEGRAM_BOT_TOKEN).build() as app:
#         try:
#             await app.bot.send_message(
#                 chat_id=telegram_id,
#                 text=message,
#                 parse_mode="Markdown",
#                 disable_notification=False,
#             )
#             logger.info(f"Sent notification to {telegram_id}: {message}")
#         except Exception as e:
#             logger.error(f"Failed to send notification to {telegram_id}: {str(e)}")


# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     try:
#         logger.info(f"Received /start from user {user_id}")
#         session = get_user_session(user_id)
#         if session.get("logged_in"):
#             user = User.get_user_by_email(session["email"])
#             if user:
#                 await update.message.reply_text(
#                     f"🎉 *Welcome back, {user.first_name}!*\nChoose an action to get started:",
#                     parse_mode="Markdown",
#                     reply_markup=build_main_menu(),
#                 )
#                 logger.info(f"User {user.email} already logged in")
#                 return ConversationHandler.END
#         keyboard = [
#             [InlineKeyboardButton("📝 Register", callback_data="register")],
#             [InlineKeyboardButton("🔑 Login", callback_data="login")],
#             [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
#         ]
#         await update.message.reply_text(
#             "🌟 *Welcome to MegaCloud Bot!*\nStore files, connect cloud storage, and chat with AI.\nChoose an option:",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup(keyboard),
#         )
#         logger.info("Sent welcome message for /start")
#         return ConversationHandler.END
#     except Exception as e:
#         logger.error(f"Error in start handler: {str(e)}", exc_info=True)
#         await update.message.reply_text(
#             "⚠️ *Something went wrong.* Please try again later.", parse_mode="Markdown"
#         )
#         return ConversationHandler.END


# async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     help_text = (
#         "📚 *MegaCloud Bot Help*\n\n"
#         "Manage your files and interact with AI:\n"
#         "• /start - Begin or log in\n"
#         "• /help - Show this guide\n"
#         "• 📤 *Upload File*: Send files up to 100MB\n"
#         "• 📂 *My Files*: Browse by category or sort\n"
#         "• 🔍 *Search Files*: Find files by name\n"
#         "• 🤖 *Ask AI*: Query about files or general topics\n"
#         "• ☁️ *Storage Accounts*: Add Google Drive/Dropbox\n"
#         "• 📊 *Stats*: View storage usage\n"
#         "\nUse inline buttons or reply keyboards to navigate!"
#     )
#     await update.message.reply_text(
#         help_text, parse_mode="Markdown", reply_markup=build_main_menu()
#     )
#     logger.info(f"Displayed help for user {update.effective_user.id}")


# async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
#     user_id = str(query.from_user.id)
#     if rate_limit_exceeded(user_id):
#         await query.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     if query.data == "register":
#         await query.message.reply_text(
#             "📝 *Register*\nEnter: First Name Last Name Username Email\nExample: John Doe johndoe john@example.com",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardRemove(),
#         )
#         return REGISTRATION
#     elif query.data == "login":
#         await query.message.reply_text(
#             "🔑 *Login*\nEnter your email or username:",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardRemove(),
#         )
#         return LOGIN
#     elif query.data == "main_menu":
#         await query.message.reply_text(
#             "🌟 *MegaCloud Menu*\nWhat would you like to do?",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END
#     elif query.data == "upload_file":
#         await query.message.reply_text(
#             "📤 *Upload File*\nSend one or more files (max 100MB each):",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True),
#         )
#         return UPLOAD_FILE
#     elif query.data == "recent_files":
#         await list_files_by_category(query, context, "All", 1, sort_by="date")
#         return ConversationHandler.END
#     elif query.data == "list_files":
#         await query.message.reply_text(
#             "📂 *My Files*\nSelect a category or sort option:",
#             parse_mode="Markdown",
#             reply_markup=build_file_category_menu(),
#         )
#         return ConversationHandler.END
#     elif query.data.startswith("category_"):
#         category, page = query.data.split("_")[1].capitalize(), int(
#             query.data.split("_")[2]
#         )
#         if category == "All":
#             category = "All"
#         await list_files_by_category(query, context, category, page)
#         return ConversationHandler.END
#     elif query.data.startswith("sort_"):
#         sort_by, page = query.data.split("_")[1], int(query.data.split("_")[2])
#         await list_files_by_category(query, context, "All", page, sort_by=sort_by)
#         return ConversationHandler.END
#     elif query.data.startswith("page_"):
#         category, page = query.data.split("_")[1].capitalize(), int(
#             query.data.split("_")[2]
#         )
#         if category == "All":
#             category = "All"
#         sort_by = session.get("sort_by", "name")
#         await list_files_by_category(query, context, category, page, sort_by=sort_by)
#         return ConversationHandler.END
#     elif query.data == "search_files":
#         await query.message.reply_text(
#             "🔍 *Search Files*\nEnter your search query:",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True),
#         )
#         return SEARCH_FILES
#     elif query.data == "stats":
#         await show_stats(query, context)
#         return ConversationHandler.END
#     elif query.data == "storage_accounts":
#         await manage_storage_accounts(query, context)
#         return ConversationHandler.END
#     elif query.data == "ai_ask":
#         session["ai_context"] = []
#         save_user_session(user_id, session)
#         await query.message.reply_text(
#             "🤖 *Chat with AI*\nAsk about files (e.g., 'Summarize my PDF') or general questions (e.g., 'What is cloud storage?').",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardMarkup(
#                 [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
#             ),
#         )
#         return AI_QUERY
#     elif query.data == "logout":
#         clear_user_session(user_id)
#         await query.message.reply_text(
#             "👋 *Logged out successfully!*\nUse /start to begin again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END
#     elif query.data.startswith("preview_"):
#         file_id = query.data.split("_")[1]
#         await preview_file(query, context, file_id)
#         return ConversationHandler.END
#     elif query.data.startswith("download_"):
#         file_id = query.data.split("_")[1]
#         await download_file(query, context, file_id)
#         return ConversationHandler.END
#     elif query.data.startswith("delete_"):
#         file_id = query.data.split("_")[1]
#         filename = session.get("file_map", {}).get(file_id, "Unknown")
#         await query.message.reply_text(
#             f"🗑️ *Delete File*\nAre you sure you want to delete *{filename}*?",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup(
#                 [
#                     [
#                         InlineKeyboardButton(
#                             "✅ Yes", callback_data=f"confirm_delete_{file_id}"
#                         )
#                     ],
#                     [InlineKeyboardButton("❌ No", callback_data="list_files")],
#                 ]
#             ),
#         )
#         return ConversationHandler.END
#     elif query.data.startswith("confirm_delete_"):
#         file_id = query.data.split("_")[2]
#         await delete_file(query, context, file_id)
#         return ConversationHandler.END
#     elif query.data == "add_storage":
#         keyboard = [
#             [
#                 InlineKeyboardButton(
#                     "Google Drive", callback_data="provider_google_drive"
#                 )
#             ],
#             [InlineKeyboardButton("Dropbox", callback_data="provider_dropbox")],
#             [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#         ]
#         await query.message.reply_text(
#             "☁️ *Add Storage*\nSelect a provider:",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup(keyboard),
#         )
#         return ConversationHandler.END
#     elif query.data.startswith("provider_"):
#         logger.debug(f"Provider selection - query.data: {query.data}")
#         try:
#             provider_type = query.data.split("_")[1]
#             logger.debug(f"Parsed provider_type: {provider_type}")
#             if provider_type not in ["google_drive", "dropbox"]:
#                 logger.error(f"Invalid provider_type parsed: {provider_type}")
#                 await query.message.reply_text(
#                     "⚠️ *Invalid provider selected.* Please try again.",
#                     parse_mode="Markdown",
#                     reply_markup=build_main_menu(),
#                 )
#                 return ConversationHandler.END
#             session["storage_pending_provider"] = provider_type
#             save_user_session(user_id, session)
#             logger.debug(f"Saved session with storage_pending_provider: {provider_type}")
#             await query.message.reply_text(
#                 f"☁️ *Add {provider_type.replace('_', ' ').title()}*\nEnter the account email:",
#                 parse_mode="Markdown",
#                 reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True),
#             )
#             return ADD_STORAGE_EMAIL
#         except IndexError as e:
#             logger.error(f"Failed to parse provider from query.data: {query.data}, error: {str(e)}")
#             await query.message.reply_text(
#                 "⚠️ *Error selecting provider.* Please try again.",
#                 parse_mode="Markdown",
#                 reply_markup=build_main_menu(),
#             )
#             return ConversationHandler.END
#     elif query.data.startswith("delete_storage_"):
#         account_id = query.data.split("_")[2]
#         await delete_storage_account(query, context, account_id)
#         return ConversationHandler.END
#     elif query.data == "help":
#         await help_command(query, context)
#         return ConversationHandler.END
#     elif query.data == "cancel":
#         await cancel(query, context)
#         return ConversationHandler.END


# async def registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     text = update.message.text.strip()
#     if text.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Registration cancelled.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     try:
#         parts = text.split()
#         if len(parts) != 4:
#             raise ValueError("Invalid format")
#         first_name, last_name, username, email = parts
#         if not validate_email(email):
#             await update.message.reply_text(
#                 "⚠️ *Invalid email format.*\nEnter a valid email.", parse_mode="Markdown"
#             )
#             return REGISTRATION
#         if User.get_user_by_email(email):
#             await update.message.reply_text(
#                 "⚠️ *Email already registered.*\nTry logging in.", parse_mode="Markdown"
#             )
#             return ConversationHandler.END
#         if User.get_user_by_username(username):
#             await update.message.reply_text(
#                 "⚠️ *Username taken.*\nChoose another.", parse_mode="Markdown"
#             )
#             return REGISTRATION
#         user = User(
#             email=email, first_name=first_name, last_name=last_name, username=username
#         )
#         otp = user.generate_otp()
#         if user.save() and AuthManager.send_otp_email(email, otp):
#             session = {"email": email, "telegram_id": user_id, "notifications": True}
#             save_user_session(user_id, session)
#             await update.message.reply_text(
#                 "📧 *OTP sent!*\nEnter the 6-digit OTP from your email:",
#                 parse_mode="Markdown",
#                 reply_markup=InlineKeyboardMarkup(
#                     [
#                         [
#                             InlineKeyboardButton(
#                                 "🔄 Resend OTP", callback_data="resend_otp_register"
#                             )
#                         ],
#                         [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
#                     ]
#                 ),
#             )
#             await send_notification(
#                 user_id, f"📧 *OTP sent to {email}.* Check your inbox!"
#             )
#             return REGISTRATION_OTP
#         else:
#             await update.message.reply_text(
#                 "⚠️ *Failed to send OTP.*\nPlease try again.", parse_mode="Markdown"
#             )
#             return ConversationHandler.END
#     except ValueError:
#         await update.message.reply_text(
#             "⚠️ *Invalid format.*\nEnter: First Name Last Name Username Email\nExample: John Doe johndoe john@example.com",
#             parse_mode="Markdown",
#         )
#         return REGISTRATION
#     except Exception as e:
#         logger.error(f"Registration error: {str(e)}", exc_info=True)
#         await update.message.reply_text(
#             f"⚠️ *Error: {str(e)}*\nPlease try again.", parse_mode="Markdown"
#         )
#         return REGISTRATION


# async def registration_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     otp = update.message.text.strip()
#     if otp.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Registration cancelled.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     email = session.get("email")
#     if not email:
#         await update.message.reply_text(
#             "⚠️ *Session expired.*\nStart registration again.", parse_mode="Markdown"
#         )
#         return ConversationHandler.END

#     success, message = AuthManager.verify_otp(email, otp)
#     if success:
#         user = User.get_user_by_email(email)
#         session["logged_in"] = True
#         save_user_session(user_id, session)
#         await update.message.reply_text(
#             f"✅ *Registration successful!*\nWelcome, *{user.first_name}!*\nWhat’s next?",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         logger.info(f"User {email} registered via Telegram")
#         await send_notification(
#             user_id, f"🎉 *Welcome to MegaCloud, {user.first_name}!*"
#         )
#         return ConversationHandler.END
#     else:
#         await update.message.reply_text(
#             f"⚠️ *{message}*\nEnter the OTP again:",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup(
#                 [
#                     [
#                         InlineKeyboardButton(
#                             "🔄 Resend OTP", callback_data="resend_otp_register"
#                         )
#                     ],
#                     [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
#                 ]
#             ),
#         )
#         return REGISTRATION_OTP


# async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     identifier = update.message.text.strip()
#     if identifier.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Login cancelled.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     user = User.get_user_by_email(identifier) or User.get_user_by_username(identifier)
#     if not user:
#         await update.message.reply_text(
#             "⚠️ *User not found.*\nPlease register first.", parse_mode="Markdown"
#         )
#         return ConversationHandler.END

#     otp = user.generate_otp()
#     if user.save() and AuthManager.send_otp_email(user.email, otp):
#         session = get_user_session(user_id)
#         session.update(
#             {
#                 "email": user.email,
#                 "telegram_id": user_id,
#             }
#         )
#         save_user_session(user_id, session)
#         await update.message.reply_text(
#             "📧 *OTP sent!*\nEnter the 6-digit OTP from your email:",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup(
#                 [
#                     [
#                         InlineKeyboardButton(
#                             "🔄 Resend OTP", callback_data="resend_otp_login"
#                         )
#                     ],
#                     [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
#                 ]
#             ),
#         )
#         await send_notification(
#             user_id, f"📧 *OTP sent to {user.email}.* Check your inbox!"
#         )
#         return LOGIN_OTP
#     else:
#         await update.message.reply_text(
#             "⚠️ *Failed to send OTP.*\nPlease try again.", parse_mode="Markdown"
#         )
#         return ConversationHandler.END


# async def login_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     otp = update.message.text.strip()
#     if otp.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Login cancelled.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     email = session.get("email")
#     if not email:
#         await update.message.reply_text(
#             "⚠️ *Session expired.*\nStart login again.", parse_mode="Markdown"
#         )
#         return ConversationHandler.END

#     success, message = AuthManager.verify_otp(email, otp)
#     if success:
#         user = User.get_user_by_email(email)
#         session["logged_in"] = True
#         save_user_session(user_id, session)
#         await update.message.reply_text(
#             f"✅ *Login successful!*\nWelcome back, *{user.first_name}!*\nWhat’s next?",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         logger.info(f"User {email} logged in via Telegram")
#         await send_notification(user_id, f"👋 *Welcome back, {user.first_name}!*")
#         return ConversationHandler.END
#     else:
#         await update.message.reply_text(
#             f"⚠️ *{message}*\nEnter the OTP again:",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup(
#                 [
#                     [
#                         InlineKeyboardButton(
#                             "🔄 Resend OTP", callback_data="resend_otp_login"
#                         )
#                     ],
#                     [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
#                 ]
#             ),
#         )
#         return LOGIN_OTP


# async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await update.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     if update.message.text and update.message.text.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Upload cancelled.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     if not update.message.document:
#         await update.message.reply_text(
#             "⚠️ *Please send a file.*\nMax size: 100MB.", parse_mode="Markdown"
#         )
#         return UPLOAD_FILE

#     documents = [update.message.document] if update.message.document else []
#     if update.message.media_group_id:
#         # Handle media group (multiple files)
#         if "media_group" not in context.user_data:
#             context.user_data["media_group"] = []
#         context.user_data["media_group"].append(update.message.document)
#         return UPLOAD_FILE  # Wait for all files in the group

#     # Process single file or media group
#     documents = context.user_data.get("media_group", documents)
#     context.user_data.pop("media_group", None)

#     user = User.get_user_by_email(session["email"])
#     file_manager = FileManager(user)
#     uploaded_files = []

#     for document in documents:
#         if document.file_size > 100 * 1024 * 1024:
#             await update.message.reply_text(
#                 f"⚠️ *{document.file_name} too large.*\nMax size: 100MB.",
#                 parse_mode="Markdown",
#             )
#             continue

#         await update.message.reply_text(
#             f"⏳ *Uploading {document.file_name}…*", parse_mode="Markdown"
#         )
#         try:
#             file = await document.get_file()
#             base_filename = secure_filename(document.file_name)
#             unique_suffix = uuid.uuid4().hex[:8]
#             storage_filename = f"{base_filename}_{unique_suffix}"
#             temp_path = os.path.join(tempfile.gettempdir(), storage_filename)

#             await file.download_to_drive(temp_path)
#             file_size = os.path.getsize(temp_path)
#             size_mb = file_size / (1024 * 1024)

#             content = ai_agent.extract_text(temp_path)
#             temp_file_id = str(uuid.uuid4())
#             if content:
#                 ai_agent.store_content(temp_file_id, base_filename, content)

#             chunk_ids = file_manager.upload_file(
#                 temp_path, storage_filename, user.email
#             )
#             if not chunk_ids:
#                 ai_agent.delete_content(temp_file_id)
#                 raise Exception("File upload to storage provider failed")

#             file_obj = File(
#                 filename=storage_filename,
#                 user_email=user.email,
#                 chunk_ids=chunk_ids,
#                 size_mb=size_mb,
#             )
#             if not file_obj.save():
#                 ai_agent.delete_content(temp_file_id)
#                 raise Exception("Failed to save file metadata")

#             if content:
#                 ai_agent.delete_content(temp_file_id)
#                 ai_agent.store_content(file_obj.id, base_filename, content)

#             user.update_storage_used(size_mb)
#             user.save()
#             uploaded_files.append((file_obj.id, base_filename, size_mb))

#             await send_notification(
#                 user_id,
#                 f"✅ *{base_filename}* ({size_mb:.2f} MB) uploaded successfully!",
#             )
#         except Exception as e:
#             logger.error(
#                 f"Upload failed for {document.file_name}: {str(e)}", exc_info=True
#             )
#             await update.message.reply_text(
#                 f"⚠️ *Error uploading {document.file_name}: {str(e)}*",
#                 parse_mode="Markdown",
#             )
#         finally:
#             if os.path.exists(temp_path):
#                 try:
#                     os.remove(temp_path)
#                 except Exception as e:
#                     logger.error(f"Cleanup failed for {temp_path}: {str(e)}")

#     if uploaded_files:
#         message = "✅ *Upload Complete!*\n"
#         for file_id, filename, size_mb in uploaded_files:
#             message += f"• *{filename}* ({size_mb:.2f} MB)\n"
#         keyboard = [
#             [InlineKeyboardButton("📤 Upload More", callback_data="upload_file")],
#             [InlineKeyboardButton("📂 View Files", callback_data="list_files")],
#             [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#         ]
#         await update.message.reply_text(
#             message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
#         )
#         logger.info(f"Uploaded {len(uploaded_files)} files for {user.email}")
#     return ConversationHandler.END


# async def list_files_by_category(
#     query, context, category: str, page: int = 1, sort_by: str = "name"
# ):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     files = File.get_files(user.email)
#     if files is None:
#         await query.message.reply_text(
#             "⚠️ *Failed to retrieve files.*",
#             parse_mode="Markdown",
#             reply_markup=build_file_category_menu(),
#         )
#         return

#     if category != "All":
#         files = [f for f in files if f["category"] == category]

#     if not files:
#         await query.message.reply_text(
#             f"📂 *No {category.lower()} files found.*",
#             parse_mode="Markdown",
#             reply_markup=build_file_category_menu(),
#         )
#         return

#     # Sorting
#     if sort_by == "date":
#         files.sort(key=lambda x: x.get("created_at", 0), reverse=True)
#     elif sort_by == "size":
#         files.sort(key=lambda x: x["size_mb"], reverse=True)
#     else:
#         files.sort(key=lambda x: "_".join(x["filename"].split("_")[:-1]).lower())

#     session["sort_by"] = sort_by
#     save_user_session(user_id, session)

#     files_per_page = 5
#     total_pages = (len(files) + files_per_page - 1) // files_per_page
#     start_idx = (page - 1) * files_per_page
#     end_idx = start_idx + files_per_page
#     paginated_files = files[start_idx:end_idx]

#     file_map = session.get("file_map", {})
#     for f in paginated_files:
#         f["display_filename"] = "_".join(f["filename"].split("_")[:-1])
#         file_map[f["id"]] = f["display_filename"]
#     session["file_map"] = file_map
#     save_user_session(user_id, session)

#     message = f"📂 *{category} Files (Page {page}/{total_pages})*\n\n"
#     for f in paginated_files:
#         message += f"📄 *{f['display_filename']}* ({f['size_mb']:.2f} MB)\nCategory: {f['category']}\n\n"

#     pagination_buttons = build_pagination_buttons(page, total_pages, category)
#     keyboard = pagination_buttons + [
#         [InlineKeyboardButton("🔙 Categories", callback_data="list_files")],
#         [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#     ]
#     await query.message.reply_text(
#         message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
#     )

#     for f in paginated_files:
#         await query.message.reply_text(
#             f"📄 *{f['display_filename']}*",
#             parse_mode="Markdown",
#             reply_markup=build_file_actions(f["id"]),
#         )
#     logger.info(
#         f"Listed {len(paginated_files)} {category.lower()} files for {user.email} (page {page}, sorted by {sort_by})"
#     )


# async def search_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await update.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     query = update.message.text.strip()
#     if query.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Search cancelled.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     user = User.get_user_by_email(session["email"])
#     files = File.get_files(user.email)
#     if files is None:
#         await update.message.reply_text(
#             "⚠️ *Failed to retrieve files.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     filtered = [
#         f
#         for f in files
#         if query.lower() in "_".join(f["filename"].split("_")[:-1]).lower()
#     ]
#     if not filtered:
#         await update.message.reply_text(
#             "📂 *No files match your search.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     file_map = session.get("file_map", {})
#     for f in filtered:
#         f["display_filename"] = "_".join(f["filename"].split("_")[:-1])
#         file_map[f["id"]] = f["display_filename"]
#     session["file_map"] = file_map
#     save_user_session(user_id, session)

#     message = f"🔍 *Search Results* ({len(filtered)} files)\n\n"
#     for f in filtered:
#         message += f"📄 *{f['display_filename']}* ({f['size_mb']:.2f} MB)\nCategory: {f['category']}\n\n"
#     await update.message.reply_text(
#         message,
#         parse_mode="Markdown",
#         reply_markup=InlineKeyboardMarkup(
#             [[InlineKeyboardButton("🏠 Home", callback_data="main_menu")]]
#         ),
#     )

#     for f in filtered:
#         await update.message.reply_text(
#             f"📄 *{f['display_filename']}*",
#             parse_mode="Markdown",
#             reply_markup=build_file_actions(f["id"]),
#         )
#     logger.info(
#         f"Searched files for {user.email} with query '{query}': {len(filtered)} results"
#     )
#     return ConversationHandler.END


# async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.inline_query.query.strip()
#     user_id = str(update.inline_query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await update.inline_query.answer(
#             [], switch_pm_text="Please login first", switch_pm_parameter="login"
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     files = File.get_files(user.email) or []
#     filtered = [
#         f
#         for f in files
#         if query.lower() in "_".join(f["filename"].split("_")[:-1]).lower()
#     ][:10]

#     results = []
#     for f in filtered:
#         f["display_filename"] = "_".join(f["filename"].split("_")[:-1])
#         results.append(
#             InlineQueryResultArticle(
#                 id=f["id"],
#                 title=f["display_filename"],
#                 description=f"{f['size_mb']:.2f} MB | {f['category']}",
#                 input_message_content=InputTextMessageContent(
#                     f"📄 *{f['display_filename']}* ({f['size_mb']:.2f} MB)\nCategory: {f['category']}",
#                     parse_mode="Markdown",
#                 ),
#                 reply_markup=InlineKeyboardMarkup(
#                     [
#                         [
#                             InlineKeyboardButton(
#                                 "👁️ Preview", callback_data=f"preview_{f['id']}"
#                             ),
#                             InlineKeyboardButton(
#                                 "📥 Download", callback_data=f"download_{f['id']}"
#                             ),
#                         ]
#                     ]
#                 ),
#             )
#         )
#     await update.inline_query.answer(results)
#     logger.info(
#         f"Inline query by {user.email}: '{query}' returned {len(results)} results"
#     )


# async def show_stats(query, context):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     files = File.get_files(user.email)
#     if files is None:
#         await query.message.reply_text(
#             "⚠️ *Failed to retrieve stats.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     total_files = len(files)
#     total_size = sum(f["size_mb"] for f in files) if files else 0.0
#     total_available = user.get_total_available_storage()
#     message = (
#         f"📊 *Storage Stats*\n"
#         f"• Total Files: {total_files}\n"
#         f"• Storage Used: {total_size:.2f} MB\n"
#         f"• Total Available: {total_available:.2f} MB\n"
#     )
#     if total_available < 100:
#         await send_notification(
#             user_id, f"⚠️ *Low storage warning!* Only {total_available:.2f} MB left."
#         )
#     await query.message.reply_text(
#         message, parse_mode="Markdown", reply_markup=build_main_menu()
#     )
#     logger.info(f"Displayed stats for {user.email}")


# async def manage_storage_accounts(query, context):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     accounts = user.get_storage_accounts_info()
#     total_storage = user.get_total_available_storage()

#     message = f"☁️ *Storage Accounts*\n*Total Available*: {total_storage:.2f} MB\n\n"
#     if not accounts:
#         message += "No storage accounts connected.\nAdd one below!"
#     for acc in accounts:
#         message += (
#             f"• *{acc['provider_type'].replace('_', ' ').title()}*\n"
#             f"  Email: {acc['email']}\n"
#             f"  Status: {acc['status']}\n"
#             f"  Storage: {acc['free_mb']:.2f} MB free / {acc['total_mb']:.2f} MB\n"
#         )
#         if acc["status"] == "active":
#             message += f"  [Delete](delete_storage_{acc['id']})\n\n"
#         else:
#             message += "\n"

#     keyboard = [
#         [InlineKeyboardButton("➕ Add Storage", callback_data="add_storage")],
#         [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#     ]
#     await query.message.reply_text(
#         message,
#         parse_mode="Markdown",
#         reply_markup=InlineKeyboardMarkup(keyboard),
#         disable_web_page_preview=True,
#     )
#     logger.info(f"Displayed storage accounts for {user.email}")


# async def add_storage_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await update.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     email = update.message.text.strip()
#     if email.lower() == "cancel":
#         await update.message.reply_text(
#             "❌ *Cancelled adding storage.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     if not validate_email(email):
#         await update.message.reply_text(
#             "⚠️ *Invalid email format.*\nEnter a valid email.", parse_mode="Markdown"
#         )
#         return ADD_STORAGE_EMAIL

#     provider_type = session.get("storage_pending_provider")
#     logger.debug(f"Retrieved provider_type from session: {provider_type}")
#     if not provider_type:
#         logger.error("No provider_type found in session")
#         await update.message.reply_text(
#             "⚠️ *Session expired or no provider selected.*\nPlease select a provider again.",
#             parse_mode="Markdown",
#             reply_markup=InlineKeyboardMarkup([
#                 [
#                     InlineKeyboardButton("➕ Add Storage", callback_data="add_storage"),
#                     InlineKeyboardButton("🏠 Home", callback_data="main_menu"),
#                 ]
#             ]),
#         )
#         return ConversationHandler.END

#     user = User.get_user_by_email(session["email"])
#     if any(
#         acc["email"] == email and acc["provider_type"] == provider_type
#         for acc in user.storage_accounts
#     ):
#         await update.message.reply_text(
#             "⚠️ *Account already added.*", parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     account = user.add_storage_account(provider_type, email, status="initializing")
#     if not user.save():
#         await update.message.reply_text(
#             "⚠️ *Failed to initialize storage.*", parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     session["pending_storage_account"] = account["id"]
#     save_user_session(user_id, session)

#     auth_url = None
#     if provider_type == "google_drive":
#         google_client_id = os.getenv("GOOGLE_CLIENT_ID")
#         google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
#         if not google_client_id or not google_redirect_uri:
#             logger.error(
#                 f"Missing Google Drive credentials: GOOGLE_CLIENT_ID={google_client_id}, GOOGLE_REDIRECT_URI={google_redirect_uri}"
#             )
#             await update.message.reply_text(
#                 "⚠️ *Google Drive configuration error.* Please contact support.",
#                 parse_mode="Markdown",
#                 reply_markup=build_main_menu(),
#             )
#             return ConversationHandler.END
#         auth_url = (
#             f"https://accounts.google.com/o/oauth2/auth?"
#             f"client_id={google_client_id}&"
#             f"redirect_uri={google_redirect_uri}&"
#             f"scope=https://www.googleapis.com/auth/drive&"
#             f"response_type=code&"
#             f"state={account['id']}&"
#             f"access_type=offline&"
#             f"prompt=consent&"
#             f"login_hint={email}"
#         )
#         logger.debug(f"Generated Google Drive auth_url: {auth_url}")
#     elif provider_type == "dropbox":
#         dropbox_app_key = os.getenv("DROPBOX_APP_KEY")
#         dropbox_redirect_uri = os.getenv("DROPBOX_REDIRECT_URI")
#         if not dropbox_app_key or not dropbox_redirect_uri:
#             logger.error(
#                 f"Missing Dropbox credentials: DROPBOX_APP_KEY={dropbox_app_key}, DROPBOX_REDIRECT_URI={dropbox_redirect_uri}"
#             )
#             await update.message.reply_text(
#                 "⚠️ *Dropbox configuration error.* Please contact support.",
#                 parse_mode="Markdown",
#                 reply_markup=build_main_menu(),
#             )
#             return ConversationHandler.END
#         auth_url = (
#             f"https://www.dropbox.com/oauth2/authorize?"
#             f"client_id={dropbox_app_key}&"
#             f"redirect_uri={dropbox_redirect_uri}&"
#             f"response_type=code&"
#             f"state={account['id']}&"
#             f"token_access_type=offline"
#         )
#         logger.debug(f"Generated Dropbox auth_url: {auth_url}")
#     else:
#         logger.error(f"Invalid provider type: {provider_type}")
#         await update.message.reply_text(
#             f"⚠️ *Invalid provider: {provider_type}.* Please select a valid provider.",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     if auth_url:
#         try:
#             keyboard = [
#                 [
#                     InlineKeyboardButton(
#                         f"Connect {provider_type.replace('_', ' ').title()}",
#                         url=auth_url,
#                     )
#                 ],
#                 [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
#             ]
#             await update.message.reply_text(
#                 f"🔗 *Connect {provider_type.replace('_', ' ').title()}*\n"
#                 "1. Click the button below to authorize.\n"
#                 "2. Return here after authorization.\n"
#                 "3. Check *Storage Accounts* for status.",
#                 parse_mode="Markdown",
#                 reply_markup=InlineKeyboardMarkup(keyboard),
#             )
#             await send_notification(
#                 user_id,
#                 f"🔗 *Connect {provider_type.replace('_', ' ').title()}*: Authorize using the provided link.",
#             )
#             logger.info(f"Sent authorization URL for {provider_type} to {user.email}")
#             return ConversationHandler.END
#         except telegram_error.BadRequest as e:
#             logger.error(f"Failed to send auth URL for {provider_type}: {str(e)}")
#             await update.message.reply_text(
#                 "⚠️ *Failed to send authorization link.* Please try again or contact support.",
#                 parse_mode="Markdown",
#                 reply_markup=build_main_menu(),
#             )
#             return ConversationHandler.END
#     else:
#         logger.error(f"Failed to generate auth_url for provider: {provider_type}")
#         await update.message.reply_text(
#             "⚠️ *Failed to generate authorization URL.* Please contact support.",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END


# async def delete_storage_account(query, context, account_id):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     account = next(
#         (acc for acc in user.storage_accounts if acc["id"] == account_id), None
#     )
#     if not account:
#         await query.message.reply_text("⚠️ *Account not found.*", parse_mode="Markdown")
#         return

#     user.storage_accounts = [
#         acc for acc in user.storage_accounts if acc["id"] != account_id
#     ]
#     if not user.save():
#         await query.message.reply_text(
#             "⚠️ *Failed to delete storage account.*", parse_mode="Markdown"
#         )
#         return

#     await query.message.reply_text(
#         f"✅ *{account['provider_type'].replace('_', ' ').title()} account deleted.*",
#         parse_mode="Markdown",
#         reply_markup=build_main_menu(),
#     )
#     logger.info(f"Deleted storage account {account_id} for {user.email}")
#     await send_notification(
#         user_id,
#         f"🗑️ *{account['provider_type'].replace('_', ' ').title()} account deleted.*",
#     )


# async def preview_file(query, context, file_id):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     file = next((f for f in File.get_files(user.email) if f["id"] == file_id), None)
#     if not file:
#         await query.message.reply_text("⚠️ *File not found.*", parse_mode="Markdown")
#         return

#     await query.message.reply_text("⏳ *Preparing preview…*", parse_mode="Markdown")
#     temp_dir = tempfile.gettempdir()
#     output_path = os.path.join(temp_dir, file["filename"])
#     try:
#         file_manager = FileManager(user)
#         file_manager.download_file(
#             file["filename"], file["chunk_ids"], output_path, user.email
#         )
#         if not os.path.exists(output_path):
#             raise FileNotFoundError("File reconstruction failed")

#         base_filename = "_".join(file["filename"].split("_")[:-1])
#         mime_type = mimetypes.guess_type(base_filename)[0] or "application/octet-stream"

#         if mime_type.startswith("image/"):
#             img = Image.open(output_path)
#             img.thumbnail((200, 200))
#             thumb_io = io.BytesIO()
#             img.save(thumb_io, format="JPEG", quality=85)
#             thumb_io.seek(0)
#             await query.message.reply_photo(
#                 photo=thumb_io, caption=f"🖼️ *{base_filename}*", parse_mode="Markdown"
#             )
#         elif mime_type.startswith("video/"):
#             with open(output_path, "rb") as f:
#                 await query.message.reply_video(
#                     video=f, caption=f"🎥 *{base_filename}*", parse_mode="Markdown"
#                 )
#         elif mime_type.startswith("audio/"):
#             with open(output_path, "rb") as f:
#                 await query.message.reply_audio(
#                     audio=f, caption=f"🎵 *{base_filename}*", parse_mode="Markdown"
#                 )
#         elif mime_type in ["application/pdf", "text/plain"]:
#             content = ai_agent.extract_text(output_path)
#             snippet = content[:200] + "..." if len(content) > 200 else content
#             await query.message.reply_text(
#                 f"📄 *{base_filename}*\n\n*Preview:*\n{snippet}", parse_mode="Markdown"
#             )
#         else:
#             with open(output_path, "rb") as f:
#                 await query.message.reply_document(
#                     document=f,
#                     filename=base_filename,
#                     caption=f"📄 *{base_filename}*",
#                     parse_mode="Markdown",
#                 )
#         logger.info(f"Previewed {file['filename']} for {user.email}")
#         await query.message.reply_text(
#             "✅ *Preview complete.*\nWhat’s next?",
#             parse_mode="Markdown",
#             reply_markup=build_file_actions(file_id),
#         )
#     except Exception as e:
#         logger.error(f"Preview failed for {file_id}: {str(e)}", exc_info=True)
#         await query.message.reply_text(f"⚠️ *Error: {str(e)}*", parse_mode="Markdown")
#     finally:
#         if os.path.exists(output_path):
#             try:
#                 os.remove(output_path)
#             except Exception as e:
#                 logger.error(f"Cleanup failed for {output_path}: {str(e)}")


# async def download_file(query, context, file_id):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     file = next((f for f in File.get_files(user.email) if f["id"] == file_id), None)
#     if not file:
#         await query.message.reply_text("⚠️ *File not found.*", parse_mode="Markdown")
#         return

#     await query.message.reply_text("⏳ *Downloading file…*", parse_mode="Markdown")
#     temp_dir = tempfile.gettempdir()
#     output_path = os.path.join(temp_dir, file["filename"])
#     try:
#         file_manager = FileManager(user)
#         file_manager.download_file(
#             file["filename"], file["chunk_ids"], output_path, user.email
#         )
#         if not os.path.exists(output_path):
#             raise FileNotFoundError("File reconstruction failed")

#         base_filename = "_".join(file["filename"].split("_")[:-1])
#         with open(output_path, "rb") as f:
#             await query.message.reply_document(
#                 document=f,
#                 filename=base_filename,
#                 caption=f"📥 *{base_filename}*",
#                 parse_mode="Markdown",
#             )
#         logger.info(f"Downloaded {file['filename']} for {user.email}")
#         await query.message.reply_text(
#             "✅ *Download complete.*\nWhat’s next?",
#             parse_mode="Markdown",
#             reply_markup=build_file_actions(file_id),
#         )
#     except Exception as e:
#         logger.error(f"Download failed for {file_id}: {str(e)}", exc_info=True)
#         await query.message.reply_text(f"⚠️ *Error: {str(e)}*", parse_mode="Markdown")
#     finally:
#         if os.path.exists(output_path):
#             try:
#                 os.remove(output_path)
#             except Exception as e:
#                 logger.error(f"Cleanup failed for {output_path}: {str(e)}")


# async def delete_file(query, context, file_id):
#     user_id = str(query.from_user.id)
#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await query.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return

#     user = User.get_user_by_email(session["email"])
#     file = next((f for f in File.get_files(user.email) if f["id"] == file_id), None)
#     if not file:
#         await query.message.reply_text("⚠️ *File not found.*", parse_mode="Markdown")
#         return

#     file_manager = FileManager(user)
#     success = file_manager.delete_file(file["filename"], file["chunk_ids"], user.email)
#     if not success:
#         await query.message.reply_text(
#             "⚠️ *Failed to delete file.*", parse_mode="Markdown"
#         )
#         return

#     user.update_storage_used(-file["size_mb"])
#     user.save()
#     File.delete_file(file_id)
#     ai_agent.delete_content(file_id)
#     filename = session.get("file_map", {}).get(file_id, "Unknown")
#     await query.message.reply_text(
#         f"✅ *File {filename} deleted.*",
#         parse_mode="Markdown",
#         reply_markup=build_main_menu(),
#     )
#     logger.info(f"Deleted {file['filename']} for {user.email}")
#     await send_notification(user_id, f"🗑️ *File {filename} deleted.*")


# async def ai_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     if rate_limit_exceeded(user_id):
#         await update.message.reply_text(
#             "⚠️ *Too many requests.* Please wait a minute and try again.",
#             parse_mode="Markdown",
#         )
#         return ConversationHandler.END

#     session = get_user_session(user_id)
#     if not session.get("logged_in"):
#         await update.message.reply_text(
#             "⚠️ *Please login first.*",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END

#     query = update.message.text.strip()
#     if query.lower() == "stop ai chat":
#         session.pop("ai_context", None)
#         save_user_session(user_id, session)
#         await update.message.reply_text(
#             "❌ *AI chat ended.*\nWhat’s next?",
#             parse_mode="Markdown",
#             reply_markup=build_main_menu(),
#         )
#         return ConversationHandler.END
#     elif query.lower() == "clear ai history":
#         session["ai_context"] = []
#         save_user_session(user_id, session)
#         await update.message.reply_text(
#             "🧹 *AI chat history cleared.*\nAsk a new question:",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardMarkup(
#                 [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
#             ),
#         )
#         return AI_QUERY

#     await update.message.reply_text(
#         "⏳ *Processing your query…*", parse_mode="Markdown"
#     )
#     user = User.get_user_by_email(session["email"])
#     files = File.get_files(user.email) or []
#     try:
#         ai_context = session.get("ai_context", [])
#         ai_context.append({"role": "user", "content": query})
#         ai_context = ai_context[-10:]  # Limit to last 10 messages

#         full_query = "Conversation history:\n"
#         for msg in ai_context:
#             role = "User" if msg["role"] == "user" else "Assistant"
#             full_query += f"{role}: {msg['content']}\n"
#         full_query += f"Current question: {query}"

#         answer = ai_agent.answer_query(full_query, user.email, files)
#         if not answer or "unknown" in answer.lower():
#             web_results = await ai_agent.search_web(
#                 query
#             )  # Requires implementation in ai_agent.py
#             answer = (
#                 f"No specific file content found. Based on web search:\n{web_results}"
#             )

#         ai_context.append({"role": "assistant", "content": answer})
#         session["ai_context"] = ai_context
#         save_user_session(user_id, session)

#         await update.message.reply_text(
#             f"🤖 *AI Response*\n{answer}\n\nAsk another question or stop:",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardMarkup(
#                 [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
#             ),
#         )
#         logger.info(f"AI query answered for {user.email}: {query}")
#     except Exception as e:
#         logger.error(f"AI query failed: {str(e)}", exc_info=True)
#         answer = "I couldn't process that query. Please try rephrasing or ask something else."
#         await update.message.reply_text(
#             f"🤖 *AI Response*\n{answer}\n\nAsk another question or stop:",
#             parse_mode="Markdown",
#             reply_markup=ReplyKeyboardMarkup(
#                 [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
#             ),
#         )
#     return AI_QUERY


# async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     session = get_user_session(user_id)
#     session.pop("ai_context", None)
#     session.pop("storage_pending_provider", None)  # Clear provider on cancel
#     save_user_session(user_id, session)
#     await update.message.reply_text(
#         "❌ *Operation cancelled.*",
#         parse_mode="Markdown",
#         reply_markup=build_main_menu(),
#     )
#     return ConversationHandler.END


# async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     logger.error(f"Update {update} caused error {context.error}", exc_info=True)
#     if update and update.message:
#         await update.message.reply_text(
#             "⚠️ *An unexpected error occurred.* Please try again later.",
#             parse_mode="Markdown",
#         )


# def main():
#     try:
#         logger.info("Starting Telegram bot application")
#         logger.debug(f"Environment variables - GOOGLE_CLIENT_ID: {os.getenv('GOOGLE_CLIENT_ID')}")
#         logger.debug(f"Environment variables - GOOGLE_REDIRECT_URI: {os.getenv('GOOGLE_REDIRECT_URI')}")
#         logger.debug(f"Environment variables - DROPBOX_APP_KEY: {os.getenv('DROPBOX_APP_KEY')}")
#         logger.debug(f"Environment variables - DROPBOX_REDIRECT_URI: {os.getenv('DROPBOX_REDIRECT_URI')}")
#         application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

#         application.add_handler(CommandHandler("start", start))
#         application.add_handler(CommandHandler("help", help_command))
#         application.add_handler(InlineQueryHandler(inline_query))

#         conv_handler = ConversationHandler(
#             entry_points=[
#                 CallbackQueryHandler(button_callback),
#             ],
#             states={
#                 REGISTRATION: [
#                     MessageHandler(filters.TEXT & ~filters.COMMAND, registration)
#                 ],
#                 REGISTRATION_OTP: [
#                     MessageHandler(filters.TEXT & ~filters.COMMAND, registration_otp)
#                 ],
#                 LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, login)],
#                 LOGIN_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_otp)],
#                 UPLOAD_FILE: [
#                     MessageHandler(filters.Document.ALL | filters.TEXT, upload_file)
#                 ],
#                 ADD_STORAGE_EMAIL: [
#                     MessageHandler(filters.TEXT & ~filters.COMMAND, add_storage_email)
#                 ],
#                 AI_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_query)],
#                 SEARCH_FILES: [
#                     MessageHandler(filters.TEXT & ~filters.COMMAND, search_files)
#                 ],
#             },
#             fallbacks=[
#                 CommandHandler("cancel", cancel),
#                 CallbackQueryHandler(button_callback, pattern="^cancel$"),
#             ],
#             per_message=False,
#         )

#         application.add_handler(conv_handler)
#         application.add_error_handler(error_handler)
#         logger.info("Starting polling")
#         application.run_polling()
#     except Exception as e:
#         logger.error(f"Error in main: {str(e)}", exc_info=True)


# if __name__ == "__main__":
#     main()













import os
import logging
import uuid
import tempfile
import re
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    InlineQueryHandler,
    filters,
    ContextTypes,
)
from telegram import error as telegram_error
from werkzeug.utils import secure_filename
from firebase_admin import firestore
from models import User, File, UserRepository
from file_manager import FileManager
from ai_agent import AIAgent
import mimetypes
import aiohttp
from PIL import Image
import io
from cachetools import TTLCache

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for detailed tracing
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(stream=sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FLASK_APP_URL = os.getenv("FLASK_APP_URL", "http://localhost:5000")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")

# Initialize Firestore
db = firestore.client()

# Initialize AI Agent
ai_agent = AIAgent()

# Conversation states
(
    REGISTRATION,
    REGISTRATION_OTP,
    LOGIN,
    LOGIN_OTP,
    UPLOAD_FILE,
    ADD_STORAGE,
    ADD_STORAGE_EMAIL,
    AI_QUERY,
    DELETE_FILE,
    SEARCH_FILES,
) = range(10)

# Rate limiting
RATE_LIMIT = 30  # Max commands per minute
USER_REQUESTS = {}  # Track requests per user
SESSION_CACHE = TTLCache(maxsize=1000, ttl=86400)  # 24-hour session cache


def rate_limit_exceeded(user_id: str) -> bool:
    now = datetime.utcnow()
    if user_id not in USER_REQUESTS:
        USER_REQUESTS[user_id] = []
    USER_REQUESTS[user_id] = [
        t for t in USER_REQUESTS[user_id] if now - t < timedelta(minutes=1)
    ]
    if len(USER_REQUESTS[user_id]) >= RATE_LIMIT:
        return True
    USER_REQUESTS[user_id].append(now)
    return False


# Session management
def get_user_session(telegram_id: str) -> dict:
    if telegram_id in SESSION_CACHE:
        logger.debug(f"Retrieved session from cache for {telegram_id}: {SESSION_CACHE[telegram_id]}")
        return SESSION_CACHE[telegram_id]
    try:
        doc_ref = db.collection("telegram_sessions").document(str(telegram_id))
        doc = doc_ref.get()
        session = doc.to_dict() if doc.exists else {}
        SESSION_CACHE[telegram_id] = session
        logger.debug(f"Retrieved session from Firestore for {telegram_id}: {session}")
        return session
    except Exception as e:
        logger.error(f"Failed to get session for {telegram_id}: {str(e)}")
        return {}


def save_user_session(telegram_id: str, data: dict):
    data["last_updated"] = datetime.utcnow().timestamp()
    SESSION_CACHE[telegram_id] = data
    logger.debug(f"Saved session to cache for {telegram_id}: {data}")
    try:
        db.collection("telegram_sessions").document(str(telegram_id)).set(data)
        logger.debug(f"Saved session to Firestore for {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to save session to Firestore for {telegram_id}: {str(e)}")


def clear_user_session(telegram_id: str):
    if telegram_id in SESSION_CACHE:
        del SESSION_CACHE[telegram_id]
        logger.debug(f"Cleared session cache for {telegram_id}")
    try:
        db.collection("telegram_sessions").document(str(telegram_id)).delete()
        logger.debug(f"Cleared session from Firestore for {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to clear session for {telegram_id}: {str(e)}")


# Helper functions
def validate_email(email: str) -> bool:
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(pattern, email))


def build_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("📤 Quick Upload", callback_data="upload_file"),
            InlineKeyboardButton("📂 Recent Files", callback_data="recent_files"),
        ],
        [
            InlineKeyboardButton("🤖 Ask AI", callback_data="ai_ask"),
            InlineKeyboardButton("🔍 Search Files", callback_data="search_files"),
        ],
        [
            InlineKeyboardButton(
                "☁️ Storage Accounts", callback_data="storage_accounts"
            ),
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
        ],
        [InlineKeyboardButton("🚪 Logout", callback_data="logout")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_quick_actions():
    keyboard = [
        [InlineKeyboardButton("📤 Upload File", callback_data="upload_file")],
        [InlineKeyboardButton("📂 My Files", callback_data="list_files")],
        [InlineKeyboardButton("🤖 Ask AI", callback_data="ai_ask")],
        [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_file_category_menu():
    keyboard = [
        [InlineKeyboardButton("📚 All Files", callback_data="category_all_1")],
        [InlineKeyboardButton("🖼️ Images", callback_data="category_images_1")],
        [InlineKeyboardButton("📄 Documents", callback_data="category_documents_1")],
        [InlineKeyboardButton("🎥 Videos", callback_data="category_videos_1")],
        [InlineKeyboardButton("🎵 Audio", callback_data="category_audio_1")],
        [InlineKeyboardButton("🔢 Other", callback_data="category_other_1")],
        [InlineKeyboardButton("📅 Sort by Date", callback_data="sort_date_1")],
        [InlineKeyboardButton("📏 Sort by Size", callback_data="sort_size_1")],
        [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_file_actions(file_id: str):
    keyboard = [
        [
            InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{file_id}"),
            InlineKeyboardButton("📥 Download", callback_data=f"download_{file_id}"),
        ],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{file_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="list_files")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_pagination_buttons(page: int, total_pages: int, category: str):
    keyboard = []
    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{category}_{page-1}")
        )
    if page < total_pages:
        row.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"page_{category}_{page+1}")
        )
    if row:
        keyboard.append(row)
    return keyboard


async def send_notification(telegram_id: str, message: str):
    async with Application.builder().token(TELEGRAM_BOT_TOKEN).build() as app:
        try:
            await app.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode="Markdown",
                disable_notification=False,
            )
            logger.info(f"Sent notification to {telegram_id}: {message}")
        except Exception as e:
            logger.error(f"Failed to send notification to {telegram_id}: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    try:
        logger.info(f"Received /start from user {user_id}")
        session = get_user_session(user_id)
        if session.get("logged_in"):
            user = User.get_user_by_email(session["email"])
            if user:
                await update.message.reply_text(
                    f"🎉 *Welcome back, {user.first_name}!*\nChoose an action to get started:",
                    parse_mode="Markdown",
                    reply_markup=build_main_menu(),
                )
                logger.info(f"User {user.email} already logged in")
                return ConversationHandler.END
        keyboard = [
            [InlineKeyboardButton("📝 Register", callback_data="register")],
            [InlineKeyboardButton("🔑 Login", callback_data="login")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        ]
        await update.message.reply_text(
            "🌟 *Welcome to MegaCloud Bot!*\nStore files, connect cloud storage, and chat with AI.\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        logger.info("Sent welcome message for /start")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "⚠️ *Something went wrong.* Please try again later.", parse_mode="Markdown"
        )
        return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 *MegaCloud Bot Help*\n\n"
        "Manage your files and interact with AI:\n"
        "• /start - Begin or log in\n"
        "• /help - Show this guide\n"
        "• 📤 *Upload File*: Send files up to 100MB\n"
        "• 📂 *My Files*: Browse by category or sort\n"
        "• 🔍 *Search Files*: Find files by name\n"
        "• 🤖 *Ask AI*: Query about files or general topics\n"
        "• ☁️ *Storage Accounts*: Add Google Drive/Dropbox\n"
        "• 📊 *Stats*: View storage usage\n"
        "\nUse inline buttons or reply keyboards to navigate!"
    )
    await update.message.reply_text(
        help_text, parse_mode="Markdown", reply_markup=build_main_menu()
    )
    logger.info(f"Displayed help for user {update.effective_user.id}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if rate_limit_exceeded(user_id):
        await query.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    if query.data == "register":
        await query.message.reply_text(
            "📝 *Register*\nEnter: First Name Last Name Username Email\nExample: John Doe johndoe john@example.com",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return REGISTRATION
    elif query.data == "login":
        await query.message.reply_text(
            "🔑 *Login*\nEnter your email or username:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return LOGIN
    elif query.data == "main_menu":
        await query.message.reply_text(
            "🌟 *MegaCloud Menu*\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END
    elif query.data == "upload_file":
        await query.message.reply_text(
            "📤 *Upload File*\nSend one or more files (max 100MB each):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True),
        )
        return UPLOAD_FILE
    elif query.data == "recent_files":
        await list_files_by_category(query, context, "All", 1, sort_by="date")
        return ConversationHandler.END
    elif query.data == "list_files":
        await query.message.reply_text(
            "📂 *My Files*\nSelect a category or sort option:",
            parse_mode="Markdown",
            reply_markup=build_file_category_menu(),
        )
        return ConversationHandler.END
    elif query.data.startswith("category_"):
        category, page = query.data.split("_")[1].capitalize(), int(
            query.data.split("_")[2]
        )
        if category == "All":
            category = "All"
        await list_files_by_category(query, context, category, page)
        return ConversationHandler.END
    elif query.data.startswith("sort_"):
        sort_by, page = query.data.split("_")[1], int(query.data.split("_")[2])
        await list_files_by_category(query, context, "All", page, sort_by=sort_by)
        return ConversationHandler.END
    elif query.data.startswith("page_"):
        category, page = query.data.split("_")[1].capitalize(), int(
            query.data.split("_")[2]
        )
        if category == "All":
            category = "All"
        sort_by = session.get("sort_by", "name")
        await list_files_by_category(query, context, category, page, sort_by=sort_by)
        return ConversationHandler.END
    elif query.data == "search_files":
        await query.message.reply_text(
            "🔍 *Search Files*\nEnter your search query:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True),
        )
        return SEARCH_FILES
    elif query.data == "stats":
        await show_stats(query, context)
        return ConversationHandler.END
    elif query.data == "storage_accounts":
        await manage_storage_accounts(query, context)
        return ConversationHandler.END
    elif query.data == "ai_ask":
        session["ai_context"] = []
        save_user_session(user_id, session)
        await query.message.reply_text(
            "🤖 *Chat with AI*\nAsk about files (e.g., 'Summarize my PDF') or general questions (e.g., 'What is cloud storage?').",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
            ),
        )
        return AI_QUERY
    elif query.data == "logout":
        clear_user_session(user_id)
        await query.message.reply_text(
            "👋 *Logged out successfully!*\nUse /start to begin again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    elif query.data.startswith("preview_"):
        file_id = query.data.split("_")[1]
        await preview_file(query, context, file_id)
        return ConversationHandler.END
    elif query.data.startswith("download_"):
        file_id = query.data.split("_")[1]
        await download_file(query, context, file_id)
        return ConversationHandler.END
    elif query.data.startswith("delete_"):
        file_id = query.data.split("_")[1]
        filename = session.get("file_map", {}).get(file_id, "Unknown")
        await query.message.reply_text(
            f"🗑️ *Delete File*\nAre you sure you want to delete *{filename}*?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Yes", callback_data=f"confirm_delete_{file_id}"
                        )
                    ],
                    [InlineKeyboardButton("❌ No", callback_data="list_files")],
                ]
            ),
        )
        return ConversationHandler.END
    elif query.data.startswith("confirm_delete_"):
        file_id = query.data.split("_")[2]
        await delete_file(query, context, file_id)
        return ConversationHandler.END
    elif query.data == "add_storage":
        keyboard = [
            [
                InlineKeyboardButton(
                    "Google Drive", callback_data="provider_google_drive"
                )
            ],
            [InlineKeyboardButton("Dropbox", callback_data="provider_dropbox")],
            [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
        ]
        await query.message.reply_text(
            "☁️ *Add Storage*\nSelect a provider:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return ConversationHandler.END
    elif query.data.startswith("provider_"):
        logger.debug(f"Provider selection - query.data: {query.data}")
        try:
            provider_type = query.data.split("_")[1]
            logger.debug(f"Parsed provider_type: {provider_type}")
            if provider_type not in ["google_drive", "dropbox"]:
                logger.error(f"Invalid provider_type parsed: {provider_type}")
                await query.message.reply_text(
                    "⚠️ *Invalid provider selected.* Please try again.",
                    parse_mode="Markdown",
                    reply_markup=build_main_menu(),
                )
                return ConversationHandler.END
            session["storage_pending_provider"] = provider_type
            save_user_session(user_id, session)
            logger.debug(f"Saved session with storage_pending_provider: {provider_type}")
            await query.message.reply_text(
                f"☁️ *Add {provider_type.replace('_', ' ').title()}*\nEnter the account email:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True),
            )
            return ADD_STORAGE_EMAIL
        except IndexError as e:
            logger.error(f"Failed to parse provider from query.data: {query.data}, error: {str(e)}")
            await query.message.reply_text(
                "⚠️ *Error selecting provider.* Please try again.",
                parse_mode="Markdown",
                reply_markup=build_main_menu(),
            )
            return ConversationHandler.END
    elif query.data.startswith("delete_storage_"):
        account_id = query.data.split("_")[2]
        await delete_storage_account(query, context, account_id)
        return ConversationHandler.END
    elif query.data == "help":
        await help_command(query, context)
        return ConversationHandler.END
    elif query.data == "cancel":
        await cancel(query, context)
        return ConversationHandler.END


async def registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    text = update.message.text.strip()
    if text.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Registration cancelled.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    try:
        parts = text.split()
        if len(parts) != 4:
            raise ValueError("Invalid format")
        first_name, last_name, username, email = parts
        if not validate_email(email):
            await update.message.reply_text(
                "⚠️ *Invalid email format.*\nEnter a valid email.", parse_mode="Markdown"
            )
            return REGISTRATION
        if User.get_user_by_email(email):
            await update.message.reply_text(
                "⚠️ *Email already registered.*\nTry logging in.", parse_mode="Markdown"
            )
            return ConversationHandler.END
        if User.get_user_by_username(username):
            await update.message.reply_text(
                "⚠️ *Username taken.*\nChoose another.", parse_mode="Markdown"
            )
            return REGISTRATION
        user = User(
            email=email, first_name=first_name, last_name=last_name, username=username
        )
        otp = user.generate_otp()
        if user.save() and AuthManager.send_otp_email(email, otp):
            session = {"email": email, "telegram_id": user_id, "notifications": True}
            save_user_session(user_id, session)
            await update.message.reply_text(
                "📧 *OTP sent!*\nEnter the 6-digit OTP from your email:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔄 Resend OTP", callback_data="resend_otp_register"
                            )
                        ],
                        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                    ]
                ),
            )
            await send_notification(
                user_id, f"📧 *OTP sent to {email}.* Check your inbox!"
            )
            return REGISTRATION_OTP
        else:
            await update.message.reply_text(
                "⚠️ *Failed to send OTP.*\nPlease try again.", parse_mode="Markdown"
            )
            return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "⚠️ *Invalid format.*\nEnter: First Name Last Name Username Email\nExample: John Doe johndoe john@example.com",
            parse_mode="Markdown",
        )
        return REGISTRATION
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ *Error: {str(e)}*\nPlease try again.", parse_mode="Markdown"
        )
        return REGISTRATION


async def registration_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    otp = update.message.text.strip()
    if otp.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Registration cancelled.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    email = session.get("email")
    if not email:
        await update.message.reply_text(
            "⚠️ *Session expired.*\nStart registration again.", parse_mode="Markdown"
        )
        return ConversationHandler.END

    success, message = AuthManager.verify_otp(email, otp)
    if success:
        user = User.get_user_by_email(email)
        session["logged_in"] = True
        save_user_session(user_id, session)
        await update.message.reply_text(
            f"✅ *Registration successful!*\nWelcome, *{user.first_name}!*\nWhat’s next?",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        logger.info(f"User {email} registered via Telegram")
        await send_notification(
            user_id, f"🎉 *Welcome to MegaCloud, {user.first_name}!*"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            f"⚠️ *{message}*\nEnter the OTP again:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Resend OTP", callback_data="resend_otp_register"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                ]
            ),
        )
        return REGISTRATION_OTP


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    identifier = update.message.text.strip()
    if identifier.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Login cancelled.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    user = User.get_user_by_email(identifier) or User.get_user_by_username(identifier)
    if not user:
        await update.message.reply_text(
            "⚠️ *User not found.*\nPlease register first.", parse_mode="Markdown"
        )
        return ConversationHandler.END

    otp = user.generate_otp()
    if user.save() and AuthManager.send_otp_email(user.email, otp):
        session = get_user_session(user_id)
        session.update(
            {
                "email": user.email,
                "telegram_id": user_id,
            }
        )
        save_user_session(user_id, session)
        await update.message.reply_text(
            "📧 *OTP sent!*\nEnter the 6-digit OTP from your email:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Resend OTP", callback_data="resend_otp_login"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                ]
            ),
        )
        await send_notification(
            user_id, f"📧 *OTP sent to {user.email}.* Check your inbox!"
        )
        return LOGIN_OTP
    else:
        await update.message.reply_text(
            "⚠️ *Failed to send OTP.*\nPlease try again.", parse_mode="Markdown"
        )
        return ConversationHandler.END


async def login_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    otp = update.message.text.strip()
    if otp.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Login cancelled.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    email = session.get("email")
    if not email:
        await update.message.reply_text(
            "⚠️ *Session expired.*\nStart login again.", parse_mode="Markdown"
        )
        return ConversationHandler.END

    success, message = AuthManager.verify_otp(email, otp)
    if success:
        user = User.get_user_by_email(email)
        session["logged_in"] = True
        save_user_session(user_id, session)
        await update.message.reply_text(
            f"✅ *Login successful!*\nWelcome back, *{user.first_name}!*\nWhat’s next?",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        logger.info(f"User {email} logged in via Telegram")
        await send_notification(user_id, f"👋 *Welcome back, {user.first_name}!*")
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            f"⚠️ *{message}*\nEnter the OTP again:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Resend OTP", callback_data="resend_otp_login"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                ]
            ),
        )
        return LOGIN_OTP


async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await update.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    if update.message.text and update.message.text.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Upload cancelled.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    if not update.message.document:
        await update.message.reply_text(
            "⚠️ *Please send a file.*\nMax size: 100MB.", parse_mode="Markdown"
        )
        return UPLOAD_FILE

    documents = [update.message.document] if update.message.document else []
    if update.message.media_group_id:
        # Handle media group (multiple files)
        if "media_group" not in context.user_data:
            context.user_data["media_group"] = []
        context.user_data["media_group"].append(update.message.document)
        return UPLOAD_FILE  # Wait for all files in the group

    # Process single file or media group
    documents = context.user_data.get("media_group", documents)
    context.user_data.pop("media_group", None)

    user = User.get_user_by_email(session["email"])
    file_manager = FileManager(user)
    uploaded_files = []

    for document in documents:
        if document.file_size > 100 * 1024 * 1024:
            await update.message.reply_text(
                f"⚠️ *{document.file_name} too large.*\nMax size: 100MB.",
                parse_mode="Markdown",
            )
            continue

        await update.message.reply_text(
            f"⏳ *Uploading {document.file_name}…*", parse_mode="Markdown"
        )
        try:
            file = await document.get_file()
            base_filename = secure_filename(document.file_name)
            unique_suffix = uuid.uuid4().hex[:8]
            storage_filename = f"{base_filename}_{unique_suffix}"
            temp_path = os.path.join(tempfile.gettempdir(), storage_filename)

            await file.download_to_drive(temp_path)
            file_size = os.path.getsize(temp_path)
            size_mb = file_size / (1024 * 1024)

            content = ai_agent.extract_text(temp_path)
            temp_file_id = str(uuid.uuid4())
            if content:
                ai_agent.store_content(temp_file_id, base_filename, content)

            chunk_ids = file_manager.upload_file(
                temp_path, storage_filename, user.email
            )
            if not chunk_ids:
                ai_agent.delete_content(temp_file_id)
                raise Exception("File upload to storage provider failed")

            file_obj = File(
                filename=storage_filename,
                user_email=user.email,
                chunk_ids=chunk_ids,
                size_mb=size_mb,
            )
            if not file_obj.save():
                ai_agent.delete_content(temp_file_id)
                raise Exception("Failed to save file metadata")

            if content:
                ai_agent.delete_content(temp_file_id)
                ai_agent.store_content(file_obj.id, base_filename, content)

            user.update_storage_used(size_mb)
            user.save()
            uploaded_files.append((file_obj.id, base_filename, size_mb))

            await send_notification(
                user_id,
                f"✅ *{base_filename}* ({size_mb:.2f} MB) uploaded successfully!",
            )
        except Exception as e:
            logger.error(
                f"Upload failed for {document.file_name}: {str(e)}", exc_info=True
            )
            await update.message.reply_text(
                f"⚠️ *Error uploading {document.file_name}: {str(e)}*",
                parse_mode="Markdown",
            )
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    logger.error(f"Cleanup failed for {temp_path}: {str(e)}")

    if uploaded_files:
        message = "✅ *Upload Complete!*\n"
        for file_id, filename, size_mb in uploaded_files:
            message += f"• *{filename}* ({size_mb:.2f} MB)\n"
        keyboard = [
            [InlineKeyboardButton("📤 Upload More", callback_data="upload_file")],
            [InlineKeyboardButton("📂 View Files", callback_data="list_files")],
            [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
        ]
        await update.message.reply_text(
            message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"Uploaded {len(uploaded_files)} files for {user.email}")
    return ConversationHandler.END


async def list_files_by_category(
    query, context, category: str, page: int = 1, sort_by: str = "name"
):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session["email"])
    files = File.get_files(user.email)
    if files is None:
        await query.message.reply_text(
            "⚠️ *Failed to retrieve files.*",
            parse_mode="Markdown",
            reply_markup=build_file_category_menu(),
        )
        return

    if category != "All":
        files = [f for f in files if f["category"] == category]

    if not files:
        await query.message.reply_text(
            f"📂 *No {category.lower()} files found.*",
            parse_mode="Markdown",
            reply_markup=build_file_category_menu(),
        )
        return

    # Sorting
    if sort_by == "date":
        files.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    elif sort_by == "size":
        files.sort(key=lambda x: x["size_mb"], reverse=True)
    else:
        files.sort(key=lambda x: "_".join(x["filename"].split("_")[:-1]).lower())

    session["sort_by"] = sort_by
    save_user_session(user_id, session)

    files_per_page = 5
    total_pages = (len(files) + files_per_page - 1) // files_per_page
    start_idx = (page - 1) * files_per_page
    end_idx = start_idx + files_per_page
    paginated_files = files[start_idx:end_idx]

    file_map = session.get("file_map", {})
    for f in paginated_files:
        f["display_filename"] = "_".join(f["filename"].split("_")[:-1])
        file_map[f["id"]] = f["display_filename"]
    session["file_map"] = file_map
    save_user_session(user_id, session)

    message = f"📂 *{category} Files (Page {page}/{total_pages})*\n\n"
    for f in paginated_files:
        message += f"📄 *{f['display_filename']}* ({f['size_mb']:.2f} MB)\nCategory: {f['category']}\n\n"

    pagination_buttons = build_pagination_buttons(page, total_pages, category)
    keyboard = pagination_buttons + [
        [InlineKeyboardButton("🔙 Categories", callback_data="list_files")],
        [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
    ]
    await query.message.reply_text(
        message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

    for f in paginated_files:
        await query.message.reply_text(
            f"📄 *{f['display_filename']}*",
            parse_mode="Markdown",
            reply_markup=build_file_actions(f["id"]),
        )
    logger.info(
        f"Listed {len(paginated_files)} {category.lower()} files for {user.email} (page {page}, sorted by {sort_by})"
    )


async def search_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await update.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    query = update.message.text.strip()
    if query.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Search cancelled.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    user = User.get_user_by_email(session["email"])
    files = File.get_files(user.email)
    if files is None:
        await update.message.reply_text(
            "⚠️ *Failed to retrieve files.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    filtered = [
        f
        for f in files
        if query.lower() in "_".join(f["filename"].split("_")[:-1]).lower()
    ]
    if not filtered:
        await update.message.reply_text(
            "📂 *No files match your search.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    file_map = session.get("file_map", {})
    for f in filtered:
        f["display_filename"] = "_".join(f["filename"].split("_")[:-1])
        file_map[f["id"]] = f["display_filename"]
    session["file_map"] = file_map
    save_user_session(user_id, session)

    message = f"🔍 *Search Results* ({len(filtered)} files)\n\n"
    for f in filtered:
        message += f"📄 *{f['display_filename']}* ({f['size_mb']:.2f} MB)\nCategory: {f['category']}\n\n"
    await update.message.reply_text(
        message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 Home", callback_data="main_menu")]]
        ),
    )

    for f in filtered:
        await update.message.reply_text(
            f"📄 *{f['display_filename']}*",
            parse_mode="Markdown",
            reply_markup=build_file_actions(f["id"]),
        )
    logger.info(
        f"Searched files for {user.email} with query '{query}': {len(filtered)} results"
    )
    return ConversationHandler.END


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    user_id = str(update.inline_query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await update.inline_query.answer(
            [], switch_pm_text="Please login first", switch_pm_parameter="login"
        )
        return

    user = User.get_user_by_email(session["email"])
    files = File.get_files(user.email) or []
    filtered = [
        f
        for f in files
        if query.lower() in "_".join(f["filename"].split("_")[:-1]).lower()
    ][:10]

    results = []
    for f in filtered:
        f["display_filename"] = "_".join(f["filename"].split("_")[:-1])
        results.append(
            InlineQueryResultArticle(
                id=f["id"],
                title=f["display_filename"],
                description=f"{f['size_mb']:.2f} MB | {f['category']}",
                input_message_content=InputTextMessageContent(
                    f"📄 *{f['display_filename']}* ({f['size_mb']:.2f} MB)\nCategory: {f['category']}",
                    parse_mode="Markdown",
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "👁️ Preview", callback_data=f"preview_{f['id']}"
                            ),
                            InlineKeyboardButton(
                                "📥 Download", callback_data=f"download_{f['id']}"
                            ),
                        ]
                    ]
                ),
            )
        )
    await update.inline_query.answer(results)
    logger.info(
        f"Inline query by {user.email}: '{query}' returned {len(results)} results"
    )


async def show_stats(query, context):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session["email"])
    files = File.get_files(user.email)
    if files is None:
        await query.message.reply_text(
            "⚠️ *Failed to retrieve stats.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    total_files = len(files)
    total_size = sum(f["size_mb"] for f in files) if files else 0.0
    total_available = user.get_total_available_storage()
    message = (
        f"📊 *Storage Stats*\n"
        f"• Total Files: {total_files}\n"
        f"• Storage Used: {total_size:.2f} MB\n"
        f"• Total Available: {total_available:.2f} MB\n"
    )
    if total_available < 100:
        await send_notification(
            user_id, f"⚠️ *Low storage warning!* Only {total_available:.2f} MB left."
        )
    await query.message.reply_text(
        message, parse_mode="Markdown", reply_markup=build_main_menu()
    )
    logger.info(f"Displayed stats for {user.email}")


async def manage_storage_accounts(query, context):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session["email"])
    accounts = user.get_storage_accounts_info()
    total_storage = user.get_total_available_storage()

    message = f"☁️ *Storage Accounts*\n*Total Available*: {total_storage:.2f} MB\n\n"
    if not accounts:
        message += "No storage accounts connected.\nAdd one below!"
    for acc in accounts:
        message += (
            f"• *{acc['provider_type'].replace('_', ' ').title()}*\n"
            f"  Email: {acc['email']}\n"
            f"  Status: {acc['status']}\n"
            f"  Storage: {acc['free_mb']:.2f} MB free / {acc['total_mb']:.2f} MB\n"
        )
        if acc["status"] == "active":
            message += f"  [Delete](delete_storage_{acc['id']})\n\n"
        else:
            message += "\n"

    keyboard = [
        [InlineKeyboardButton("➕ Add Storage", callback_data="add_storage")],
        [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
    ]
    await query.message.reply_text(
        message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )
    logger.info(f"Displayed storage accounts for {user.email}")


async def add_storage_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await update.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    email = update.message.text.strip()
    if email.lower() == "cancel":
        await update.message.reply_text(
            "❌ *Cancelled adding storage.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    if not validate_email(email):
        await update.message.reply_text(
            "⚠️ *Invalid email format.*\nEnter a valid email.", parse_mode="Markdown"
        )
        return ADD_STORAGE_EMAIL

    provider_type = session.get("storage_pending_provider")
    logger.debug(f"Retrieved provider_type from session: {provider_type}")
    if not provider_type:
        logger.error("No provider_type found in session")
        await update.message.reply_text(
            "⚠️ *Session expired or no provider selected.*\nPlease select a provider again.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Add Storage", callback_data="add_storage"),
                    InlineKeyboardButton("🏠 Home", callback_data="main_menu"),
                ]
            ]),
        )
        return ConversationHandler.END

    user = User.get_user_by_email(session["email"])
    if any(
        acc["email"] == email and acc["provider_type"] == provider_type
        for acc in user.storage_accounts
    ):
        await update.message.reply_text(
            "⚠️ *Account already added.*", parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    account = user.add_storage_account(provider_type, email, status="initializing")
    if not user.save():
        await update.message.reply_text(
            "⚠️ *Failed to initialize storage.*", parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    session["pending_storage_account"] = account["id"]
    save_user_session(user_id, session)

    auth_url = None
    if provider_type == "google_drive":
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not google_client_id or not google_redirect_uri:
            logger.error(
                f"Missing Google Drive credentials: GOOGLE_CLIENT_ID={google_client_id}, GOOGLE_REDIRECT_URI={google_redirect_uri}"
            )
            await update.message.reply_text(
                "⚠️ *Google Drive configuration error.* Please contact support.",
                parse_mode="Markdown",
                reply_markup=build_main_menu(),
            )
            return ConversationHandler.END
        auth_url = (
            f"https://accounts.google.com/o/oauth2/auth?"
            f"client_id={google_client_id}&"
            f"redirect_uri={google_redirect_uri}&"
            f"scope=https://www.googleapis.com/auth/drive&"
            f"response_type=code&"
            f"state={account['id']}&"
            f"access_type=offline&"
            f"prompt=consent&"
            f"login_hint={email}"
        )
        logger.debug(f"Generated Google Drive auth_url: {auth_url}")
    elif provider_type == "dropbox":
        dropbox_app_key = os.getenv("DROPBOX_APP_KEY")
        dropbox_redirect_uri = os.getenv("DROPBOX_REDIRECT_URI")
        if not dropbox_app_key or not dropbox_redirect_uri:
            logger.error(
                f"Missing Dropbox credentials: DROPBOX_APP_KEY={dropbox_app_key}, DROPBOX_REDIRECT_URI={dropbox_redirect_uri}"
            )
            await update.message.reply_text(
                "⚠️ *Dropbox configuration error.* Please contact support.",
                parse_mode="Markdown",
                reply_markup=build_main_menu(),
            )
            return ConversationHandler.END
        auth_url = (
            f"https://www.dropbox.com/oauth2/authorize?"
            f"client_id={dropbox_app_key}&"
            f"redirect_uri={dropbox_redirect_uri}&"
            f"response_type=code&"
            f"state={account['id']}&"
            f"token_access_type=offline"
        )
        logger.debug(f"Generated Dropbox auth_url: {auth_url}")
    else:
        logger.error(f"Invalid provider type: {provider_type}")
        await update.message.reply_text(
            f"⚠️ *Invalid provider: {provider_type}.* Please select a valid provider.",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    if auth_url:
        try:
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"Connect {provider_type.replace('_', ' ').title()}",
                        url=auth_url,
                    )
                ],
                [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
            ]
            await update.message.reply_text(
                f"🔗 *Connect {provider_type.replace('_', ' ').title()}*\n"
                "1. Click the button below to authorize.\n"
                "2. Return here after authorization.\n"
                "3. Check *Storage Accounts* for status.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            await send_notification(
                user_id,
                f"🔗 *Connect {provider_type.replace('_', ' ').title()}*: Authorize using the provided link.",
            )
            logger.info(f"Sent authorization URL for {provider_type} to {user.email}")
            return ConversationHandler.END
        except telegram_error.BadRequest as e:
            logger.error(f"Failed to send auth URL for {provider_type}: {str(e)}")
            await update.message.reply_text(
                "⚠️ *Failed to send authorization link.* Please try again or contact support.",
                parse_mode="Markdown",
                reply_markup=build_main_menu(),
            )
            return ConversationHandler.END
    else:
        logger.error(f"Failed to generate auth_url for provider: {provider_type}")
        await update.message.reply_text(
            "⚠️ *Failed to generate authorization URL.* Please contact support.",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END


async def delete_storage_account(query, context, account_id):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session["email"])
    account = next(
        (acc for acc in user.storage_accounts if acc["id"] == account_id), None
    )
    if not account:
        await query.message.reply_text("⚠️ *Account not found.*", parse_mode="Markdown")
        return

    user.storage_accounts = [
        acc for acc in user.storage_accounts if acc["id"] != account_id
    ]
    if not user.save():
        await query.message.reply_text(
            "⚠️ *Failed to delete storage account.*", parse_mode="Markdown"
        )
        return

    await query.message.reply_text(
        f"✅ *{account['provider_type'].replace('_', ' ').title()} account deleted.*",
        parse_mode="Markdown",
        reply_markup=build_main_menu(),
    )
    logger.info(f"Deleted storage account {account_id} for {user.email}")
    await send_notification(
        user_id,
        f"🗑️ *{account['provider_type'].replace('_', ' ').title()} account deleted.*",
    )


async def preview_file(query, context, file_id):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session["email"])
    file = next((f for f in File.get_files(user.email) if f["id"] == file_id), None)
    if not file:
        await query.message.reply_text("⚠️ *File not found.*", parse_mode="Markdown")
        return

    await query.message.reply_text("⏳ *Preparing preview…*", parse_mode="Markdown")
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, file["filename"])
    try:
        file_manager = FileManager(user)
        file_manager.download_file(
            file["filename"], file["chunk_ids"], output_path, user.email
        )
        if not os.path.exists(output_path):
            raise FileNotFoundError("File reconstruction failed")

        base_filename = "_".join(file["filename"].split("_")[:-1])
        mime_type = mimetypes.guess_type(base_filename)[0] or "application/octet-stream"

        if mime_type.startswith("image/"):
            img = Image.open(output_path)
            img.thumbnail((200, 200))
            thumb_io = io.BytesIO()
            img.save(thumb_io, format="JPEG", quality=85)
            thumb_io.seek(0)
            await query.message.reply_photo(
                photo=thumb_io, caption=f"🖼️ *{base_filename}*", parse_mode="Markdown"
            )
        elif mime_type.startswith("video/"):
            with open(output_path, "rb") as f:
                await query.message.reply_video(
                    video=f, caption=f"🎥 *{base_filename}*", parse_mode="Markdown"
                )
        elif mime_type.startswith("audio/"):
            with open(output_path, "rb") as f:
                await query.message.reply_audio(
                    audio=f, caption=f"🎵 *{base_filename}*", parse_mode="Markdown"
                )
        elif mime_type in ["application/pdf", "text/plain"]:
            content = ai_agent.extract_text(output_path)
            snippet = content[:200] + "..." if len(content) > 200 else content
            await query.message.reply_text(
                f"📄 *{base_filename}*\n\n*Preview:*\n{snippet}", parse_mode="Markdown"
            )
        else:
            with open(output_path, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    filename=base_filename,
                    caption=f"📄 *{base_filename}*",
                    parse_mode="Markdown",
                )
        logger.info(f"Previewed {file['filename']} for {user.email}")
        await query.message.reply_text(
            "✅ *Preview complete.*\nWhat’s next?",
            parse_mode="Markdown",
            reply_markup=build_file_actions(file_id),
        )
    except Exception as e:
        logger.error(f"Preview failed for {file_id}: {str(e)}", exc_info=True)
        await query.message.reply_text(f"⚠️ *Error: {str(e)}*", parse_mode="Markdown")
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                logger.error(f"Cleanup failed for {output_path}: {str(e)}")


async def download_file(query, context, file_id):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session["email"])
    file = next((f for f in File.get_files(user.email) if f["id"] == file_id), None)
    if not file:
        await query.message.reply_text("⚠️ *File not found.*", parse_mode="Markdown")
        return

    await query.message.reply_text("⏳ *Downloading file…*", parse_mode="Markdown")
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, file["filename"])
    try:
        file_manager = FileManager(user)
        file_manager.download_file(
            file["filename"], file["chunk_ids"], output_path, user.email
        )
        if not os.path.exists(output_path):
            raise FileNotFoundError("File reconstruction failed")

        base_filename = "_".join(file["filename"].split("_")[:-1])
        with open(output_path, "rb") as f:
            await query.message.reply_document(
                document=f,
                filename=base_filename,
                caption=f"📥 *{base_filename}*",
                parse_mode="Markdown",
            )
        logger.info(f"Downloaded {file['filename']} for {user.email}")
        await query.message.reply_text(
            "✅ *Download complete.*\nWhat’s next?",
            parse_mode="Markdown",
            reply_markup=build_file_actions(file_id),
        )
    except Exception as e:
        logger.error(f"Download failed for {file_id}: {str(e)}", exc_info=True)
        await query.message.reply_text(f"⚠️ *Error: {str(e)}*", parse_mode="Markdown")
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                logger.error(f"Cleanup failed for {output_path}: {str(e)}")


async def delete_file(query, context, file_id):
    user_id = str(query.from_user.id)
    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await query.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    user = User.get_user_by_email(session ["email"])
    file = next((f for f in File.get_files(user.email) if f["id"] == file_id), None)
    if not file:
        await query.message.reply_text("⚠️ *File not found.*", parse_mode="Markdown")
        return

    file_manager = FileManager(user)
    success = file_manager.delete_file(file["filename"], file["chunk_ids"], user.email)
    if not success:
        await query.message.reply_text(
            "⚠️ *Failed to delete file.*", parse_mode="Markdown"
        )
        return

    user.update_storage_used(-file["size_mb"])
    user.save()
    File.delete_file(file_id)
    ai_agent.delete_content(file_id)
    filename = session.get("file_map", {}).get(file_id, "Unknown")
    await query.message.reply_text(
        f"✅ *File {filename} deleted.*",
        parse_mode="Markdown",
        reply_markup=build_main_menu(),
    )
    logger.info(f"Deleted {file['filename']} for {user.email}")
    await send_notification(user_id, f"🗑️ *File {filename} deleted.*")


async def ai_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if rate_limit_exceeded(user_id):
        await update.message.reply_text(
            "⚠️ *Too many requests.* Please wait a minute and try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    session = get_user_session(user_id)
    if not session.get("logged_in"):
        await update.message.reply_text(
            "⚠️ *Please login first.*",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END

    query = update.message.text.strip()
    if query.lower() == "stop ai chat":
        session.pop("ai_context", None)
        save_user_session(user_id, session)
        await update.message.reply_text(
            "❌ *AI chat ended.*\nWhat’s next?",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return ConversationHandler.END
    elif query.lower() == "clear ai history":
        session["ai_context"] = []
        save_user_session(user_id, session)
        await update.message.reply_text(
            "🧹 *AI chat history cleared.*\nAsk a new question:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
            ),
        )
        return AI_QUERY

    await update.message.reply_text(
        "⏳ *Processing your query…*", parse_mode="Markdown"
    )
    user = User.get_user_by_email(session["email"])
    files = File.get_files(user.email) or []
    try:
        # Retrieve AI context from session
        ai_context = session.get("ai_context", [])
        ai_context.append({"role": "user", "content": query})
        ai_context = ai_context[-10:]  # Limit to last 10 messages

        # Fetch relevant file content
        relevant_docs = ai_agent.search_content(query, user.email, files, n_results=5)
        context_str = ""
        if relevant_docs:
            context_str = "\n".join(
                f"File: {doc['filename']}\nContent: {doc['content']}\n"
                for doc in relevant_docs
            )
        else:
            context_str = "No relevant file content found."

        # Build prompt with conversation history and file content
        conversation_history = "Conversation history:\n"
        for msg in ai_context:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation_history += f"{role}: {msg['content']}\n"

        # Rephrase query for file-related questions
        rephrased_query = query
        if any(keyword in query.lower() for keyword in ['file', 'document', 'upload', 'content', 'pdf', 'summarize']):
            rephrased_query = f"Summarize or extract relevant information from the provided file content to answer: {query}"

        prompt = (
            "You are MegaCloud AI, a highly accurate assistant for a cloud storage platform. "
            "Follow these steps to answer the user's question:\n"
            "1. **Analyze the Question**: Determine if the question refers to uploaded files (e.g., mentions 'file,' 'document,' or specific content). "
            "2. **Use File Content**: If file-related, answer **exclusively** using the provided file content. Quote relevant sections and synthesize information across files if needed. "
            "3. **Handle Complex Queries**: For tasks like summarization, comparison, or inference, break down the question and address each part clearly. "
            "4. **General Questions**: If unrelated to files, provide a precise, accurate, and professional answer using your knowledge. "
            "5. **Format Clearly**: Use markdown (bullet points, quotes, headers) for readability.\n\n"
            f"**Conversation History**:\n{conversation_history}\n"
            f"**User Question**: {rephrased_query}\n\n"
            f"**File Content** (use for file-related questions):\n{context_str}\n\n"
            "**Answer**:"
        )

        # Generate response using AIAgent
        for attempt in range(3):
            try:
                answer = ai_agent.answer_query(prompt, user.email, files)
                if not answer or "unknown" in answer.lower():
                    answer = "No specific information found in uploaded files. Please clarify or ask a different question."
                ai_context.append({"role": "assistant", "content": answer})
                session["ai_context"] = ai_context
                save_user_session(user_id, session)
                await update.message.reply_text(
                    f"🤖 *AI Response*\n{answer}\n\nAsk another question or stop:",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardMarkup(
                        [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
                    ),
                )
                logger.info(f"AI query answered for {user.email}: {query}")
                return AI_QUERY
            except Exception as e:
                logger.error(f"AI query attempt {attempt+1} failed: {str(e)}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

    except Exception as e:
        logger.error(f"AI query failed: {str(e)}", exc_info=True)
        answer = "I couldn't process that query. Please try rephrasing or ask something else."
        await update.message.reply_text(
            f"🤖 *AI Response*\n{answer}\n\nAsk another question or stop:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["Stop AI Chat"], ["Clear AI History"]], one_time_keyboard=True
            ),
        )
        return AI_QUERY


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    session = get_user_session(user_id)
    session.pop("ai_context", None)
    session.pop("storage_pending_provider", None)
    save_user_session(user_id, session)
    await update.message.reply_text(
        "❌ *Operation cancelled.*",
        parse_mode="Markdown",
        reply_markup=build_main_menu(),
    )
    return ConversationHandler.END


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    if update and update.message:
        await update.message.reply_text(
            "⚠️ *An unexpected error occurred.* Please try again later.",
            parse_mode="Markdown",
        )


def main():
    try:
        logger.info("Starting Telegram bot application")
        logger.debug(f"Environment variables - GOOGLE_CLIENT_ID: {os.getenv('GOOGLE_CLIENT_ID')}")
        logger.debug(f"Environment variables - GOOGLE_REDIRECT_URI: {os.getenv('GOOGLE_REDIRECT_URI')}")
        logger.debug(f"Environment variables - DROPBOX_APP_KEY: {os.getenv('DROPBOX_APP_KEY')}")
        logger.debug(f"Environment variables - DROPBOX_REDIRECT_URI: {os.getenv('DROPBOX_REDIRECT_URI')}")
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(InlineQueryHandler(inline_query))

        conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(button_callback),
            ],
            states={
                REGISTRATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, registration)
                ],
                REGISTRATION_OTP: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, registration_otp)
                ],
                LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, login)],
                LOGIN_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_otp)],
                UPLOAD_FILE: [
                    MessageHandler(filters.Document.ALL | filters.TEXT, upload_file)
                ],
                ADD_STORAGE_EMAIL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_storage_email)
                ],
                AI_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_query)],
                SEARCH_FILES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, search_files)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_callback, pattern="^cancel$"),
            ],
            per_message=False,
        )

        application.add_handler(conv_handler)
        application.add_error_handler(error_handler)
        logger.info("Starting polling")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
