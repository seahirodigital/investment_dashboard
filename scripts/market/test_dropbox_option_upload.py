import json
import unittest

from dropbox_option_upload import content_hash, upload_option_report


class Response:
    ok = True
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/token"):
            return Response({"access_token": "test-token"})
        return Response({"content_hash": content_hash(kwargs["data"]), "path_display": json.loads(kwargs["headers"]["Dropbox-API-Arg"])["path"]})


class DropboxUploadTest(unittest.TestCase):
    def test_uploads_exact_utf8_to_dated_path(self):
        client = Session()
        env = {"DROPBOX_APP_KEY": "key", "DROPBOX_APP_SECRET": "secret", "DROPBOX_REFRESH_TOKEN": "refresh"}
        upload_option_report("分析結果", "2026-11-13", environ=env, session=client)
        request = client.calls[-1][1]
        args = json.loads(request["headers"]["Dropbox-API-Arg"])
        self.assertTrue(args["path"].endswith("/20261113_option_analysis.md"))
        self.assertEqual(args["mode"], "add")
        self.assertEqual(request["data"], "分析結果".encode("utf-8"))

    def test_missing_credentials_fail(self):
        with self.assertRaises(RuntimeError):
            upload_option_report("分析結果", "2026-11-13", environ={}, session=Session())

    def test_hash_mismatch_fails(self):
        class InvalidHashSession(Session):
            def post(self, url, **kwargs):
                result = super().post(url, **kwargs)
                if url.endswith("/upload"):
                    result.data["content_hash"] = "wrong"
                return result
        env = {"DROPBOX_APP_KEY": "key", "DROPBOX_APP_SECRET": "secret", "DROPBOX_REFRESH_TOKEN": "refresh"}
        with self.assertRaises(RuntimeError):
            upload_option_report("分析結果", "2026-11-13", environ=env, session=InvalidHashSession())


if __name__ == "__main__":
    unittest.main()
