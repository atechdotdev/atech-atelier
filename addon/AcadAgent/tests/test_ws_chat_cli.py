"""WS-CHAT round 2, the claude_cli half: S16 (one argv builder, lean and
isolated launch), R78 (isolation), S10 (exact allowlist), R35 (prompt on
stdin, system prompt in a 0600 file), S19 (partial text, finish on
`result`), S26 (model/effort pass-through).

Same fake `claude` and PySide6 stub as test_claude_cli (imported from
there), so this runs under plain Python and the bundled 3.11 alike:

    python3 -m unittest addon/AcadAgent/tests/test_ws_chat_cli.py -v

MEASURED FIXTURES
    HELP_2_1_232 / HELP_2_0_25 are the long options `claude --help` listed
    on this machine on 2026-09-25 (~/.local/bin/claude 2.1.232 and the npm
    /usr/local/bin/claude 2.0.25), extracted with supported_flags()'s own
    regex from the saved help texts. The 2.1.232 text documents the
    -file variant only as "--append-system-prompt[-file]"; that literal is
    kept. PARTIAL_WRITE is the stream_event sequence of a real
    --include-partial-messages run (2.1.232) in which the agent wrote a
    3-line model.py, trimmed to the keys claude_cli reads (file path
    shortened).
"""
import json
import os
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_claude_cli import (LIVE_OK, FakeClaudeCase, _PKG,  # noqa: E402
                             ndjson)

cli = _PKG.claude_cli

HELP_2_1_232 = (
    "--add-dir --agent --agents --allow-dangerously-skip-permissions "
    "--allowed-tools --allowedTools --append-system-prompt "
    "--autocompact --ax-screen-reader --background --bare --betas --bg "
    "--brief --chrome --cloud --continue --dangerously-skip-permissions "
    "--debug --debug-file --disable-slash-commands --disallowed-tools "
    "--disallowedTools --effort --environment "
    "--exclude-dynamic-system-prompt-sections --fallback-model --file "
    "--fork-session --forward-subagent-text --from-pr --help --ide "
    "--include-hook-events --include-partial-messages --input-format "
    "--json-schema --max-budget-usd --mcp-config --model --name "
    "--no-chrome --no-session-persistence --output-format "
    "--permission-mode --plugin-dir --plugin-url --print "
    "--prompt-suggestions --remote-control "
    "--remote-control-session-name-prefix --replay-user-messages --resume "
    "--safe-mode --session-id --setting-sources --settings "
    "--strict-mcp-config --system-prompt --teleport --tmux --tools "
    "--verbose --version --worktree\n"
    "  Explicitly provide context via: --system-prompt[-file],\n"
    "  --append-system-prompt[-file], --add-dir\n")
HELP_2_0_25 = (
    "--add-dir --agents --allowed-tools --allowedTools "
    "--append-system-prompt --continue --dangerously-skip-permissions "
    "--debug --disallowed-tools --disallowedTools --fallback-model "
    "--fork-session --help --ide --include-partial-messages --input-format "
    "--mcp-config --mcp-debug --model --output-format --permission-mode "
    "--plugin-dir --print --replay-user-messages --resume --session-id "
    "--settings --setting-sources --strict-mcp-config --system-prompt "
    "--verbose --version\n")

def _flags(text):
    """supported_flags() on a help text, without starting a process."""
    import re
    s = set(re.findall(r"(?<![\w-])(--[a-zA-Z][a-zA-Z0-9-]*)", text))
    for b in re.findall(r"(--[a-zA-Z][a-zA-Z0-9-]*)\[-file\]", text):
        s.update((b, b + "-file"))
    return frozenset(s)


def _ev(e):
    return {"type": "stream_event", "event": e}


