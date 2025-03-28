# import sqlite3
# from flask_login import UserMixin
# from datetime import datetime, timedelta
# import json
# import logging
# import tempfile
# import os

# # Configure logging
# logging.basicConfig(level=logging.INFO, filename='app.log', filemode='a',
#                     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# class UserRepository:
#     @staticmethod
#     def get_db_connection():
#         # Use /tmp/ for deployment (e.g., Render), temp dir for local testing
#         db_path = '/tmp/megacloud.db' if os.getenv('RENDER') else os.path.join(tempfile.gettempdir(), 'megacloud.db')
#         conn = sqlite3.connect(db_path, timeout=10)
#         conn.row_factory = sqlite3.Row
#         return conn

#     @staticmethod
#     def init_db():
#         conn = UserRepository.get_db_connection()
#         cursor = conn.cursor()
#         cursor.execute('''
#             CREATE TABLE IF NOT EXISTS users (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 email TEXT UNIQUE NOT NULL,
#                 otp TEXT,
#                 otp_expiry TEXT,
#                 storage_used REAL DEFAULT 0.0
#             )
#         ''')
#         cursor.execute('''
#             CREATE TABLE IF NOT EXISTS files (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 filename TEXT NOT NULL,
#                 chunk_ids TEXT NOT NULL,
#                 user_email TEXT NOT NULL,
#                 size_mb REAL NOT NULL,
#                 category TEXT,
#                 FOREIGN KEY (user_email) REFERENCES users(email)
#             )
#         ''')
#         conn.commit()
#         conn.close()

#     @staticmethod
#     def get_user(email: str):
#         try:
#             conn = UserRepository.get_db_connection()
#             cursor = conn.cursor()
#             cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
#             user_data = cursor.fetchone()
#             conn.close()
#             if user_data:
#                 return User(
#                     id=user_data['id'],
#                     email=user_data['email'],
#                     otp=user_data['otp'],
#                     otp_expiry=user_data['otp_expiry'],
#                     storage_used=user_data['storage_used']
#                 )
#             return None
#         except Exception as e:
#             logger.error(f"Error getting user: {e}")
#             return None

#     @staticmethod
#     def save_user(user):
#         try:
#             conn = UserRepository.get_db_connection()
#             cursor = conn.cursor()
#             if user.id:
#                 cursor.execute(
#                     "UPDATE users SET email = ?, otp = ?, otp_expiry = ?, storage_used = ? WHERE id = ?",
#                     (user.email, user.otp, user.otp_expiry, user.storage_used, user.id)
#                 )
#             else:
#                 cursor.execute(
#                     "INSERT INTO users (email, otp, otp_expiry, storage_used) VALUES (?, ?, ?, ?)",
#                     (user.email, user.otp, user.otp_expiry, user.storage_used)
#                 )
#                 user.id = cursor.lastrowid
#             conn.commit()
#             conn.close()
#             return True
#         except Exception as e:
#             logger.error(f"Error saving user: {e}")
#             return False

# class User(UserMixin):
#     def __init__(self, email, otp=None, otp_expiry=None, storage_used=0.0, id=None):
#         self.id = id
#         self.email = email
#         self.otp = otp
#         self.otp_expiry = otp_expiry
#         self.storage_used = storage_used  # In MB

#     def get_id(self):
#         return str(self.email)

#     def generate_otp(self):
#         from auth import AuthManager
#         self.otp = AuthManager.generate_otp()
#         self.otp_expiry = datetime.now() + timedelta(minutes=10)
#         return self.otp

#     def verify_otp(self, otp):
#         if not self.otp or not self.otp_expiry:
#             return False
#         expiry = datetime.strptime(self.otp_expiry, '%Y-%m-%d %H:%M:%S.%f') if self.otp_expiry else None
#         return self.otp == otp and datetime.now() < expiry

#     def clear_otp(self):
#         self.otp = None
#         self.otp_expiry = None

#     def update_storage_used(self, size_mb):
#         self.storage_used += size_mb

