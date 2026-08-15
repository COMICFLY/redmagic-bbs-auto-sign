import unittest
from unittest.mock import patch

from redmagic_auto_sign import Account, RedMagicClient, run_box_for_account


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
        return 200, '{"status": 200, "msg": "success", "data": []}'


class FakeBoxClient:
    def __init__(self, claim_payload, energy_id="energy-42"):
        self.claim_payload = claim_payload
        self.energy_id = energy_id
        self.claimed_energy_ids = []

    def access_token_for(self, account):
        return account.access_token

    def home_index(self, token):
        return {"status": 200, "data": {"boxWaitingOpen": 1}}

    def open_box(self, token):
        return {
            "status": 200,
            "data": {"energy": 5, "energyId": self.energy_id, "nextOpenTime": 1786134945},
        }

    def claim_energy(self, token, energy_id):
        self.claimed_energy_ids.append(energy_id)
        return self.claim_payload


class BoxClaimTests(unittest.TestCase):
    def test_claim_energy_posts_energy_id(self):
        session = RecordingSession()
        client = RedMagicClient(session)

        with patch("redmagic_auto_sign.now_ms", return_value="123456"):
            response = client.claim_energy("test-token", "energy-42")

        self.assertEqual(response["status"], 200)
        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], "https://api-bbs.redmagic.com/points/home/havingenergy")
        self.assertEqual(call["headers"]["accessToken"], "test-token")
        self.assertEqual(call["data"], {"energyId": "energy-42", "v": "123456"})
        self.assertTrue(call["multipart"])

    def test_box_workflow_claims_energy_after_opening(self):
        client = FakeBoxClient({"status": 200, "msg": "success", "data": []})

        lines, claimed, ok = run_box_for_account(client, Account("test", "test-token"))

        self.assertTrue(claimed)
        self.assertTrue(ok)
        self.assertEqual(client.claimed_energy_ids, ["energy-42"])
        self.assertIn("Box: claimed, +5 energy, nextOpenTime=1786134945", lines)

    def test_box_workflow_marks_claim_failure(self):
        client = FakeBoxClient({"status": 500, "msg": "claim rejected", "data": []})

        lines, claimed, ok = run_box_for_account(client, Account("test", "test-token"))

        self.assertFalse(claimed)
        self.assertFalse(ok)
        self.assertEqual(client.claimed_energy_ids, ["energy-42"])
        self.assertIn(
            "Box: opened, +5 energy, but claim failed: claim rejected",
            "\n".join(lines),
        )

    def test_box_workflow_requires_energy_id(self):
        client = FakeBoxClient({"status": 200, "msg": "success", "data": []}, energy_id=None)

        lines, claimed, ok = run_box_for_account(client, Account("test", "test-token"))

        self.assertFalse(claimed)
        self.assertFalse(ok)
        self.assertEqual(client.claimed_energy_ids, [])
        self.assertIn("openbox returned no energyId", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
