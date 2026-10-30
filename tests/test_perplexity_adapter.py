import unittest
from dpp_audit.perplexity_adapter import discover_sources, normalize_response

RECORDED_RESPONSE = {
    "choices": [{"message": {"content": "Candidate sources were found; this does not verify the claim."}}],
    "citations": [
        "https://example.org/a",
        {"url": "https://example.org/b", "title": "Example B", "snippet": "Candidate snippet"},
        "https://example.org/a",
        "javascript:alert(1)",
        7,
    ],
}


class PerplexityAdapterTests(unittest.TestCase):
    def test_normalizes_recorded_provider_response_and_deduplicates(self):
        results = normalize_response(RECORDED_RESPONSE)
        self.assertEqual([r.url for r in results], ["https://example.org/a", "https://example.org/b"])
        self.assertTrue(all(r.discovery_status == "candidate_unverified" for r in results))

    def test_transport_request_shape_and_secret_not_in_results(self):
        calls = []
        def fake_transport(url, headers, body, timeout):
            calls.append((url, headers, body, timeout))
            return RECORDED_RESPONSE
        results = discover_sources("check a claim", api_key="test-secret", transport=fake_transport)
        self.assertEqual(len(results), 2)
        self.assertEqual(calls[0][1]["Authorization"], "Bearer test-secret")
        self.assertEqual(calls[0][2]["temperature"], 0)
        self.assertNotIn("test-secret", repr(results))

    def test_empty_query_rejected_before_transport(self):
        with self.assertRaisesRegex(ValueError, "query must not be empty"):
            discover_sources("  ", api_key="x")

    def test_missing_key_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "PERPLEXITY_API_KEY"):
            discover_sources("find sources", api_key="", transport=lambda *args: {})

    def test_malformed_citations_rejected(self):
        with self.assertRaisesRegex(ValueError, "citations must be a list"):
            normalize_response({"citations": "not-a-list"})

if __name__ == "__main__":
    unittest.main()
