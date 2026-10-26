"""HTTP MCP contract checks use synthetic data, never production SQL samples."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class SkillMcpTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "scripts").mkdir()
        (root / "data").mkdir()
        for name in ("training_data", "text2sql_index", "sql_templates"):
            (root / "data" / f"{name}.json").write_text("{}")
        (root / "scripts" / "retrieve_examples.py").write_text(
            "def retrieve(question, top_k, top_k_templates):\n"
            "    return {'ok': True, 'question': question, 'top_k': top_k,\n"
            "            'template_limit': top_k_templates, 'examples': [], 'schemas': {}}\n"
        )
        cls.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("serve.py"))],
            env={**os.environ, "SQL_SAFE_QUERY_DIR": str(root)},
        )
        for _ in range(100):
            try:
                with urlopen("http://127.0.0.1:8011/healthz", timeout=1) as response:
                    if json.load(response)["ok"]:
                        return
            except URLError:
                if cls.process.poll() is not None:
                    break
                time.sleep(0.1)
        cls.tearDownClass()
        raise RuntimeError("Skill MCP failed to become healthy")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.temp.cleanup()

    async def test_only_retrieval_and_original_arguments(self):
        async with streamable_http_client("http://127.0.0.1:8011/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                self.assertEqual([tool.name for tool in tools.tools], ["sql_retrieve_examples"])
                result = await session.call_tool(
                    "sql_retrieve_examples", {"question": " RTU 未解除报警 ", "top_k": 2}
                )
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent["question"], "RTU 未解除报警")
                self.assertEqual(result.structuredContent["top_k"], 2)
                self.assertEqual(result.structuredContent["template_limit"], 3)

    async def test_unbounded_or_empty_requests_are_rejected(self):
        async with streamable_http_client("http://127.0.0.1:8011/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for arguments in (
                    {"question": ""},
                    {"question": "   "},
                    {"question": "x" * 2001},
                    {"question": "RTU", "top_k": 0},
                    {"question": "RTU", "top_k": 6},
                ):
                    with self.subTest(arguments=str(arguments)[:80]):
                        result = await session.call_tool("sql_retrieve_examples", arguments)
                        self.assertTrue(result.isError)
                result = await session.call_tool("sql_query_readonly", {"sql": "SELECT 1"})
                self.assertTrue(result.isError)

    def test_incomplete_skill_fails_before_startup(self):
        spec = importlib.util.spec_from_file_location("adapter", Path(__file__).with_name("serve.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as missing:
            with self.assertRaises(FileNotFoundError):
                module.create_server(Path(missing))


if __name__ == "__main__":
    unittest.main()
