import os
import logging
import tempfile
import json
import mimetypes
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from auth import AuthManager
from models import User, File
from file_manager import FileManager
from storage_providers.google_drive import GoogleDriveProvider
from storage_providers.dropbox import DropboxProvider

# Load environment variables
load_dotenv()

# Configure logging to stdout for Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Initialize storage providers using environment variables
try:
    dropbox_token_1 = json.loads(os.getenv('DROPBOX_TOKEN_1'))
    dropbox_token_2 = json.loads(os.getenv('DROPBOX_TOKEN_2'))
    google_cred_user1 = os.getenv('GOOGLE_CRED_USER1')
    google_cred_user2 = os.getenv('GOOGLE_CRED_USER2')
    google_cred_user3 = os.getenv('GOOGLE_CRED_USER3')

    # Write Google credentials to temp files
    def create_temp_json(data, prefix):
        temp_file = tempfile.NamedTemporaryFile(mode='w', prefix=prefix, suffix='.json', delete=False)
        json.dump(json.loads(data), temp_file)
        temp_file.close()
        return temp_file.name

    storage_providers = [
        GoogleDriveProvider(create_temp_json(google_cred_user1, 'user1'), "1F2oxw2W4o1MAL0iQdVkzCc2Zjw4z5XoM"),
        GoogleDriveProvider(create_temp_json(google_cred_user2, 'user2'), "1SQGF0uGOGHJTSJvdbCnRm8cQdftMZbUy"),
        GoogleDriveProvider(create_temp_json(google_cred_user3, 'user3'), "1ZyNqPeaOkZC2uVWDnlLKg6QuEF5JOMUA"),
        DropboxProvider(dropbox_token_1, "/MegaCloud01"),
        DropboxProvider(dropbox_token_2, "/MegaCloud02"),
    ]
    file_manager = FileManager(storage_providers)
except Exception as e:
    logger.error(f"Failed to initialize storage providers: {str(e)}")
    raise

# Conversation states
AUTH_EMAIL, AUTH_OTP, MAIN_MENU, UPLOAD_FILE, FILE_ACTIONS = range(5)

