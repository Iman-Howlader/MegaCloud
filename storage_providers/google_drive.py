from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from .base_provider import BaseStorageProvider

class GoogleDriveProvider(BaseStorageProvider):
    def __init__(self, credentials_file: str, folder_id: str):
        self.credentials_file = credentials_file
        self.folder_id = folder_id
        self.service = self._authenticate()

    def _authenticate(self):
        creds = service_account.Credentials.from_service_account_file(
            self.credentials_file, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=creds)

    def upload(self, file_path: str, file_name: str) -> str:
        file_metadata = {"name": file_name, "parents": [self.folder_id]}
        media = MediaFileUpload(file_path, mimetype="application/octet-stream")
        uploaded_file = self.service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
        return uploaded_file["id"]

    def download(self, file_id: str, output_path: str) -> None:
        request = self.service.files().get_media(fileId=file_id)
        with open(output_path, "wb") as f:
            f.write(request.execute())

    def delete(self, file_id: str) -> None:
        self.service.files().delete(fileId=file_id).execute()