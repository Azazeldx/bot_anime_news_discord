import json
import unittest
from unittest.mock import patch

import requests

from translator import GeminiTranslator, TranslationUnavailable


def response(status=200, title="Judul Indonesia", summary="Ringkasan Indonesia", finish="STOP", raw=None):
    result = requests.Response()
    result.status_code = status
    data = raw if raw is not None else {"candidates": [{
        "finishReason": finish,
        "content": {"parts": [{"text": json.dumps({"title": title, "summary": summary})}]},
    }]}
    result._content = json.dumps(data).encode("utf-8")
    result._content_consumed = True
    result.encoding = "utf-8"
    return result


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.translator = GeminiTranslator(api_key="test-api-key", request_interval=0)

    def test_direct_translation_of_title_and_summary_has_timeout_and_cache(self):
        with patch("translator.requests.post", side_effect=lambda *args, **kwargs: response()) as post:
            self.assertEqual(self.translator.translate("Title", "Summary", "ja"),
                             ("Judul Indonesia", "Ringkasan Indonesia"))
            self.translator.translate("Title", "Summary", "ja")
        self.assertEqual(post.call_count, 1)
        url = post.call_args.args[0]
        args = post.call_args.kwargs
        self.assertNotIn("test-api-key", url)
        self.assertEqual(args["headers"]["x-goog-api-key"], "test-api-key")
        self.assertEqual(args["timeout"], (5, 30))
        source = json.loads(args["json"]["contents"][0]["parts"][0]["text"])
        self.assertEqual(source, {"source_language": "ja", "title": "Title", "summary": "Summary"})
        self.assertEqual(args["json"]["generationConfig"]["responseMimeType"], "application/json")

    def test_indonesian_needs_no_key_or_request(self):
        with patch("translator.requests.post") as post:
            self.assertEqual(GeminiTranslator(api_key="").translate("Judul", "Ringkasan", "id"),
                             ("Judul", "Ringkasan"))
        post.assert_not_called()

    def test_missing_key_makes_no_request(self):
        with patch("translator.requests.post") as post:
            with self.assertRaises(TranslationUnavailable):
                GeminiTranslator(api_key="").translate("Title", "", "en")
        post.assert_not_called()

    def test_429_retry_is_bounded_and_remaining_requests_are_deferred(self):
        with patch("translator.requests.post", side_effect=lambda *a, **kw: response(429)) as post, \
                patch("translator.time.sleep"):
            for title in ("Title", "Another title"):
                with self.assertRaises(TranslationUnavailable):
                    self.translator.translate(title, "", "en")
        self.assertEqual(post.call_count, 2)

    def test_large_retry_after_does_not_sleep(self):
        result = response(429)
        result.headers["Retry-After"] = "3600"
        with patch("translator.requests.post", return_value=result) as post, \
                patch("translator.time.sleep") as sleep:
            with self.assertRaises(TranslationUnavailable):
                self.translator.translate("Title", "", "en")
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_invalid_key_is_not_retried_or_logged(self):
        with patch("translator.requests.post", side_effect=lambda *a, **kw: response(403)) as post:
            for title in ("Title", "Other title"):
                with self.assertRaises(TranslationUnavailable) as error:
                    self.translator.translate(title, "", "en")
                self.assertNotIn("test-api-key", str(error.exception))
        self.assertEqual(post.call_count, 1)

    def test_connection_errors_stop_after_three_articles(self):
        with patch("translator.requests.post", side_effect=requests.Timeout("test-api-key")) as post, \
                patch("translator.time.sleep"):
            for number in range(5):
                with self.assertRaises(TranslationUnavailable) as error:
                    self.translator.translate(f"Title {number}", "", "en")
                self.assertNotIn("test-api-key", str(error.exception))
        self.assertEqual(post.call_count, 6)

    def test_transient_server_error_can_recover(self):
        with patch("translator.requests.post", side_effect=[response(503), response()]) as post, \
                patch("translator.time.sleep"):
            self.assertEqual(self.translator.translate("Title", "Summary", "es")[0], "Judul Indonesia")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self.translator.failures, 0)

    def test_truncated_or_blocked_output_is_rejected(self):
        for finish in ("MAX_TOKENS", "SAFETY"):
            with self.subTest(finish=finish), patch("translator.requests.post", return_value=response(finish=finish)):
                with self.assertRaises(TranslationUnavailable):
                    self.translator.translate("Title", "Summary", "en")

    def test_missing_fields_and_empty_title_are_rejected(self):
        for result in (response(title=""), response(summary=""), response(raw={"candidates": []}),
                       response(raw={"candidates": [None]})):
            with patch("translator.requests.post", return_value=result):
                with self.assertRaises(TranslationUnavailable):
                    GeminiTranslator(api_key="test", request_interval=0).translate("Title", "Summary", "ja")

    def test_absent_summary_cannot_be_invented(self):
        with patch("translator.requests.post", return_value=response(summary="Invented")):
            with self.assertRaises(TranslationUnavailable):
                self.translator.translate("Title", "", "en")
        with patch("translator.requests.post", return_value=response(summary="")):
            self.assertEqual(self.translator.translate("Title", "", "en"), ("Judul Indonesia", ""))

    def test_cached_success_can_be_used_after_quota_exhaustion(self):
        with patch("translator.requests.post", side_effect=[response(), response(429), response(429)]) as post, \
                patch("translator.time.sleep"):
            self.translator.translate("Title", "Summary", "en")
            with self.assertRaises(TranslationUnavailable):
                self.translator.translate("Other", "Summary", "en")
            self.assertEqual(self.translator.translate("Title", "Summary", "en")[0], "Judul Indonesia")
        self.assertEqual(post.call_count, 3)