#     def save(self):
#         return UserRepository.save_user(self)

#     @staticmethod
#     def get_user(email):
#         return UserRepository.get_user(email)

# class FileRepository:
#     @staticmethod
#     def get_db_connection():
#         # Use /tmp/ for deployment (e.g., Render), temp dir for local testing
#         db_path = '/tmp/megacloud.db' if os.getenv('RENDER') else os.path.join(tempfile.gettempdir(), 'megacloud.db')
#         conn = sqlite3.connect(db_path, timeout=10)
#         conn.row_factory = sqlite3.Row
#         return conn

#     @staticmethod
#     def save_file(file):
#         try:
#             conn = FileRepository.get_db_connection()
#             cursor = conn.cursor()
#             chunk_data = json.dumps(file.chunk_ids)
#             cursor.execute(
#                 """INSERT INTO files 
#                 (filename, chunk_ids, user_email, size_mb, category) 
#                 VALUES (?, ?, ?, ?, ?)""",
#                 (file.filename, chunk_data, file.user_email, file.size_mb, file.category)
#             )
#             conn.commit()
#             conn.close()
#             return True
#         except Exception as e:
#             logger.error(f"Error saving file: {e}")
#             return False

#     @staticmethod
#     def get_files(user_email):
#         try:
#             conn = FileRepository.get_db_connection()
#             cursor = conn.cursor()
#             cursor.execute("SELECT * FROM files WHERE user_email = ?", (user_email,))
#             files = cursor.fetchall()
#             conn.close()
#             processed_files = []
#             for f in files:
#                 try:
#                     chunk_ids = json.loads(f['chunk_ids']) if isinstance(f['chunk_ids'], str) else f['chunk_ids']
#                     if chunk_ids and isinstance(chunk_ids[0], str):
#                         chunk_ids = [
#                             {
#                                 "provider_id": (i % 5) + 1,
#                                 "chunk_number": i,
#                                 "chunk_path": chunk_id,
#                                 "chunk_hash": "placeholder"
#                             }
#                             for i, chunk_id in enumerate(chunk_ids)
#                         ]
#                     processed_files.append({
#                         "id": f['id'],
#                         "filename": f['filename'],
#                         "chunk_ids": chunk_ids,
#                         "size_mb": f['size_mb'],
#                         "category": f['category']
#                     })
#                 except Exception as e:
#                     logger.error(f"Error processing file {f['id']}: {e}")
#                     continue
#             return processed_files
#         except Exception as e:
#             logger.error(f"Error getting files: {e}")
#             return []

#     @staticmethod
#     def get_file_by_name(filename, user_email):
#         try:
#             conn = FileRepository.get_db_connection()
#             cursor = conn.cursor()
#             cursor.execute("SELECT * FROM files WHERE filename = ? AND user_email = ?", (filename, user_email))
#             file = cursor.fetchone()
#             conn.close()
#             if file:
#                 try:
#                     chunk_ids = json.loads(file['chunk_ids']) if isinstance(file['chunk_ids'], str) else file['chunk_ids']
#                     if chunk_ids and isinstance(chunk_ids[0], str):
#                         chunk_ids = [
#                             {
#                                 "provider_id": (i % 5) + 1,
#                                 "chunk_number": i,
#                                 "chunk_path": chunk_id,
#                                 "chunk_hash": "placeholder"
#                             }
#                             for i, chunk_id in enumerate(chunk_ids)
#                         ]
#                     return {
#                         "id": file['id'],
#                         "filename": file['filename'],
#                         "chunk_ids": chunk_ids,
#                         "size_mb": file['size_mb'],
#                         "category": file['category'],
#                         "user_email": file['user_email']
#                     }
#                 except Exception as e:
#                     logger.error(f"Error processing chunk IDs for file {file['id']}: {e}")
#                     return None
#             return None
#         except Exception as e:
#             logger.error(f"Error getting file: {e}")
#             return None

