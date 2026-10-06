import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import requests

import curator
import x_trends
from sources import parse_rss

NO_LLM = {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": ""}


def item(title, source="Test", **extra):
    return dict(title=title, link=f"https://example.com/{title}", source=source, lang="en", img="", **extra)


def trend(term, rank=5, region="Jepang"):
    return {"term": term, "region": region, "rank": rank}


def gemini_response(data):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps({"candidates": [{
        "finishReason": "STOP", "content": {"parts": [{"text": json.dumps(data)}]},
    }]}).encode("utf-8")
    result._content_consumed = True
    return result


class HeuristicTests(unittest.TestCase):
    def score(self, news, trends=()):
        return curator.heuristic_score(news, {}, curator.x_matches(news, trends))[0]

    def test_routine_episode_article_ranks_below_real_announcement(self):
        routine = self.score(item("The Apothecary Diaries Season 3 Episode 5 Preview"))
        announced = self.score(item("The Apothecary Diaries Season 3 Announced"))
        self.assertLess(routine, curator.MIN_SCORE)
        self.assertGreaterEqual(announced, curator.MIN_SCORE)

    def test_x_trend_matches_title_or_franchise_hashtag(self):
        trends = [trend("宇宙戦艦ヤマト", 7), trend("#呪術廻戦", 3), trend("SAO", 1), trend("OK", 2)]
        self.assertEqual(curator.x_matches(item("『宇宙戦艦ヤマト』新作映画"), trends)[0]["term"], "宇宙戦艦ヤマト")
        self.assertEqual(curator.x_matches(item("Jujutsu Kaisen final season trailer"), trends)[0]["term"], "#呪術廻戦")
        self.assertEqual(curator.x_matches(item("Saori OK new single"), trends), [])

    def test_x_trend_and_indonesia_raise_score(self):
        news = item("宇宙戦艦ヤマト new movie")
        self.assertGreater(self.score(news, [trend("宇宙戦艦ヤマト")]), self.score(news))
        self.assertGreater(self.score(item("Kobo Kanaeru solo live")), self.score(item("Someone solo live")))

    def test_heuristic_key_separates_events_of_one_franchise(self):
        self.assertNotEqual(curator._primary_key(item("One Piece anime trailer")),
                            curator._primary_key(item("One Piece final chapter")))


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def test_heuristic_mode_skips_stale_rss_and_reports_x_trend(self):
        fresh = item("Jujutsu Kaisen season 3 announced")
        stale = item("One Piece anime adaptation sequel announced",
                     published=datetime.now(timezone.utc) - timedelta(days=3))
        with patch.dict(curator.os.environ, NO_LLM):
            picks, watch = curator.select([fresh, stale], [fresh, stale], [], [trend("呪術廻戦", 4)])
        self.assertEqual([news for news, _ in picks], [fresh])
        self.assertEqual(picks[0][1]["mode"], "heuristik")
        self.assertEqual(picks[0][1]["x"][0]["term"], "呪術廻戦")
        self.assertEqual(watch, [])

    def test_gemini_mode_validates_picks_and_x_watch(self):
        candidates = [item("Frieren season 3 announced"), item("Some figure sale")]
        trends = [trend("#フリーレン", 2), trend("#ガンダム", 5), trend("ストスト", 9), trend("Some figure", 12)]
        data = {
            "picks": [
                {"id": 0, "score": 9, "reason": "r", "topic_key": "frieren-s3", "tag": "frieren s3",
                 "headline": "Akhirnya [Frieren lanjut season 3!]", "x_trend": "フリーレン"},
                {"id": 7, "score": 9, "reason": "id di luar daftar", "topic_key": "x", "tag": "X",
                 "headline": "x", "x_trend": ""},
            ],
            "x_watch": [
                {"term": "ガンダム", "tag": "gundam", "reason": "r"},
                {"term": "istilah karangan", "tag": "X", "reason": "tidak ada di x_trends"},
                {"term": "ストスト", "tag": "X", "reason": "sudah diposting"},
                {"term": "Some figure", "tag": "X", "reason": "sudah ada beritanya"},
            ],
        }
        recent = [{"link": "l", "key": "x:ストスト", "title": "ストスト",
                   "ts": datetime.now(timezone.utc).isoformat()}]
        with patch.dict(curator.os.environ, {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "key"}), \
                patch.object(curator.requests, "post", return_value=gemini_response(data)) as post:
            picks, watch = curator.select(candidates, candidates, recent, trends)

        body = post.call_args.kwargs["json"]
        self.assertNotIn("additionalProperties", json.dumps(body["generationConfig"]["responseSchema"]))
        sent = json.loads(body["contents"][0]["parts"][0]["text"])
        self.assertEqual(sent["kandidat"][0]["x_trend"], ["#フリーレン"])

        self.assertEqual(len(picks), 1)
        news, info = picks[0]
        self.assertIs(news, candidates[0])
        self.assertEqual((info["mode"], info["tag"], info["x"][0]["term"]), ("gemini", "FRIEREN S3", "#フリーレン"))
        self.assertEqual([(w["term"], w["key"], w["tag"]) for w in watch], [("#ガンダム", "x:ガンダム", "GUNDAM")])

    def test_gemini_failure_falls_back_to_heuristic(self):
        failed = requests.Response()
        failed.status_code = 400
        failed._content, failed._content_consumed = b"", True
        candidates = [item("Jujutsu Kaisen season 3 announced")]
        with patch.dict(curator.os.environ, {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "key"}), \
                patch.object(curator.requests, "post", return_value=failed) as post:
            picks, _ = curator.select(candidates, candidates, [])
        post.assert_called_once()
        self.assertEqual(picks[0][1]["mode"], "heuristik")


class FeedTests(unittest.TestCase):
    def test_atom_feed_with_escaped_image(self):
        atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
            <title>Frieren Season 3 Announced</title>
            <link href="https://www.reddit.com/r/anime/comments/1/x/"/>
            <updated>2026-10-06T03:00:00+00:00</updated>
            <content type="html">&lt;img src="https://i.redd.it/a.jpg?w=1&amp;amp;s=2" /&gt;</content>
        </entry></feed>"""
        [news] = parse_rss(atom, "Reddit")
        self.assertEqual(news["link"], "https://www.reddit.com/r/anime/comments/1/x/")
        self.assertEqual(news["img"], "https://i.redd.it/a.jpg?w=1&s=2")
        self.assertEqual(news["published"], datetime(2026, 10, 6, 3, tzinfo=timezone.utc))

    def test_rdf_feed_and_limit(self):
        rdf = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns="http://purl.org/rss/1.0/">
            <item><title>A</title><link>https://a.jp/1</link><dc:date>2026-10-06T10:00:00+09:00</dc:date></item>
            <item><title>B</title><link>https://a.jp/2</link></item>
            <item><title>C</title><link>https://a.jp/3</link></item></rdf:RDF>"""
        news = parse_rss(rdf, "Anime!Anime!", limit=2)
        self.assertEqual([n["title"] for n in news], ["A", "B"])
        self.assertEqual(news[0]["published"], datetime(2026, 10, 6, 1, tzinfo=timezone.utc))
        self.assertIsNone(news[1]["published"])

    def test_x_trends_keep_best_rank_of_recent_hours(self):
        html = """
            <div class="list-container"><ol><li><a class="trend-link">#A</a></li><li><a class="trend-link">B</a></li></ol></div>
            <div class="list-container"><ol><li><a class="trend-link">B</a></li></ol></div>"""
        self.assertEqual(sorted((t["term"], t["rank"]) for t in x_trends.parse(html, "Jepang")), [("#A", 1), ("B", 1)])


if __name__ == "__main__":
    unittest.main()