PARTIAL_WRITE = [
    {"type": "system", "subtype": "init", "session_id": "s-part"},
    _ev({"type": "message_start", "message": {"content": []}}),
    _ev({"type": "content_block_start", "index": 0, "content_block": {
        "type": "tool_use", "id": "toolu_1", "name": "Write", "input": {}}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": ""}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": "{\"file_path\": \"/tmp"}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": "/ws/model.py"}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta",
        "partial_json": "\", \"content\": \"a = 1\\nb"}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": " = 2\\nc = 3"}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": "\\n"}}),
    _ev({"type": "content_block_delta", "index": 0, "delta": {
        "type": "input_json_delta", "partial_json": "\"}"}}),
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write",
         "input": {"file_path": "/tmp/ws/model.py",
                   "content": "a = 1\nb = 2\nc = 3\n"}}]}},
    _ev({"type": "content_block_stop", "index": 0}),
    _ev({"type": "message_stop"}),
    _ev({"type": "message_start", "message": {"content": []}}),
    _ev({"type": "content_block_start", "index": 0,
         "content_block": {"type": "text", "text": ""}}),
    _ev({"type": "content_block_delta", "index": 0,
         "delta": {"type": "text_delta", "text": "DO"}}),
    _ev({"type": "content_block_delta", "index": 0,
         "delta": {"type": "text_delta", "text": "NE"}}),
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "DONE"}]}},
    _ev({"type": "content_block_stop", "index": 0}),
    {"type": "result", "subtype": "success", "is_error": False,
     "result": "DONE", "session_id": "s-part",
     "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t2",
                             "tool_input": {"command": "ls ~"}}]},
]


class TestSupportedFlags(unittest.TestCase):

    def test_bracket_file_variant_counts_as_both(self):
        f = _flags(HELP_2_1_232)
        self.assertIn("--append-system-prompt-file", f)
        self.assertIn("--append-system-prompt", f)
        self.assertNotIn("--append-system-prompt-file", _flags(HELP_2_0_25))

    def test_regex_matches_the_module(self):
        # The helper above must be the module's rule, not a second opinion.
        import inspect
        src = inspect.getsource(cli.supported_flags)
        self.assertIn(r'(?<![\w-])(--[a-zA-Z][a-zA-Z0-9-]*)', src)
        self.assertIn(r'(--[a-zA-Z][a-zA-Z0-9-]*)\[-file\]', src)


class TestAgentArgv(unittest.TestCase):

    def test_new_cli_gets_every_isolating_flag(self):
        dropped = []
        a = cli.agent_argv("/w", flags=_flags(HELP_2_1_232), dropped=dropped)
        self.assertEqual(dropped, [])
        for flag in ("--strict-mcp-config", "--disable-slash-commands",
                     "--exclude-dynamic-system-prompt-sections"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--tools") + 1],
                         "Read,Write,Edit,Bash,Glob,Grep")
        self.assertEqual(a[a.index("--setting-sources") + 1], "")
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "3.00")
        # S10: exactly the self-check command, never bare Bash.
        i = a.index("--allowedTools")
        self.assertEqual(a[i + 1:i + 3], ["Bash(./check)", "Bash(./check *)"])
        self.assertNotIn("Bash", a[i + 1:i + 3])
        # R14: one --add-dir, the workspace, last.
        self.assertEqual([a[k + 1] for k, x in enumerate(a)
                          if x == "--add-dir"], ["/w"])
        self.assertNotIn("--model", a)          # S26 default: CLI default
        self.assertNotIn("--effort", a)

    def test_old_cli_drops_what_it_does_not_have(self):
        dropped = []
        a = cli.agent_argv("/w", effort="high", budget=2.5,
                           flags=_flags(HELP_2_0_25), dropped=dropped)
        for flag in ("--tools", "--disable-slash-commands",
                     "--exclude-dynamic-system-prompt-sections",
                     "--max-budget-usd", "--effort"):
            self.assertNotIn(flag, a)
            self.assertIn(flag, dropped)
        # --strict-mcp-config alone is still isolation from MCP servers.
        self.assertIn("--strict-mcp-config", a)
        self.assertIn("--setting-sources", a)

    def test_tools_never_without_strict_mcp(self):
        f = _flags(HELP_2_1_232) - {"--strict-mcp-config"}
        a = cli.agent_argv("/w", flags=f)
        self.assertNotIn("--tools", a)

    def test_model_effort_budget_pass_through(self):
        f = _flags(HELP_2_1_232)
        a = cli.agent_argv("/w", model="sonnet", effort="xhigh", budget=1,
                           flags=f)
        self.assertEqual(a[a.index("--model") + 1], "sonnet")
        self.assertEqual(a[a.index("--effort") + 1], "xhigh")
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "1.00")
        dropped = []
        a = cli.agent_argv("/w", effort="turbo", budget=0, flags=f,
                           dropped=dropped)
        self.assertNotIn("--effort", a)
        self.assertNotIn("--max-budget-usd", a)
        self.assertIn("--effort turbo", dropped)

    def test_allowed_can_be_emptied(self):
        a = cli.agent_argv("/w", allowed=(), flags=_flags(HELP_2_1_232))
        self.assertNotIn("--allowedTools", a)

    def test_agent_settings_defaults_and_values(self):
        self.assertEqual(cli.agent_settings({}),
                         {"model": None, "effort": None, "budget": 3.0})
        self.assertEqual(
            cli.agent_settings({"agent_model": " opus ", "agent_effort":
                                "low", "agent_budget_usd": "1.5"}),
            {"model": "opus", "effort": "low", "budget": 1.5})
        self.assertEqual(cli.agent_settings(
            {"agent_budget_usd": "lots"})["budget"], 3.0)
        self.assertIsNone(cli.agent_settings(
            {"agent_budget_usd": ""})["budget"])