# Helper functions
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = None):
    keyboard = [
        [InlineKeyboardButton("📁 My Files", callback_data='list_files')],
        [InlineKeyboardButton("📤 Upload File", callback_data='upload')],
        [InlineKeyboardButton("📊 Stats", callback_data='stats')],
        [InlineKeyboardButton("🚪 Logout", callback_data='logout')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = message or "🌟 *MegaCloud*\nWhat would you like to do?"
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to edit message in show_main_menu: {str(e)}")
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    return MAIN_MENU

async def check_auth(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.user_data.get('logged_in', False)

def get_file_by_id(file_id, email):
    logger.info(f"Looking for file with ID: {file_id} for email: {email}")
    files = File.get_files(email)
    for file in files:
        if str(file['id']) == str(file_id):
            logger.info(f"Found file: {file}")
            return file
    logger.warning(f"No file found with ID: {file_id}")
    return None

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "☁️ *Welcome to MegaCloud*\n\nPlease enter your email:",
        parse_mode='Markdown'
    )
    return AUTH_EMAIL

# Authentication handlers
async def auth_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip().lower()
    try:
        success, message = AuthManager.register_or_login(email)
        if success:
            context.user_data['email'] = email
            await update.message.reply_text(
                "✅ OTP sent!\n🔑 Please enter the OTP:",
                parse_mode='Markdown'
            )
            return AUTH_OTP
        await update.message.reply_text(f"❌ {message}\nTry again:", parse_mode='Markdown')
        return AUTH_EMAIL
    except Exception as e:
        logger.error(f"Email auth error: {str(e)}")
        await update.message.reply_text("❌ Error occurred. Try again:", parse_mode='Markdown')
        return AUTH_EMAIL

async def auth_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp = update.message.text.strip()
    email = context.user_data.get('email')
    if not email:
        await update.message.reply_text("⏳ Session expired. Use /start.", parse_mode='Markdown')
        return ConversationHandler.END

    try:
        success, message = AuthManager.verify_otp(email, otp)
        if success:
            context.user_data['logged_in'] = True
            user = User.get_user(email)
            if not user:
                user = User(email=email)
                user.save()
            return await show_main_menu(update, context)
        await update.message.reply_text(f"❌ {message}\nEnter OTP again:", parse_mode='Markdown')
        return AUTH_OTP
    except Exception as e:
        logger.error(f"OTP error: {str(e)}")
        await update.message.reply_text("❌ Verification failed. Try again:", parse_mode='Markdown')
        return AUTH_OTP

# Main menu handler
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data

    if not await check_auth(context):
        await query.answer("🔒 Please login first!", show_alert=True)
        await query.edit_message_text("⏳ Session expired. Use /start.", parse_mode='Markdown')
        return ConversationHandler.END

    logger.info(f"Main menu triggered with data: {data}")

    if data == 'list_files':
        return await list_files(update, context)
    elif data == 'upload':
        return await upload_start(update, context)
    elif data == 'stats':
        return await show_stats(update, context)
    elif data == 'logout':
        return await logout(update, context)
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    
    return MAIN_MENU

# File listing
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        files = File.get_files(context.user_data['email'])
        logger.info(f"Files retrieved for {context.user_data['email']}: {files}")
        if not files:
            keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
            await update.callback_query.edit_message_text(
                "📭 No files found.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return MAIN_MENU

        keyboard = [
            [InlineKeyboardButton(f"📄 {f['filename']} ({f['size_mb']:.2f} MB)", callback_data=f"f_{f['id']}")]
            for f in files[:10]
        ]
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')])
        await update.callback_query.edit_message_text(
            "📁 *Your Files:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"List files error: {str(e)}")
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
        await update.callback_query.edit_message_text(
            f"❌ Failed to list files: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return MAIN_MENU

# File actions
async def file_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data

    if not await check_auth(context):
        await query.answer("🔒 Please login first!", show_alert=True)
        await query.edit_message_text("⏳ Session expired. Use /start.", parse_mode='Markdown')
        return ConversationHandler.END

    logger.info(f"File actions triggered with data: {data}")

    if data.startswith('f_'):
        file_id = data.replace('f_', '')
        file = get_file_by_id(file_id, context.user_data['email'])
        if not file:
            await query.answer("❌ File not found!", show_alert=True)
            await query.edit_message_text(
                "❌ File not found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📁 Files", callback_data='list_files')]])
            )
            return FILE_ACTIONS
        
        context.user_data['current_file_id'] = file_id
        filename = file['filename']
        
        keyboard = [
            [
                InlineKeyboardButton("👀 Preview", callback_data='preview'),
                InlineKeyboardButton("⬇️ Download", callback_data='download')
            ],
            [
                InlineKeyboardButton("🗑️ Delete", callback_data='delete'),
                InlineKeyboardButton("🔙 Back to Files", callback_data='list_files')
            ]
        ]
        await query.edit_message_text(
            f"📄 *{filename}*\nWhat would you like to do?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS

    elif data == 'preview':
        return await preview_file(update, context)
    elif data == 'download':
        return await download_file(update, context)
    elif data == 'delete':
        return await delete_file(update, context)
    elif data == 'list_files':
        return await list_files(update, context)
    elif data == 'main_menu':
        return await show_main_menu(update, context)

    return FILE_ACTIONS

# Upload handlers
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(context):
        await update.callback_query.answer("🔒 Please login first!", show_alert=True)
        return ConversationHandler.END
    await update.callback_query.edit_message_text(
        "📤 Send a file to upload (photo or document):\nUse /cancel to go back",
        parse_mode='Markdown'
    )
    return UPLOAD_FILE

async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(context):
        await update.message.reply_text("🔒 Please login first! Use /start", parse_mode='Markdown')
        return ConversationHandler.END

    document = update.message.document or (update.message.photo[-1] if update.message.photo else None)
    if not document:
        await update.message.reply_text(
            "❌ Please send a file!\nUse /cancel to return",
            parse_mode='Markdown'
        )
        return UPLOAD_FILE

    try:
        file = await document.get_file()
        filename = document.file_name if hasattr(document, 'file_name') else f"photo_{document.file_id}.jpg"
        temp_path = tempfile.mktemp(suffix=f"_{filename}")
        
        await update.message.reply_text(f"⏳ Uploading '{filename}'...", parse_mode='Markdown')
        await file.download_to_drive(temp_path)
        file_size = os.path.getsize(temp_path)

        result = file_manager.upload_file(temp_path, filename, context.user_data['email'])
        user = User.get_user(context.user_data['email'])
        user.update_storage_used(file_size / (1024 * 1024))
        user.save()

        await update.message.reply_text(
            f"✅ '{filename}' ({file_size / (1024 * 1024):.2f} MB) uploaded!",
            parse_mode='Markdown'
        )
        os.remove(temp_path)
        
        return await list_files(update, context)
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        await update.message.reply_text(
            f"❌ Upload failed: {str(e)}\nTry again or /cancel",
            parse_mode='Markdown'
        )
        return UPLOAD_FILE

# File operations
async def preview_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = context.user_data.get('current_file_id')
    if not file_id:
        await update.callback_query.answer("❌ No file selected!", show_alert=True)
        return FILE_ACTIONS

    try:
        file = get_file_by_id(file_id, context.user_data['email'])
        if not file:
            await update.callback_query.answer("❌ File not found!", show_alert=True)
            return FILE_ACTIONS
        filename = file['filename']

        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file_manager.download_file(filename, file['chunk_ids'], temp_path)
        mime_type, _ = mimetypes.guess_type(temp_path)
        
        keyboard = [
            [
                InlineKeyboardButton("👀 Preview", callback_data='preview'),
                InlineKeyboardButton("⬇️ Download", callback_data='download')
            ],
            [
                InlineKeyboardButton("🗑️ Delete", callback_data='delete'),
                InlineKeyboardButton("🔙 Back to Files", callback_data='list_files')
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ]
        
        if mime_type and mime_type.startswith('image/'):
            with open(temp_path, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=update.callback_query.message.chat_id,
                    photo=f,
                    caption=f"📸 {filename}\nWhat would you like to do next?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            await update.callback_query.delete_message()
        else:
            await update.callback_query.edit_message_text(
                "❌ Preview available only for images.\nTry downloading instead.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        os.remove(temp_path)
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"Preview error: {str(e)}")
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"f_{file_id}")]]
        await update.callback_query.edit_message_text(
            f"❌ Preview failed: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS

async def download_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = context.user_data.get('current_file_id')
    if not file_id:
        await update.callback_query.answer("❌ No file selected!", show_alert=True)
        return FILE_ACTIONS

    try:
        file = get_file_by_id(file_id, context.user_data['email'])
        if not file:
            await update.callback_query.answer("❌ File not found!", show_alert=True)
            return FILE_ACTIONS
        filename = file['filename']

        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file_manager.download_file(filename, file['chunk_ids'], temp_path)
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back", callback_data=f"f_{file_id}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ]
        with open(temp_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.callback_query.message.chat_id,
                document=f,
                filename=filename,
                caption=f"⬇️ {filename}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        await update.callback_query.delete_message()
        os.remove(temp_path)
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        await update.callback_query.edit_message_text(
            f"❌ Download failed: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"f_{file_id}")]]),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS

async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = context.user_data.get('current_file_id')
    if not file_id:
        await update.callback_query.answer("❌ No file selected!", show_alert=True)
        return FILE_ACTIONS

    try:
        file = get_file_by_id(file_id, context.user_data['email'])
        if not file:
            await update.callback_query.answer("❌ File not found!", show_alert=True)
            return FILE_ACTIONS
        filename = file['filename']

        file_manager.delete_file(filename, file['chunk_ids'], context.user_data['email'])
        user = User.get_user(context.user_data['email'])
        user.update_storage_used(-file['size_mb'])
        user.save()
        File.delete_file(file['id'])

        keyboard = [
            [InlineKeyboardButton("📁 Files", callback_data='list_files')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ]
        await update.callback_query.edit_message_text(
            f"🗑️ '{filename}' deleted!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        await update.callback_query.edit_message_text(
            f"❌ Delete failed: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"f_{file_id}")]]),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS

# Stats
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(context):
        await update.callback_query.answer("🔒 Please login first!", show_alert=True)
        return ConversationHandler.END

    try:
        files = File.get_files(context.user_data['email'])
        total_files = len(files)
        total_size = sum(f['size_mb'] for f in files)
        user = User.get_user(context.user_data['email'])

        message = (
            f"📊 *Storage Stats*\n\n"
            f"📄 Files: {total_files}\n"
            f"💾 Size: {total_size:.2f} MB\n"
            f"🗄️ Used: {user.storage_used:.2f} MB"
        )
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
        await update.callback_query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
        await update.callback_query.edit_message_text(
            f"❌ Failed to fetch stats: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return MAIN_MENU

# Logout
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.callback_query.edit_message_text(
        "🚪 Logged out.\nUse /start to begin again.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_auth(context):
        return await show_main_menu(update, context, "✅ Cancelled. What's next?")
    await update.message.reply_text("✅ Cancelled. Use /start.", parse_mode='Markdown')
    return ConversationHandler.END

# Flask route
@app.route('/')
def home():
    return "Telegram Bot is alive!"

# Run Flask in a thread
def run_flask():
    port = int(os.getenv('PORT', 8080))  # Render provides PORT env var
    app.run(host='0.0.0.0', port=port)

# Main function to start bot and Flask
def main():
    # Start Flask in a separate thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True  # Daemonize so it stops with main thread
    flask_thread.start()

    # Start Telegram bot
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_email)],
            AUTH_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_otp)],
            MAIN_MENU: [CallbackQueryHandler(main_menu)],
            UPLOAD_FILE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, upload_file),
                MessageHandler(filters.ALL & ~filters.COMMAND, upload_file),
            ],
            FILE_ACTIONS: [CallbackQueryHandler(file_actions)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
        per_message=False
    )

    application.add_handler(conv_handler)
    
    logger.info("Starting Telegram bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()