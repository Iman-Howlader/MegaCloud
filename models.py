import os
import json
import logging
import time
from flask_login import UserMixin
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

try:
    firebase_creds = os.getenv('FIREBASE_CREDENTIALS')
    if not firebase_creds:
        raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")
    cred = credentials.Certificate(json.loads(firebase_creds))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase Firestore initialized successfully with JSON string from env")
except ValueError as ve:
    logger.error(f"Firebase initialization failed: {ve}")
    raise
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")
    raise

class UserRepository:
    @staticmethod
    def init_db():
        logger.info("Firestore initialized (no schema creation required)")

    @staticmethod
    def get_user(email: str):
        try:
            doc_ref = db.collection('users').document(email)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return User(
                    id=doc.id,
                    email=data['email'],
                    otp=data.get('otp'),
                    otp_expiry=data.get('otp_expiry'),
                    storage_used=data.get('storage_used', 0.0)
                )
            return None
        except Exception as e:
            logger.error(f"Error getting user {email}: {e}")
            return None

    @staticmethod
    def save_user(user):
        try:
            doc_ref = db.collection('users').document(user.email)
            doc_ref.set({
                'email': user.email,
                'otp': user.otp,
                'otp_expiry': user.otp_expiry.isoformat() if user.otp_expiry else None,
                'storage_used': user.storage_used
            }, merge=True)
            logger.info(f"Saved user {user.email} to Firestore")
            return True
        except Exception as e:
            logger.error(f"Error saving user {user.email}: {e}")
            return False

class User(UserMixin):
    def __init__(self, email, otp=None, otp_expiry=None, storage_used=0.0, id=None):
        self.id = id or email
        self.email = email
        self.otp = otp
        self.otp_expiry = datetime.strptime(otp_expiry, '%Y-%m-%dT%H:%M:%S.%f') if otp_expiry else None
        self.storage_used = storage_used

    def get_id(self):
        return self.email

    def generate_otp(self):
        from auth import AuthManager
        self.otp = AuthManager.generate_otp()
        self.otp_expiry = datetime.now() + timedelta(minutes=10)
        return self.otp

    def verify_otp(self, otp):
        if not self.otp or not self.otp_expiry:
            return False
        return self.otp == otp and datetime.now() < self.otp_expiry

    def clear_otp(self):
        self.otp = None
        self.otp_expiry = None

    def update_storage_used(self, size_mb):
        self.storage_used += size_mb

    def save(self):
        return UserRepository.save_user(self)

    @staticmethod
    def get_user(email):
        return UserRepository.get_user(email)

class FileRepository:
    @staticmethod
    def save_file(file):
        try:
            # Check if file already exists for this user
            existing_file = FileRepository.get_file_by_name(file.filename, file.user_email)
            if existing_file:
                logger.warning(f"File {file.filename} already exists for {file.user_email}, skipping save")
                return False  # Indicate that save was skipped due to duplicate
            
            doc_ref = db.collection('files').document()
            doc_ref.set({
                'filename': file.filename,
                'chunk_ids': json.dumps(file.chunk_ids),
                'user_email': file.user_email,
                'size_mb': file.size_mb,
                'category': file.category,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"Saved file {file.filename} for {file.user_email}")
            return True
        except Exception as e:
            logger.error(f"Error saving file {file.filename}: {e}")
            return False

    @staticmethod
    def get_files(user_email):
        try:
            query = db.collection('files').where('user_email', '==', user_email).stream()
            processed_files = []
            for doc in query:
                data = doc.to_dict()
                chunk_ids = json.loads(data['chunk_ids']) if data['chunk_ids'] else []
                if chunk_ids and isinstance(chunk_ids[0], str):
                    chunk_ids = [
                        {
                            "provider_id": (i % 5) + 1,
                            "chunk_number": i,
                            "chunk_path": chunk_id,
                            "chunk_hash": "placeholder"
                        }
                        for i, chunk_id in enumerate(chunk_ids)
                    ]
                processed_files.append({
                    "id": doc.id,
                    "filename": data['filename'],
                    "chunk_ids": chunk_ids,
                    "size_mb": data['size_mb'],
                    "category": data['category']
                })
            return processed_files
        except Exception as e:
            logger.error(f"Error getting files for {user_email}: {e}")
            return []

    @staticmethod
    def get_file_by_name(filename, user_email):
        max_retries = 3
        retry_delay = 0.5  # seconds
        
        for attempt in range(max_retries):
            try:
                query = db.collection('files').where('filename', '==', filename).where('user_email', '==', user_email).stream()
                for doc in query:
                    data = doc.to_dict()
                    chunk_ids = json.loads(data['chunk_ids']) if data['chunk_ids'] else []
                    if chunk_ids and isinstance(chunk_ids[0], str):
                        chunk_ids = [
                            {
                                "provider_id": (i % 5) + 1,
                                "chunk_number": i,
                                "chunk_path": chunk_id,
                                "chunk_hash": "placeholder"
                            }
                            for i, chunk_id in enumerate(chunk_ids)
                        ]
                    logger.info(f"Found file {filename} for {user_email} on attempt {attempt + 1}")
                    return {
                        "id": doc.id,
                        "filename": data['filename'],
                        "chunk_ids": chunk_ids,
                        "size_mb": data['size_mb'],
                        "category": data['category'],
                        "user_email": data['user_email']
                    }
                logger.info(f"No file {filename} found for {user_email} on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return None
            except Exception as e:
                logger.error(f"Error getting file {filename} for {user_email}: {str(e)}")
                return None

    @staticmethod
    def delete_file(file_id):
        try:
            db.collection('files').document(file_id).delete()
            logger.info(f"Deleted file with ID {file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            return False

class File:
    def __init__(self, filename, user_email, chunk_ids=None, chunks=None, size_mb=0.0, file_size=None, category=None):
        self.filename = filename
        self.user_email = user_email
        self.size_mb = size_mb or (file_size / (1024 * 1024) if file_size else 0.0)
        self.category = category or self._categorize()
        if chunks:
            self.chunk_ids = chunks
        elif isinstance(chunk_ids, list):
            if all(isinstance(x, dict) for x in chunk_ids):
                self.chunk_ids = chunk_ids
            else:
                self.chunk_ids = [
                    {
                        "provider_id": (i % 5) + 1,
                        "chunk_number": i,
                        "chunk_path": chunk_id,
                        "chunk_hash": "placeholder"
                    }
                    for i, chunk_id in enumerate(chunk_ids)
                ]
        else:
            self.chunk_ids = []

    def _categorize(self):
        ext = self.filename.lower().split('.')[-1]
        if ext in ['png', 'jpg', 'jpeg', 'gif']:
            return "Images"
        elif ext in ['pdf', 'doc', 'docx', 'txt']:
            return "Documents"
        elif ext in ['mp4', 'webm', 'ogg', 'mov', 'avi']:
            return "Videos"
        return "Other"

    def save(self):
        return FileRepository.save_file(self)

    @staticmethod
    def get_files(user_email):
        return FileRepository.get_files(user_email)

    @staticmethod
    def get_file_by_name(filename, user_email):
        return FileRepository.get_file_by_name(filename, user_email)

    @staticmethod
    def delete_file(file_id):
        return FileRepository.delete_file(file_id)