import unittest
from unittest.mock import patch

from redmagic_auto_sign import Account, RedMagicClient, ensure_signed, run_tasks_for_account


def home_payload(is_registered, score="1040", reward="20"):
    return {
        "status": 200,
        "data": {
            "userInfo": {"nickname": "test", "score": score, "energy": 100},
            "registerData": {
                "isRegister": is_registered,
                "todayEnergy": reward,
                "txt": "sign status",
            },
        },
    }


class RecordingSession:
    def __init__(self):
        self.calls = []

    def post_form(self, url, headers, data, multipart=False):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "data": data,
                "multipart": multipart,
            }
        )
        return 200, '{"status": 200, "msg": "success", "data": {"continueDays": 3}}'


class FakeSignClient:
    def __init__(self, sign_payload=None, verified_home=None):
        self.sign_payload = sign_payload or {
            "status": 200,
            "msg": "success",
            "data": {"continueDays": 3},
        }
        self.verified_home = verified_home or home_payload(1, score="1060")
        self.sign_calls = 0
        self.home_calls = 0

    def sign_in(self, token):
        self.sign_calls += 1
        return self.sign_payload

    def home_index(self, token):
        self.home_calls += 1
        return self.verified_home


class FakeDailyClient(FakeSignClient):
    def __init__(self):
        super().__init__(verified_home=home_payload(0))
        self.lottery_calls = 0

    def access_token_for(self, account):
        return account.access_token

    def launch_prize(self, token):
        self.lottery_calls += 1
        return {
            "status": 200,
            "data": {"prize_desc": "no prize", "surplus_num": 0},
        }


class SignInTests(unittest.TestCase):
    def test_sign_in_posts_points_register(self):
        session = RecordingSession()
        client = RedMagicClient(session)

        with patch("redmagic_auto_sign.now_ms", return_value="123456"):
            response = client.sign_in("test-token")

        self.assertEqual(response["status"], 200)
        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], "https://api-bbs.redmagic.com/points/home/pointsRegister")
        self.assertEqual(call["headers"]["accessToken"], "test-token")
        self.assertEqual(call["data"], {"v": "123456"})
        self.assertTrue(call["multipart"])

    def test_unsigned_account_signs_and_verifies(self):
        client = FakeSignClient()

        lines, verified_home, ok = ensure_signed(client, "test-token", home_payload(0))

        self.assertTrue(ok)
        self.assertEqual(client.sign_calls, 1)
        self.assertEqual(client.home_calls, 1)
        self.assertEqual(verified_home["data"]["userInfo"]["score"], "1060")
        self.assertIn("Sign: completed, reward=20, continueDays=3", lines)

    def test_already_signed_account_does_not_sign_again(self):
        client = FakeSignClient()

        lines, verified_home, ok = ensure_signed(client, "test-token", home_payload(1))

        self.assertTrue(ok)
        self.assertEqual(client.sign_calls, 0)
        self.assertEqual(client.home_calls, 0)
        self.assertEqual(verified_home["data"]["registerData"]["isRegister"], 1)
        self.assertIn("Sign: already signed, sign status", lines)

    def test_sign_request_must_be_verified(self):
        client = FakeSignClient(verified_home=home_payload(0))

        lines, verified_home, ok = ensure_signed(client, "test-token", home_payload(0))

        self.assertFalse(ok)
        self.assertEqual(client.sign_calls, 1)
        self.assertEqual(client.home_calls, 1)
        self.assertEqual(verified_home["data"]["registerData"]["isRegister"], 0)
        self.assertIn("Sign: request succeeded but isRegister=0", lines)

    def test_failed_sign_verification_does_not_skip_lottery(self):
        client = FakeDailyClient()

        with patch.dict(
            "os.environ",
            {
                "REDMAGIC_ENABLE_BOX": "false",
                "REDMAGIC_ENABLE_LOTTERY": "true",
                "REDMAGIC_LOTTERY_TIMES": "1",
            },
        ):
            lines, ok = run_tasks_for_account(
                client,
                Account(name="test", access_token="test-token"),
            )

        self.assertFalse(ok)
        self.assertEqual(client.lottery_calls, 1)
        self.assertIn("Sign: request succeeded but isRegister=0", lines)
        self.assertIn("Lottery #1: no prize, surplus=0", lines)


if __name__ == "__main__":
    unittest.main()
