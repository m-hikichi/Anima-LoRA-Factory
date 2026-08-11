import importlib.util
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "danbooru-dataset-downloader"
    / "download_danbooru_dataset.py"
)
SPEC = importlib.util.spec_from_file_location("danbooru_dataset_downloader", MODULE_PATH)
downloader = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(downloader)


class DanbooruDatasetDownloaderTests(unittest.TestCase):
    def test_build_search_tags_adds_requested_filters(self):
        tags = downloader.build_search_tags(
            ["hatsune_miku", "solo"], "general", "popular", False
        )
        self.assertEqual(
            tags,
            "hatsune_miku solo rating:g order:rank status:active",
        )

    def test_build_search_tags_preserves_explicit_metatags(self):
        tags = downloader.build_search_tags(
            ["1girl", "rating:s", "order:score"], "general", "newest", False
        )
        self.assertEqual(tags, "1girl rating:s order:score status:active")

    def test_prompt_uses_comma_separated_tags(self):
        prompt = downloader.prompt_from_post({"tag_string": "1girl solo blue_hair"})
        self.assertEqual(prompt, "1girl, solo, blue_hair")

    def test_auth_header_is_only_created_with_credentials(self):
        self.assertIsNone(downloader.build_auth_header(None, None))
        self.assertEqual(
            downloader.build_auth_header("user", "key"),
            "Basic dXNlcjprZXk=",
        )

    def test_safe_name_removes_path_components(self):
        self.assertEqual(downloader.safe_name("../123 bad/name"), "123_bad_name")


if __name__ == "__main__":
    unittest.main()
