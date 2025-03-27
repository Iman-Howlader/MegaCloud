import dropbox
from .base_provider import BaseStorageProvider

class DropboxProvider(BaseStorageProvider):
    def __init__(self, token_info: dict, folder_path: str):
        self.app_key = token_info["app_key"]
        self.app_secret = token_info["app_secret"]
        self.refresh_token = token_info["refresh_token"]
        self.folder_path = folder_path
        self.client = self._authenticate()

    def _authenticate(self):
        # Modern Dropbox SDK uses oauth2_refresh_token
        return dropbox.Dropbox(
            oauth2_refresh_token=self.refresh_token,
            app_key=self.app_key,
            app_secret=self.app_secret
        )

    def upload(self, file_path: str, file_name: str) -> str:
        dropbox_path = f"{self.folder_path}/{file_name}"
        with open(file_path, "rb") as f:
            self.client.files_upload(f.read(), dropbox_path)
        return dropbox_path

    def download(self, file_id: str, output_path: str) -> None:
        self.client.files_download_to_file(output_path, file_id)

    def delete(self, file_id: str) -> None:
        self.client.files_delete_v2(file_id)