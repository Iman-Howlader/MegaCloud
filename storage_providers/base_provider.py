from abc import ABC, abstractmethod

class BaseStorageProvider(ABC):
    """Base class for all storage providers."""

    @abstractmethod
    def upload(self, file_path: str, file_name: str) -> str:
        """Upload a file and return its unique identifier."""
        pass

    @abstractmethod
    def download(self, file_id: str, output_path: str) -> None:
        """Download a file using its unique identifier."""
        pass

    @abstractmethod
    def delete(self, file_id: str) -> None:
        """Delete a file using its unique identifier."""
        pass