class _Run(FakeClaudeCase):
    def setUp(self):
        super().setUp()
        cli._HELP.clear()
        self.addCleanup(cli._HELP.clear)

    def help(self, text):
        self.env.set("FAKE_CLAUDE_HELP", text)


class TestRunStdinAndSystemPrompt(_Run):

    def test_prompt_on_stdin_and_system_prompt_in_a_0600_file(self):
        self.help(HELP_2_1_232)
        self.fixture(ndjson(LIVE_OK))
        prompt = "-5 mm thinner\n- and round the corners"
        got = self.turn(prompt=prompt, system_prompt="SECRET SYSTEM PROMPT",
                        agent={"ws": self.tmp})
        self.assertEqual(got["failed"], [])
        rec = self.recorded()
        # R35: a prompt starting with "-" reaches the CLI intact, and no
        # free text is on the command line.
        self.assertEqual(rec["stdin"], prompt)
        blob = json.dumps(rec["argv"])
        self.assertNotIn("thinner", blob)
        self.assertNotIn("SECRET", blob)
        self.assertEqual(rec["spf"]["text"], "SECRET SYSTEM PROMPT")
        self.assertEqual(rec["spf"]["mode"], "0o600")
        self.assertEqual(rec["spf"]["dir_mode"], "0o700")
        self.assertFalse(os.path.exists(rec["spf"]["path"]),
                         "the system prompt file outlived the turn")
        argv = rec["argv"]
        self.assertIn("--strict-mcp-config", argv)       # agent_argv ran
        self.assertIn("--include-partial-messages", argv)
        self.assertEqual(got["run"].dropped, [])
        self.assertNotIn("SECRET", " ".join(got["run"].flags()))

    def test_old_cli_gets_the_inline_system_prompt(self):
        self.help(HELP_2_0_25)
        self.fixture(ndjson(LIVE_OK))
        got = self.turn(system_prompt="SYS", agent={"ws": self.tmp})
        argv = self.recorded()["argv"]
        self.assertEqual(argv[argv.index("--append-system-prompt") + 1],
                         "SYS")
        self.assertNotIn("--append-system-prompt-file", argv)
        self.assertNotIn("--tools", argv)
        self.assertIn("--append-system-prompt-file", got["run"].dropped)
        self.assertEqual(got["run"].flags()[
            got["run"].flags().index("--append-system-prompt") + 1],
            "<3 chars>")

    def test_unreadable_help_drops_optional_flags_but_still_runs(self):
        self.help("")
        self.fixture(ndjson(LIVE_OK))
        got = self.turn(system_prompt="SYS", agent={"ws": self.tmp})
        self.assertEqual(got["ok"][0][0], "PARSER_OK")
        argv = self.recorded()["argv"]
        self.assertNotIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--add-dir") + 1], self.tmp)

    def test_unreadable_help_is_not_cached(self):
        # Review round 2: one failed --help must not pin every later turn
        # to the un-isolated launch (R78).
        self.help("")
        exe = cli.find_claude()
        self.assertEqual(cli.supported_flags(exe), frozenset())
        self.assertNotIn(exe, cli._HELP)

    def test_flags_is_none_before_the_worker_built_argv(self):
        run = cli.ClaudeRun("x", cwd=self.tmp)
        self.assertIsNone(run.flags())


