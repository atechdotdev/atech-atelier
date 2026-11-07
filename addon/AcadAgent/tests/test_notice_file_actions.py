"""Notice file buttons survive a saved chat (panel.FileAction).

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_notice_file_actions

The "Assembly video ready" notice came back from past chats (and from a
chat kept in the .FCStd) as text only: every notice button was dropped as
a callable. Play / Show in Finder are now data and are drawn again; data
from another computer's file can never "open" anything but a video or a
picture.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import projects_store as ps  # noqa: E402

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import panel
except ImportError:
    panel = None


def _snap(video):
    return {"entries": [{
        "kind": "notice", "title": "Assembly video ready: Walker",
        "body": "25.6 s", "detail": None, "tag": None, "enabled": [True, True],
        "actions": [("Play", panel.FileAction("open", video)),
                    ("Show in Finder", panel.FileAction("reveal", video)),
                    ("Retry", print)]}], "last_text": ""}


@unittest.skipIf(panel is None, "PySide6 not installed")
class TestFileActions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.video = os.path.join(self.tmp, "walker.mp4")
        with open(self.video, "wb") as fh:
            fh.write(b"\0")

    def notice_from(self, entry):
        acts = panel._live_actions(entry["actions"])
        return panel.Notice(entry["title"], entry["body"], actions=acts)

    def test_past_chat_keeps_play_and_reveal(self):
        plain = json.loads(json.dumps(panel._plain_transcript(_snap(self.video))))
        e = plain["entries"][0]
        self.assertEqual([a[0] for a in e["actions"]], ["Play", "Show in Finder"])
        n = self.notice_from(e)
        self.assertEqual([b.text() for b in n.buttons], ["Play", "Show in Finder"])
        fn = n.spec[2][0][1]
        self.assertEqual((fn.kind, fn.path), ("open", self.video))

    def test_chat_in_the_file_keeps_them(self):
        tr = json.loads(json.dumps(ps.serialize_transcript(_snap(self.video))))
        e = ps.unpack_chat({"transcript": tr, "files": []},
                           os.path.join(self.tmp, "ws"))["entries"][0]
        n = self.notice_from(e)
        self.assertEqual([b.text() for b in n.buttons], ["Play", "Show in Finder"])

    def test_sabotage_lambdas_are_still_dropped(self):
        snap = _snap(self.video)
        snap["entries"][0]["actions"] = [("Play", lambda: None)]
        e = panel._plain_transcript(snap)["entries"][0]
        self.assertEqual(e["actions"], [])

    def test_data_never_opens_an_app_or_script(self):
        for p in ("/Applications/Evil.app", "/tmp/x.command", "/tmp/x.sh",
                  "relative.mp4"):
            self.assertIsNone(panel.FileAction.from_data(
                {"file_action": "open", "path": p}), p)
        self.assertIsNotNone(panel.FileAction.from_data(
            {"file_action": "reveal", "path": "/tmp/x.command"}))
        self.assertIsNone(panel.FileAction.from_data(
            {"file_action": "rm", "path": self.video}))


if __name__ == "__main__":
    unittest.main()
