from flask import Flask, request, jsonify, render_template, session, send_file, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from auth import AuthManager
from models import User, File, UserRepository
from file_manager import FileManager
from ai_agent import AIAgent
import tempfile
import os
import json
import mimetypes
import logging
import uuid
from dotenv import load_dotenv
import requests
from werkzeug.utils import secure_filename
import time

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
load_dotenv()
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

preview_files = {}
download_files = {}

# OAuth configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/oauth/google/callback')
DROPBOX_CLIENT_ID = os.getenv('DROPBOX_APP_KEY')
DROPBOX_CLIENT_SECRET = os.getenv('DROPBOX_APP_SECRET')
DROPBOX_REDIRECT_URI = os.getenv('DROPBOX_REDIRECT_URI', 'http://localhost:5000/oauth/dropbox/callback')

# Initialize AI Agent
ai_agent = AIAgent()

@login_manager.user_loader
def load_user(email):
    return User.get_user_by_email(email)  

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    try:
        data = request.form or request.get_json()
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        email = data.get('email')
        username = data.get('username')
        
        if not all([first_name, last_name, email, username]):
            return jsonify({"error": "All fields are required"}), 400
            
        if User.get_user_by_email(email):  # Changed from get_user to get_user_by_email
            return jsonify({"error": "Email already registered"}), 400
            
        if User.get_user_by_username(username):
            return jsonify({"error": "Username already taken"}), 400
            
        user = User(email=email, first_name=first_name, last_name=last_name, username=username)
        otp = user.generate_otp()
        if user.save() and AuthManager.send_otp_email(email, otp):
            session['email'] = email
            return jsonify({"message": "OTP sent to email", "redirect": "/verify_register"}), 200
        return jsonify({"error": "Failed to register"}), 500
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/verify_register', methods=['GET', 'POST'])
def verify_register():
    if request.method == 'GET':
        return render_template('verify_register.html')
    data = request.get_json() or request.form
    email = session.get('email')
    otp = data.get('otp')
    
    if not email or not otp:
        return jsonify({"error": "Email or OTP missing"}), 400
        
    success, message = AuthManager.verify_otp(email, otp)
    if success:
        user = User.get_user_by_email(email)  # Changed from get_user to get_user_by_email
        login_user(user)
        logger.info(f"User {email} registered and logged in")
        return jsonify({"message": message, "redirect": "/dashboard"}), 200
    logger.error(f"OTP verification failed for {email}: {message}")
    return jsonify({"error": message}), 400

@app.route('/test_db')
def test_db():
    UserRepository.init_db()
    return "DB OK", 200

