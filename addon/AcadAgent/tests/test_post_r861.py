"""R861 Post to atech.dev (post.py): a Showcase post as the signed-in
account.

  TestPublish  the create call the site's API takes, each file uploaded
               to the post as multipart with its type and the bearer, files
               the site would refuse kept back with why, a 401
  TestDialog   offscreen: signed out offers Sign in, the share image and
               latest video ticked, "Built by" from the account, Post
               opens /community
No network: a fake account and a fake opener for the uploads.
"""
import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from acadagent import post, shop  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


class FakeAccount:
    def __init__(self, signed=True, create=(201, {"id": "post-1"})):
        self.signed, self.create = signed, create
        self.requests = []
        self.opener = None
        self.user = {"id": "u1", "email": "maker@example.com", "name": "David"} if signed else None

    def signed_in(self):
        return self.signed

    def request(self, method, path, body=None):
        self.requests.append((method, path, body))
        return self.create

    def token(self):
        return "tok"


class Uploads:
    """The opener for the media POSTs: records them, answers 201."""

    def __init__(self, status=201):
        self.status, self.seen = status, []

    def __call__(self, req, timeout):
        self.seen.append(req)
        status = self.status

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"name": "x.png", "type": "image"}).encode()
        r = R()
        r.status = status
        return r


def tmpfile(name, data):
    d = tempfile.mkdtemp(prefix="r861_")
    p = os.path.join(d, name)
    with open(p, "wb") as fh:
        fh.write(data)
    return p


class TestPublish(unittest.TestCase):
    def test_creates_then_uploads(self):
        acct, up = FakeAccount(), Uploads()
        pic = tmpfile("Rover share.png", PNG)
        res = post.publish("Rover", post.compose_body("It drives.", "David"), "Robotics",
                           [pic], acct=acct, opener=up)
        self.assertEqual(acct.requests, [("POST", "/api/community/posts", {
            "title": "Rover", "body": "It drives.\n\nBuilt by: David", "category": "Robotics"})])
        self.assertEqual((res["ok"], res["id"], res["uploaded"], res["failed"]), (True, "post-1", 1, []))
        req = up.seen[0]
        self.assertEqual(req.full_url, shop.SITE + "/api/community/posts/post-1/media")
        self.assertEqual(req.get_header("Authorization"), "Bearer tok")
        self.assertIn(b'name="file"; filename="Rover share.png"', req.data)
        self.assertIn(b"Content-Type: image/png", req.data)

    def test_keeps_back_what_the_site_refuses(self):
        acct, up = FakeAccount(), Uploads()
        big = tmpfile("long.mp4", b"\0")
        os.truncate(big, post.MAX_FILE_BYTES + 1)
        doc = tmpfile("notes.pdf", b"%PDF")
        res = post.publish("Rover", "", "", [big, doc], acct=acct, opener=up)
        self.assertEqual(up.seen, [])
        self.assertEqual([os.path.basename(p) for p, _ in res["failed"]], ["long.mp4", "notes.pdf"])
        self.assertIn("25 MB", res["failed"][0][1])

    def test_signed_out(self):
        res = post.publish("Rover", "", "", [], acct=FakeAccount(create=(401, {})))
        self.assertFalse(res["ok"])
        self.assertIn("Sign in", res["message"])

    def test_site_refusal_is_shown(self):
        res = post.publish("Rover", "", "", [], acct=FakeAccount(
            create=(422, {"detail": {"message": "a post needs a title."}})))
        self.assertEqual(res["message"], "a post needs a title.")

    def test_latest_video(self):
        from acadagent import promo_video
        d = tempfile.mkdtemp(prefix="r861v_")
        old = os.path.join(d, "Rover assembly 2026-11-01 at 10.00.00.mp4")
        new = os.path.join(d, "Rover assembly 2026-11-06 at 10.00.00.mp4")
        other = os.path.join(d, "Crane assembly 2026-11-07 at 10.00.00.mp4")
        for i, p in enumerate((old, new, other)):
            open(p, "wb").close()
            os.utime(p, (1000 + i, 1000 + i))
        real = promo_video.video_dir
        promo_video.video_dir = lambda: d
        try:
            self.assertEqual(post.latest_video("Rover"), new)
            self.assertIsNone(post.latest_video("Boat"))
        finally:
            promo_video.video_dir = real


try:
    from PySide6 import QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except Exception:                                         # noqa: BLE001
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestDialog(unittest.TestCase):
    def make(self, acct):
        self.opened, self.published = [], []
        self.pic = tmpfile("Rover share.png", PNG)
        self.vid = tmpfile("Rover assembly.mp4", b"\0\0\0\x18ftypmp42")

        def publisher(**kw):
            self.published.append(kw)
            return {"ok": True, "id": "post-1", "uploaded": len(kw["files"]), "failed": [],
                    "message": ""}
        return post.PostDialog(None, lambda: types.SimpleNamespace(Label="Rover"), acct=acct,
                               opener=self.opened.append, background=False,
                               share_fn=lambda doc: self.pic, video_fn=lambda label: self.vid,
                               publisher=publisher)

    def test_signed_out_offers_sign_in(self):
        d = self.make(FakeAccount(signed=False))
        self.assertFalse(d.sign_in.isHidden())
        self.assertFalse(d.post.isEnabled())
        self.assertIn("Sign in with your Atech account", d.who.text())

    def test_posts_with_the_picture_and_video(self):
        d = self.make(FakeAccount())
        self.assertTrue(d.sign_in.isHidden())
        self.assertEqual(d.title.text(), "Rover")
        self.assertEqual(d.by.text(), "David")
        self.assertEqual(d.chosen(), [self.pic, self.vid])
        d.text.setPlainText("It drives.")
        d.category.setCurrentIndex(1)
        d.post.click()
        kw = self.published[0]
        self.assertEqual((kw["title"], kw["body"], kw["category"], kw["files"]),
                         ("Rover", "It drives.\n\nBuilt by: David", "Gadgets", [self.pic, self.vid]))
        self.assertEqual(self.opened, [post.COMMUNITY_URL])
        self.assertIn("Posted on atech.dev/community with 2 files", d.status.text())
        self.assertEqual(d.post.text(), "Posted")

    def test_untick_and_no_title(self):
        from PySide6 import QtCore
        d = self.make(FakeAccount())
        d.media.item(1).setCheckState(QtCore.Qt.Unchecked)
        self.assertEqual(d.chosen(), [self.pic])
        d.title.setText("  ")
        self.assertFalse(d.post.isEnabled())


if __name__ == "__main__":
    unittest.main()
