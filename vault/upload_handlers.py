from django.core.files.uploadhandler import FileUploadHandler, StopUpload

from vault.services import uploads


class UploadSizeLimitHandler(FileUploadHandler):
    chunk_size = 64 * 1024

    def __init__(self, request=None):
        super().__init__(request)
        self.total_size = 0

    def receive_data_chunk(self, raw_data, start):
        self.total_size += len(raw_data)
        if self.total_size > uploads.MAX_UPLOAD_BYTES:
            self.request.upload_too_large = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None