@app.route('/request_otp', methods=['POST'])
def request_otp():
    try:
        data = request.form or request.get_json()
        identifier = data.get('identifier')
        if not identifier:
            return jsonify({"error": "Username or email required"}), 400
        user = User.get_user_by_email(identifier) or User.get_user_by_username(identifier)  # Changed from get_user to get_user_by_email
        if not user:
            return jsonify({"error": "User not registered. Please register first"}), 400
        otp = user.generate_otp()
        if user.save() and AuthManager.send_otp_email(user.email, otp):
            session['email'] = user.email
            return jsonify({"message": "OTP sent"}), 200
        return jsonify({"error": "Failed to send OTP"}), 500
    except Exception as e:
        logger.error(f"Error in request_otp: {str(e)}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json() or request.form
    email = session.get('email')
    otp = data.get('otp')
    if not email or not otp:
        return jsonify({"error": "Email or OTP missing"}), 400
    success, message = AuthManager.verify_otp(email, otp)
    if success:
        user = User.get_user_by_email(email)  # Changed from get_user to get_user_by_email
        login_user(user)
        logger.info(f"User {email} verified and logged in")
        return jsonify({"message": message, "redirect": "/dashboard"}), 200
    logger.error(f"OTP verification failed for {email}: {message}")
    return jsonify({"error": message}), 400

@app.route('/logout')
@login_required
def logout():
    email = current_user.email
    logout_user()
    session.clear()
    logger.info(f"User {email} logged out")
    return jsonify({"message": "Logged out", "redirect": "/"}), 200

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route("/upload", methods=["POST"])
@login_required
@csrf.exempt
def upload():
    if 'file' not in request.files:
        logger.error("No file selected in upload request")
        return jsonify({"error": "No file selected"}), 400
        
    file = request.files['file']
    if file.filename == '':
        logger.error("Empty filename in upload request")
        return jsonify({"error": "No file selected"}), 400
    if file.content_length > 100 * 1024 * 1024:  # 100MB limit
        logger.error(f"File too large: {file.filename}")
        return jsonify({"error": "File too large (max 100MB)"}), 400

    temp_path = None
    try:
        base_filename = secure_filename(file.filename)
        unique_suffix = uuid.uuid4().hex[:8]
        storage_filename = f"{base_filename}_{unique_suffix}"  # Filename for storage providers
        temp_path = os.path.join(tempfile.gettempdir(), storage_filename)
        
        # Save file in chunks
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(temp_path, 'wb') as f:
            while True:
                chunk = file.stream.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
        
        file_size = os.path.getsize(temp_path)
        size_mb = file_size / (1024 * 1024)
        
        # Extract and store file content using AIAgent
        content = ai_agent.extract_text(temp_path)
        if content:
            temp_file_id = str(uuid.uuid4())
            ai_agent.store_content(temp_file_id, base_filename, content)
        
        logger.info(f"Uploading file: {storage_filename} ({size_mb:.2f} MB) for {current_user.email}")
        file_manager = FileManager(current_user)
        chunk_ids = file_manager.upload_file(temp_path, storage_filename, current_user.email)
        if not chunk_ids:
            raise Exception("File upload to storage provider failed")
        
        # Use base_filename for File object to ensure correct categorization
        file_obj = File(filename=base_filename, user_email=current_user.email, chunk_ids=chunk_ids, size_mb=size_mb)
        if not file_obj.save():
            logger.error(f"Failed to save {base_filename} metadata to Firestore")
            ai_agent.delete_content(temp_file_id)
            raise Exception("Failed to save file metadata to Firestore")
        
        # Update file_id in content storage
        if content:
            ai_agent.delete_content(temp_file_id)
            ai_agent.store_content(file_obj.id, base_filename, content)
        
        user = User.get_user_by_email(current_user.email)
        user.update_storage_used(size_mb)
        user.save()
        
        logger.info(f"Uploaded {base_filename}, Size: {size_mb:.2f} MB, New Storage Used: {user.storage_used:.2f} MB")
        
        return jsonify({
            "message": "File uploaded successfully",
            "filename": base_filename,
            "size_mb": size_mb
        })
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as cleanup_error:
                logger.error(f"Cleanup failed for {temp_path}: {str(cleanup_error)}")

@app.route("/list_files", methods=["GET"])
@login_required
def list_files():
    try:
        files = File.get_files(current_user.email)
        if files is None:
            return jsonify({"error": "Failed to retrieve files"}), 500
            
        for f in files:
            f['display_filename'] = '_'.join(f['filename'].split('_')[:-1])
            f['file_id'] = f['id']
        categorized = {
            "Images": [f for f in files if f['category'] == "Images"],
            "Documents": [f for f in files if f['category'] == "Documents"],
            "Videos": [f for f in files if f['category'] == "Videos"],
            "Audio": [f for f in files if f['category'] == "Audio"],
            "Other": [f for f in files if f['category'] == "Other"]
        }
        logger.info(f"Listed files for {current_user.email}: {len(files)} files found")
        return jsonify({
            "success": True,
            "files": files,
            "categorized": categorized
        })
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/search_files", methods=["GET"])
@login_required
def search_files():
    query = request.args.get('query', '').lower()
    try:
        files = File.get_files(current_user.email)
        filtered = [f for f in files if query in '_'.join(f['filename'].split('_')[:-1]).lower()]
        for f in filtered:
            f['display_filename'] = '_'.join(f['filename'].split('_')[:-1])
            f['file_id'] = f['id']
        logger.info(f"Searched files for {current_user.email} with query '{query}': {len(filtered)} results")
        return jsonify({"success": True, "files": filtered})
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/stats", methods=["GET"])
@login_required
def stats():
    try:
        files = File.get_files(current_user.email)
        if files is None:
            raise ValueError("Failed to retrieve files")
        total_files = len(files)
        total_size = sum(f['size_mb'] for f in files) if files else 0.0
        
        user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
        if user is None:
            raise ValueError("User not found")
        
        if abs(user.storage_used - total_size) > 0.01:
            user.storage_used = total_size
            user.save()
            logger.warning(f"Corrected storage_used for {current_user.email} to match total_size: {total_size} MB")
        
        logger.info(f"Stats for {current_user.email}: Files: {total_files}, Total Size: {total_size} MB, Storage Used: {user.storage_used:.2f} MB")
        return jsonify({
            "success": True,
            "total_files": total_files,
            "total_size_mb": round(total_size, 2),
            "storage_used": round(user.storage_used, 2)
        })
    except Exception as e:
        logger.error(f"Stats failed for {current_user.email}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to fetch stats: {str(e)}"}), 500

