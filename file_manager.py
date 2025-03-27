import os
import logging
from models import File  # Import File model for database integration

# Configure logging to file for debugging
logging.basicConfig(level=logging.INFO, filename='upload.log', filemode='a',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, storage_providers: list):
        self.storage_providers = storage_providers
        logger.info(f"Initialized FileManager with {len(storage_providers)} providers")

    def upload_file(self, file_path: str, file_name: str, user_email: str) -> dict:
        """Uploads file and returns chunk information"""
        try:
            # Calculate file size and chunks
            file_size = os.path.getsize(file_path)
            num_providers = len(self.storage_providers)
            if num_providers == 0:
                logger.error("No storage providers available")
                raise ValueError("No storage providers available")
            
            chunk_size = file_size // num_providers
            chunk_paths = []
            
            logger.info(f"Starting upload for {file_name} by {user_email}, size: {file_size} bytes")

            # Split file into chunks
            with open(file_path, "rb") as f:
                for i in range(num_providers):
                    chunk_path = f"chunk_{i}_{file_name}"
                    with open(chunk_path, "wb") as chunk_file:
                        if i == num_providers - 1:  # Last chunk gets remainder
                            chunk_file.write(f.read())
                        else:
                            chunk_file.write(f.read(chunk_size))
                    chunk_paths.append(chunk_path)
                    logger.info(f"Created chunk {i} at {chunk_path}")

            # Upload chunks and collect their IDs
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

            # Prepare data for database
            size_mb = file_size / (1024 * 1024)  # Convert bytes to MB
            
            # Create File object with correct parameters
            new_file = File(
                filename=file_name,
                chunks=chunk_ids,  # Pass the full chunk information
                user_email=user_email,
                size_mb=size_mb
            )
            
            # Save to database
            if not new_file.save():
                logger.error(f"Failed to save {file_name} to database")
                raise Exception("Database save failed")
            logger.info(f"File {file_name} saved to database")

            return {
                "file_name": file_name,
                "size_bytes": file_size,
                "chunks": chunk_ids
            }
            
        except Exception as e:
            logger.error(f"Upload failed for {file_name}: {str(e)}", exc_info=True)
            raise

    def download_file(self, file_name: str, chunks: list, output_path: str) -> None:
        """Downloads a file by retrieving its chunks from storage providers and merging them"""
        chunk_paths = []
        try:
            # Ensure the output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Sort chunks by chunk_number to ensure correct order
            sorted_chunks = sorted(chunks, key=lambda x: x['chunk_number'])
            
            for chunk in sorted_chunks:
                provider_idx = chunk['provider_id'] - 1  # Convert to 0-based index
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

            # Merge chunks with proper error handling
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
            # Clean up any partial downloads
            for chunk_path in chunk_paths:
                try:
                    os.remove(chunk_path)
                except:
                    pass
            raise

    def delete_file(self, file_name: str, chunks: list, user_email: str) -> None:
        """Deletes a file by removing its chunks from storage providers"""
        for chunk in chunks:
            provider = self.storage_providers[chunk['provider_id'] - 1]
            try:
                provider.delete(chunk['chunk_path'])
                logger.info(f"Deleted chunk {chunk['chunk_number']} for {file_name}")
            except Exception as e:
                logger.error(f"Failed to delete chunk {chunk['chunk_number']}: {str(e)}")
                raise