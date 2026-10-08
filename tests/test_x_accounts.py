import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import main
import sources
import x_accounts

NOW = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)


def tweet(id_str, text, created="Thu Oct 08 03:00:00 +0000 2026", **extra):
    return {"type": "tweet", "content": {"tweet": dict({
        "id_str": id_str, "full_text": text, "created_at": created,
        "user": {"screen_name": "Dexerto", "name": "Dexerto",
                 "profile_image_url_https": "https://pbs.twimg.com/profile_images/1/a_normal.jpg"},
    }, **extra)}}


def timeline_html(entries):
    data = {"props": {"pageProps": {"timeline": {"entries": entries}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


class SyndicationTests(unittest.TestCase):
    def test_parses_newest_tweets_and_skips_retweets_replies_old(self):
        html = timeline_html([
            tweet("100", "Pinned lama", created="Mon Jan 01 00:00:00 +0000 2024"),
            tweet("300", "Anime baru https://t.co/a https://t.co/img",
                  entities={"urls": [{"url": "https://t.co/a", "expanded_url": "https://ex.com/a"}],
                            "media": [{"url": "https://t.co/img"}]},
                  extended_entities={"media": [{"url": "https://t.co/img",
                                                "media_url_https": "https://pbs.twimg.com/media/x.jpg"}]}),
            tweet("400", "RT @lain: halo", retweeted_status={"id_str": "1"}),
            tweet("500", "@lain balasan", in_reply_to_status_id_str="9"),
            tweet("200", "Tweet kedua &amp; terakhir"),
        ])
        items = x_accounts.parse_syndication(html, "Dexerto", now=NOW)
        self.assertEqual([i["link"] for i in items], ["https://x.com/Dexerto/status/300",
                                                       "https://x.com/Dexerto/status/200"])
        self.assertEqual(items[0]["title"], "Anime baru https://ex.com/a")
        self.assertEqual(items[0]["img"], "https://pbs.twimg.com/media/x.jpg")
        self.assertEqual(items[0]["source"], "X @Dexerto")
        self.assertIn("_bigger.", items[0]["x_avatar"])
        self.assertEqual(items[1]["title"], "Tweet kedua & terakhir")
        self.assertEqual(items[0]["published"], datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc))

    def test_blocked_page_raises_so_account_is_skipped(self):
        with self.assertRaises(ValueError):
            x_accounts.parse_syndication("<html>Login</html>", "Dexerto")

    def test_rss_bridge_items_are_normalized(self):
        items = [
            {"title": "RT someone: halo", "link": "https://n.example/Dexerto/status/1", "summary": "x"},
            {"title": "Berita", "link": "https://n.example/Dexerto/status/2#m", "summary": "Berita lengkap",
             "img": "", "published": NOW},
        ]
        result = x_accounts.normalize_rss(items, "Dexerto", now=NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["link"], "https://x.com/Dexerto/status/2")
        self.assertEqual(result[0]["title"], "Berita lengkap")

    def test_fetch_uses_rss_bridge_when_configured(self):
        session = MagicMock()
        session.get.return_value.content = b"<rss/>"
        parse_rss = MagicMock(return_value=[])
        with patch.dict(x_accounts.os.environ, {"X_RSS_URL": "https://rss.example/twitter/user/{account}"}):
            x_accounts.fetch(session, {"x": "Dexerto"}, parse_rss)
        self.assertEqual(session.get.call_args.args[0], "https://rss.example/twitter/user/Dexerto")

    def test_accounts_env_override(self):
        with patch.dict(x_accounts.os.environ, {"X_TWITTER_ACCOUNTS": "@Foo:ja, bad-name ,Bar"}):
            self.assertEqual(x_accounts.accounts(), [("Foo", "ja"), ("Bar", "en")])


class IntegrationTests(unittest.TestCase):
    def test_all_requested_accounts_go_to_twitter_channel(self):
        handles = {s["x"] for s in sources.TARGETS if s.get("channel") == "TWITTER"}
        self.assertEqual(handles, {"SomosKudasai", "animetrends", "Dexerto", "animetv_jp", "MangaMoguraRE",
                                   "WSJ_manga", "AniNewsAndFacts", "seiyuucorner", "Seifukuanimehub"})

    def test_tweet_items_skip_article_enrichment(self):
        site = {"x": "Dexerto", "lang": "en", "channel": "TWITTER"}
        with patch.object(x_accounts, "fetch", return_value=[{"title": "t", "link": "https://x.com/a/status/1"}]):
            item = main.fetch_items(site)[0]
        self.assertTrue(item["_enriched"])
        self.assertIs(item["site"], site)

    def test_tweet_embed(self):
        site = {"x": "Dexerto", "lang": "en", "channel": "TWITTER", "emoji": "🐦", "color": "1d9bf0",
                "home": "https://x.com/Dexerto"}
        item = {"title": "Headline\nDetail", "link": "https://x.com/Dexerto/status/1", "img": "",
                "source": "X @Dexerto", "lang": "en", "site": site, "x_name": "Dexerto",
                "title_id": "Judul\nDetail terjemahan", "summary_id": "", "published": NOW}
        embed = main.build_news_embed(item)
        self.assertEqual(embed.title, "🐦 Judul")
        self.assertTrue(embed.description.startswith("Detail terjemahan"))
        self.assertIn("> 📝 Headline\n> Detail", embed.description)
        self.assertEqual(embed.author["name"], "Dexerto (@Dexerto)")


if __name__ == "__main__":
    unittest.main()
