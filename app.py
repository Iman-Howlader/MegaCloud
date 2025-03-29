from flask import Flask, request, jsonify, render_template, session, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from auth import AuthManager
from models import User, File, UserRepository
from file_manager import FileManager
from storage_providers.google_drive import GoogleDriveProvider
from storage_providers.dropbox import DropboxProvider
import tempfile
import os
import json
import mimetypes
import logging
import uuid
from dotenv import load_dotenv

# Configure logging to both file and stdout
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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

@login_manager.user_loader
def load_user(email):
    return User.get_user(email)

def create_temp_json_file(data_str, prefix):
    if data_str:
        data_str = data_str.replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '').strip()
    try:
        data_dict = json.loads(data_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {data_str[:200]}... - Error: {e}")
        raise
    temp_file = tempfile.NamedTemporaryFile(mode='w', prefix=prefix, suffix='.json', delete=False)
    json.dump(data_dict, temp_file)
    temp_file.close()
    return temp_file.name

storage_providers = []
try:
    dropbox_tokens_json = {
        "dropbox_token_1": json.loads(os.getenv('DROPBOX_TOKEN_1')),
        "dropbox_token_2": json.loads(os.getenv('DROPBOX_TOKEN_2'))
    }
    dropbox_tokens_file = create_temp_json_file(json.dumps(dropbox_tokens_json), 'dropbox_tokens')
    with open(dropbox_tokens_file) as f:
        dropbox_tokens = json.load(f)
    if not isinstance(dropbox_tokens.get("dropbox_token_1"), dict):
        raise ValueError("DROPBOX_TOKEN_1 must be a dictionary with app_key, app_secret, and refresh_token")
    if not isinstance(dropbox_tokens.get("dropbox_token_2"), dict):
        raise ValueError("DROPBOX_TOKEN_2 must be a dictionary with app_key, app_secret, and refresh_token")

    google_cred_user1_file = create_temp_json_file(os.getenv('GOOGLE_CRED_USER1'), 'google_user1')
    google_cred_user2_file = create_temp_json_file(os.getenv('GOOGLE_CRED_USER2'), 'google_user2')
    google_cred_user3_file = create_temp_json_file(os.getenv('GOOGLE_CRED_USER3'), 'google_user3')

    google_providers = [
        GoogleDriveProvider(google_cred_user1_file, "1F2oxw2W4o1MAL0iQdVkzCc2Zjw4z5XoM"),
        GoogleDriveProvider(google_cred_user2_file, "1SQGF0uGOGHJTSJvdbCnRm8cQdftMZbUy"),
        GoogleDriveProvider(google_cred_user3_file, "1ZyNqPeaOkZC2uVWDnlLKg6QuEF5JOMUA")
    ]
    storage_providers.extend(google_providers)
    logger.info("Google Drive providers initialized successfully")

    dropbox_providers = [
        DropboxProvider(dropbox_tokens["dropbox_token_1"], "/MegaCloud01"),
        DropboxProvider(dropbox_tokens["dropbox_token_2"], "/MegaCloud02")
    ]
    storage_providers.extend(dropbox_providers)
    logger.info("Dropbox providers initialized successfully")

except FileNotFoundError as e:
    logger.error(f"Config file missing: {str(e)}")
    raise
except ValueError as e:
    logger.error(f"Configuration error: {str(e)}")
    raise
except Exception as e:
    logger.error(f"Failed to initialize some storage providers: {str(e)}. Proceeding with available providers.")

file_manager = FileManager(storage_providers)
logger.info(f"FileManager initialized with {len(storage_providers)} providers")

preview_files = {}

def get_file_by_id(file_id, email):
    logger.info(f"Looking for file with ID: {file_id} for email: {email}")
    files = File.get_files(email)
    for file in files:
        if str(file['id']) == str(file_id):
            logger.info(f"Found file: {file}")
            return file
    logger.warning(f"No file found with ID: {file_id}")
    return None

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/test_db')
def test_db():
    UserRepository.init_db()
    return "DB OK", 200

@app.route('/request_otp', methods=['POST'])
def request_otp():
    try:
        data = request.form or request.get_json()
        logger.info(f"Received request_otp data: {data}")
        email = data.get('email') if data else None
        if not email:
            logger.error("No email provided in request_otp")
            return jsonify({"error": "Email required"}), 400
        user = User.get_user(email)
        if not user:
            user = User(email=email)
            logger.info(f"Created new user for {email}")
        otp = user.generate_otp()
        logger.info(f"Generated OTP for {email}: {otp}")
        if user.save():
            logger.info(f"Saved user {email} to database")
            if AuthManager.send_otp_email(email, otp):
                logger.info(f"Sent OTP to {email}")
                session['email'] = email
                return jsonify({"message": "OTP sent"}), 200
            else:
                logger.error("Failed to send OTP")
                return jsonify({"error": "Failed to send OTP"}), 500
        else:
            logger.error("Failed to save user to database")
            return jsonify({"error": "Failed to save user"}), 500
    except Exception as e:
        logger.error(f"Error in request_otp: {str(e)}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json() or request.form
    email = session.get('email')
    otp = data.get('otp')
    if not email or not otp:
        logger.warning("Email or OTP missing in /verify_otp")
        return jsonify({"error": "Email or OTP missing"}), 400
    success, message = AuthManager.verify_otp(email, otp)
    if success:
        user = User.get_user(email)
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
    return render_template('dashboard.html')

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if 'file' not in request.files:
        logger.error("No file selected in upload request")
        return jsonify({"error": "No file selected"}), 400
        
    file = request.files['file']
    if file.filename == '':
        logger.error("Empty filename in upload request")
        return jsonify({"error": "No file selected"}), 400

    temp_path = None
    try:
        base_filename = file.filename
        # Append a unique suffix to the filename to avoid Firestore conflicts
        unique_suffix = uuid.uuid4().hex[:8]
        filename = f"{base_filename}_{unique_suffix}"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(temp_path)
        
        file_size = os.path.getsize(temp_path)
        size_mb = file_size / (1024 * 1024)
        
        logger.info(f"Uploading file: {filename} ({size_mb:.2f} MB) for {current_user.email}")
        chunk_ids = file_manager.upload_file(temp_path, filename, current_user.email)
        if not chunk_ids:
            raise Exception("File upload to storage provider failed")
        
        # Save file metadata with the unique filename
        file_obj = File(filename=filename, user_email=current_user.email, chunk_ids=chunk_ids, size_mb=size_mb)
        save_result = file_obj.save()
        if not save_result:
            logger.warning(f"File.save() returned False for {filename}, checking if it exists in Firestore")
            # Verify if the file is already in Firestore
            files = File.get_files(current_user.email)
            if not any(f['filename'] == filename for f in files):
                logger.error(f"Failed to save {filename} metadata to Firestore and it’s not present in the database")
                raise Exception("Failed to save file metadata to Firestore due to a database error")
            else:
                logger.info(f"File {filename} already exists in Firestore, proceeding despite save() returning False")
        
        user = User.get_user(current_user.email)
        if not user:
            user = User(email=current_user.email)
        user.update_storage_used(size_mb)
        if not user.save():
            raise Exception("Failed to update user storage in Firestore")
        
        logger.info(f"Uploaded {filename}, Size: {size_mb:.2f} MB, New Storage Used: {user.storage_used:.2f} MB")
        
        return jsonify({
            "message": "File uploaded successfully",
            "filename": base_filename,  # Return original filename without suffix
            "size_mb": size_mb
        })
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.route("/list_files", methods=["GET"])
@login_required
def list_files():
    try:
        files = File.get_files(current_user.email)
        # Remove unique suffix for display and include file ID
        for f in files:
            f['display_filename'] = '_'.join(f['filename'].split('_')[:-1])
            f['file_id'] = f['id']  # Include file ID for frontend actions
        categorized = {
            "Images": [f for f in files if f['category'] == "Images"],
            "Documents": [f for f in files if f['category'] == "Documents"],
            "Videos": [f for f in files if f['category'] == "Videos"],
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
        # Remove unique suffix for search and include file ID
        filtered = [f for f in files if query in '_'.join(f['filename'].split('_')[:-1]).lower()]
        for f in filtered:
            f['display_filename'] = '_'.join(f['filename'].split('_')[:-1])
            f['file_id'] = f['id']  # Include file ID for frontend actions
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
        
        user = User.get_user(current_user.email)
        if user is None:
            raise ValueError("User not found")
        
        if abs(user.storage_used - total_size) > 0.01:
            user.storage_used = total_size
            user.save()
            logger.warning(f"Corrected storage_used for {current_user.email} to match total_size: {total_size} MB")
        
        logger.info(f"Stats for {current_user.email}: Files: {total_files}, Total Size: {total_size} MB, Storage Used: {user.storage_used} MB")
        return jsonify({
            "success": True,
            "total_files": total_files,
            "total_size_mb": round(total_size, 2),
            "storage_used": round(user.storage_used, 2)
        })
    except Exception as e:
        logger.error(f"Stats failed for {current_user.email}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to fetch stats: {str(e)}"}), 500


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
        
        file_manager.download_file(file['filename'], chunks, output_path)
        
        if not os.path.exists(output_path):
            raise FileNotFoundError("File reconstruction failed")
            
        base_filename = '_'.join(file['filename'].split('_')[:-1])
        mime_type = mimetypes.guess_type(base_filename)[0] or "application/octet-stream"
        logger.info(f"Downloaded {file['filename']} for {current_user.email}")
        response = send_file(
            output_path,
            as_attachment=True,
            mimetype=mime_type,
            download_name=base_filename
        )
        # Delay cleanup to avoid PermissionError
        def cleanup():
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                    logger.info(f"Cleaned up download file: {output_path}")
            except Exception as e:
                logger.error(f"Failed to clean up {output_path}: {str(e)}")
        
        from threading import Timer
        Timer(5.0, cleanup).start()  # Cleanup after 5 seconds
        return response
        
    except Exception as e:
        logger.error(f"Download failed for file ID {file_id}: {str(e)}", exc_info=True)
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
        
        file_manager.download_file(file['filename'], chunks, output_path)
        
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
            
        file_manager.delete_file(file['filename'], file['chunk_ids'], current_user.email)
        
        user = User.get_user(current_user.email)
        user.update_storage_used(-file['size_mb'])
        user.save()
        logger.info(f"Deleted {file['filename']}, New Storage Used: {user.storage_used} MB")
        
        File.delete_file(file['id'])
        
        return jsonify({"success": True, "message": "File deleted successfully"})
    except Exception as e:
        logger.error(f"Delete failed for file ID {file_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    UserRepository.init_db()
    port = int(os.getenv('PORT', 5000))
    app.run(debug=os.getenv('FLASK_ENV') == 'development', host='0.0.0.0', port=port)