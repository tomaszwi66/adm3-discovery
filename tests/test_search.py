"""Exercise provider routing and the MCP transport through research consumption."""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import config
from agents import researcher
from tools import search

if importlib.util.find_spec("mcp") is not None:
    from tools import parallel_search
else:
    parallel_search = None


class RoutingTests(unittest.TestCase):
    def test_default_saved_choice_and_cli_override(self):
        with patch.object(sys, "argv", ["main.py"]):
            self.assertEqual(config.parse_args().search_provider, "duckduckgo")
        with patch.object(config, "SEARCH_PROVIDER", "parallel"):
            with patch.object(sys, "argv", ["main.py"]):
                self.assertEqual(config.parse_args().search_provider, "parallel")
            with patch.object(sys, "argv", ["main.py", "--search-provider", "none"]):
                self.assertEqual(config.parse_args().search_provider, "none")

    def test_default_routes_to_duckduckgo(self):
        with patch.object(config, "SEARCH_PROVIDER", "duckduckgo"), patch.object(
            search, "_search_duckduckgo", return_value=[{"title": "DDG"}]
        ) as ddg:
            self.assertEqual(search.search_web("research"), [{"title": "DDG"}])
            ddg.assert_called_once_with("research", config.SEARCH_RESULTS)

    def test_disabled_empty_limit_and_unknown_do_not_dispatch(self):
        with patch.object(search, "_search_duckduckgo") as ddg:
            for provider, limit in [("none", 5), ("parallel", 0), ("invalid", 5)]:
                with patch.object(config, "SEARCH_PROVIDER", provider), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(search.search_web("research", limit), [])
            ddg.assert_not_called()

    def test_cli_applies_override_to_runtime(self):
        import main

        seen = []
        def iteration(*args):
            seen.append(config.SEARCH_PROVIDER)
            return {}, {}
        with patch.object(sys, "argv", ["main.py", "--problem", "research", "-n", "1", "--search-provider", "none"]), patch.object(
            config, "SEARCH_PROVIDER", "duckduckgo"
        ), patch.object(config, "MEMORY_FILE", "memory.json"), patch.object(
            main.store, "load_memory", return_value={}
        ), patch.object(main, "run_iteration", side_effect=iteration), contextlib.redirect_stdout(io.StringIO()):
            main.main()
        self.assertEqual(seen, ["none"])

    def test_missing_optional_dependency_warns_without_fallback(self):
        stderr = io.StringIO()
        with patch.dict(sys.modules, {"tools.parallel_search": None}), patch.object(
            config, "SEARCH_PROVIDER", "parallel"
        ), patch.object(search, "_search_duckduckgo") as ddg, contextlib.redirect_stderr(stderr):
            self.assertEqual(search.search_web("research"), [])
            ddg.assert_not_called()
        self.assertIn("requirements-parallel.txt", stderr.getvalue())


