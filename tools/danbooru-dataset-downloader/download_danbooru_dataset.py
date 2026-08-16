#!/usr/bin/env python3
"""Build an Anima LoRA training dataset from Danbooru posts."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API_BASE_URL = "https://danbooru.donmai.us"
DEFAULT_USER_AGENT = "anima-lora-factory-dataset-downloader/1.0"
RATING_ALIASES = {
    "g": "g",
    "general": "g",
    "s": "s",
    "sensitive": "s",
    "q": "q",
    "questionable": "q",
    "e": "e",
    "explicit": "e",
    "sfw": "g,s",
    "nsfw": "q,e",
}
ORDER_ALIASES = {
    "newest": ("id_desc", "新着順"),
    "oldest": ("id", "古い順"),
    "score": ("score", "スコアが高い順"),
    "score_asc": ("score_asc", "スコアが低い順"),
    "favorites": ("favcount", "お気に入り数が多い順"),
    "favorites_asc": ("favcount_asc", "お気に入り数が少ない順"),
    "popular": ("rank", "人気順(スコアと新しさ)"),
    "rank": ("rank", "人気順(スコアと新しさ)"),
    "updated": ("change", "更新が新しい順"),
    "updated_asc": ("change_asc", "更新が古い順"),
    "random": ("random", "ランダム順"),
    "none": ("none", "指定なし"),
}


class DanbooruError(RuntimeError):
    """Raised when Danbooru or the network returns an unrecoverable error."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download images from Danbooru by tag and save matching tag prompts."
    )
    parser.add_argument(
        "tags",
        nargs="+",
        help='Danbooru tags or metatags, for example: "hatsune_miku rating:g".',
    )
    parser.add_argument(
        "--image-count",
        type=int,
        default=20,
        help="Number of usable images to save. Default: 20.",
    )
    parser.add_argument(
        "--exclude-tags",
        nargs="+",
        action="extend",
        default=[],
        metavar="TAG",
        help="Exclude posts containing any of these Danbooru tags.",
    )
    parser.add_argument(
        "-r",
        "--rating",
        choices=sorted(RATING_ALIASES),
        help=(
            "Rating filter: g/general, s/sensitive, q/questionable, e/explicit, "
            "sfw(g,s), or nsfw(q,e). If omitted, no rating is added."
        ),
    )
    parser.add_argument(
        "--order",
        choices=sorted(ORDER_ALIASES),
        default="newest",
        help=(
            "Result order. Default: newest. Choices include oldest, score, "
            "favorites, popular, updated, random, none."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default="/datasets",
        help="Output directory. Default: /datasets.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Posts requested per API call, max 200. Default: 100.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.25,
        help="Seconds to wait between requests. Default: 0.25.",
    )
    parser.add_argument(
        "--include-deleted",
        action="store_true",
        help="Do not automatically add is_deleted:false to the tag query.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip image download when the target image file already exists.",
    )
    parser.add_argument(
        "--api-base-url",
        default=API_BASE_URL,
        help=f"Danbooru-compatible API base URL. Default: {API_BASE_URL}.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("DANBOORU_USER_AGENT", DEFAULT_USER_AGENT),
        help="HTTP User-Agent. Can also be set with DANBOORU_USER_AGENT.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("DANBOORU_USERNAME"),
        help="Danbooru username. Can also be set with DANBOORU_USERNAME.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("DANBOORU_API_KEY"),
        help="Danbooru API key. Can also be set with DANBOORU_API_KEY.",
    )
    args = parser.parse_args()

    if args.image_count < 1:
        parser.error("--image-count must be at least 1")
    if any(not tag.strip() for tag in args.exclude_tags):
        parser.error("--exclude-tags must not contain empty tags")
    if not 1 <= args.page_size <= 200:
        parser.error("--page-size must be between 1 and 200")
    if args.sleep < 0:
        parser.error("--sleep must not be negative")
    if bool(args.username) != bool(args.api_key):
        parser.error("--username and --api-key must be supplied together")

    return args


def has_metatag(tags: str, name: str) -> bool:
    return any(part == f"{name}:" or part.startswith(f"{name}:") for part in tags.split())


def metatag_value(tags: str, name: str) -> str | None:
    prefix = f"{name}:"
    for part in tags.split():
        if part.startswith(prefix):
            return part.removeprefix(prefix)
    return None


def build_search_tags(raw_tags: list[str], rating: str | None, order: str, include_deleted: bool) -> str:
    tags = " ".join(raw_tags).strip()

    if rating and not has_metatag(tags, "rating") and not has_metatag(tags, "-rating"):
        tags = f"{tags} rating:{RATING_ALIASES[rating]}".strip()

    order_value = ORDER_ALIASES[order][0]
    if order_value != "none" and not has_metatag(tags, "order"):
        tags = f"{tags} order:{order_value}".strip()

    if (
        not include_deleted
        and not has_metatag(tags, "status")
        and not has_metatag(tags, "-status")
        and not has_metatag(tags, "is")
        and not has_metatag(tags, "-is")
    ):
        tags = f"{tags} status:active".strip()

    return tags


def search_summary(
    raw_tags: list[str],
    effective_tags: str,
    rating: str | None,
    order: str,
    exclude_tags: list[str] | None = None,
    image_count: int | None = None,
) -> dict[str, Any]:
    order_value, order_label = ORDER_ALIASES[order]
    effective_order = metatag_value(effective_tags, "order") or order_value
    effective_rating = metatag_value(effective_tags, "rating")
    return {
        "requested_tags": raw_tags,
        "excluded_tags": exclude_tags or [],
        "requested_image_count": image_count,
        "effective_query": effective_tags,
        "rating": {
            "argument": rating,
            "danbooru_value": effective_rating,
            "note": "未指定の場合はrating条件を追加しません。",
        },
        "order": {
            "argument": order,
            "danbooru_value": effective_order,
            "description": describe_order(effective_order, order_label),
            "note": "Danbooruには公開APIで使える閲覧数順の検索指定はないため、人気系はpopular(rank)、favorites、scoreを使います。",
        },
    }


def describe_order(order_value: str, fallback: str) -> str:
    for alias_value, label in ORDER_ALIASES.values():
        if alias_value == order_value:
            return label
    return fallback if order_value == "none" else f"Danbooru order:{order_value}"


def build_auth_header(username: str | None, api_key: str | None) -> str | None:
    if not username or not api_key:
        return None
    token = base64.b64encode(f"{username}:{api_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def request_json(
    url: str,
    user_agent: str,
    auth_header: str | None,
    timeout: float = 30,
) -> Any:
    request = Request(url, headers=build_headers(user_agent, auth_header))
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise DanbooruError(f"HTTP {exc.code} for {url}: {body[:500]}") from exc
    except (URLError, TimeoutError) as exc:
        raise DanbooruError(f"Request failed for {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DanbooruError(f"Invalid JSON returned from {url}") from exc


def download_file(
    url: str,
    path: Path,
    user_agent: str,
    auth_header: str | None,
    timeout: float = 60,
) -> None:
    request = Request(url, headers=build_headers(user_agent, auth_header))
    try:
        with urlopen(request, timeout=timeout) as response:
            with path.open("wb") as output_file:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output_file.write(chunk)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise DanbooruError(f"HTTP {exc.code} while downloading {url}: {body[:500]}") from exc
    except (URLError, TimeoutError) as exc:
        raise DanbooruError(f"Download failed for {url}: {exc}") from exc


def build_headers(user_agent: str, auth_header: str | None) -> dict[str, str]:
    headers = {"User-Agent": user_agent}
    if auth_header:
        headers["Authorization"] = auth_header
    return headers


def fetch_posts(
    api_base_url: str,
    tags: str,
    image_count: int,
    page_size: int,
    sleep_seconds: float,
    user_agent: str,
    auth_header: str | None,
    exclude_tags: set[str] | None = None,
) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    excluded_tags = {tag.strip().lower() for tag in (exclude_tags or set())}
    page = "1"
    page_number = 1
    order_value = metatag_value(tags, "order")
    use_id_cursor = order_value in (None, "id_desc")

    while len(posts) < image_count:
        params = urlencode({"tags": tags, "limit": page_size, "page": page})
        url = f"{api_base_url.rstrip('/')}/posts.json?{params}"
        batch = request_json(url, user_agent, auth_header)

        if not isinstance(batch, list):
            raise DanbooruError(f"Unexpected API response for {url}")
        if not batch:
            break

        for post in batch:
            if has_excluded_tag(post, excluded_tags) or post_file_url(post) is None:
                continue
            posts.append(post)
            if len(posts) >= image_count:
                break

        if use_id_cursor:
            last_id = batch[-1].get("id")
            if not isinstance(last_id, int):
                break
            page = f"b{last_id}"
        else:
            page_number += 1
            page = str(page_number)

        if len(posts) < image_count:
            time.sleep(sleep_seconds)

    return posts


def post_file_url(post: dict[str, Any]) -> str | None:
    for key in ("file_url", "large_file_url", "preview_file_url"):
        value = post.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def tags_from_post(post: dict[str, Any]) -> set[str]:
    tag_string = post.get("tag_string")
    if isinstance(tag_string, str) and tag_string.strip():
        return {tag.lower() for tag in tag_string.split()}

    tags: set[str] = set()
    for key in (
        "tag_string_artist",
        "tag_string_character",
        "tag_string_copyright",
        "tag_string_general",
        "tag_string_meta",
    ):
        value = post.get(key)
        if isinstance(value, str):
            tags.update(tag.lower() for tag in value.split())
    return tags


def has_excluded_tag(post: dict[str, Any], exclude_tags: set[str]) -> bool:
    return bool(exclude_tags.intersection(tags_from_post(post)))


def file_extension(url: str, post: dict[str, Any]) -> str:
    extension = Path(urlparse(url).path).suffix
    if extension:
        return extension

    file_ext = post.get("file_ext")
    if isinstance(file_ext, str) and file_ext:
        return f".{file_ext.lstrip('.')}"

    return ".bin"


def prompt_from_post(post: dict[str, Any]) -> str:
    tag_string = post.get("tag_string")
    if isinstance(tag_string, str) and tag_string.strip():
        return tag_string.strip().replace(" ", ", ")

    tag_parts: list[str] = []
    for key in (
        "tag_string_artist",
        "tag_string_character",
        "tag_string_copyright",
        "tag_string_general",
        "tag_string_meta",
    ):
        value = post.get(key)
        if isinstance(value, str) and value.strip():
            tag_parts.extend(value.split())
    return ", ".join(tag_parts)


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._-") or "post"


def save_post_files(
    post: dict[str, Any],
    output_dir: Path,
    user_agent: str,
    auth_header: str | None,
    skip_existing: bool,
) -> str:
    post_id = post.get("id")
    if not isinstance(post_id, int):
        raise DanbooruError("Post is missing an integer id")

    url = post_file_url(post)
    if not url:
        return f"skip post {post_id}: no downloadable file URL"

    basename = safe_name(f"{post_id}_{post.get('md5', '')}")
    image_path = output_dir / f"{basename}{file_extension(url, post)}"
    prompt_path = output_dir / f"{basename}.txt"
    metadata_path = output_dir / f"{basename}.json"

    if image_path.exists() and skip_existing:
        image_status = "image exists"
    else:
        download_file(url, image_path, user_agent, auth_header)
        image_status = "downloaded"

    prompt_path.write_text(prompt_from_post(post) + "\n", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(post, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return f"{image_status} post {post_id}: {image_path.name}"


def main() -> int:
    args = parse_args()
    tags = build_search_tags(args.tags, args.rating, args.order, args.include_deleted)
    exclude_tags = list(dict.fromkeys(tag.strip().lower() for tag in args.exclude_tags))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    auth_header = build_auth_header(args.username, args.api_key)
    summary = search_summary(
        args.tags,
        tags,
        args.rating,
        args.order,
        exclude_tags,
        args.image_count,
    )
    (output_dir / "search_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Search query: {tags}")
    print(f"Order: {summary['order']['description']} ({summary['order']['danbooru_value']})")
    if summary["rating"]["danbooru_value"]:
        print(f"Rating: {summary['rating']['danbooru_value']}")
    if exclude_tags:
        print(f"Excluded tags: {', '.join(exclude_tags)}")

    try:
        posts = fetch_posts(
            api_base_url=args.api_base_url,
            tags=tags,
            image_count=args.image_count,
            page_size=args.page_size,
            sleep_seconds=args.sleep,
            user_agent=args.user_agent,
            auth_header=auth_header,
            exclude_tags=set(exclude_tags),
        )

        if not posts:
            print("No posts found.", file=sys.stderr)
            return 1

        for index, post in enumerate(posts, start=1):
            print(f"[{index}/{len(posts)}] {save_post_files(post, output_dir, args.user_agent, auth_header, args.skip_existing)}")
            if index < len(posts):
                time.sleep(args.sleep)
    except DanbooruError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if len(posts) < args.image_count:
        print(
            f"Warning: only {len(posts)} usable image(s) were found; "
            f"requested {args.image_count}.",
            file=sys.stderr,
        )
    print(f"Saved {len(posts)} usable image(s) to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
