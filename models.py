import os
import json
import logging
import time
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from dotenv import load_dotenv
import uuid
import requests
from storage_providers.google_drive import GoogleDriveProvider
from storage_providers.dropbox import DropboxProvider
from tenacity import retry, stop_after_attempt, wait_exponential
from flask_login import UserMixin

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

# Initialize Firebase Firestore
try:
    firebase_creds = os.getenv('FIREBASE_CREDENTIALS')
    if not firebase_creds:
        raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")
    cred = credentials.Certificate(json.loads(firebase_creds))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase Firestore initialized successfully with JSON string from env")
except Exception as e:
    logger.error(f"Failed to initialize Firestore: {str(e)}", exc_info=True)
    raise

class UserRepository:
    @staticmethod
    def init_db():
        try:
            test_doc = db.collection('test').document('init')
            test_doc.set({'initialized': True})
            test_doc.delete()
            logger.info("Firestore database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore database: {str(e)}", exc_info=True)
            raise

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_user_by_email(email: str):
        try:
            doc_ref = db.collection('users').document(email)
            doc = doc_ref.get()
            if doc.exists:
                return User.from_dict(doc.to_dict())
            return None
        except Exception as e:
            logger.error(f"Failed to fetch user {email} from Firestore: {str(e)}", exc_info=True)
            raise

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_user_by_username(username: str):
        try:
            query = db.collection('users').where(filter=FieldFilter('username', '==', username)).limit(1).stream()
            for doc in query:
                return User.from_dict(doc.to_dict())
            return None
        except Exception as e:
            logger.error(f"Failed to fetch user by username {username} from Firestore: {str(e)}", exc_info=True)
            raise

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def save_user(user: 'User'):
        try:
            doc_ref = db.collection('users').document(user.email)
            current_data = doc_ref.get().to_dict() if doc_ref.get().exists else {}
            new_data = user.to_dict()
            if current_data == new_data:
                logger.debug(f"No changes for user {user.email}, skipping save")
                return True
            doc_ref.set(new_data)
            logger.info(f"User {user.email} saved to Firestore")
            return True
        except Exception as e:
            logger.error(f"Failed to save user {user.email} to Firestore: {str(e)}", exc_info=True)
            return False

