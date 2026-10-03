"""Parser contract tests for acadagent.client.

WHY THIS FILE EXISTS
    client.py's parser was wrong for the entire life of the addon. It read
    `m["info"]["role"] == "assistant"` against records that carry NO "info",
    NO "parts" and NO "role". Every record was skipped, so the panel sat
    silent for 180s and then blamed a missing API key. The credentials were
    always fine.

    The fixture below is not invented. It is the VERBATIM shape returned by
    live opencode 1.18.18 on 2026-09-24, captured from
    GET /api/session/{id}/message after a real prompt. The assistant reply
    carried a `reasoning` item AND a `text` item, which is the exact case
    the skip rule has to get right.

WHAT IS PINNED
    1. type=="assistant" is how role is carried (NOT info.role).
    2. Text comes from content[] items of type=="text".
    3. A `reasoning` item is NEVER emitted. The model's private reasoning
       must not reach the user's chat. This currently holds by omission -
       _texts() admits type=="text" and nothing else - which is correct but
       would silently regress the moment someone "helpfully" broadened the
       filter to `p.get("text")`. That regression is what this file catches.
    4. Completion fires on m["finish"].
    5. The backend's own named error wins over a guessed one.

RUN
    python3 -m pytest addon/AcadAgent/tests/test_client_parse.py
    (or plain `python3 addon/AcadAgent/tests/test_client_parse.py`)

    client.py imports PySide6 at module scope for its QThread. These tests
    exercise the pure parse functions only, so PySide6 is stubbed if absent -
    the parse logic is what is under test, not Qt.
"""
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # -> addon/AcadAgent

# --- stub PySide6 so the parse functions import without a Qt runtime -------
if "PySide6" not in sys.modules:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        class _Signal:
            def __init__(self, *a, **k):
                pass

        class _QThread:
            def __init__(self, *a, **k):
                pass

        _qtcore = types.SimpleNamespace(Signal=_Signal, QThread=_QThread)
        _pyside = types.ModuleType("PySide6")
        _pyside.QtCore = _qtcore
        sys.modules["PySide6"] = _pyside
        sys.modules["PySide6.QtCore"] = _qtcore

from acadagent import client  # noqa: E402


# --- VERBATIM live capture, opencode 1.18.18, 2026-09-24 ------------------
# GET /api/session/ses_f2f766f21ffec97mqzoEQfow4k/message
# after POST /api/session/{id}/prompt {"prompt":{"text":"Reply with exactly: PARSER_OK"}}
LIVE_ASSISTANT = {
    "id": "msg_47ba2a4b5ffff09aRCzOpeSXtC",
    "type": "assistant",
    "agent": "build",
    "model": {"providerID": "opencode", "modelID": "grok-code"},
    "time": {"created": 1790205071700, "completed": 1790205073100},
    "finish": "stop",
    "cost": 0,
    "tokens": {"input": 12, "output": 9},
    "content": [
        {"id": "prt_r1", "type": "reasoning", "time": {"start": 1790205071800},
         "text": "We need answer exactly PARSER_OK. No tools."},
        {"id": "prt_t1", "type": "text", "text": "PARSER_OK"},
    ],
}

LIVE_USER = {
    "id": "msg_0d08990f200166e0SrJGuuPIf3",
    "type": "user",
    "time": {"created": 1790205071602},
    "text": "Reply with exactly: PARSER_OK",
}

# The private reasoning string, live-captured. If this ever appears in the
# panel it is a privacy leak, not a cosmetic bug.
REASONING_TEXT = "We need answer exactly PARSER_OK. No tools."


class TestRoleDetection(unittest.TestCase):
    """Role is carried by "type". The old parser looked under "info"."""

    def test_assistant_record_is_recognised(self):
        self.assertTrue(client._is_assistant(LIVE_ASSISTANT))

    def test_user_record_is_not_assistant(self):
        self.assertFalse(client._is_assistant(LIVE_USER))

    def test_the_old_broken_predicate_would_have_matched_nothing(self):
        """Pin the bug itself so nobody reintroduces it as a 'fallback'."""
        for rec in (LIVE_ASSISTANT, LIVE_USER):
            info = rec.get("info", rec)
            self.assertNotEqual(
                info.get("role"), "assistant",
                "live records carry no 'role' key; a parser keyed on it "
                "silently matches nothing and hangs for the full timeout")


