from abc import ABC, abstractmethod

class BaseStorageProvider(ABC):
    @abstractmethod
    def upload(self, file_path: str, file_name: str) -> str:
        pass

    @abstractmethod
    def download(self, file_id: str, output_path: str) -> None:
        pass

    @abstractmethod
    def delete(self, file_id: str) -> None:
        pass