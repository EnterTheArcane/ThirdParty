import os
import shutil
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from thirdparty._internal.errors import AuthenticationException, ForbiddenException, NotFoundException
from thirdparty._internal.output import Output
from thirdparty._internal.util.download_cache import DownloadCache
from thirdparty._internal.util.file_downloader import FileDownloader
from thirdparty._internal.util.files import mkdir, set_dirty_context_manager, remove_if_dirty, human_size
from thirdparty._internal.util.http_requester import HttpRequester
from thirdparty.errors import RecipeException

from typing import Any, cast
from thirdparty.recipe import RecipeBase


def _o3de_download_cache_folder() -> str:
    """Default source cache folder used when no Recipe cache is configured."""
    base = os.environ.get("O3DE_THIRDPARTY_CACHE", str(Path.home() / ".o3de" / "ThirdParty"))
    return str(Path(base) / "Downloads")


class SourcesCachingDownloader:
    """ Class for downloading recipe download() urls
    if the config is active, it can use caching/backup-sources
    """

    def __init__(self, recipe: RecipeBase):
        self._conf = recipe.conf
        self._file_downloader = FileDownloader(
            HttpRequester(recipe.conf), scope=recipe.name or "", source_credentials=True)
        self._output = recipe.output
        self._recipe = recipe

    def download(
        self, urls: Any, file_path: str, retry: int, retry_wait: int, verify_ssl: bool, auth: Any, headers: Any, sha256: str | None):
        download_cache_folder = self._conf.core.sources.download_cache
        source_origins = self._conf.core.sources.download_urls
        if source_origins and not download_cache_folder:
            # If backups are defined, but the download cache is not defined, use a default one
            download_cache_folder = _o3de_download_cache_folder()
        if download_cache_folder and not os.path.isabs(download_cache_folder):
            raise RecipeException("core.sources:download_cache must be an absolute path")
        source_origins = source_origins or ["origin"]
        if download_cache_folder and not sha256:
            self._output.warning("Cannot cache download() without sha256 checksum")
            download_cache_folder = None  # Cannot cache
            source_origins = ["origin"]
        if None in source_origins:  # pyright: ignore[reportUnnecessaryContains]  # defensive: conf list may contain None at runtime
            raise RecipeException(
                f"Incorrect 'core.sources:download_urls' contains invalid 'None'"
                f"url: {source_origins}")

        # O3DE fallback: when no Recipe download cache is configured, use the local O3DE cache.
        if not download_cache_folder and sha256:
            download_cache_folder = _o3de_download_cache_folder()

        # First, see if it is already in the download cache
        if download_cache_folder:
            download_cache = DownloadCache(os.fspath(download_cache_folder))
            download_path = download_cache.source_path(sha256)

            with download_cache.lock(sha256):
                remove_if_dirty(download_path)

                in_cache = os.path.exists(download_path)
                need_download = not in_cache
                if in_cache:
                    recorded_urls = download_cache.get_urls_from_backup_sources(download_path)
                    urls_set = set(cast("list[Any]", urls if isinstance(urls, (list, tuple)) else [urls]))
                    # URLs mismatch: only re-download if there are recorded URLs and they don't match the requested ones.
                    # Some users could not have available the metadata files (json) while using
                    # backup-sources. We do not want to force re-downloading
                    if recorded_urls and not recorded_urls.intersection(urls_set):
                        self._output.warning(
                            "The requested URL(s) are not listed in backup-sources metadata for this "
                            "SHA256 cache entry. This may be a mistake, or the same checksum "
                            "reused for a different upstream version. Re-downloading to verify.")
                        need_download = True
                    else:
                        self._output.info(f"Source {urls} retrieved from local download cache")

                if need_download:
                    with set_dirty_context_manager(download_path):
                        self._do_download(
                            source_origins, urls, download_path, retry, retry_wait, verify_ssl, auth, headers, sha256)

                # copy it to the package "source" folder
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                shutil.copy2(download_path, file_path)
                download_cache.update_backup_sources_json(download_path, self._recipe, urls)
        else:
            # Not in local cache, check origins from core.sources:download_urls
            # This doesn't need to be dirty-protected, as the full "source" folder is protected
            self._do_download(
                source_origins, urls, file_path, retry, retry_wait, verify_ssl, auth, headers, sha256)

    def _do_download(
        self, source_origins: Any, urls: Any, download_path: str, retry: int, retry_wait: int, verify_ssl: bool, auth: Any, headers: Any, sha256: str | None):
        # iterates the origins until one works
        for backup_url in source_origins:
            if backup_url == "origin":  # download from the internet
                try:
                    self._download_from_urls(
                        urls, download_path, retry, retry_wait, verify_ssl, auth, headers, sha256)
                    return
                except Exception as e:
                    if backup_url is source_origins[-1]:
                        raise
                    self._output.warning(f"Sources for {urls} failed in 'origin': {e}")
            else:  # Download from a backup server
                try:
                    self._output.info(f"Checking backup: {backup_url}")
                    backup_url = backup_url if backup_url.endswith("/") else backup_url + "/"
                    # The download happens to the user download folder, not to the download cache
                    self._file_downloader.download(
                        backup_url + sha256, download_path, sha256=sha256, overwrite=True)
                    self._file_downloader.download(
                        backup_url + sha256 + ".json", download_path + ".json", overwrite=True)
                    self._output.info(f"Sources for {urls} found in remote backup {backup_url}")
                    return
                except NotFoundException:
                    msg = f"Sources for {urls} not found in remote backup {backup_url}"
                    if backup_url is source_origins[-1]:
                        raise NotFoundException(msg)
                    else:
                        self._output.warning(msg)
                except (AuthenticationException, ForbiddenException) as e:
                    raise RecipeException(
                        f"Authentication to source backup server '{backup_url}' "
                        f"failed: {e}. "
                        f"Please check your 'source_credentials.json'")

    def _download_from_urls(
        self, urls: Any, file_path: str, retry: int, retry_wait: int, verify_ssl: bool, auth: Any, headers: Any, sha256: str | None):
        """ iterate the recipe provided list of urls (mirrors, all with same checksum) until
        one succeed
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  # filename in subfolder must exist
        if not isinstance(urls, (list, tuple)):
            urls = [urls]
        urls = cast("list[Any]", urls)
        for url in urls:
            try:
                if url.startswith("file:"):  # plain copy from local disk, no real download
                    file_origin = url2pathname(urlparse(str(url)).path)
                    shutil.copyfile(file_origin, file_path)
                    self._file_downloader.check_checksum(file_path, sha256)
                else:
                    self._file_downloader.download(
                        url, file_path, retry, retry_wait, verify_ssl, auth, True, headers, sha256)
                self._output.info(f"Sources correctly downloaded from {url}")
                return  # Success! Return to caller
            except Exception as error:
                if url != urls[-1]:  # If it is not the last one, do not raise, warn and move to next
                    msg = f"Could not download from the URL {url}: {error}."
                    self._output.warning(msg)
                    self._output.info("Trying another mirror.")
                else:
                    raise


class PackageCacheDownloader:
    """ This is used for the download of Recipe packages from server, not for sources/backup sources
    """

    def __init__(
        self,
        requester: Any,
        config: Any,
        scope: Any = None):
        self._download_cache = config.core.download.download_cache
        if self._download_cache and not os.path.isabs(self._download_cache):
            raise RecipeException("core.download:download_cache must be an absolute path")
        self._file_downloader = FileDownloader(requester, scope=scope)
        self._scope = scope

    def download(
        self,
        url: str,
        file_path: str,
        auth: Any,
        verify_ssl: bool,
        retry: int,
        retry_wait: int,
        metadata: bool = False):
        if not self._download_cache or metadata:  # Metadata not cached and can be overwritten
            self._file_downloader.download(
                url, file_path, retry=retry, retry_wait=retry_wait, verify_ssl=verify_ssl, auth=auth, overwrite=metadata)
            return

        download_cache = DownloadCache(self._download_cache)
        cached_path, h = download_cache.cached_path(url)
        with download_cache.lock(h):
            remove_if_dirty(cached_path)

            if not os.path.exists(cached_path):
                with set_dirty_context_manager(cached_path):
                    self._file_downloader.download(
                        url, cached_path, retry=retry, retry_wait=retry_wait, verify_ssl=verify_ssl, auth=auth, overwrite=False)
            else:  # Found in cache!
                total_length = os.path.getsize(cached_path)
                is_large_file = total_length > 10000000  # 10 MB
                if is_large_file:
                    base_name = os.path.basename(file_path)
                    hs = human_size(total_length)
                    Output(scope=self._scope).info(
                        f"Copying {hs} {base_name} from download "
                        f"cache, instead of downloading it")

            # Everything good, file in the cache, just copy it to final destination
            mkdir(os.path.dirname(file_path))
            shutil.copy2(cached_path, file_path)
