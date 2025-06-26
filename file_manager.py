import os
import uuid
import logging
import shutil
import tempfile
from typing import List, Dict, Optional
from googleapiclient.errors import HttpError
from storage_providers.google_drive import GoogleDriveProvider
from storage_providers.dropbox import DropboxProvider

logger = logging.getLogger(__name__)

class FileManager:
    DROPBOX_MAX_CHUNK_MB = 50  # Dropbox max chunk size in MB

    def __init__(self, user):
        self.user = user
        self.storage_providers = self._initialize_providers()

    def _initialize_providers(self) -> Dict[str, List]:
        providers = {'google_drive': [], 'dropbox': []}
        self.user.refresh_credentials()  # Ensure tokens are valid
        for account in self.user.get_active_storage_accounts():
            try:
                if account['provider_type'] == 'google_drive':
                    provider = GoogleDriveProvider(
                        account['credentials'], 
                        f"MegaCloud/{self.user.email}", 
                        self.user.email
                    )
                    providers['google_drive'].append(provider)
                elif account['provider_type'] == 'dropbox':
                    provider = DropboxProvider(
                        account['credentials'], 
                        f"/MegaCloud/{self.user.email}"
                    )
                    providers['dropbox'].append(provider)
            except Exception as e:
                logger.error(f"Failed to initialize {account['provider_type']} provider for {account['email']}: {str(e)}")
        logger.info(f"Initialized FileManager with {len(providers['google_drive'])} Google Drive and {len(providers['dropbox'])} Dropbox providers")
        return providers

    def _split_file(self, file_path: str, chunk_size: int) -> List[str]:
        chunk_paths = []
        file_size = os.path.getsize(file_path)
        with open(file_path, 'rb') as f:
            for i in range(0, file_size, chunk_size):
                chunk_path = os.path.join(tempfile.gettempdir(), f"chunk_{uuid.uuid4().hex[:8]}")
                chunk_data = f.read(chunk_size)
                with open(chunk_path, 'wb') as chunk_file:
                    chunk_file.write(chunk_data)
                chunk_paths.append(chunk_path)
        return chunk_paths

    def upload_file(self, file_path: str, filename: str, user_email: str) -> Optional[List[Dict[str, str]]]:
        try:
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            temp_dir = tempfile.gettempdir()
            disk_usage = shutil.disk_usage(temp_dir)
            free_space = disk_usage.free
            
            if free_space < file_size * 2:
                raise OSError(f"Not enough disk space in {temp_dir}. Required: {file_size * 2} bytes, Available: {free_space} bytes")

            active_providers = self.storage_providers['google_drive'] + self.storage_providers['dropbox']
            if not active_providers:
                raise ValueError("No active storage providers available")

            provider_storage = [(p, p.get_storage_quota().get('free_mb', 0.0)) for p in active_providers if p.get_storage_quota().get('free_mb', 0.0) > 0]
            total_free_mb = sum(free_mb for _, free_mb in provider_storage)
            if total_free_mb < file_size_mb:
                raise ValueError(f"Insufficient total storage: {total_free_mb} MB available, {file_size_mb} MB needed")

            chunk_ids = []
            chunk_number = 1
            remaining_size_mb = file_size_mb

            # Preserve original extension for chunk naming
            base_name, ext = os.path.splitext(filename)
            
            with open(file_path, 'rb') as f:
                for provider, free_mb in provider_storage:
                    if remaining_size_mb <= 0:
                        break

                    proportion = free_mb / total_free_mb
                    chunk_size_mb = min(remaining_size_mb, file_size_mb * proportion)
                    chunk_size_bytes = int(chunk_size_mb * 1024 * 1024)

                    if provider.__class__.__name__ == 'DropboxProvider' and chunk_size_mb > self.DROPBOX_MAX_CHUNK_MB:
                        chunk_size_mb = self.DROPBOX_MAX_CHUNK_MB
                        chunk_size_bytes = int(chunk_size_mb * 1024 * 1024)

                    chunk_path = os.path.join(tempfile.gettempdir(), f"chunk_{uuid.uuid4().hex[:8]}")
                    chunk_data = f.read(chunk_size_bytes)
                    if not chunk_data:
                        break

                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk_data)

                    actual_chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)

                    if provider.__class__.__name__ == 'DropboxProvider' and actual_chunk_size_mb > self.DROPBOX_MAX_CHUNK_MB:
                        sub_chunks = self._split_file(chunk_path, int(self.DROPBOX_MAX_CHUNK_MB * 1024 * 1024))
                        for sub_chunk_path in sub_chunks:
                            unique_filename = f"{base_name}_part{chunk_number}_{uuid.uuid4().hex[:8]}{ext}"
                            chunk_path_uploaded = provider.upload(sub_chunk_path, unique_filename)
                            chunk_ids.append({
                                'provider_id': provider.__class__.__name__,
                                'chunk_number': str(chunk_number),
                                'chunk_path': chunk_path_uploaded,
                                'account_email': self.user.email
                            })
                            logger.info(f"Uploaded sub-chunk {sub_chunk_path} to Dropbox as {unique_filename}")
                            os.remove(sub_chunk_path)
                            if provider.__class__.__name__ == 'DropboxProvider':
                                self.user.refresh_credentials()  # Update stored token
                            chunk_number += 1
                        os.remove(chunk_path)
                    else:
                        unique_filename = f"{base_name}_part{chunk_number}_{uuid.uuid4().hex[:8]}{ext}"
                        chunk_path_uploaded = provider.upload(chunk_path, unique_filename)
                        chunk_ids.append({
                            'provider_id': provider.__class__.__name__,
                            'chunk_number': str(chunk_number),
                            'chunk_path': chunk_path_uploaded,
                            'account_email': self.user.email
                        })
                        logger.info(f"Uploaded {chunk_path} to {provider.__class__.__name__} as {unique_filename}")
                        os.remove(chunk_path)
                        if provider.__class__.__name__ == 'DropboxProvider':
                            self.user.refresh_credentials()  # Update stored token
                        chunk_number += 1

                    remaining_size_mb -= actual_chunk_size_mb

            total_uploaded_mb = file_size_mb - remaining_size_mb
            if abs(file_size_mb - total_uploaded_mb) > 0.001:
                raise ValueError(f"Failed to upload entire file: {file_size_mb - total_uploaded_mb} MB not uploaded")

            return chunk_ids

        except Exception as e:
            logger.error(f"Upload failed for {filename}: {str(e)}")
            return None
        finally:
            for temp_file in os.listdir(tempfile.gettempdir()):
                if temp_file.startswith('chunk_'):
                    try:
                        os.remove(os.path.join(tempfile.gettempdir(), temp_file))
                    except Exception as e:
                        logger.error(f"Failed to clean up temp file {temp_file}: {str(e)}")

    def download_file(self, filename: str, chunk_ids: List[Dict[str, str]], output_path: str, user_email: str) -> None:
        try:
            if not chunk_ids or not isinstance(chunk_ids, list):
                raise ValueError("Invalid chunk_ids provided")

            sorted_chunks = sorted(chunk_ids, key=lambda x: int(x.get('chunk_number', '0')))
            temp_chunk_paths = []

            provider_map = {}
            for provider_type, provider_list in self.storage_providers.items():
                for provider in provider_list:
                    email = self.user.email
                    provider_map[(provider.__class__.__name__, email)] = provider

            for chunk_info in sorted_chunks:
                provider_type = chunk_info.get('provider_id')
                chunk_path = chunk_info.get('chunk_path')
                chunk_num = chunk_info.get('chunk_number')
                account_email = chunk_info.get('account_email')

                if not provider_type or not chunk_path or not chunk_num:
                    raise ValueError(f"Chunk data missing required fields: {chunk_info}")

                provider = provider_map.get((provider_type, account_email))
                if not provider:
                    raise ValueError(f"No matching provider found for {provider_type} with email {account_email}")

                temp_chunk_path = os.path.join(tempfile.gettempdir(), f"download_chunk_{chunk_num}_{uuid.uuid4().hex[:8]}")
                try:
                    provider.download(chunk_path, temp_chunk_path)
                    temp_chunk_paths.append(temp_chunk_path)
                    logger.info(f"Downloaded chunk {chunk_num} for {filename} from {provider_type} to {temp_chunk_path}")
                    if provider.__class__.__name__ == 'DropboxProvider':
                        self.user.refresh_credentials()  # Update stored token
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.warning(f"Chunk {chunk_path} not found on {provider_type}, skipping...")
                        continue
                    raise

            if not temp_chunk_paths:
                raise ValueError("No chunks were successfully downloaded")

            with open(output_path, 'wb') as outfile:
                for temp_chunk_path in sorted(temp_chunk_paths, key=lambda x: int(x.split('_chunk_')[1].split('_')[0])):
                    with open(temp_chunk_path, 'rb') as infile:
                        outfile.write(infile.read())
            logger.info(f"Reconstructed {filename} to {output_path}")

        except Exception as e:
            logger.error(f"Download failed for {filename}: {str(e)}")
            raise
        finally:
            for temp_chunk_path in temp_chunk_paths:
                if os.path.exists(temp_chunk_path):
                    try:
                        os.remove(temp_chunk_path)
                    except Exception as e:
                        logger.error(f"Failed to clean up temp chunk {temp_chunk_path}: {str(e)}")

    def delete_file(self, filename: str, chunk_ids: List[Dict[str, str]], user_email: str) -> bool:
        try:
            if not chunk_ids or not isinstance(chunk_ids, list):
                raise ValueError("Invalid chunk_ids provided")

            provider_map = {}
            for provider_type, provider_list in self.storage_providers.items():
                for provider in provider_list:
                    email = self.user.email
                    provider_map[(provider.__class__.__name__, email)] = provider

            all_deleted = True
            for chunk_info in chunk_ids:
                provider_type = chunk_info.get('provider_id')
                chunk_path = chunk_info.get('chunk_path')
                account_email = chunk_info.get('account_email')

                if not provider_type or not chunk_path:
                    raise ValueError(f"Chunk data missing required fields: {chunk_info}")

                provider = provider_map.get((provider_type, account_email))
                if not provider:
                    logger.warning(f"No matching provider found for {provider_type} with email {account_email}, skipping chunk deletion")
                    all_deleted = False
                    continue

                try:
                    provider.delete(chunk_path)
                    logger.info(f"Deleted chunk {chunk_path} for {filename} from {provider_type}")
                    if provider.__class__.__name__ == 'DropboxProvider':
                        self.user.refresh_credentials()  # Update stored token
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.warning(f"Chunk {chunk_path} already deleted or not found on {provider_type}, continuing...")
                    else:
                        logger.error(f"Failed to delete chunk {chunk_path} from {provider_type}: {str(e)}")
                        all_deleted = False

            return all_deleted

        except Exception as e:
            logger.error(f"Delete failed for {filename}: {str(e)}")
            return False

    def get_total_available_storage(self) -> float:
        total_free_mb = 0.0
        try:
            for provider_list in self.storage_providers.values():
                for provider in provider_list:
                    quota = provider.get_storage_quota()
                    total_free_mb += quota.get('free_mb', 0.0)
            return total_free_mb
        except Exception as e:
            logger.error(f"Failed to calculate total available storage: {str(e)}")
            return 0.0