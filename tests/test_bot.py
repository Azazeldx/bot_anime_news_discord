import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from discord_webhook import DiscordEmbed

import main
import history_store


def response(status, body=""):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode("utf-8")
    result._content_consumed = True
    result.encoding = "utf-8"
    return result


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.dry = patch.object(main, "DRY_RUN", False)
        self.dry.start()
        self.addCleanup(self.dry.stop)

    def test_400_retries_without_image_and_204_is_success(self):
        embed = DiscordEmbed(title="News")
        embed.set_image(url="https://example.com/image.jpg")
        images = []

        def send(webhook):
            images.append("image" in webhook.embeds[0])
            return response(400 if len(images) == 1 else 204)

        with patch.object(main.DiscordWebhook, "api_post_request", send):
            self.assertTrue(main.send_webhook("https://example.com/webhook", embed))
        self.assertEqual(images, [True, False])

    def test_repeated_429_has_bounded_retries(self):
        with patch.object(main.DiscordWebhook, "api_post_request",
                          side_effect=lambda: response(429, '{"retry_after": 0.1}')) as send, \
                patch.object(main.time, "sleep") as sleep:
            self.assertFalse(main.send_webhook("https://example.com/webhook", DiscordEmbed(title="News")))
        self.assertEqual(send.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_large_retry_after_is_deferred_without_sleep(self):
        with patch.object(main.DiscordWebhook, "api_post_request", return_value=response(429, '{"retry_after": 3600}')), \
                patch.object(main.time, "sleep") as sleep:
            self.assertFalse(main.send_webhook("https://example.com/webhook", DiscordEmbed(title="News")))
        sleep.assert_not_called()

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(folder) / "history.json"
        self.stack.enter_context(patch.object(main, "HISTORY_FILE", str(self.path)))
        self.stack.enter_context(patch.object(main, "DRY_RUN", False))
        self.stack.enter_context(patch.object(main, "WH_AREAANIME", None))
        self.stack.enter_context(patch.dict(main.os.environ, {"DISCORD_WEBHOOK_TEST": "category"}))
        self.stack.enter_context(patch.object(main.time, "sleep"))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.site = {"url": "https://example.com", "channel": "TEST"}
        self.stack.enter_context(patch.object(main, "TARGETS", [self.site]))
        self.items = [dict(title=title, link=f"https://example.com/{title}", lang="id",
                           source="Test", site=self.site) for title in ("new", "old")]
        self.stack.enter_context(patch.object(main, "fetch_items", return_value=self.items))
        self.stack.enter_context(patch.object(main, "enrich", side_effect=lambda item: item))
        self.stack.enter_context(patch.object(main, "build_news_embed", return_value=DiscordEmbed(title="Test")))

    def test_interruption_keeps_each_successful_delivery(self):
        with patch.object(main, "send_webhook", side_effect=[True, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                main.main()
        self.assertEqual(history_store.load(self.path)["sent"], ["https://example.com/old"])

    def test_failed_delivery_remains_retryable(self):
        with patch.object(main, "send_webhook", side_effect=[False, True]):
            main.main()
        self.assertEqual(history_store.load(self.path)["sent"], ["https://example.com/new"])

    def test_areaanime_is_first_and_failed_pick_is_not_seen(self):
        info = {"score": 8, "reason": "Test", "key": "test", "mode": "heuristik"}
        with patch.object(main, "WH_AREAANIME", "areaanime"), \
                patch.object(main.curator, "select", return_value=[(self.items[0], info)]), \
                patch.object(main, "build_areaanime_embed", return_value=DiscordEmbed(title="Area")), \
                patch.object(main, "send_webhook", side_effect=[False, True, True]) as send:
            main.main()
        self.assertEqual([call.args[0] for call in send.call_args_list], ["areaanime", "category", "category"])
        data = history_store.load(self.path)
        self.assertNotIn(self.items[0]["link"], data["areaanime_seen"])
        self.assertEqual(data["areaanime_posts"], [])

    def test_successful_area_post_survives_later_interruption(self):
        info = {"score": 8, "reason": "Test", "key": "test", "mode": "heuristik"}
        with patch.object(main, "WH_AREAANIME", "areaanime"), \
                patch.object(main.curator, "select", return_value=[(self.items[0], info)]), \
                patch.object(main, "build_areaanime_embed", return_value=DiscordEmbed(title="Area")), \
                patch.object(main, "send_webhook", side_effect=[True, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                main.main()
        data = history_store.load(self.path)
        self.assertIn(self.items[0]["link"], data["areaanime_seen"])
        self.assertEqual(data["areaanime_posts"][0]["link"], self.items[0]["link"])

    def test_dry_run_never_sends_or_changes_history(self):
        self.path.write_text(json.dumps(["existing"]), encoding="utf-8")
        before = self.path.read_bytes()
        with patch.object(main, "DRY_RUN", True), \
                patch.object(main.DiscordWebhook, "api_post_request") as send:
            main.main()
        send.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_gemini_key_defers_foreign_news_without_marking_sent(self):
        for item in self.items:
            item['lang'] = 'ja'
        with patch.object(main, 'TRANSLATOR', main.GeminiTranslator(api_key='')), \
                patch.object(main, 'build_news_embed', side_effect=lambda item: main.translate_item(item)), \
                patch.object(main, 'send_webhook') as send:
            main.main()
        send.assert_not_called()
        self.assertEqual(history_store.load(self.path)['sent'], [])
        self.assertNotIn('title_id', self.items[0])

    def test_missing_key_keeps_selected_area_news_retryable(self):
        self.items[0]['lang'] = 'ja'
        info = {'score': 8, 'reason': 'Test', 'key': 'test', 'mode': 'heuristik'}
        with patch.object(main, 'TRANSLATOR', main.GeminiTranslator(api_key='')), \
                patch.object(main, 'WH_AREAANIME', 'areaanime'), \
                patch.object(main.curator, 'select', return_value=[(self.items[0], info)]), \
                patch.object(main, 'build_areaanime_embed', side_effect=lambda item, info: main.translate_item(item)), \
                patch.object(main, 'build_news_embed', side_effect=lambda item: main.translate_item(item)), \
                patch.object(main, 'send_webhook', return_value=True) as send:
            main.main()
        self.assertEqual([call.args[0] for call in send.call_args_list], ['category'])
        data = history_store.load(self.path)
        self.assertEqual(data['sent'], [self.items[1]['link']])
        self.assertNotIn(self.items[0]['link'], data['areaanime_seen'])
        self.assertEqual(data['areaanime_posts'], [])

    def test_translated_item_is_reused_across_channels(self):
        self.items[0]['lang'] = 'ja'
        with patch.object(main.TRANSLATOR, 'translate', return_value=('Judul', 'Ringkasan')) as translate:
            main.translate_item(self.items[0])
            main.translate_item(self.items[0])
        translate.assert_called_once()
        self.assertEqual(self.items[0]['title_id'], 'Judul')
