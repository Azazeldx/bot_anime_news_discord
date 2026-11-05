import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import digest

NOW = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)


def item(title, link, source="Test", **extra):
    return dict({"title": title, "link": link, "source": source, "lang": "en", "summary": "",
                 "site": {"channel": "GENERAL"}}, **extra)


class DigestTests(unittest.TestCase):
    def test_ranked_by_initial_score_with_context(self):
        big = item("Jujutsu Kaisen season 3 anime announced", "https://a/1",
                   summary="New trailer\nand visual", published=NOW)
        small = item("Figure preorder campaign", "https://a/2")
        leak = item("LEAK: Frieren season 3 has 12 episodes", "https://t.me/s/1", source="Sugoi LITE",
                    site={"channel": "LEAKS", "leak": True}, x_link="https://x.com/SugoiLITE/status/1")
        trends = [{"term": "#呪術廻戦", "region": "Jepang", "rank": 2}]
        ranked = digest.rank([small, big, leak], [small, big, leak], trends)
        self.assertEqual(ranked[-1][0], small)  # merch: skor awal terendah
        text = digest.build(ranked, trends, ["Topik lama"], NOW)
        self.assertIn("# Digest Berita Areaanime · 2026-11-05 10:00 WIB", text)
        self.assertIn("Ringkasan: New trailer / and visual", text)
        self.assertIn("BOCORAN (belum resmi)", text)
        self.assertIn("Postingan X: https://x.com/SugoiLITE/status/1", text)
        self.assertIn("- Topik lama", text)
        self.assertIn("## Aturan judul feed Areaanime", text)
        self.assertLess(text.index("https://a/1"), text.index("https://a/2"))

    def test_lowest_scores_are_cut_beyond_max_items(self):
        items = [item(f"News {n}", f"https://a/{n}") for n in range(5)]
        with patch.object(digest, "MAX_ITEMS", 3):
            text = digest.build(digest.rank(items, items, []), [], [], NOW)
        self.assertIn("5 berita baru", text)
        self.assertIn("2 berita dengan skor awal terendah tidak dicantumkan", text)
        self.assertEqual(text.count("\nLink: "), 3)


if __name__ == "__main__":
    unittest.main()
