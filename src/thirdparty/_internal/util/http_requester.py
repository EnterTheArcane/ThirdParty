import jinja2
import fnmatch
import json
import logging
import os
import platform

import requests
import urllib3
from requests.adapters import HTTPAdapter
from typing import Any, cast

from thirdparty._internal.output import Output
# Capture SSL warnings as pointed out here:
# https://urllib3.readthedocs.org/en/latest/security.html#insecureplatformwarning
# TODO: Fix this security warning
from thirdparty._internal.util.files import load
from thirdparty.errors import RecipeException

logging.captureWarnings(True)

DEFAULT_TIMEOUT = (30, 60)  # connect, read timeouts
INFINITE_TIMEOUT = -1


class _SourceURLCredentials:
    """
    Load credentials from source_credentials.json for sources download
    """

    def __init__(self, cache_folder: Any):
        self._urls = {}
        if not cache_folder:
            return
        creds_path = os.path.join(cache_folder, "source_credentials.json")
        if not os.path.exists(creds_path):
            return

        def _get_auth(credentials: Any) -> Any:
            if ("headers" in credentials or "token" in credentials or ("user" in credentials and "password" in credentials)):
                return credentials
            raise RecipeException(f"Unknown credentials method for '{credentials["url"]}'")

        try:
            template = jinja2.Template(load(creds_path))
            content = template.render({"platform": platform, "os": os})
            content = json.loads(content)
            self._urls = {credentials["url"]: _get_auth(credentials) for credentials in content["credentials"]}
        except Exception as e:
            raise RecipeException(f"Error loading 'source_credentials.json' {creds_path}: {repr(e)}")

    def add_auth(self, url: str, kwargs: Any):
        # Find the credentials in "_urls"
        for u, creds in self._urls.items():
            if url.startswith(u):
                token = creds.get("token")
                if token:
                    kwargs["headers"]["Authorization"] = f"Bearer {token}"
                user = creds.get("user")
                password = creds.get("password")
                if user and password:
                    kwargs["auth"] = (user, password)
                headers = creds.get("headers")
                if headers:
                    kwargs.setdefault("headers", {}).update(headers)
                break


class HttpRequester:
    def __init__(self, config: Any, cache_folder: Any = None):
        self._url_creds = _SourceURLCredentials(cache_folder)
        _max_retries = config.core.net.http.max_retries if config.core.net.http.max_retries is not None else 2
        self._http_requester = requests.Session()
        _adapter = HTTPAdapter(max_retries=self._get_retries(_max_retries))
        self._http_requester.mount("http://", _adapter)
        self._http_requester.mount("https://", _adapter)
        self._timeout = config.core.net.http.timeout if config.core.net.http.timeout is not None else DEFAULT_TIMEOUT
        self._no_proxy_match = config.core.net.http.no_proxy_match
        self._proxies = config.core.net.http.proxies
        self._cacert_path = config.core.net.http.cacert_path
        self._client_certificates = config.core.net.http.client_cert
        self._clean_system_proxy = config.core.net.http.clean_system_proxy or False
        platform_info = "; ".join(
            [
                " ".join([platform.system(), platform.release()]), "Python " + platform.python_version(), platform.machine(),
            ])
        self._user_agent = "O3DE-ThirdParty/1.0 (%s)" % (platform_info)

    @staticmethod
    def _get_retries(max_retries: int):
        retry = max_retries
        if retry == 0:
            return 0
        retry_status_code_set = {
            requests.codes.internal_server_error,
            requests.codes.bad_gateway,
            requests.codes.service_unavailable,
            requests.codes.gateway_timeout,
            requests.codes.variant_also_negotiates,
            requests.codes.insufficient_storage,
            requests.codes.bandwidth_limit_exceeded,
        }
        return urllib3.Retry(
            total=retry, backoff_factor=0.05, status_forcelist=cast("set[int]", retry_status_code_set))

    def _should_skip_proxy(self, url: str) -> bool:
        if self._no_proxy_match:
            for entry in self._no_proxy_match:
                if fnmatch.fnmatch(url, entry):
                    return True
        return False

    def _add_kwargs(self, url: str, kwargs: Any):
        # verify is the caller-provided SSL setting for source downloads.
        source_credentials = kwargs.pop("source_credentials", None)
        if kwargs.get("verify", None) is not False:  # False means de-activate
            if self._cacert_path is not None:
                kwargs["verify"] = self._cacert_path
        kwargs["cert"] = self._client_certificates
        if self._proxies:
            if not self._should_skip_proxy(url):
                kwargs["proxies"] = self._proxies
        if self._timeout and self._timeout != INFINITE_TIMEOUT:
            kwargs["timeout"] = self._timeout
        if not kwargs.get("headers"):
            kwargs["headers"] = {}

        if source_credentials:
            self._url_creds.add_auth(url, kwargs)

        # Only set User-Agent if none was provided
        if not kwargs["headers"].get("User-Agent"):
            kwargs["headers"]["User-Agent"] = self._user_agent

        return kwargs

    def get(self, url: str, **kwargs: Any):
        return self._call_method("get", url, **kwargs)

    def head(self, url: str, **kwargs: Any):
        return self._call_method("head", url, **kwargs)

    def put(self, url: str, **kwargs: Any):
        return self._call_method("put", url, **kwargs)

    def delete(self, url: str, **kwargs: Any):
        return self._call_method("delete", url, **kwargs)

    def post(self, url: str, **kwargs: Any):
        return self._call_method("post", url, **kwargs)

    def _call_method(
        self,
        method: str,
        url: str,
        **kwargs: Any):
        popped = False
        old_env: dict[str, str] = {}
        if self._clean_system_proxy:
            old_env = dict(os.environ)
            # Clean the proxies from the environ and use the recipe specified proxies
            for var_name in ("http_proxy", "https_proxy", "ftp_proxy", "all_proxy", "no_proxy"):
                popped = True if os.environ.pop(var_name, None) else popped
                popped = True if os.environ.pop(var_name.upper(), None) else popped
        Output(scope="HttpRequest").trace(f"{method}: {url}")
        try:
            all_kwargs = self._add_kwargs(url, kwargs)
            tmp = getattr(self._http_requester, method)(url, **all_kwargs)
            return tmp
        finally:
            if popped:
                os.environ.clear()
                os.environ.update(old_env)
