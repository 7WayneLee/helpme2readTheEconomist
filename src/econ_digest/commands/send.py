"""Resumable Telegram delivery with issue-level idempotency."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from ..config import Config
from ..images import load_issue_images
from ..render import write_outputs
from ..render.html import render_html
from ..site import build_site
from ..site.backup import backup_output
from ..site.publish import publish_site
from ..models import Digest, load_json, save_json
from ..render.telegraph import (PREVIEW_URL, original_text_messages, render_telegraph,
                                caption_length, summary_caption, summary_message, with_navigation)
from ..state import AlreadyRunning, load_state, run_lock, save_state, utc_now
from ..telegraph import TelegraphClient, content_size
from ..telegraph.publish import load_pages, publish_pages
from ..telegram import TelegramClient
from ..telegram.format import check_html, utf16_len, escape, link
from ..research.cna import cna_url
from . import add_issue_argument
from .render import saved_issue_directory
from .telegraph_setup import ensure_account

SETUP_INSTRUCTIONS = ("尚未設定 Telegram：請在 ~/.config/econ-digest/env 填入 TELEGRAM_BOT_TOKEN，"
                      "再執行 econ-digest telegram-setup 設定 TELEGRAM_CHAT_ID。")


def _progress(path: Path, fingerprint: str, message_count: int, *, force: bool,
              telegraph: bool) -> dict:
    progress = {"fingerprint": fingerprint, "next_message": 0, "document_sent": False}
    if telegraph:
        progress["pages_published"] = False
    if path.exists() and not force:
        previous = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict) or previous.get("fingerprint") != fingerprint:
            raise ValueError("報告或聊天室已變更；請確認後使用 --force 重新傳送")
        progress = previous
    progress.setdefault("channel_sent", False)
    if type(progress["channel_sent"]) is not bool:
        raise ValueError("telegram_progress.json 的頻道進度無效")
    next_message = progress.get("next_message")
    if (type(next_message) is not int or not 0 <= next_message <= message_count
            or type(progress.get("document_sent")) is not bool
            or telegraph and type(progress.get("pages_published")) is not bool):
        raise ValueError("telegram_progress.json 的傳送進度無效")
    if telegraph and next_message and not progress["pages_published"]:
        raise ValueError("telegram_progress.json 的頁面發布進度無效")
    return progress


def _validate_messages(messages: list[str]) -> None:
    if not isinstance(messages, list) or not all(isinstance(message, str) for message in messages):
        raise ValueError("telegram_messages.json 必須是字串陣列")
    for message in messages:
        check_html(message)
        if utf16_len(message) > 4000:
            raise ValueError("Telegram 訊息超過 4000 個 UTF-16 單位；請重新 render")


def fact_alert_message(digest: Digest) -> str | None:
    alerts = [item for item in digest.fact_alerts if isinstance(item, dict)
              and isinstance(item.get("fact"), str) and isinstance(item.get("suspected_new_value"), str)
              and cna_url(item.get("evidence_url"))][:5]
    if not alerts:
        return None
    lines = ["⚠️ 台灣事實檔可能需要更新："]
    for item in alerts:
        lines.append("• " + escape(item["fact"][:45]) + " → " + escape(item["suspected_new_value"][:70])
                     + "（" + link(item["evidence_url"], "中央社") + "）")
    return "\n".join([*lines, "（請確認）"])


def _telegraph_messages(digest: Digest, pages: list, urls: dict[str, str], originals: list[str],
                        *, photo: bool, site_url: str | None = None) -> tuple[list[str], int]:
    summary = summary_message(digest, pages, urls, site_url=site_url)
    alerts = [message] if (message := fact_alert_message(digest)) else []
    if not photo:
        return [summary, *originals, *alerts], 0
    caption, separate = summary_caption(digest, pages, urls)
    if site_url:
        from ..telegram.format import link
        private = "\n🔒 圖文完整版（需帳密）：" + link(site_url, "開啟")
        if caption_length(caption + private) <= 1024:
            caption += private
        else:
            separate = True
    return [caption, *([summary] if separate else []), *originals, *alerts], 1 if separate else -1


def send_digest(config: Config, issue_spec: str = "latest", *, force: bool = False,
                dry_run: bool = False, pages_only: bool = False,
                log: Callable[[str], None] = print) -> int:
    telegraph = config.telegram.delivery == "telegraph"
    if pages_only and not telegraph:
        log("--pages-only 僅適用於 Telegraph 模式；請將 telegram.delivery 設為 telegraph。")
        return 2
    token, chat_id = config.secrets.telegram_bot_token, config.secrets.telegram_chat_id
    if not dry_run and not pages_only and (not token or not chat_id):
        log(SETUP_INSTRUCTIONS)
        return 2
    directory = saved_issue_directory(config, issue_spec)
    digest = load_json(directory / "digest.json", Digest)
    if not pages_only:
        state = load_state(config.paths.data_dir)
        if digest.issue_date in state["delivered"] and not force and not (dry_run and telegraph):
            log("本期已傳送；如需再次傳送，請加上 --force。")
            return 0
    pages_path = directory / "telegraph_pages.json"
    epub = directory / f"TheEconomist.{digest.issue_date}.epub"
    site_url = None
    cover_url = None
    if dry_run:
        if config.site.enabled:
            site_url = config.site.base_url.rstrip("/") + "/" + digest.issue_date.replace(".", "-") + "/index.html"
            log(f"將建立並發布私人網站：{site_url}（含 epub）")
            record = directory / "site_publish.json"
            if record.exists():
                cover_url = json.loads(record.read_text(encoding="utf-8")).get("cover_url")
            if cover_url is None and epub.exists() and load_issue_images(epub).cover:
                cover_url = config.site.base_url.rstrip("/") + "/covers/" + "0" * 32 + ".jpg"
        else:
            log("將建立本期網站封存；網站發布未啟用，使用單檔報告備援。")
        backup_output(config.paths.output_dir, config.backup, digest.issue_date, config.paths.data_dir,
                      dry_run=True, log=log)
    else:
        if telegraph:
            illustrations = load_issue_images(epub) if config.report.embed_images and epub.exists() else None
            (directory / "report.html").write_text(render_html(digest, illustrations), encoding="utf-8")
        elif not (directory / "report.html").exists():
            write_outputs(digest, directory, embed_images=config.report.embed_images)
        site = build_site(digest, config.paths.output_dir, epub)
        published_site = publish_site(site, config.site, directory / "site_publish.json", log=log)
        if published_site:
            site_url, cover_url = published_site.index_url, published_site.cover_url
        backup_output(config.paths.output_dir, config.backup, digest.issue_date, config.paths.data_dir,
                      record_state=not pages_only, log=log)
    send_report = config.telegram.send_report_file or (telegraph and site_url is None)
    progress_path = directory / "telegram_progress.json"
    if not dry_run and not pages_only and not force and progress_path.exists():
        previous_progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if "send_report" in previous_progress:
            site_url = previous_progress.get("site_url")
            cover_url = previous_progress.get("cover_url")
            send_report = previous_progress["send_report"]
    cover = None
    if telegraph:
        stored = load_pages(pages_path)
        reserve = max([len(PREVIEW_URL), *[len(page.url.encode("utf-8")) for page in stored]])
        pages = render_telegraph(digest, config.telegraph.page_limit_bytes, url_reserve_bytes=reserve, cover_url=cover_url)
        known_urls = {page.key: page.url for page in stored}
        urls = {page.key: known_urls.get(page.key, f"https://telegra.ph/{index:016x}-00-00")
                for index, page in enumerate(pages, 1)}
        if pages_only:
            if dry_run:
                for page in with_navigation(pages, urls):
                    log(f"{page.title}｜{content_size(page.nodes)} 位元組")
            else:
                access_token = ensure_account(config, log=log)
                published = publish_pages(TelegraphClient(access_token), pages, pages_path, config.telegraph)
                log(f"已更新 {len(published)} 個 Telegraph 頁面。")
            return 0
        originals = original_text_messages(digest) if config.telegram.original_text_messages else []
        epub = directory / f"TheEconomist.{digest.issue_date}.epub"
        if config.telegram.cover_photo and site_url and epub.exists():
            cover = load_issue_images(epub).cover
        messages, summary_index = _telegraph_messages(digest, pages, urls, originals, photo=cover is not None, site_url=site_url)
    else:
        messages = json.loads((directory / "telegram_messages.json").read_text(encoding="utf-8"))
        if alert := fact_alert_message(digest):
            messages.append(alert)
    _validate_messages(messages)
    channel_id = config.secrets.telegram_channel_id
    channel_message = summary_message(digest, pages, urls) if telegraph and channel_id else None
    if dry_run:
        if telegraph:
            log("Telegraph 離線預覽（尚未發布的頁面使用預覽網址）。")
            for page in with_navigation(pages, urls):
                log(f"{page.title}｜{content_size(page.nodes)} 位元組")
        for index, message in enumerate(messages, 1):
            if cover is not None and index == 1:
                log(f"--- 封面照片 {index}/{len(messages)}｜圖說可見長度 {caption_length(message)}/1024 個 UTF-16 單位 ---\n{message}")
            else:
                log(f"--- 訊息 {index}/{len(messages)} ---\n{message}")
        if channel_message:
            log(f"--- 頻道訊息 ---\n{channel_message}")
        if send_report:
            log(f"--- 文件：{directory / 'report.html'} ---\n完整報告（含插圖與英文選文原文）")
        return 0
    assert token is not None and chat_id is not None
    report_path = directory / "report.html"
    report_bytes = report_path.read_bytes() if send_report else b""
    payload = ([[asdict(page) for page in pages], originals, chat_id, send_report, channel_id, site_url, cover_url,
                asdict(config.telegraph), "telegraph", hashlib.sha256(cover.data).hexdigest() if cover else None,
                digest.fact_alerts] if telegraph
               else [messages, chat_id, send_report])
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8") + report_bytes).hexdigest()
    progress_path = directory / "telegram_progress.json"
    progress = _progress(progress_path, fingerprint, len(messages), force=force, telegraph=telegraph)
    if telegraph:
        progress.update(site_url=site_url, cover_url=cover_url, send_report=send_report)
        save_json(progress_path, progress)
        if not progress["pages_published"]:
            access_token = ensure_account(config, log=log)
            published = publish_pages(TelegraphClient(access_token), pages, pages_path, config.telegraph)
            urls = {page.key: page.url for page in published}
            progress["pages_published"] = True
            save_json(progress_path, progress)
        elif any(page.key not in known_urls for page in pages):
            raise ValueError("已發布的 Telegraph 頁面紀錄遺失；請檢查 telegraph_pages.json")
        messages, summary_index = _telegraph_messages(digest, pages, urls, originals, photo=cover is not None, site_url=site_url)
        _validate_messages(messages)
    next_message = progress["next_message"]
    client = TelegramClient(token, min_interval=config.telegram.message_delay_seconds)
    for index in range(next_message, len(messages)):
        if cover is not None and index == 0:
            client.send_photo_safe(chat_id, cover.data, filename="cover.jpg", caption_html=messages[index])
        elif telegraph and index == summary_index:
            client.send_message_safe(chat_id, messages[index], link_preview_url=urls[pages[0].key], prefer_large_media=True)
        else:
            client.send_message_safe(chat_id, messages[index])
        progress["next_message"] = index + 1
        save_json(progress_path, progress)
    if telegraph and channel_id and not progress["channel_sent"]:
        channel_message = summary_message(digest, pages, urls)
        client.send_message_safe(channel_id, channel_message, link_preview_url=urls[pages[0].key], prefer_large_media=True)
        progress["channel_sent"] = True
        save_json(progress_path, progress)
    if send_report and not progress["document_sent"]:
        client.send_document(chat_id, report_path, caption_html="完整報告（含插圖與英文選文原文）")
        progress["document_sent"] = True
        save_json(progress_path, progress)
    state = load_state(config.paths.data_dir)
    state["delivered"][digest.issue_date] = {"delivered_at": utc_now(), "message_count": len(messages)}
    if digest.english:
        article = next((item for item in digest.issue.articles if item.id == digest.english.article_id), None)
        if article:
            record = {"issue_date": digest.issue_date, "article_id": article.id, "section": article.section,
                      "kind": article.kind, "title": article.title}
            if record not in state["english_history"]:
                state["english_history"].append(record)
    save_state(config.paths.data_dir, state)
    log(f"已傳送 {len(messages)} 則訊息。")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)
    parser.add_argument("--force", action="store_true", help="重新傳送本期所有訊息")
    parser.add_argument("--dry-run", action="store_true", help="離線列印頁面大小與訊息內容")
    parser.add_argument("--pages-only", action="store_true", help="僅更新 Telegraph 頁面，保留聊天進度與傳送紀錄")


def run(args: argparse.Namespace, config: Config) -> int:
    try:
        with run_lock(config.paths.data_dir):
            return send_digest(config, args.issue, force=args.force, dry_run=args.dry_run,
                               pages_only=getattr(args, "pages_only", False))
    except AlreadyRunning:
        print("已有 econ-digest 程序正在執行。")
        return 0
    except Exception as error:
        print(f"傳送失敗（{type(error).__name__}）；再次執行 send 可接續傳送。")
        return 1