@unittest.skipIf(parallel_search is None, "Install requirements-parallel.txt for MCP checks")
class ParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.response = None
        cls.delay = 0
        cls.http_status = 200
        cls.advertise = True

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.requests.append({"path": self.path, "headers": dict(self.headers), "data": data})
                method = data["method"]
                if "id" not in data:
                    self.send_response(202)
                    self.end_headers()
                    return
                status = 200
                if method == "initialize":
                    result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fixture", "version": "1"}}
                elif method == "tools/list":
                    result = {"tools": [{"name": "web_search", "inputSchema": {"type": "object"}}] if cls.advertise else []}
                elif method == "tools/call":
                    time.sleep(cls.delay)
                    result = cls.response
                    status = cls.http_status
                else:
                    self.send_error(400)
                    return
                body = json.dumps({"jsonrpc": "2.0", "id": data["id"], "result": result}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        type(self).requests.clear()
        type(self).delay = 0
        type(self).http_status = 200
        type(self).advertise = True
        self.payload = {"results": [{"title": "Evidence", "url": "https://example.org/paper", "excerpts": ["A measured effect.", "Independent evidence."]}]}
        type(self).response = {"content": [], "structuredContent": self.payload, "isError": False}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.stack.enter_context(patch.object(config, "SEARCH_PROVIDER", "parallel"))
        self.stack.enter_context(patch.object(config, "SEARCH_TIMEOUT", 2))
        self.stack.enter_context(patch.object(parallel_search, "MCP_URL", f"http://127.0.0.1:{self.server.server_port}/mcp"))
        self.ddg = self.stack.enter_context(patch.object(search, "_search_duckduckgo"))
        self.stderr = io.StringIO()
        self.stack.enter_context(contextlib.redirect_stderr(self.stderr))

    def test_research_agent_consumes_excerpts_and_source_urls(self):
        prompts = []
        def llm(prompt, **kwargs):
            prompts.append(prompt)
            return json.dumps({"research": [{"id": 1, "novelty": "Partial overlap", "supporting_evidence": ["A measured effect."], "updated_p_correct": 55}]})
        with patch.object(researcher, "query_llm", side_effect=llm), contextlib.redirect_stdout(io.StringIO()):
            result = researcher.research([{"id": 1, "hypothesis": "Mechanism", "p_correct": 40}], "Research problem", "scripted-model")
        self.assertEqual(result[0]["p_correct"], 55)
        self.assertIn("A measured effect.\nIndependent evidence.", prompts[0])
        self.assertIn("Source: https://example.org/paper", prompts[0])
        calls = [r for r in self.requests if r["data"]["method"] == "tools/call"]
        args = calls[0]["data"]["params"]["arguments"]
        self.assertEqual(args["objective"], "Research problem Mechanism")
        self.assertEqual(args["search_queries"], ["Research problem Mechanism"])
        self.assertEqual(args["session_id"], parallel_search._SESSION_ID)
        for request in self.requests:
            self.assertEqual(request["path"], "/mcp")
            self.assertEqual(request["headers"]["User-Agent"], parallel_search.USER_AGENT)
            self.assertNotIn("Authorization", request["headers"])
        self.ddg.assert_not_called()

    def test_text_response_limit_and_stable_session(self):
        self.payload["results"].append({"title": None, "url": "http://example.org/second", "excerpts": []})
        type(self).response = {"content": [{"type": "text", "text": json.dumps(self.payload)}]}
        self.assertEqual(len(search.search_web("query", 1)), 1)
        results = search.search_web("query", 2)
        self.assertEqual(results[1], {"title": "http://example.org/second", "href": "http://example.org/second", "body": ""})
        ids = [r["data"]["params"]["arguments"]["session_id"] for r in self.requests if r["data"]["method"] == "tools/call"]
        self.assertEqual(ids, [parallel_search._SESSION_ID] * 2)

    def test_tool_error_http_error_and_invalid_responses(self):
        for response in [
            {"content": [{"type": "text", "text": "Usage limit reached"}], "isError": True},
            {"content": [{"type": "text", "text": "not JSON"}]},
            {"content": [], "structuredContent": {}},
            {"content": [], "structuredContent": {"results": [{"url": "file:///tmp/private", "excerpts": ["bad"]}]}},
            {"content": [], "structuredContent": {"results": [{"url": "https://example.org", "excerpts": [42]}]}},
        ]:
            with self.subTest(response=response):
                type(self).response = response
                self.assertEqual(search.search_web("query"), [])
        type(self).http_status = 403
        self.assertEqual(search.search_web("query"), [])
        self.ddg.assert_not_called()

    def test_missing_tool_does_not_call_search(self):
        type(self).advertise = False
        self.assertEqual(search.search_web("query"), [])
        self.assertFalse(any(r["data"]["method"] == "tools/call" for r in self.requests))

    def test_disabled_search_has_no_network_requests(self):
        with patch.object(config, "SEARCH_PROVIDER", "none"):
            self.assertEqual(search.search_web("query"), [])
        self.assertEqual(self.requests, [])

    def test_timeout_is_bounded_and_does_not_fallback(self):
        type(self).delay = 0.5
        with patch.object(config, "SEARCH_TIMEOUT", 0.1):
            start = time.monotonic()
            self.assertEqual(search.search_web("query"), [])
            self.assertLess(time.monotonic() - start, 1.5)
        self.ddg.assert_not_called()

    def test_cancellation_propagates_and_closes_transport(self):
        type(self).delay = 0.5
        async def cancel():
            task = asyncio.create_task(parallel_search.search_parallel("query", 5))
            for _ in range(100):
                if any(r["data"]["method"] == "tools/call" for r in self.requests):
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(any(r["data"]["method"] == "tools/call" for r in self.requests))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        asyncio.run(cancel())
        self.ddg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