class TestTextExtraction(unittest.TestCase):

    def test_extracts_the_assistant_text(self):
        self.assertEqual(client._texts(LIVE_ASSISTANT), ["PARSER_OK"])

    def test_reasoning_is_never_emitted(self):
        """THE load-bearing assertion of this file.

        The live reply interleaves reasoning and text. Only text may escape.
        """
        out = client._texts(LIVE_ASSISTANT)
        self.assertNotIn(REASONING_TEXT, out)
        for chunk in out:
            self.assertNotIn("We need answer", chunk)

    def test_a_reasoning_only_reply_yields_nothing(self):
        """No text part -> no output at all, not the reasoning as a stand-in.

        A missing value stays missing (P1).
        """
        msg = {"type": "assistant", "finish": "stop",
               "content": [{"type": "reasoning", "text": REASONING_TEXT}]}
        self.assertEqual(client._texts(msg), [])

    def test_parts_key_is_not_read(self):
        """"parts" belongs to the OTHER API surface (/session, no /api).

        Reading it here is the T5 trap: the schema looks plausible and
        matches nothing.
        """
        wrong_surface = {"type": "assistant",
                         "parts": [{"type": "text", "text": "WRONG_SURFACE"}]}
        self.assertEqual(client._texts(wrong_surface), [])

    def test_blank_and_whitespace_text_is_dropped(self):
        msg = {"type": "assistant",
               "content": [{"type": "text", "text": "   "},
                           {"type": "text", "text": "kept"}]}
        self.assertEqual(client._texts(msg), ["kept"])

    def test_missing_content_key_does_not_raise(self):
        self.assertEqual(client._texts({"type": "assistant"}), [])


class TestCompletion(unittest.TestCase):

    def test_finish_marks_the_reply_complete(self):
        self.assertTrue(LIVE_ASSISTANT.get("finish"))

    def test_in_flight_reply_is_not_complete(self):
        in_flight = {"type": "assistant", "content": [], "time": {"created": 1}}
        self.assertFalse(in_flight.get("finish"))
        self.assertFalse((in_flight.get("time") or {}).get("completed"))


class TestNamedError(unittest.TestCase):
    """When the backend names the failure, report ITS words, not a guess."""

    def test_error_message_is_surfaced(self):
        msg = dict(LIVE_ASSISTANT)
        msg["error"] = {"type": "unknown",
                        "message": "provider returned 401 unauthorized"}
        self.assertEqual(client._error_of(msg),
                         "provider returned 401 unauthorized")

    def test_no_error_is_none_not_empty_string(self):
        self.assertIsNone(client._error_of(LIVE_ASSISTANT))

    def test_blank_error_message_is_none(self):
        msg = {"error": {"type": "unknown", "message": "   "}}
        self.assertIsNone(client._error_of(msg))


class TestToolParts(unittest.TestCase):
    """Tool output lives in state["content"][], not a plain "output" string."""

    def test_tool_output_is_flattened_from_content(self):
        msg = {"type": "assistant", "content": [{
            "id": "prt_x", "type": "tool", "name": "get_view",
            "state": {"status": "completed", "input": {"doc": "XWing"},
                      "content": [{"type": "text", "text": "saved view.png"}]},
        }]}
        tools = client._tools(msg)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "get_view")
        self.assertEqual(tools[0]["status"], "completed")
        self.assertEqual(tools[0]["output"], "saved view.png")

    def test_text_parts_are_not_reported_as_tools(self):
        self.assertEqual(client._tools(LIVE_ASSISTANT), [])


class TestPromptBody(unittest.TestCase):
    """The prompt schema is additionalProperties:false over
    {id, prompt, delivery, resume}. A top-level "model" key returns 200 and
    is silently ignored - which looked exactly like model selection working.
    """

    def test_send_does_not_smuggle_a_model_key(self):
        sent = {}

        def fake_req(url, method="GET", payload=None, timeout=60):
            sent["url"] = url
            sent["payload"] = payload
            return {"data": {"admittedSeq": 1}}

        real = client._req
        client._req = fake_req
        try:
            client.Backend("http://127.0.0.1:4199").send(
                "ses_1", "hello", provider="opencode", model="grok-code")
        finally:
            client._req = real

        self.assertEqual(sent["payload"], {"prompt": {"text": "hello"}})
        self.assertNotIn("model", sent["payload"])
        self.assertTrue(sent["url"].endswith("/api/session/ses_1/prompt"))


class TestEndToEndPollShape(unittest.TestCase):
    """The whole fresh-message list, parsed the way ChatWorker.run parses it."""

    def test_full_transcript_yields_only_the_answer(self):
        fresh = [LIVE_ASSISTANT, LIVE_USER]
        seen = []
        done = False
        for m in fresh:
            if not client._is_assistant(m):
                continue
            for t in client._texts(m):
                if t not in seen:
                    seen.append(t)
            if m.get("finish"):
                done = True

        self.assertTrue(done, "completion must fire on finish")
        self.assertEqual(seen, ["PARSER_OK"])
        self.assertNotIn(REASONING_TEXT, "\n\n".join(seen))




