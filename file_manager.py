import os
import logging
from models import File

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, storage_providers: list):
        self.storage_providers = storage_providers
        logger.info(f"Initialized FileManager with {len(storage_providers)} providers")

    def upload_file(self, file_path: str, file_name: str, user_email: str) -> dict:
        try:
            # Log the start of the upload to detect duplicate calls
            logger.info(f"Attempting upload for {file_name} by {user_email}")
            
            file_size = os.path.getsize(file_path)
            num_providers = len(self.storage_providers)
            if num_providers == 0:
                logger.error("No storage providers available")
                raise ValueError("No storage providers available")
            
            chunk_size = file_size // num_providers
            chunk_paths = []
            
            logger.info(f"Starting upload for {file_name} by {user_email}, size: {file_size} bytes")

            with open(file_path, "rb") as f:
                for i in range(num_providers):
                    chunk_path = f"chunk_{i}_{file_name}"
                    with open(chunk_path, "wb") as chunk_file:
                        if i == num_providers - 1:
                            chunk_file.write(f.read())
                        else:
                            chunk_file.write(f.read(chunk_size))
                    chunk_paths.append(chunk_path)
                    logger.info(f"Created chunk {i} at {chunk_path}")

            chunk_ids = []
            for i, chunk_path in enumerate(chunk_paths):
                provider = self.storage_providers[i % num_providers]
                try:
                    logger.info(f"Uploading chunk {i} to {provider.__class__.__name__}")
                    chunk_id = provider.upload(chunk_path, f"{user_email}/{file_name}/chunk_{i}")
                    if not chunk_id:
                        logger.error(f"Provider {i} failed to upload chunk")
                        raise ValueError(f"Provider {i} failed to upload chunk")
                    chunk_ids.append({
                        "provider_id": (i % num_providers) + 1,
                        "chunk_number": i,
                        "chunk_path": chunk_id,
                        "chunk_hash": "placeholder"
                    })
                    logger.info(f"Chunk {i} uploaded, chunk_id: {chunk_id}")
                finally:
                    os.remove(chunk_path)
                    logger.info(f"Deleted chunk {i}: {chunk_path}")

            size_mb = file_size / (1024 * 1024)
            new_file = File(filename=file_name, chunks=chunk_ids, user_email=user_email, size_mb=size_mb)
            
            if not new_file.save():
                logger.error(f"Failed to save {file_name} to database or file already exists")
                raise Exception("Database save failed or file already exists")
            logger.info(f"File {file_name} saved to database")

            return chunk_ids
        except Exception as e:
            logger.error(f"Upload failed for {file_name}: {str(e)}", exc_info=True)
            raise

    def download_file(self, file_name: str, chunks: list, output_path: str) -> None:
        chunk_paths = []
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            sorted_chunks = sorted(chunks, key=lambda x: x['chunk_number'])
            
            for chunk in sorted_chunks:
                provider_idx = chunk['provider_id'] - 1
                if provider_idx >= len(self.storage_providers):
                    raise ValueError(f"Invalid provider index {provider_idx}")
                    
                provider = self.storage_providers[provider_idx]
                chunk_path = f"temp_chunk_{chunk['chunk_number']}"
                
                try:
                    logger.info(f"Downloading chunk {chunk['chunk_number']} from provider {chunk['provider_id']}")
                    provider.download(chunk['chunk_path'], chunk_path)
                    chunk_paths.append(chunk_path)
                except Exception as e:
                    logger.error(f"Failed to download chunk {chunk['chunk_number']}: {str(e)}")
                    raise

            with open(output_path, 'wb') as output_file:
                for chunk_path in sorted(chunk_paths):
                    try:
                        with open(chunk_path, 'rb') as chunk_file:
                            output_file.write(chunk_file.read())
                    except Exception as e:
                        logger.error(f"Failed to merge chunk {chunk_path}: {str(e)}")
                        raise
                    finally:
                        try:
                            os.remove(chunk_path)
                        except:
                            pass

            logger.info(f"File {file_name} successfully reconstructed at {output_path}")
        except Exception as e:
            logger.error(f"Download failed for {file_name}: {str(e)}")
            for chunk_path in chunk_paths:
                try:
                    os.remove(chunk_path)
                except:
                    pass
            raise

    def delete_file(self, file_name: str, chunks: list, user_email: str) -> None:
        for chunk in chunks:
            provider = self.storage_providers[chunk['provider_id'] - 1]
            try:
                provider.delete(chunk['chunk_path'])
                logger.info(f"Deleted chunk {chunk['chunk_number']} for {file_name}")
            except Exception as e:
                logger.error(f"Failed to delete chunk {chunk['chunk_number']}: {str(e)}")
                raise