#     @staticmethod
#     def delete_file(file_id):
#         try:
#             conn = FileRepository.get_db_connection()
#             cursor = conn.cursor()
#             cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
#             conn.commit()
#             conn.close()
#             return True
#         except Exception as e:
#             logger.error(f"Error deleting file: {e}")
#             return False

# class File:
#     def __init__(self, filename, user_email, chunk_ids=None, chunks=None, size_mb=0.0, file_size=None, category=None):
#         self.filename = filename
#         self.user_email = user_email
#         self.size_mb = size_mb or (file_size / (1024 * 1024) if file_size else 0.0)
#         self.category = category or self._categorize()
#         if chunks:
#             self.chunk_ids = chunks
#         elif isinstance(chunk_ids, list):
#             if all(isinstance(x, dict) for x in chunk_ids):
#                 self.chunk_ids = chunk_ids
#             else:
#                 self.chunk_ids = [
#                     {
#                         "provider_id": (i % 5) + 1,
#                         "chunk_number": i,
#                         "chunk_path": chunk_id,
#                         "chunk_hash": "placeholder"
#                     }
#                     for i, chunk_id in enumerate(chunk_ids)
#                 ]
#         else:
#             self.chunk_ids = []

#     def _categorize(self):
#         ext = self.filename.lower().split('.')[-1]
#         if ext in ['png', 'jpg', 'jpeg', 'gif']:
#             return "Images"
#         elif ext in ['pdf', 'doc', 'docx', 'txt']:
#             return "Documents"
#         return "Other"

#     def save(self):
#         return FileRepository.save_file(self)

#     @staticmethod
#     def get_files(user_email):
#         return FileRepository.get_files(user_email)

#     @staticmethod
#     def get_file_by_name(filename, user_email):
#         return FileRepository.get_file_by_name(filename, user_email)

#     @staticmethod
#     def delete_file(file_id):
#         return FileRepository.delete_file(file_id)

# UserRepository.init_db()






import os
import json
import logging
import tempfile
from flask_login import UserMixin
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, filename='app.log', filemode='a',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables for Supabase
load_dotenv()

# Global variable for the connection pool, initialized lazily
db_pool = None

