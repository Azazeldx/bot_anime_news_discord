import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import bluesky
import main
import sources
import telegram_channels

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def tg_message(post, text="", when="2026-11-04T08:00:00+00:00", photos=(), reply=None, link=None):
    reply_html = ""
    if reply:
        reply_html = (f'<a class="tgme_widget_message_reply" href="https://t.me/sugoileaks/1">'
                      f'<i class="tgme_widget_message_reply_thumb" style="background-image:url(\'https://cdn/reply.jpg\')"></i>'
                      f'<div class="tgme_widget_message_text js-message_reply_text">{reply}</div></a>')
    photo_html = "".join(f'<a class="tgme_widget_message_photo_wrap" style="width:1px;background-image:url(\'{p}\')"></a>'
                         for p in photos)
    body = f'<a href="{link}">{text}</a>' if link else text
    text_html = f'<div class="tgme_widget_message_text js-message_text">{body}</div>' if text else ""
    return (f'<div class="tgme_widget_message" data-post="sugoileaks/{post}">{reply_html}{photo_html}{text_html}'
            f'<a class="tgme_widget_message_date"><time datetime="{when}"></time></a></div>')


def tg_page(*messages):
    return ('<div class="tgme_channel_info_header_photo"><img src="https://cdn/avatar.jpg"></div>'
            + "".join(messages))


class TelegramTests(unittest.TestCase):
    def test_parses_posts_newest_first_with_reply_context_and_album(self):
        html = tg_page(
            tg_message(7600, 'LEAK: "OTAKU VAMPIRE" anime<br/><br/>Studio: X', photos=["https://cdn/a.jpg", "https://cdn/b.jpg"]),
            tg_message(7607, "The Latest KV!!", photos=["https://cdn/kv.jpg"], reply='LEAK: "OTAKU VAMPIRE" anime'),
            tg_message(7611, photos=["https://cdn/no-text.jpg"]),
            tg_message(7500, "Lama", when="2026-11-01T00:00:00+00:00"),
            tg_message(7604, "✅ Official", link="https://Fixupx.com/SugoiLITE/status/123"),
        )
        items = telegram_channels.parse(html, "sugoileaks", "Sugoi LITE", now=NOW)
        self.assertEqual([i["link"] for i in items], ["https://t.me/sugoileaks/7607", "https://t.me/sugoileaks/7604",
                                                       "https://t.me/sugoileaks/7600"])
        reply, official, album = items
        self.assertEqual(reply["title"], 'The Latest KV!!\n\n» LEAK: "OTAKU VAMPIRE" anime')
        self.assertEqual(reply["images"], ["https://cdn/kv.jpg"])  # thumbnail pesan yang dibalas tidak ikut
        self.assertEqual(album["title"], 'LEAK: "OTAKU VAMPIRE" anime\n\nStudio: X')
        self.assertEqual(album["images"], ["https://cdn/a.jpg", "https://cdn/b.jpg"])
        self.assertEqual(official["x_link"], "https://x.com/SugoiLITE/status/123")
        self.assertEqual((album["source"], album["author_avatar"]), ("Sugoi LITE", "https://cdn/avatar.jpg"))

    def test_empty_preview_raises_so_channel_is_skipped(self):
        with self.assertRaises(ValueError):
            telegram_channels.parse("<html></html>", "sugoileaks", "Sugoi LITE")

    def test_channels_env_override(self):
        with patch.dict(telegram_channels.os.environ, {"TELEGRAM_CHANNELS": "@sugoileaks:en:Sugoi LITE, bad!, other_chan"}):
            self.assertEqual(telegram_channels.channels(),
                             [("sugoileaks", "en", "Sugoi LITE"), ("other_chan", "en", "other_chan")])

    def test_post_body_is_translated_separately_from_headline(self):
        site = next(s for s in sources.TARGETS if s.get("telegram") == "sugoileaks")
        item = {"title": "LEAK: X\n\nStudio: A\nDirector: B", "lang": "en", "site": site}
        with patch.object(main.TRANSLATOR, "translate", return_value=("BOCORAN: X", "Studio: A\nSutradara: B")) as tr:
            main.translate_item(item)
        tr.assert_called_once_with("LEAK: X", "Studio: A\nDirector: B", "en")
        self.assertEqual(item["title_id"], "BOCORAN: X\n\nStudio: A\nSutradara: B")

    def test_sugoi_goes_to_leaks_channel(self):
        leaks = [s for s in sources.TARGETS if s.get("channel") == "LEAKS"]
        self.assertEqual([s["telegram"] for s in leaks], ["sugoileaks"])

    def test_leak_embed(self):
        site = next(s for s in sources.TARGETS if s.get("telegram") == "sugoileaks")
        item = {"title": "LEAK: X\nDetail", "link": "https://t.me/sugoileaks/1", "img": "https://cdn/a.jpg",
                "source": "Sugoi LITE", "lang": "en", "site": site, "author_name": "Sugoi LITE",
                "title_id": "BOCORAN: X\nDetail", "summary_id": "", "published": NOW,
                "x_link": "https://x.com/SugoiLITE/status/1"}
        embed = main.build_news_embed(item)
        self.assertEqual(embed.title, "🤫 BOCORAN: X")
        self.assertIn("Bocoran (leak)", embed.description)
        self.assertIn("[Postingan X](https://x.com/SugoiLITE/status/1)", embed.description)
        self.assertEqual(embed.author["name"], "Sugoi LITE (t.me/sugoileaks)")
        self.assertEqual(embed.footer["text"], "Telegram • Bot Berita")


