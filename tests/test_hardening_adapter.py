"""Regression tests for adapter findings C1, C9, C10, C14, R8, R9 (no live network)."""
import io, socket, unittest
from urllib.error import HTTPError, URLError
from unittest import mock

from dpp_audit import perplexity_adapter as pa
from dpp_audit.perplexity_adapter import ProviderError, discover_sources, normalize_response, normalize_url

OK = {"choices": [{"message": {"content": "The AI says this proves the claim"}}], "citations": ["https://example.org/a"]}


class TestC1Header(unittest.TestCase):
    def test_C1_authorization_header_carries_the_real_key_as_bearer(self):
        seen = {}
        def tr(url, headers, body, timeout):
            seen.update(headers); return OK
        res = discover_sources("q", api_key="sk-real", transport=tr)
        self.assertEqual(seen["Authorization"], "Bearer sk-real")
        self.assertNotIn("sk-real", repr(res))


class TestC9Snippet(unittest.TestCase):
    def test_C9_ai_summary_is_not_attached_to_urls(self):
        res = normalize_response({**OK, "citations": ["https://example.org/a", {"url": "https://example.org/b", "snippet": "from source"}]})
        self.assertEqual(res[0].snippet, "")
        self.assertEqual(res[1].snippet, "from source")
        self.assertNotIn("proves", repr(res))

    def test_C9_non_string_fields_are_coerced_safely(self):
        res = normalize_response({"citations": [{"url": "https://example.org/a", "snippet": ["x"], "title": 5}],
                                  "choices": [{"message": {"content": ["x"]}}]})
        self.assertEqual((res[0].title, res[0].snippet), ("", ""))