def get_file_by_id(file_id, user_email):
    files = File.get_files(user_email)
    return next((f for f in files if f['id'] == file_id), None)

@app.route("/download/<file_id>", methods=["GET"])
@login_required
def download(file_id):
    try:
        file = get_file_by_id(file_id, current_user.email)
        if not file:
            logger.error(f"File with ID {file_id} not found for {current_user.email}")
            return jsonify({"error": "File not found"}), 404
            
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, file['filename'])
        
        chunks = file['chunk_ids']
        if not chunks or not isinstance(chunks, list):
            raise ValueError("Invalid chunk data structure")
            
        required_fields = ['provider_id', 'chunk_number', 'chunk_path']
        for chunk in chunks:
            if not all(field in chunk for field in required_fields):
                raise ValueError("Chunk data missing required fields")
        
        file_manager = FileManager(current_user)
        file_manager.download_file(file['filename'], chunks, output_path, current_user.email)
        
        if not os.path.exists(output_path):
            raise FileNotFoundError("File reconstruction failed")
            
        base_filename = '_'.join(file['filename'].split('_')[:-1])
        mime_type = mimetypes.guess_type(base_filename)[0] or "application/octet-stream"
        
        download_files[base_filename] = output_path
        logger.info(f"Downloaded {file['filename']} for {current_user.email}")
        
        return send_file(
            output_path,
            as_attachment=True,
            mimetype=mime_type,
            download_name=base_filename
        )
        
    except Exception as e:
        logger.error(f"Download failed for file ID {file_id}: {str(e)}", exc_info=True)
        if 'output_path' in locals() and os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Cleaned up {output_path} in exception handler")
            except Exception as cleanup_error:
                logger.error(f"Cleanup failed in exception block: {str(cleanup_error)}")
        return jsonify({"error": str(e)}), 500

@app.route("/cleanup_download/<filename>", methods=["POST"])
@login_required
def cleanup_download(filename):
    try:
        if filename in download_files:
            output_path = download_files.pop(filename)
            if os.path.exists(output_path):
                os.remove(output_path)
                logger.info(f"Cleaned up download file: {output_path}")
            return jsonify({"success": True, "message": "Download file cleaned up"}), 200
        logger.warning(f"File {filename} not found in download cache")
        return jsonify({"error": "File not found in download cache"}), 404
    except Exception as e:
        logger.error(f"Cleanup failed for {filename}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/preview/<file_id>", methods=["GET"])
@login_required
def preview(file_id):
    try:
        file = get_file_by_id(file_id, current_user.email)
        if not file:
            logger.error(f"File with ID {file_id} not found for {current_user.email}")
            return jsonify({"error": "File not found"}), 404
            
        os.makedirs("downloads", exist_ok=True)
        output_path = os.path.join("downloads", file['filename'])
        
        chunks = file['chunk_ids']
        if not chunks or not isinstance(chunks, list):
            raise ValueError("Invalid chunk data structure")
            
        required_fields = ['provider_id', 'chunk_number', 'chunk_path']
        for chunk in chunks:
            if not all(field in chunk for field in required_fields):
                raise ValueError("Chunk data missing required fields")
        
        file_manager = FileManager(current_user)
        file_manager.download_file(file['filename'], chunks, output_path, current_user.email)
        
        if not os.path.exists(output_path):
            raise FileNotFoundError("File reconstruction failed")
            
        base_filename = '_'.join(file['filename'].split('_')[:-1])
        mime_type = mimetypes.guess_type(base_filename)[0] or "application/octet-stream"
        
        preview_files[base_filename] = output_path
        logger.info(f"Previewing {file['filename']} for {current_user.email} with MIME type {mime_type}")
        
        return send_file(
            output_path,
            as_attachment=False,
            mimetype=mime_type
        )
        
    except Exception as e:
        logger.error(f"Preview failed for file ID {file_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/cleanup_preview/<filename>", methods=["POST"])
