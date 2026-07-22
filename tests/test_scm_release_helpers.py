import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from github.GithubException import GithubException


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty.scm.github import GithubRepository
from thirdparty.scm.web import NugetPackage, SourceForgeProject, WebReleaseIndex


class ReleaseHelperTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"GH_TOKEN": "", "GITHUB_TOKEN": ""})
        environment.start()
        self.addCleanup(environment.stop)

    def test_web_release_index_selects_highest_stable_match(self):
        response = MagicMock(text="pkg-1.2.0.tar.xz pkg-1.10.0.tar.xz pkg-2.0.0-beta.tar.xz")
        with patch("thirdparty.scm.web.requests.get", return_value=response):
            value = WebReleaseIndex(MagicMock(), "https://example.invalid/").latest_release(
                r"pkg-([\d.]+(?:-beta)?)\.tar\.xz")
        self.assertEqual(value, "1.10.0")
        response.raise_for_status.assert_called_once()

    def test_web_release_index_compares_underscore_separated_versions(self):
        response = MagicMock(text="jom_1_0_16.zip jom_1_1_7.zip")
        with patch("thirdparty.scm.web.requests.get", return_value=response):
            value = WebReleaseIndex(MagicMock(), "https://example.invalid/").latest_release(
                r"jom_([\d_]+)\.zip")
        self.assertEqual(value, "1_1_7")

    def test_sourceforge_extracts_version_from_best_release(self):
        response = MagicMock()
        response.json.return_value = {"release": {"filename": "/pkg/pkg-6.4.2.tar.gz"}}
        with patch("thirdparty.scm.web.requests.get", return_value=response):
            value = SourceForgeProject(MagicMock(), "pkg").latest_release(
                r"pkg-([\d.]+)\.tar\.gz")
        self.assertEqual(value, "6.4.2")

    def test_nuget_ignores_prereleases(self):
        response = MagicMock()
        response.json.return_value = {
            "versions": ["10.0.1", "10.0.2-preview", "10.0.1.9"],
        }
        with patch("thirdparty.scm.web.requests.get", return_value=response):
            value = NugetPackage(MagicMock(), "Example.Package").latest_release
        self.assertEqual(value, "10.0.1.9")

    def test_github_latest_commit_date_uses_default_branch(self):
        response = MagicMock(text="""<?xml version="1.0"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry><updated>2026-07-22T12:34:56Z</updated></entry>
            </feed>""")
        with patch("thirdparty.scm.github.requests.get", return_value=response) as get:
            repo = GithubRepository(MagicMock(), "example/commit-project")
            self.assertEqual(repo.latest_commit_date(), "20260722")
        get.assert_called_once_with(
            "https://github.com/example/commit-project/commits.atom",
            headers={"User-Agent": "thirdparty-outdated"},
            timeout=30)

    def test_github_latest_tag_matching_returns_highest_capture(self):
        result = SimpleNamespace(stdout="""
            a refs/tags/107.3-physx-5.6.1
            b refs/tags/110.1-physx-5.9.0
            c refs/tags/ovphysx-0.5.9
        """.replace(" refs", "\trefs"))
        with patch("thirdparty.scm.github.subprocess.run", return_value=result):
            repo = GithubRepository(MagicMock(), "example/tag-project")
            self.assertEqual(
                repo.latest_tag_matching(r"\d+\.\d+-physx-(\d+\.\d+\.\d+)"),
                "5.9.0")

    def test_github_latest_tag_matching_can_normalize_for_comparison(self):
        result = SimpleNamespace(stdout="""
            a refs/tags/core-8-6-18
            b refs/tags/core-9-0-4
            c refs/tags/core-9-1-b0
        """.replace(" refs", "\trefs"))
        with patch("thirdparty.scm.github.subprocess.run", return_value=result):
            repo = GithubRepository(MagicMock(), "example/hyphen-version-project")
            self.assertEqual(
                repo.latest_tag_matching(
                    r"core-(\d+-\d+-\d+)",
                    version_transform=lambda value: value.replace("-", ".")),
                "9-0-4")

    def test_github_latest_tag_orders_numbered_prereleases_naturally(self):
        result = SimpleNamespace(stdout="""
            a refs/tags/v4.3
            b refs/tags/v5.0.0-beta9
            c refs/tags/v5.0.0-beta10
        """.replace(" refs", "\trefs"))
        with patch("thirdparty.scm.github.subprocess.run", return_value=result):
            repo = GithubRepository(MagicMock(), "example/prerelease-project")
            self.assertEqual(repo.latest_tag("v"), "v5.0.0-beta10")

    def test_github_latest_release_uses_redirect_and_git_tags_without_api(self):
        response = MagicMock(
            status_code=200,
            url="https://github.com/example/release-project/releases/tag/v1.2.0")
        result = SimpleNamespace(stdout="a\trefs/tags/v1.2.0\nb\trefs/tags/v1.3.0\n")
        with (
            patch("thirdparty.scm.github.requests.head", return_value=response),
            patch("thirdparty.scm.github.subprocess.run", return_value=result),
        ):
            repo = GithubRepository(MagicMock(), "example/release-project")
            self.assertEqual(repo.latest_release, "v1.3.0")

    def test_github_latest_release_uses_authenticated_api_when_token_is_available(self):
        client = MagicMock()
        repository = client.get_repo.return_value
        repository.get_latest_release.return_value.tag_name = "v1.2.0"
        result = SimpleNamespace(stdout="a\trefs/tags/v1.2.0\nb\trefs/tags/v1.3.0\n")
        with (
            patch.dict("os.environ", {"GH_TOKEN": "secret", "GITHUB_TOKEN": ""}),
            patch("thirdparty.scm.github._github_client", return_value=client) as client_factory,
            patch("thirdparty.scm.github.subprocess.run", return_value=result),
            patch("thirdparty.scm.github.requests.head") as head,
        ):
            repo = GithubRepository(MagicMock(), "example/authenticated-project")
            self.assertEqual(repo.latest_release, "v1.3.0")
        client_factory.assert_called_once_with("secret")
        client.get_repo.assert_called_once_with("example/authenticated-project")
        repository.get_latest_release.assert_called_once_with()
        head.assert_not_called()

    def test_github_rate_limited_authenticated_release_falls_back_without_retrying(self):
        client = MagicMock()
        repository = client.get_repo.return_value
        repository.get_latest_release.side_effect = GithubException(
            status=403,
            data={"message": "API rate limit exceeded"},
            headers={})
        response = MagicMock(
            status_code=200,
            url="https://github.com/example/rate-limited/releases/tag/v2.0.0")
        with (
            patch.dict("os.environ", {"GH_TOKEN": "secret", "GITHUB_TOKEN": ""}),
            patch("thirdparty.scm.github._github_client", return_value=client),
            patch("thirdparty.scm.github.requests.head", return_value=response) as head,
        ):
            repo = GithubRepository(MagicMock(), "example/rate-limited")
            self.assertEqual(repo.latest_formal_release, "v2.0.0")
        repository.get_latest_release.assert_called_once_with()
        head.assert_called_once()

    def test_github_repository_without_releases_falls_back_to_git_tags(self):
        response = MagicMock(
            status_code=200,
            url="https://github.com/example/tag-only/releases")
        result = SimpleNamespace(stdout="a\trefs/tags/v2.3.0\n")
        with (
            patch("thirdparty.scm.github.requests.head", return_value=response),
            patch("thirdparty.scm.github.subprocess.run", return_value=result),
        ):
            repo = GithubRepository(MagicMock(), "example/tag-only")
            self.assertEqual(repo.latest_release, "v2.3.0")


if __name__ == "__main__":
    unittest.main()