def bsky_post(rkey, text, facets=(), embed=None, reason=None, reply=None):
    record = {"text": text, "createdAt": "2026-11-04T21:02:09+09:00", "facets": list(facets)}
    if reply:
        record["reply"] = reply
    entry = {"post": {"uri": f"at://did:plc:x/app.bsky.feed.post/{rkey}", "author": {"handle": "comic.natalie.mu"},
                      "record": record, "embed": embed}}
    if reason:
        entry["reason"] = reason
    return entry


def link_facet(text, url_text, uri):
    start = text.encode("utf-8").index(url_text.encode("utf-8"))
    return {"index": {"byteStart": start, "byteEnd": start + len(url_text.encode("utf-8"))},
            "features": [{"$type": bluesky.LINK_FACET, "uri": uri}]}


class BlueskyTests(unittest.TestCase):
    def test_article_post_uses_article_link_and_drops_url_text(self):
        text = "アニメ「DEATH NOTE」全話一挙放送\r\nnatalie.mu/comic/news/6..."
        facet = link_facet(text, "natalie.mu/comic/news/6...",
                           "https://natalie.mu/comic/news/696593?utm_source=bluesky&utm_medium=social")
        embed = {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": "https://cdn/1.jpg"},
                                                                    {"fullsize": "https://cdn/2.jpg"}]}
        data = {"feed": [
            bsky_post("a1", "リポスト", reason={"$type": "app.bsky.feed.defs#reasonRepost"}),
            bsky_post("a2", "返信", reply={"parent": {}}),
            bsky_post("a3", text, facets=[facet], embed=embed),
        ]}
        [item] = bluesky.parse(data, "Comic Natalie")
        self.assertEqual(item["title"], "アニメ「DEATH NOTE」全話一挙放送")
        self.assertEqual(item["link"], "https://natalie.mu/comic/news/696593")
        self.assertEqual(item["images"], ["https://cdn/1.jpg", "https://cdn/2.jpg"])
        self.assertEqual(item["published"], datetime(2026, 11, 4, 12, 2, 9, tzinfo=timezone.utc))

    def test_post_without_link_uses_bluesky_url_and_external_card(self):
        embed = {"$type": "app.bsky.embed.external#view",
                 "external": {"uri": "https://ex.com/a?id=1&utm_campaign=x", "title": "Judul", "description": "Isi",
                              "thumb": "https://cdn/t.jpg"}}
        [card] = bluesky.parse({"feed": [bsky_post("b1", "", embed=embed)]}, "Akun")
        self.assertEqual((card["title"], card["link"], card["summary"], card["img"]),
                         ("Judul", "https://ex.com/a?id=1", "Isi", "https://cdn/t.jpg"))
        [plain] = bluesky.parse({"feed": [bsky_post("b2", "Halo")]}, "Akun")
        self.assertEqual(plain["link"], "https://bsky.app/profile/comic.natalie.mu/post/b2")


if __name__ == "__main__":
    unittest.main()
