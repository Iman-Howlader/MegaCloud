import os
import logging
import time
import dropbox
from dropbox.exceptions import ApiError, AuthError
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

class DropboxProvider:
    MAX_RETRIES = 3

    def __init__(self, credentials: dict, folder_path: str):
        self.access_token = credentials['access_token']
        self.refresh_token = credentials.get('refresh_token')
        self.folder_path = folder_path
        self.app_key = os.getenv('DROPBOX_APP_KEY')
        self.app_secret = os.getenv('DROPBOX_APP_SECRET')
        if not self.app_key or not self.app_secret:
            logger.error("Dropbox app key or secret is missing from environment variables")
            raise ValueError("Dropbox app key or secret is missing")
        
        try:
            self.dbx = dropbox.Dropbox(
                oauth2_access_token=self.access_token,
                oauth2_refresh_token=self.refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret
            )
            self.dbx.users_get_current_account()
            logger.info(f"Initialized Dropbox client for {folder_path}")
        except AuthError as e:
            logger.error(f"Dropbox authentication failed: {str(e)}", exc_info=True)
            raise
        except ApiError as e:
            logger.error(f"Dropbox API error during initialization: {str(e)}", exc_info=True)
            raise

    def update_credentials(self):
        try:
            self.dbx.check_and_refresh_access_token()
            self.access_token = self.dbx._oauth2_access_token
            return {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_in': 14400,
                'expires_at': time.time() + 14400 - 60
            }
        except Exception as e:
            logger.error(f"Failed to refresh Dropbox token: {str(e)}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def upload(self, file_path: str, filename: str) -> str:
        try:
            self.dbx.check_and_refresh_access_token()
            dest_path = f"{self.folder_path}/{filename}"
            with open(file_path, 'rb') as f:
                self.dbx.files_upload(f.read(), dest_path, mute=True)
            logger.info(f"Uploaded {filename} to Dropbox at {dest_path}")
            return dest_path
        except ApiError as e:
            logger.error(f"Failed to upload {filename} to Dropbox: {str(e)}", exc_info=True)
            if hasattr(e, 'error'):
                logger.error(f"Dropbox API error details: {e.error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading {filename}: {str(e)}", exc_info=True)
            raise
            

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def download(self, file_path: str, output_path: str):
        try:
            self.dbx.check_and_refresh_access_token()  # Ensure token is valid
            self.dbx.files_download_to_file(output_path, file_path)
            logger.info(f"Downloaded {file_path} to {output_path}")
        except ApiError as e:
            logger.error(f"Failed to download {file_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error downloading {file_path}: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def delete(self, file_path: str):
        try:
            self.dbx.check_and_refresh_access_token()  # Ensure token is valid
            self.dbx.files_delete_v2(file_path)
            logger.info(f"Deleted {file_path} from Dropbox")
        except ApiError as e:
            logger.error(f"Failed to delete {file_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting {file_path}: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(2))
    def get_storage_quota(self) -> dict:
        try:
            self.dbx.check_and_refresh_access_token()  # Ensure token is valid
            usage = self.dbx.users_get_space_usage()
            total_mb = usage.allocation.get_individual().allocated / (1024 * 1024)
            used_mb = usage.used / (1024 * 1024)
            free_mb = total_mb - used_mb
            return {
                'total_mb': total_mb,
                'used_mb': used_mb,
                'free_mb': max(0, free_mb)
            }
        except Exception as e:
            logger.error(f"Failed to get Dropbox storage quota: {str(e)}")
            return {'total_mb': 0, 'used_mb': 0, 'free_mb': 0}