class TestPartialAndResult(_Run):

    def test_partial_text_and_writing_progress(self):
        self.help(HELP_2_1_232)
        self.fixture(ndjson(PARTIAL_WRITE))
        run = cli.ClaudeRun("x", cwd=self.tmp, agent={"ws": self.tmp})
        deltas, progress, ok = [], [], []
        run.delta.connect(deltas.append)
        run.progress.connect(progress.append)
        run.finished_ok.connect(lambda t, r: ok.append(r))
        run.run()
        self.assertEqual(progress, ["writing model.py: 1 line",
                                    "writing model.py: 2 lines",
                                    "writing model.py: 3 lines"])
        self.assertEqual(deltas, ["DO", "DONE"])
        # S16: the denials reach the panel on the result record.
        self.assertEqual(ok[0]["permission_denials"][0]["tool_input"],
                         {"command": "ls ~"})

    def test_finished_ok_on_the_result_line_not_on_exit(self):
        """S19 verify: a CLI that sleeps 1 s after `result` - finished_ok
        must arrive < 50 ms after the result line (baseline: at exit)."""
        self.fixture(ndjson(LIVE_OK))
        self.env.set("FAKE_CLAUDE_SLEEP_AFTER", "1.0")
        run = cli.ClaudeRun("x", cwd=self.tmp)
        stamps = {}
        run.finished_ok.connect(
            lambda t, r: stamps.setdefault("ok", time.monotonic()))
        t0 = time.monotonic()
        th = threading.Thread(target=run.run, daemon=True)
        th.start()
        th.join(20)
        self.assertFalse(th.is_alive())
        end = time.monotonic()
        lag = (stamps["ok"] - t0) - run.timings["result"]
        print("\n  [S19] finished_ok %.1f ms after the result line; the "
              "CLI exited %.2f s later" % (lag * 1000, end - stamps["ok"]))
        self.assertLess(lag, 0.05)
        self.assertGreater(end - stamps["ok"], 0.8,
                           "the run should still reap the exiting CLI")
        self.assertIn("exit", run.timings)

    def test_error_result_still_waits_for_exit_and_fails_once(self):
        recs = [LIVE_OK[1], {"type": "result", "subtype": "success",
                             "is_error": True, "result": "Not logged in"}]
        self.fixture(ndjson(recs), exit_code=1)
        got = self.turn()
        self.assertEqual(got["ok"], [])
        self.assertEqual(got["failed"], ["Not logged in"])

    def test_cli_that_never_exits_after_result_is_signalled(self):
        self.fixture(ndjson(LIVE_OK))
        self.env.set("FAKE_CLAUDE_SLEEP_AFTER", "60")
        run = cli.ClaudeRun("x", cwd=self.tmp)
        run.EXIT_GRACE = 0.3
        ok = []
        run.finished_ok.connect(lambda t, r: ok.append(t))
        th = threading.Thread(target=run.run, daemon=True)
        th.start()
        th.join(10)
        self.assertFalse(th.is_alive(), "a hung CLI kept the thread")
        self.assertEqual(ok, ["PARSER_OK"])


if __name__ == "__main__":
    unittest.main()
