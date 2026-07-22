import hashlib
import json
import os
from contextlib import contextmanager
from threading import Lock

import fasteners  # pyright: ignore[reportMissingTypeStubs]

from thirdparty._internal.util.dates import timestamp_now
from thirdparty._internal.util.files import load, save, remove_if_dirty
from thirdparty.errors import RecipeException

from typing import Any, cast
from thirdparty.recipe import RecipeBase


class DownloadCache:
    """ The download cache has 3 folders
    - "s": SOURCE_BACKUP for the files.download(internet_url) backup sources feature
    - "c": RECIPE_CACHE: for caching Recipe packages artifacts
    - "locks": The LOCKS folder containing the file locks for concurrent access to the cache
    """
    _LOCKS = "locks"
    _SOURCE_BACKUP = "s"
    _RECIPE_CACHE = "c"

    def __init__(self, path: str):
        self._path: str = path

    def source_path(self, sha256: Any) -> str:
        return os.path.join(self._path, self._SOURCE_BACKUP, sha256)

    def cached_path(self, url: str) -> tuple[str, str]:
        md = hashlib.sha256()
        md.update(url.encode())
        h = md.hexdigest()
        return os.path.join(self._path, self._RECIPE_CACHE, h), h

    _thread_locks: dict[str, Lock] = {}  # Needs to be shared among all instances

    @contextmanager
    def lock(self, lock_id: Any):
        lock = os.path.join(self._path, self._LOCKS, lock_id)
        with fasteners.InterProcessLock(lock):  # TODO: Abstract away when necessary for concurrency
            # Once the process has access, make sure multithread is locked too
            # as SimpleLock doesn't work multithread
            thread_lock = self._thread_locks.setdefault(lock, Lock())
            thread_lock.acquire()
            try:
                yield
            finally:
                thread_lock.release()

    def get_backup_sources_files(
        self,
        excluded_urls: Any,
        package_list: Any = None,
        only_upload: bool = True) -> list[str]:
        """Get list of backup source files currently present in the cache,
        either all of them if no package_list is give, or filtered by those belonging to the references in the package_list

        Will exclude the sources that come from URLs present in excluded_urls

        @param excluded_urls: a list of URLs to exclude backup sources files if they come from any of these URLs
        @param package_list: optional package metadata used to filter backup files by reference
        @param only_upload: if True, only return the files for packages that are set to be uploaded"""
        path_backups = os.path.join(self._path, self._SOURCE_BACKUP)

        if not os.path.exists(path_backups):
            return []

        if excluded_urls is None:
            excluded_urls = []

        def has_excluded_urls(backup_urls: Any) -> bool:
            return all(
                any(
                    url.startswith(excluded_url) for excluded_url in excluded_urls) for url in backup_urls)

        all_refs: set[str] = set()
        if package_list is not None:
            for ref, packages in package_list.items():
                ref_info = package_list.recipe_dict(ref)
                if (not only_upload or ref_info.get("upload") or any(package_list.package_dict(p).get("upload") for p in packages)):
                    all_refs.add(str(ref))

        path_backups_contents: list[str] = []

        dirty_ext = ".dirty"
        for path in os.listdir(path_backups):
            if remove_if_dirty(os.path.join(path_backups, path)):
                continue
            if path.endswith(dirty_ext):
                if not os.path.exists(os.path.join(path_backups, os.path.splitext(path)[0])):
                    if os.path.exists(os.path.join(path_backups, path)):
                        os.remove(os.path.join(path_backups, path))
                continue
            if not path.endswith(".json"):
                path_backups_contents.append(path)

        files_to_upload: list[str] = []

        for path in path_backups_contents:
            blob_path = os.path.join(path_backups, path)
            metadata_path = os.path.join(blob_path + ".json")
            if not os.path.exists(metadata_path):
                raise RecipeException(f"Missing metadata file for backup source {blob_path}")
            metadata = json.loads(load(metadata_path))
            refs = metadata["references"]
            for ref, urls in refs.items():
                if not has_excluded_urls(urls) and (not only_upload or package_list is None or ref in all_refs):
                    files_to_upload.append(metadata_path)
                    files_to_upload.append(blob_path)
                    break
        return files_to_upload

    @staticmethod
    def get_urls_from_backup_sources(cached_path: str) -> set[str]:
        """All download URLs stored in the backup-sources summary file ``<cached_path>.json``.
        """
        summary_path = cached_path + ".json"
        if not os.path.exists(summary_path):
            return set()
        refs: dict[str, Any] = json.loads(load(summary_path)).get("references") or {}
        return {url for urls in refs.values() for url in urls}

    @staticmethod
    def update_backup_sources_json(cached_path: str, recipe: RecipeBase, urls: Any):
        """ create or update the sha256.json file with the references and new urls used
        """
        summary_path = cached_path + ".json"
        summary: dict[str, Any]
        if os.path.exists(summary_path):
            summary = json.loads(load(summary_path))
        else:
            summary = {"references": {}, "timestamp": timestamp_now()}

        # The recipe path would differ between machines, so when a recipe has no name fall
        # back to "unknown".
        summary_key = recipe.name or "unknown"

        if not isinstance(urls, (list, tuple)):
            urls = [urls]
        urls = cast("list[Any]", urls)
        existing_urls: list[Any] = summary["references"].setdefault(summary_key, [])
        existing_urls.extend(url for url in urls if url not in existing_urls)
        recipe.output.verbose(f"Updating {summary_path} summary file")
        summary_dump = json.dumps(summary)
        recipe.output.debug(f"New summary: ${summary_dump}")
        save(summary_path, json.dumps(summary))
