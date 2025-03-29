import os
import logging
import tempfile
import json
import mimetypes
import uuid
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
import asyncio
import telegram.error

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

try:
    dropbox_token_1 = json.loads(os.getenv('DROPBOX_TOKEN_1'))
    dropbox_token_2 = json.loads(os.getenv('DROPBOX_TOKEN_2'))
    google_cred_user1 = os.getenv('GOOGLE_CRED_USER1')
    google_cred_user2 = os.getenv('GOOGLE_CRED_USER2')
    google_cred_user3 = os.getenv('GOOGLE_CRED_USER3')

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
    logger.error(f"Failed to initialize storage providers: {str(e)}", exc_info=True)
    raise

AUTH_EMAIL, AUTH_OTP, MAIN_MENU, UPLOAD_FILE, FILE_ACTIONS = range(5)

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
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            await update.callback_query.delete_message()
        except Exception as e:
            logger.error(f"Failed to send main menu: {str(e)}", exc_info=True)
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "☁️ *Welcome to MegaCloud*\n\nPlease enter your email:",
        parse_mode='Markdown'
    )
    return AUTH_EMAIL

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
        logger.error(f"Email auth error: {str(e)}", exc_info=True)
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
        logger.error(f"OTP error: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Verification failed. Try again:", parse_mode='Markdown')
        return AUTH_OTP

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data

    if not await check_auth(context):
        await query.answer("🔒 Please login first!", show_alert=True)
        await query.message.reply_text("⏳ Session expired. Use /start.", parse_mode='Markdown')
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

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        files = File.get_files(context.user_data['email'])
        logger.info(f"Files retrieved for {context.user_data['email']}: {len(files)} files")
        if not files:
            keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    "📭 No files found.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                await update.callback_query.delete_message()
            else:
                await update.message.reply_text(
                    "📭 No files found.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            return MAIN_MENU

        keyboard = []
        for f in files[:10]:
            escaped_filename = f['filename'].replace('_', '__')
            button_text = f"📄 {escaped_filename} ({f['size_mb']:.2f} MB)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"f_{f['id']}")])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')])
        if update.callback_query:
            await update.callback_query.message.reply_text(
                "📁 *Your Files:*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            await update.callback_query.delete_message()
        else:
            await update.message.reply_text(
                "📁 *Your Files:*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"List files error: {str(e)}", exc_info=True)
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
        if update.callback_query:
            await update.callback_query.message.reply_text(
                f"❌ Failed to list files: {str(e)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            await update.callback_query.delete_message()
        else:
            await update.message.reply_text(
                f"❌ Failed to list files: {str(e)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        return MAIN_MENU

async def file_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data

    if not await check_auth(context):
        await query.answer("🔒 Please login first!", show_alert=True)
        await query.message.reply_text("⏳ Session expired. Use /start.", parse_mode='Markdown')
        return ConversationHandler.END

    logger.info(f"File actions triggered with data: {data}")

    if data.startswith('f_'):
        file_id = data.replace('f_', '')
        file = get_file_by_id(file_id, context.user_data['email'])
        if not file:
            await query.answer("❌ File not found!", show_alert=True)
            await query.message.reply_text(
                "❌ File not found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📁 Files", callback_data='list_files')]])
            )
            return FILE_ACTIONS
        
        context.user_data['current_file_id'] = file_id
        filename = file['filename'].replace('_', '__')
        
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

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(context):
        await update.callback_query.answer("🔒 Please login first!", show_alert=True)
        return ConversationHandler.END
    await update.callback_query.message.reply_text(
        "📤 Send a file to upload (photo, video, document, etc.):\nUse /cancel to go back",
        parse_mode='Markdown'
    )
    return UPLOAD_FILE

async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(context):
        await update.message.reply_text("🔒 Please login first! Use /start", parse_mode='Markdown')
        return ConversationHandler.END

    # Prevent double processing of the same message
    message_id = update.message.message_id
    if context.user_data.get('last_processed_message_id') == message_id:
        logger.info(f"Skipping duplicate processing of message ID {message_id}")
        return UPLOAD_FILE
    context.user_data['last_processed_message_id'] = message_id

    file_obj = (
        update.message.document or
        (update.message.photo[-1] if update.message.photo else None) or
        update.message.video or
        update.message.audio or
        update.message.voice
    )
    if not file_obj:
        await update.message.reply_text(
            "❌ Please send a file (photo, video, document, etc.)!\nUse /cancel to return",
            parse_mode='Markdown'
        )
        return UPLOAD_FILE

    temp_path = None
    try:
        file = await file_obj.get_file()
        if hasattr(file_obj, 'file_name') and file_obj.file_name:
            base_filename = file_obj.file_name
        elif update.message.document:
            base_filename = update.message.document.file_name
        elif update.message.photo:
            base_filename = f"photo_{update.message.message_id}.jpg"
        elif update.message.video:
            base_filename = update.message.video.file_name or f"video_{update.message.message_id}.mp4"
        elif update.message.audio:
            base_filename = update.message.audio.file_name or f"audio_{update.message.message_id}.mp3"
        elif update.message.voice:
            base_filename = f"voice_{update.message.message_id}.ogg"
        else:
            base_filename = f"file_{update.message.message_id}"

        # Append a unique suffix to the filename to avoid Firestore conflicts
        unique_suffix = uuid.uuid4().hex[:8]
        filename = f"{base_filename}_{unique_suffix}"
        temp_path = tempfile.mktemp(suffix=f"_{filename}")
        escaped_filename = base_filename.replace('_', '__')  # Display original name without suffix
        await update.message.reply_text(f"⏳ Uploading '{escaped_filename}'...", parse_mode='Markdown')

        try:
            await file.download_to_drive(temp_path)
        except Exception as e:
            logger.error(f"Failed to download file from Telegram: {str(e)}", exc_info=True)
            raise Exception("Failed to download file from Telegram")

        file_size = os.path.getsize(temp_path)
        size_mb = file_size / (1024 * 1024)

        logger.info(f"Uploading file: {filename} ({size_mb:.2f} MB) for {context.user_data['email']}")
        chunk_ids = file_manager.upload_file(temp_path, filename, context.user_data['email'])
        if not chunk_ids:
            raise Exception("File upload to storage provider failed")

        # Save file metadata with the unique filename
        file_obj = File(filename=filename, user_email=context.user_data['email'], chunk_ids=chunk_ids, size_mb=size_mb)
        save_result = file_obj.save()
        if not save_result:
            logger.warning(f"File.save() returned False for {filename}, checking if it exists in Firestore")
            # Verify if the file is already in Firestore
            files = File.get_files(context.user_data['email'])
            if not any(f['filename'] == filename for f in files):
                logger.error(f"Failed to save {filename} metadata to Firestore and it’s not present in the database")
                raise Exception("Failed to save file metadata to Firestore due to a database error")
            else:
                logger.info(f"File {filename} already exists in Firestore, proceeding despite save() returning False")

        user = User.get_user(context.user_data['email'])
        if not user:
            user = User(email=context.user_data['email'])
        user.update_storage_used(size_mb)
        if not user.save():
            raise Exception("Failed to update user storage in Firestore")

        await update.message.reply_text(
            f"✅ '{escaped_filename}' ({size_mb:.2f} MB) uploaded!",
            parse_mode='Markdown'
        )
        
        return await list_files(update, context)
    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ Upload failed: {str(e)}\nTry again or /cancel",
            parse_mode='Markdown'
        )
        return UPLOAD_FILE
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

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
        filename = file['filename'].split('_')[:-1]  # Remove unique suffix for display
        escaped_filename = '_'.join(filename).replace('_', '__')

        temp_path = os.path.join(tempfile.gettempdir(), file['filename'])
        logger.info(f"Attempting to preview {file['filename']} at {temp_path}")
        file_manager.download_file(file['filename'], file['chunk_ids'], temp_path)
        if not os.path.exists(temp_path):
            raise FileNotFoundError(f"Reconstructed file not found at {temp_path}")
        
        mime_type, _ = mimetypes.guess_type(temp_path)
        logger.info(f"Detected MIME type: {mime_type} for {file['filename']}")
        
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
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                chat_id = update.callback_query.message.chat_id
                if mime_type and mime_type.startswith('image/'):
                    with open(temp_path, 'rb') as f:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=f,
                            caption=f"📸 {escaped_filename}\nWhat would you like to do next?",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                elif mime_type and mime_type.startswith('video/'):
                    with open(temp_path, 'rb') as f:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=f,
                            caption=f"🎥 {escaped_filename}\nWhat would you like to do next?",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                elif mime_type and mime_type == 'application/pdf':
                    with open(temp_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            filename=file['filename'],
                            caption=f"📜 {escaped_filename} (PDF Preview)\nWhat would you like to do next?",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                else:
                    with open(temp_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            filename=file['filename'],
                            caption=f"📄 {escaped_filename} (Preview)\nWhat would you like to do next?",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                await update.callback_query.delete_message()
                logger.info(f"Successfully previewed {file['filename']}")
                os.remove(temp_path)
                return FILE_ACTIONS
            except telegram.error.TimedOut as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Preview attempt {attempt + 1} timed out, retrying...")
                    await asyncio.sleep(2)
                    continue
                logger.error(f"Preview failed after {max_retries} attempts: {str(e)}")
                raise
    except Exception as e:
        logger.error(f"Preview error for file ID {file_id}: {str(e)}", exc_info=True)
        keyboard = [[InlineKeyboardButton("🔙 Back to Files", callback_data='list_files')]]
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
        filename = file['filename'].split('_')[:-1]  # Remove unique suffix for display
        escaped_filename = '_'.join(filename).replace('_', '__')

        temp_path = os.path.join(tempfile.gettempdir(), file['filename'])
        logger.info(f"Attempting to download {file['filename']} to {temp_path}")
        file_manager.download_file(file['filename'], file['chunk_ids'], temp_path)
        if not os.path.exists(temp_path):
            raise FileNotFoundError(f"Reconstructed file not found at {temp_path}")
        
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
        with open(temp_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.callback_query.message.chat_id,
                document=f,
                filename=file['filename'],
                caption=f"⬇️ {escaped_filename}\nWhat would you like to do next?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        await update.callback_query.delete_message()
        logger.info(f"Successfully downloaded {file['filename']}")
        os.remove(temp_path)
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"Download error for file ID {file_id}: {str(e)}", exc_info=True)
        keyboard = [[InlineKeyboardButton("🔙 Back to Files", callback_data='list_files')]]
        await update.callback_query.edit_message_text(
            f"❌ Download failed: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
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
        filename = file['filename'].split('_')[:-1]  # Remove unique suffix for display
        escaped_filename = '_'.join(filename).replace('_', '__')

        logger.info(f"Starting async deletion for {file['filename']}")
        keyboard = [
            [InlineKeyboardButton("📁 Files", callback_data='list_files')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ]
        try:
            await update.callback_query.edit_message_text(
                f"🗑️ '{escaped_filename}' is being deleted...",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except telegram.error.BadRequest as e:
            logger.warning(f"Failed to edit message: {str(e)}, sending new message instead")
            await context.bot.send_message(
                chat_id=update.callback_query.message.chat_id,
                text=f"🗑️ '{escaped_filename}' is being deleted...",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        async def perform_deletion():
            try:
                file_manager.delete_file(file['filename'], file['chunk_ids'], context.user_data['email'])
                user = User.get_user(context.user_data['email'])
                user.update_storage_used(-file['size_mb'])
                user.save()
                File.delete_file(file_id)
                logger.info(f"Successfully deleted {file['filename']}")
            except Exception as e:
                logger.error(f"Background delete error for {file['filename']}: {str(e)}", exc_info=True)
                await context.bot.send_message(
                    chat_id=update.callback_query.message.chat_id,
                    text=f"❌ Failed to delete '{escaped_filename}': {str(e)}",
                    parse_mode='Markdown'
                )

        asyncio.create_task(perform_deletion())
        return FILE_ACTIONS
    except Exception as e:
        logger.error(f"Delete initiation error for file ID {file_id}: {str(e)}", exc_info=True)
        keyboard = [[InlineKeyboardButton("🔙 Back to Files", callback_data='list_files')]]
        await update.callback_query.edit_message_text(
            f"❌ Delete failed to start: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return FILE_ACTIONS

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_auth(context):
        await update.callback_query.answer("🔒 Please login first!", show_alert=True)
        return ConversationHandler.END

    try:
        files = File.get_files(context.user_data['email'])
        total_files = len(files)
        total_size = sum(f['size_mb'] for f in files)
        user = User.get_user(context.user_data['email'])

        if abs(user.storage_used - total_size) > 0.01:
            user.storage_used = total_size
            user.save()
            logger.warning(f"Corrected storage_used for {context.user_data['email']} to match total_size: {total_size} MB")

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
        logger.error(f"Stats error: {str(e)}", exc_info=True)
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]]
        await update.callback_query.edit_message_text(
            f"❌ Failed to fetch stats: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return MAIN_MENU

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.callback_query.edit_message_text(
        "🚪 Logged out.\nUse /start to begin again.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_auth(context):
        return await show_main_menu(update, context, "✅ Cancelled. What's next?")
    await update.message.reply_text("✅ Cancelled. Use /start.", parse_mode='Markdown')
    return ConversationHandler.END

@app.route('/')
def home():
    return "Telegram Bot is alive!"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def main():
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    application = Application.builder().token(token).read_timeout(60).write_timeout(60).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_email)],
            AUTH_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_otp)],
            MAIN_MENU: [CallbackQueryHandler(main_menu)],
            UPLOAD_FILE: [
                MessageHandler(
                    filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE,
                    upload_file
                )
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
    
    logger.info("Starting Telegram bot with increased timeout...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, timeout=60)

if __name__ == "__main__":
    main()