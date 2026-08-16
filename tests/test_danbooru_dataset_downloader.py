import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


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
    def test_parse_args_accepts_image_count_and_repeated_exclude_tags(self):
        argv = [
            "download_danbooru_dataset.py",
            "1girl",
            "--image-count",
            "3",
            "--exclude-tags",
            "comic",
            "watermark",
            "--exclude-tags",
            "monochrome",
        ]
        with patch.object(sys, "argv", argv):
            args = downloader.parse_args()

        self.assertEqual(args.image_count, 3)
        self.assertEqual(args.exclude_tags, ["comic", "watermark", "monochrome"])

    def test_parse_args_defaults_image_count_to_twenty(self):
        with patch.object(sys, "argv", ["download_danbooru_dataset.py", "1girl"]):
            args = downloader.parse_args()

        self.assertEqual(args.image_count, 20)

    def test_parse_args_rejects_invalid_or_removed_count_options(self):
        invalid_arguments = [
            ["1girl", "--image-count", "0"],
            ["1girl", "--limit", "3"],
            ["1girl", "-n", "3"],
        ]
        for arguments in invalid_arguments:
            with (
                self.subTest(arguments=arguments),
                patch.object(
                    sys,
                    "argv",
                    ["download_danbooru_dataset.py", *arguments],
                ),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                downloader.parse_args()

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

    def test_excluded_tags_use_exact_tag_matching(self):
        post = {"tag_string": "1girl blue_hair solo"}
        self.assertTrue(downloader.has_excluded_tag(post, {"blue_hair"}))
        self.assertFalse(downloader.has_excluded_tag(post, {"hair"}))

    @patch.object(downloader.time, "sleep")
    @patch.object(downloader, "request_json")
    def test_fetch_posts_refills_after_excluded_and_unusable_posts(
        self, request_json, _sleep
    ):
        request_json.side_effect = [
            [
                {
                    "id": 10,
                    "tag_string": "1girl comic",
                    "file_url": "https://example.test/10.jpg",
                },
                {"id": 9, "tag_string": "1girl solo"},
            ],
            [
                {
                    "id": 8,
                    "tag_string": "1girl solo",
                    "file_url": "https://example.test/8.jpg",
                },
                {
                    "id": 7,
                    "tag_string": "1girl blue_hair",
                    "file_url": "https://example.test/7.jpg",
                },
            ],
        ]

        posts = downloader.fetch_posts(
            api_base_url="https://example.test",
            tags="1girl",
            image_count=2,
            page_size=2,
            sleep_seconds=0,
            user_agent="test",
            auth_header=None,
            exclude_tags={"comic"},
        )

        self.assertEqual([post["id"] for post in posts], [8, 7])
        self.assertEqual(request_json.call_count, 2)
        second_url = request_json.call_args_list[1].args[0]
        self.assertEqual(parse_qs(urlparse(second_url).query)["page"], ["b9"])

    @patch.object(downloader.time, "sleep")
    @patch.object(downloader, "request_json")
    def test_fetch_posts_stops_when_results_are_exhausted(
        self, request_json, _sleep
    ):
        request_json.side_effect = [
            [
                {
                    "id": 10,
                    "tag_string": "1girl comic",
                    "file_url": "https://example.test/10.jpg",
                }
            ],
            [],
        ]

        posts = downloader.fetch_posts(
            api_base_url="https://example.test",
            tags="1girl",
            image_count=2,
            page_size=1,
            sleep_seconds=0,
            user_agent="test",
            auth_header=None,
            exclude_tags={"comic"},
        )

        self.assertEqual(posts, [])
        self.assertEqual(request_json.call_count, 2)

    def test_search_summary_records_exclusions_and_requested_image_count(self):
        summary = downloader.search_summary(
            ["1girl"], "1girl order:id_desc", None, "newest", ["comic"], 25
        )
        self.assertEqual(summary["excluded_tags"], ["comic"])
        self.assertEqual(summary["requested_image_count"], 25)

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
