"""Shared upload limits for application validation and the HTTP server."""

MAX_IMPORT_BATCH_SIZE = 20 * 1024 * 1024
# Multipart boundaries, file headers and ordinary form fields are additional
# to file bytes. Keep the application limit independent of transport overhead.
MAX_REQUEST_BODY_SIZE = MAX_IMPORT_BATCH_SIZE + 1024 * 1024