class User(UserMixin):
    def __init__(self, email: str, first_name: str = "", last_name: str = "", 
                 username: str = "", storage_used: float = 0.0, storage_accounts: list = None, 
                 otp: str = None, otp_expiry: float = None):
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.storage_used = storage_used
        self.storage_accounts = storage_accounts or []
        self.otp = otp
        self.otp_expiry = otp_expiry

    def get_id(self):
        return self.email

    @staticmethod
    def get_user_by_email(email: str):
        return UserRepository.get_user_by_email(email)

    @staticmethod
    def get_user_by_username(username: str):
        return UserRepository.get_user_by_username(username)

    @staticmethod
    def get_user_by_identifier(identifier: str):
        user = User.get_user_by_email(identifier)
        if not user:
            user = User.get_user_by_username(identifier)
        return user

    def save(self):
        return UserRepository.save_user(self)

    def generate_otp(self):
        from auth import AuthManager
        self.otp = AuthManager.generate_otp()
        self.otp_expiry = (datetime.utcnow() + timedelta(minutes=10)).timestamp()
        return self.otp

    def verify_otp(self, otp: str) -> bool:
        if not self.otp or not self.otp_expiry:
            return False
        if datetime.utcnow().timestamp() > self.otp_expiry:
            return False
        return self.otp == otp

    def clear_otp(self):
        self.otp = None
        self.otp_expiry = None

    def add_storage_account(self, provider_type: str, email: str, status: str = 'initializing'):
        account = {
            'id': str(uuid.uuid4()),
            'provider_type': provider_type,
            'email': email,
            'status': status,
            'is_active': False,
            'credentials': None,
            'storage_quota': {'total_mb': 0, 'used_mb': 0, 'free_mb': 0}
        }
        self.storage_accounts.append(account)
        return account

    def get_active_storage_accounts(self):
        self.refresh_credentials()
        return [acc for acc in self.storage_accounts if acc.get('is_active', False)]

    def refresh_credentials(self):
        for account in self.storage_accounts:
            if not account.get('credentials') or not account.get('is_active', False):
                continue
            try:
                if account['provider_type'] == 'google_drive':
                    self._refresh_google_drive_token(account)
                elif account['provider_type'] == 'dropbox':
                    self._verify_dropbox_token(account)
            except Exception as e:
                logger.error(f"Failed to refresh credentials for {account['email']} ({account['provider_type']}): {str(e)}")
                account['status'] = 'failed'
                account['error'] = str(e)
        self.save()

    def _refresh_google_drive_token(self, account):
        credentials = account['credentials']
        if not credentials.get('refresh_token'):
            account['status'] = 'failed'
            account['error'] = 'No refresh token available'
            return

        expires_at = credentials.get('expires_at', 0)
        if expires_at > time.time() + 300:
            return

        try:
            response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                    'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                    'refresh_token': credentials['refresh_token'],
                    'grant_type': 'refresh_token'
                },
                timeout=10
            )
            response.raise_for_status()
            token_data = response.json()
            
            account['credentials'] = {
                'access_token': token_data['access_token'],
                'refresh_token': credentials['refresh_token'],
                'expires_in': token_data['expires_in'],
                'expires_at': time.time() + token_data['expires_in'] - 60
            }
            account['status'] = 'connected'
            account['is_active'] = True
            logger.info(f"Refreshed Google Drive token for {account['email']}")
        except Exception as e:
            account['status'] = 'failed'
            account['error'] = str(e)
            logger.error(f"Google Drive token refresh failed for {account['email']}: {str(e)}")

    def _verify_dropbox_token(self, account):
        credentials = account['credentials']
        try:
            provider = DropboxProvider(account['credentials'], f"/MegaCloud/{self.email}")
            provider.get_storage_quota()
            account['status'] = 'connected'
            account['is_active'] = True
            account['credentials'] = provider.update_credentials()
            logger.info(f"Verified Dropbox token for {account['email']}")
        except Exception as e:
            account['status'] = 'failed'
            account['error'] = str(e)
            logger.error(f"Dropbox token verification failed for {account['email']}: {str(e)}")

    def update_storage_used(self, size_mb: float):
        self.storage_used = max(0.0, self.storage_used + size_mb)

    def get_storage_accounts_info(self):
        self.update_storage_quota()
        return [
            {
                'id': acc['id'],
                'provider_type': acc['provider_type'],
                'email': acc['email'],
                'status': acc['status'],
                'total_mb': acc['storage_quota']['total_mb'],
                'used_mb': acc['storage_quota']['used_mb'],
                'free_mb': acc['storage_quota']['free_mb'],
                'error': acc.get('error')
            }
            for acc in self.storage_accounts
        ]

    def get_total_available_storage(self):
        self.update_storage_quota()
        return sum(acc['storage_quota']['free_mb'] for acc in self.storage_accounts)

    def update_storage_quota(self):
        self.refresh_credentials()
        for account in self.storage_accounts:
            if account.get('is_active') and account.get('credentials'):
                try:
                    if account['provider_type'] == 'google_drive':
                        provider = GoogleDriveProvider(account['credentials'], f"MegaCloud/{self.email}", self.email)
                        account['storage_quota'] = provider.get_storage_quota()
                    elif account['provider_type'] == 'dropbox':
                        provider = DropboxProvider(account['credentials'], f"/MegaCloud/{self.email}")
                        account['storage_quota'] = provider.get_storage_quota()
                except Exception as e:
                    logger.error(f"Quota update failed for {account['email']} ({account['provider_type']}): {str(e)}")
                    account['storage_quota'] = {'total_mb': 0, 'used_mb': 0, 'free_mb': 0}
                    account['status'] = 'failed'
                    account['error'] = str(e)

    def to_dict(self):
        return {
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'username': self.username,
            'storage_used': self.storage_used,
            'storage_accounts': self.storage_accounts,
            'otp': self.otp,
            'otp_expiry': self.otp_expiry
        }

    @staticmethod
    def from_dict(data: dict):
        return User(
            email=data['email'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            username=data.get('username', ''),
            storage_used=data.get('storage_used', 0.0),
            storage_accounts=data.get('storage_accounts', []),
            otp=data.get('otp'),
            otp_expiry=data.get('otp_expiry')
        )

class File:
    FILE_CATEGORIES = {
        'Images': ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'],
        'Documents': ['pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx', 'csv'],
        'Videos': ['mp4', 'avi', 'mov', 'wmv', 'mkv'],
        'Audio': ['mp3', 'wav', 'ogg', 'flac'],
        'Other': []
    }

    def __init__(self, filename: str, user_email: str, chunk_ids: list, size_mb: float):
        self.id = str(uuid.uuid4())
        self.filename = filename
        self.user_email = user_email
        self.chunk_ids = chunk_ids
        self.size_mb = size_mb
        self.upload_timestamp = datetime.utcnow().timestamp()
        self.category = self._categorize()

    def _categorize(self):
        ext = self.filename.split('.')[-1].lower() if '.' in self.filename else ''
        for category, extensions in self.FILE_CATEGORIES.items():
            if ext in extensions:
                return category
        return 'Other'

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_files(user_email: str):
        try:
            docs = db.collection('files').where(filter=FieldFilter('user_email', '==', user_email)).stream()
            files = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                if 'chunk_ids' in data and isinstance(data['chunk_ids'], list):
                    if not all(isinstance(chunk, dict) for chunk in data['chunk_ids']):
                        logger.warning(f"Converting legacy chunk_ids for file {data['filename']}")
                        data['chunk_ids'] = [
                            {'chunk_path': chunk} if isinstance(chunk, str) else chunk
                            for chunk in data['chunk_ids']
                        ]
                files.append(data)
            logger.info(f"Retrieved {len(files)} files for {user_email}")
            return files
        except Exception as e:
            logger.error(f"Failed to fetch files for {user_email}: {str(e)}", exc_info=True)
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def save(self):
        try:
            doc_ref = db.collection('files').document(self.id)
            doc_ref.set({
                'filename': self.filename,
                'user_email': self.user_email,
                'chunk_ids': self.chunk_ids,
                'size_mb': self.size_mb,
                'upload_timestamp': self.upload_timestamp,
                'category': self.category
            })
            logger.info(f"File {self.filename} saved with ID {self.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save file {self.filename}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def delete_file(file_id: str):
        try:
            doc_ref = db.collection('files').document(file_id)
            doc_ref.delete()
            logger.info(f"File with ID {file_id} deleted from Firestore")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {str(e)}", exc_info=True)
            return False