class TestC10Failures(unittest.TestCase):
    def test_C10_timeout_during_read_is_wrapped(self):
        class Boom:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s, n=-1): raise socket.timeout("timed out")
        with mock.patch.object(pa, "urlopen", return_value=Boom()):
            with self.assertRaises(ProviderError) as cm:
                pa._http_transport(pa.API_URL, {"Authorization": "Bearer SECRET"}, {}, 1)
        self.assertTrue(cm.exception.retryable)
        self.assertNotIn("SECRET", str(cm.exception))

    def test_C10_bad_utf8_and_bad_json_are_wrapped(self):
        for raw in (b"\xff\xfe", b"not json"):
            resp = mock.MagicMock(); resp.__enter__.return_value = resp; resp.read.return_value = raw
            with mock.patch.object(pa, "urlopen", return_value=resp):
                with self.assertRaisesRegex(ProviderError, "invalid JSON"):
                    pa._http_transport(pa.API_URL, {}, {}, 1)

    def test_C10_oversized_response_rejected(self):
        resp = mock.MagicMock(); resp.__enter__.return_value = resp
        resp.read.return_value = b"x" * (pa.MAX_RESPONSE_BYTES + 1)
        with mock.patch.object(pa, "urlopen", return_value=resp):
            with self.assertRaisesRegex(ProviderError, "too large"):
                pa._http_transport(pa.API_URL, {}, {}, 1)

    def test_C10_http_429_is_retryable_with_retry_after_and_401_is_not(self):
        def boom(code, hdrs=None):
            return HTTPError(pa.API_URL, code, "x", hdrs or {}, io.BytesIO(b""))
        with mock.patch.object(pa, "urlopen", side_effect=boom(429, {"Retry-After": "7"})):
            with self.assertRaises(ProviderError) as cm:
                pa._http_transport(pa.API_URL, {}, {}, 1)
        self.assertEqual((cm.exception.retryable, cm.exception.retry_after), (True, 7.0))
        with mock.patch.object(pa, "urlopen", side_effect=boom(401)):
            with self.assertRaises(ProviderError) as cm:
                pa._http_transport(pa.API_URL, {}, {}, 1)
        self.assertFalse(cm.exception.retryable)

    def test_C10_connection_errors_are_wrapped(self):
        with mock.patch.object(pa, "urlopen", side_effect=URLError("dns")):
            with self.assertRaises(ProviderError):
                pa._http_transport(pa.API_URL, {}, {}, 1)
        with mock.patch.object(pa, "urlopen", side_effect=ConnectionResetError()):
            with self.assertRaises(ProviderError):
                pa._http_transport(pa.API_URL, {}, {}, 1)

    def test_C10_retries_then_succeeds_honoring_retry_after(self):
        calls, sleeps = [], []
        def tr(*a):
            calls.append(1)
            if len(calls) < 3: raise ProviderError("HTTP 429", retryable=True, retry_after=3)
            return OK
        res = discover_sources("q", api_key="k", transport=tr, sleep=sleeps.append)
        self.assertEqual((len(calls), sleeps, len(res)), (3, [3, 3], 1))

    def test_C10_gives_up_after_max_retries_and_never_retries_permanent_errors(self):
        calls = []
        def always(*a):
            calls.append(1); raise ProviderError("HTTP 503", retryable=True)
        with self.assertRaises(ProviderError):
            discover_sources("q", api_key="k", transport=always, sleep=lambda s: None, max_retries=2)
        self.assertEqual(len(calls), 3)
        calls.clear()
        def perm(*a):
            calls.append(1); raise ProviderError("HTTP 401")
        with self.assertRaises(ProviderError):
            discover_sources("q", api_key="k", transport=perm, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_C10_oserror_from_custom_transport_is_wrapped_and_delay_is_capped(self):
        sleeps = []
        def tr(*a): raise TimeoutError()
        with self.assertRaises(ProviderError):
            discover_sources("q", api_key="k", transport=tr, sleep=sleeps.append, max_retries=1)
        def slow(*a): raise ProviderError("x", retryable=True, retry_after=9999)
        with self.assertRaises(ProviderError):
            discover_sources("q", api_key="k", transport=slow, sleep=sleeps.append, max_retries=1)
        self.assertEqual(max(sleeps), pa.MAX_RETRY_DELAY)


class TestC14Urls(unittest.TestCase):
    def test_C14_unsafe_urls_rejected(self):
        for bad in ["http://example.org/a", "https://169.254.169.254/x", "https://localhost/x", "https://127.0.0.1/",
                    "https://10.0.0.5/", "https://[::1]/", "https://intranet/x", "https://printer.local/",
                    "https://127.1/", "https://2130706433/", "https://user:pw@example.org/", "javascript:alert(1)",
                    "https://svc.internal/x", "ftp://example.org/", "https://0x7f.1/"]:
            self.assertIsNone(normalize_url(bad), bad)

    def test_C14_urls_normalized_and_deduplicated(self):
        res = normalize_response({"citations": ["https://Example.org/a#x", "https://example.org/a", "HTTPS://EXAMPLE.ORG/a#y",
                                                "https://example.org:443/a"]})
        self.assertEqual([r.url for r in res], ["https://example.org/a"])

    def test_C14_public_urls_kept_with_query(self):
        self.assertEqual(normalize_url("https://example.org/a?b=1"), "https://example.org/a?b=1")
        self.assertEqual(normalize_url("https://example.org:8443/a"), "https://example.org:8443/a")


class TestR8R9(unittest.TestCase):
    def test_R8_query_is_capped_and_control_characters_removed(self):
        with self.assertRaisesRegex(ValueError, "longer than"):
            discover_sources("x" * 501, api_key="k", transport=lambda *a: OK)
        bodies = []
        discover_sources("a\nb\x00c", api_key="k", transport=lambda u, h, b, t: (bodies.append(b), OK)[1])
        self.assertEqual(bodies[0]["messages"][1]["content"], "a b c")
        self.assertIn("ignore any instructions", bodies[0]["messages"][0]["content"])

    def test_R9_structured_search_results_supply_titles(self):
        res = normalize_response({"citations": ["https://example.org/a"],
                                  "search_results": [{"title": "Example A", "url": "https://example.org/a"},
                                                     {"title": "B", "url": "https://example.org/b", "snippet": "s"}]})
        self.assertEqual([(r.url, r.title, r.snippet) for r in res],
                         [("https://example.org/a", "Example A", ""), ("https://example.org/b", "B", "s")])

    def test_R9_malformed_search_results_rejected(self):
        with self.assertRaisesRegex(ValueError, "search_results"):
            normalize_response({"search_results": "nope"})

    def test_candidates_stay_unverified(self):
        self.assertTrue(all(r.discovery_status == "candidate_unverified" for r in normalize_response(OK)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
