import hashlib


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of an in-memory buffer.

    ``util.files.sha256sum`` hashes a file on disk; the OCI backend builds blobs
    (config/manifest/index JSON, the gzipped layer) in memory, so it needs the buffer
    variant.  Returns the bare hex digest (no ``sha256:`` prefix)."""
    return hashlib.sha256(data).hexdigest()


def oci_digest(data: bytes) -> str:
    """OCI content digest for *data*: ``"sha256:" + hex``.

    This ``algorithm:hex`` form is what every OCI descriptor, blob reference, and
    ``diff_id`` uses; the bare hex from :func:`sha256_bytes` is only the on-disk blob
    filename under ``blobs/sha256/``."""
    return "sha256:" + sha256_bytes(data)