@login_required
def cleanup_preview(filename):
    try:
        if filename in preview_files:
            output_path = preview_files.pop(filename)
            if os.path.exists(output_path):
                os.remove(output_path)
                logger.info(f"Cleaned up preview file: {output_path}")
            return jsonify({"success": True, "message": "Preview file cleaned up"}), 200
        logger.warning(f"File {filename} not found in preview cache")
        return jsonify({"error": "File not found in preview cache"}), 404
    except Exception as e:
        logger.error(f"Cleanup failed for {filename}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/delete/<file_id>", methods=["DELETE"])
@login_required
def delete(file_id):
    try:
        file = get_file_by_id(file_id, current_user.email)
        if not file:
            logger.error(f"File with ID {file_id} not found for {current_user.email}")
            return jsonify({"error": "File not found"}), 404
            
        file_manager = FileManager(current_user)
        success = file_manager.delete_file(file['filename'], file['chunk_ids'], current_user.email)
        
        if not success:
            logger.error(f"Failed to delete all chunks for {file['filename']} from storage providers")
            return jsonify({"error": "Failed to delete file from all providers"}), 500
        
        user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
        user.update_storage_used(-file['size_mb'])
        user.save()
        logger.info(f"Deleted {file['filename']} from providers, New Storage Used: {user.storage_used:.2f} MB")
        
        File.delete_file(file['id'])
        ai_agent.delete_content(file['id'])
        logger.info(f"Deleted {file['filename']} from Firestore and Firestore content")
        return jsonify({"success": True, "message": "File deleted"}), 200
        
    except Exception as e:
        logger.error(f"Delete failed for file ID {file_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/storage_accounts', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_storage_accounts():
    if request.method == 'GET':
        try:
            user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
            return jsonify({
                "success": True,
                "storage_accounts": user.get_storage_accounts_info(),
                "total_storage": user.get_total_available_storage()
            })
        except Exception as e:
            logger.error(f"Failed to get storage accounts: {str(e)}")
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        data = request.get_json() or request.form
        provider_type = data.get('provider_type')
        email = data.get('email')
        
        if not provider_type or not email:
            return jsonify({"error": "Provider type and email are required"}), 400
        
        user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
        if any(acc['email'] == email and acc['provider_type'] == provider_type 
               for acc in user.storage_accounts):
            return jsonify({"error": "This account is already added"}), 400
        
        account = user.add_storage_account(provider_type, email, status='initializing')
        if not user.save():
            return jsonify({"error": "Failed to initialize storage account"}), 500
        
        session['pending_storage_account'] = account['id']
        
        if provider_type == 'google_drive':
            auth_url = (
                f"https://accounts.google.com/o/oauth2/auth?"
                f"client_id={GOOGLE_CLIENT_ID}&"
                f"redirect_uri={GOOGLE_REDIRECT_URI}&"
                f"scope=https://www.googleapis.com/auth/drive&"
                f"response_type=code&"
                f"state={account['id']}&"
                f"access_type=offline&"
                f"prompt=consent&"
                f"login_hint={email}"
            )
            return jsonify({
                "success": True,
                "auth_url": auth_url,
                "message": "Redirect to Google for authorization"
            })
        
        elif provider_type == 'dropbox':
            auth_url = (
                f"https://www.dropbox.com/oauth2/authorize?"
                f"client_id={DROPBOX_CLIENT_ID}&"
                f"redirect_uri={DROPBOX_REDIRECT_URI}&"
                f"response_type=code&"
                f"state={account['id']}&"
                f"token_access_type=offline"  # Ensure refresh token is requested
            )
            return jsonify({
                "success": True,
                "auth_url": auth_url,
                "message": "Redirect to Dropbox for authorization"
            })
        
        return jsonify({"error": "Unsupported provider"}), 400

    elif request.method == 'DELETE':
        account_id = request.args.get('account_id')
        if not account_id:
            return jsonify({"error": "Account ID required"}), 400
            
        user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
        account = next((acc for acc in user.storage_accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({"error": "Account not found"}), 404
            
        user.storage_accounts = [acc for acc in user.storage_accounts if acc['id'] != account_id]
        if not user.save():
            return jsonify({"error": "Failed to delete storage account"}), 500
            
        return jsonify({"success": True, "message": "Storage account deleted"})

@app.route('/oauth/google/callback')
@login_required
def google_oauth_callback():
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        if not code or not state:
            return jsonify({"error": "Authorization failed"}), 400
        
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        response = requests.post(token_url, data=data, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        
        user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
        account = next((acc for acc in user.storage_accounts if acc['id'] == state), None)
        if not account:
            return jsonify({"error": "Storage account not found"}), 404
        
        account['credentials'] = {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token'),
            'expires_in': token_data['expires_in'],
            'expires_at': time.time() + token_data['expires_in'] - 60
        }
        account['status'] = 'connected'
        account['is_active'] = True
        
        user.update_storage_quota()
        if not user.save():
            return jsonify({"error": "Failed to save account"}), 500
        
        session.pop('pending_storage_account', None)
        return redirect('/dashboard?storage=connected')
    except Exception as e:
        logger.error(f"Google OAuth callback failed: {str(e)}")
        user = User.get_user_by_email(current_user.email)  # Changed from get_user to get_user_by_email
        account = next((acc for acc in user.storage_accounts if acc['id'] == state), None)
        if account:
            account['status'] = 'failed'
            account['error'] = str(e)
            user.save()
        return redirect('/dashboard?storage=failed')

@app.route('/oauth/dropbox/callback')
@login_required
def dropbox_oauth_callback():
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        if not code or not state:
            return jsonify({"error": "Authorization failed"}), 400
        
        token_url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            'code': code,
            'client_id': DROPBOX_CLIENT_ID,
            'client_secret': DROPBOX_CLIENT_SECRET,
            'redirect_uri': DROPBOX_REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        response = requests.post(token_url, data=data, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        
        logger.info(f"Dropbox OAuth response: {token_data}")
        if 'refresh_token' not in token_data:
            logger.error(f"No refresh token received for Dropbox account (state: {state})")
        
        user = User.get_user_by_email(current_user.email)
        account = next((acc for acc in user.storage_accounts if acc['id'] == state), None)
        if not account:
            return jsonify({"error": "Storage account not found"}), 404
        
        account['credentials'] = {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token'),
            'expires_in': token_data.get('expires_in', 14400),
            'expires_at': time.time() + token_data.get('expires_in', 14400) - 60
        }
        account['status'] = 'connected'
        account['is_active'] = True
        
        user.update_storage_quota()
        if not user.save():
            return jsonify({"error": "Failed to save account"}), 500
        
        session.pop('pending_storage_account', None)
        return redirect('/dashboard?storage=connected')
    except Exception as e:
        logger.error(f"Dropbox OAuth callback failed: {str(e)}", exc_info=True)
        user = User.get_user_by_email(current_user.email)
        account = next((acc for acc in user.storage_accounts if acc['id'] == state), None)
        if account:
            account['status'] = 'failed'
            account['error'] = str(e)
            user.save()
        return redirect('/dashboard?storage=failed')

@app.route('/ai/ask', methods=['POST'])
@login_required
def ai_ask():
    try:
        data = request.get_json()
        query = data.get('question')
        if not query:
            return jsonify({"error": "Question required"}), 400
            
        logger.info(f"AI query from {current_user.email}: {query}")
        
        # Get user files for context
        files = File.get_files(current_user.email)
        if files is None:
            files = []
        
        # Use AIAgent to process query
        answer = ai_agent.answer_query(query, current_user.email, files)
        
        return jsonify({"success": True, "answer": answer})
        
    except Exception as e:
        logger.error(f"AI query failed for {current_user.email}: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=os.getenv('FLASK_ENV') == 'development', port=port)