# ==========================================================================
# ATTACHMENT CONTRACT
# Measured live against opencode 1.18.18 on 2026-09-24 with a 64x64 PNG.
# All three URI forms were ADMITTED (HTTP 200). Only the data: URI produced
# an answer; the other two failed ASYNCHRONOUSLY with
#     "OpenAI Chat media must contain valid base64"
# which mentions base64, not URIs, and so points away from the real cause.
# ==========================================================================
import base64      # noqa: E402
import os          # noqa: E402
import tempfile    # noqa: E402


# A real, minimal PNG (1x1). Not a fake byte string - attachment() verifies
# nothing about pixels, but the tests should not lie about what a PNG is.
_PNG_1x1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    b"IQAAAABJRU5ErkJggg==")


class TestAttachment(unittest.TestCase):

    def setUp(self):
        fd, self.png = tempfile.mkstemp(suffix=".png")
        os.write(fd, _PNG_1x1)
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self.png) and os.remove(self.png))

    def test_uri_is_a_data_uri_not_a_path(self):
        """THE load-bearing assertion. A file:// or bare path is admitted
        with HTTP 200 and then fails ~10s later. Measured, both forms."""
        att = client.attachment(self.png)
        self.assertTrue(att["uri"].startswith("data:image/png;base64,"),
                        "the server never opens a path; bytes must be inline")
        self.assertNotIn("file://", att["uri"])
        self.assertFalse(att["uri"].startswith("/"))

    def test_bytes_round_trip_intact(self):
        att = client.attachment(self.png)
        payload = att["uri"].split(",", 1)[1]
        self.assertEqual(base64.b64decode(payload), _PNG_1x1)

    def test_mime_and_name_are_present(self):
        att = client.attachment(self.png, name="viewport.png")
        self.assertEqual(att["mime"], "image/png")
        self.assertEqual(att["name"], "viewport.png")

    def test_name_defaults_to_the_basename(self):
        self.assertEqual(client.attachment(self.png)["name"],
                         os.path.basename(self.png))

    def test_only_the_three_schema_keys_are_sent(self):
        """PromptFileAttachment is additionalProperties:false over
        {uri, mime, name, description, source}. Extra keys are rejected."""
        allowed = {"uri", "mime", "name", "description", "source"}
        self.assertTrue(set(client.attachment(self.png)).issubset(allowed))

    def test_unknown_extension_raises_rather_than_guessing(self):
        """A wrong MIME fails async and confusingly. Refuse instead (P1)."""
        fd, path = tempfile.mkstemp(suffix=".fcstd")
        os.write(fd, b"not an image")
        os.close(fd)
        try:
            with self.assertRaises(ValueError):
                client.attachment(path)
        finally:
            os.remove(path)

    def test_empty_file_is_refused(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with self.assertRaises(ValueError):
                client.attachment(path)
        finally:
            os.remove(path)


class TestSendWithImages(unittest.TestCase):

    def setUp(self):
        fd, self.png = tempfile.mkstemp(suffix=".png")
        os.write(fd, _PNG_1x1)
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self.png) and os.remove(self.png))
        self.sent = {}

        def fake_req(url, method="GET", payload=None, timeout=60):
            self.sent["url"] = url
            self.sent["payload"] = payload
            return {"data": {"admittedSeq": 1}}

        real = client._req
        client._req = fake_req
        self.addCleanup(lambda: setattr(client, "_req", real))

    def test_images_become_prompt_files(self):
        client.Backend("http://127.0.0.1:4199").send(
            "ses_1", "what is this?", images=[self.png])
        prompt = self.sent["payload"]["prompt"]
        self.assertEqual(prompt["text"], "what is this?")
        self.assertEqual(len(prompt["files"]), 1)
        self.assertTrue(prompt["files"][0]["uri"].startswith("data:image/png;base64,"))

    def test_no_images_sends_no_files_key(self):
        """An empty files[] is not the same as no attachment. Send neither."""
        client.Backend("http://127.0.0.1:4199").send("ses_1", "hello")
        self.assertEqual(self.sent["payload"], {"prompt": {"text": "hello"}})

    def test_files_sits_under_prompt_not_at_top_level(self):
        """A top-level {"parts":[...]} body is the OTHER surface and returns
        HTTP 400 that reads exactly like an auth failure (T5)."""
        client.Backend("http://127.0.0.1:4199").send(
            "ses_1", "x", images=[self.png])
        self.assertEqual(set(self.sent["payload"]), {"prompt"})
        self.assertNotIn("parts", self.sent["payload"])
        self.assertNotIn("files", self.sent["payload"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