def initialize_db_pool():
    global db_pool
    if db_pool is None:
        try:
            db_pool = pool.SimpleConnectionPool(
                1, 20,  # Min 1, max 20 connections
                host=os.getenv('PGHOST'),
                port=os.getenv('PGPORT'),
                user=os.getenv('PGUSER'),
                password=os.getenv('PGPASSWORD'),
                database=os.getenv('PGDATABASE')
            )
            logger.info("Database pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

class UserRepository:
    @staticmethod
    def get_db_connection():
        initialize_db_pool()  # Ensure pool is ready
        conn = db_pool.getconn()
        return conn

    @staticmethod
    def release_db_connection(conn):
        db_pool.putconn(conn)

    @staticmethod
    def init_db():
        conn = UserRepository.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        otp TEXT,
                        otp_expiry TEXT,
                        storage_used REAL DEFAULT 0.0
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS files (
                        id SERIAL PRIMARY KEY,
                        filename TEXT NOT NULL,
                        chunk_ids JSONB NOT NULL,
                        user_email TEXT NOT NULL,
                        size_mb REAL NOT NULL,
                        category TEXT,
                        CONSTRAINT fk_user
                            FOREIGN KEY (user_email)
                            REFERENCES users(email)
                            ON DELETE CASCADE
                    )
                ''')
                conn.commit()
                logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
        finally:
            UserRepository.release_db_connection(conn)

    @staticmethod
    def get_user(email: str):
        try:
            conn = UserRepository.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                user_data = cur.fetchone()
                if user_data:
                    return User(
                        id=user_data[0],
                        email=user_data[1],
                        otp=user_data[2],
                        otp_expiry=user_data[3],
                        storage_used=user_data[4]
                    )
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
        finally:
            UserRepository.release_db_connection(conn)

    @staticmethod
    def save_user(user):
        try:
            conn = UserRepository.get_db_connection()
            with conn.cursor() as cur:
                if user.id:
                    cur.execute(
                        "UPDATE users SET email = %s, otp = %s, otp_expiry = %s, storage_used = %s WHERE id = %s",
                        (user.email, user.otp, user.otp_expiry, user.storage_used, user.id)
                    )
                else:
                    cur.execute(
                        "INSERT INTO users (email, otp, otp_expiry, storage_used) VALUES (%s, %s, %s, %s) RETURNING id",
                        (user.email, user.otp, user.otp_expiry, user.storage_used)
                    )
                    user.id = cur.fetchone()[0]
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving user: {e}")
            return False
        finally:
            UserRepository.release_db_connection(conn)

class User(UserMixin):
    def __init__(self, email, otp=None, otp_expiry=None, storage_used=0.0, id=None):
        self.id = id
        self.email = email
        self.otp = otp
        self.otp_expiry = otp_expiry
        self.storage_used = storage_used  # In MB

    def get_id(self):
        return str(self.email)

    def generate_otp(self):
        from auth import AuthManager
        self.otp = AuthManager.generate_otp()
        self.otp_expiry = datetime.now() + timedelta(minutes=10)
        return self.otp

    def verify_otp(self, otp):
        if not self.otp or not self.otp_expiry:
            return False
        expiry = datetime.strptime(self.otp_expiry, '%Y-%m-%d %H:%M:%S.%f') if self.otp_expiry else None
        return self.otp == otp and datetime.now() < expiry

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
    def get_db_connection():
        initialize_db_pool()  # Ensure pool is ready
        conn = db_pool.getconn()
        return conn

    @staticmethod
    def release_db_connection(conn):
        db_pool.putconn(conn)

    @staticmethod
    def save_file(file):
        try:
            conn = FileRepository.get_db_connection()
            with conn.cursor() as cur:
                chunk_data = json.dumps(file.chunk_ids)
                cur.execute(
                    """INSERT INTO files 
                    (filename, chunk_ids, user_email, size_mb, category) 
                    VALUES (%s, %s, %s, %s, %s)""",
                    (file.filename, chunk_data, file.user_email, file.size_mb, file.category)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return False
        finally:
            FileRepository.release_db_connection(conn)

    @staticmethod
    def get_files(user_email):
        try:
            conn = FileRepository.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM files WHERE user_email = %s", (user_email,))
                files = cur.fetchall()
                processed_files = []
                for f in files:
                    try:
                        chunk_ids = json.loads(f[2]) if isinstance(f[2], str) else f[2]
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
                            "id": f[0],
                            "filename": f[1],
                            "chunk_ids": chunk_ids,
                            "size_mb": f[4],
                            "category": f[5]
                        })
                    except Exception as e:
                        logger.error(f"Error processing file {f[0]}: {e}")
                        continue
            return processed_files
        except Exception as e:
            logger.error(f"Error getting files: {e}")
            return []
        finally:
            FileRepository.release_db_connection(conn)

    @staticmethod
    def get_file_by_name(filename, user_email):
        try:
            conn = FileRepository.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM files WHERE filename = %s AND user_email = %s", (filename, user_email))
                file = cur.fetchone()
                if file:
                    try:
                        chunk_ids = json.loads(file[2]) if isinstance(file[2], str) else file[2]
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
                        return {
                            "id": file[0],
                            "filename": file[1],
                            "chunk_ids": chunk_ids,
                            "size_mb": file[4],
                            "category": file[5],
                            "user_email": file[3]
                        }
                    except Exception as e:
                        logger.error(f"Error processing chunk IDs for file {file[0]}: {e}")
                        return None
            return None
        except Exception as e:
            logger.error(f"Error getting file: {e}")
            return None
        finally:
            FileRepository.release_db_connection(conn)

    @staticmethod
    def delete_file(file_id):
        try:
            conn = FileRepository.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM files WHERE id = %s", (file_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False
        finally:
            FileRepository.release_db_connection(conn)

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

# Initialize the database only when needed (e.g., first DB call), not at import
# UserRepository.init_db()  # Uncomment if you want to force init on startup