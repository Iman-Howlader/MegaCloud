import os
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import io
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

class GoogleDriveProvider:
    SCOPES = ['https://www.googleapis.com/auth/drive']
    MAX_RETRIES = 3

    def __init__(self, credentials: dict, folder_name: str, user_email: str):
        self.credentials = credentials
        self.folder_name = folder_name
        self.user_email = user_email
        self.service = self._get_service()
        self.folder_id = self._get_or_create_folder()

    def _get_service(self):
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials(
                token=self.credentials['access_token'],
                refresh_token=self.credentials.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=os.getenv('GOOGLE_CLIENT_ID'),
                client_secret=os.getenv('GOOGLE_CLIENT_SECRET')
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Failed to create Google Drive service: {str(e)}")
            raise

    def _get_or_create_folder(self):
        try:
            query = f"name='{self.folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            folders = response.get('files', [])
            if folders:
                return folders[0]['id']
            
            file_metadata = {
                'name': self.folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            return folder.get('id')
        except Exception as e:
            logger.error(f"Failed to get or create folder {self.folder_name}: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def upload(self, file_path: str, filename: str) -> str:
        try:
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id]
            }
            media = MediaFileUpload(file_path)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            file_id = file.get('id')
            logger.info(f"Uploaded {filename} to Google Drive with ID {file_id}")
            return file_id
        except Exception as e:
            logger.error(f"Failed to upload {filename} to Google Drive: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def download(self, file_id: str, output_path: str):
        try:
            request = self.service.files().get_media(fileId=file_id)
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            logger.info(f"Downloaded file ID {file_id} to {output_path}")
        except Exception as e:
            logger.error(f"Failed to download file ID {file_id}: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def delete(self, file_id: str):
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file ID {file_id} from Google Drive")
        except Exception as e:
            logger.error(f"Failed to delete file ID {file_id}: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def get_storage_quota(self) -> dict:
        try:
            about = self.service.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})
            total_mb = int(quota.get('limit', 0)) / (1024 * 1024) if quota.get('limit') else 15000
            used_mb = int(quota.get('usage', 0)) / (1024 * 1024)
            free_mb = total_mb - used_mb
            return {
                'total_mb': total_mb,
                'used_mb': used_mb,
                'free_mb': max(0, free_mb)
            }
        except Exception as e:
            logger.error(f"Failed to get Google Drive storage quota: {str(e)}")
            return {'total_mb': 0, 'used_mb': 0, 'free_mb': 0}