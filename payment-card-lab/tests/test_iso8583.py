import unittest

from pailab.iso8583 import DE, MTI, Iso8583Message


class TestIso8583(unittest.TestCase):
    def test_build_and_serialize(self):
        m = Iso8583Message.request(MTI.AUTH_REQ)
        m.set("PAN", "4532191234567890")
        m.set("AMOUNT", 12345)
        m.set("CURRENCY", "MXN")
        wire = m.to_wire()
        m2 = Iso8583Message.from_wire(wire)
        self.assertEqual(m2.mti, MTI.AUTH_REQ)
        self.assertEqual(m2.get("PAN"), "4532191234567890")
        self.assertEqual(m2.get("AMOUNT"), "12345")

    def test_reply_keeps_de_and_swaps_mti(self):
        m = Iso8583Message.request(MTI.AUTH_REQ)
        m.set("PAN", "4111111111111111")
        m.set("AMOUNT", 100)
        r = m.reply("00", auth_code="123456")
        self.assertEqual(r.mti, MTI.AUTH_RESP)
        self.assertEqual(r.get("RESPONSE_CODE"), "00")
        self.assertEqual(r.get("AUTH_CODE"), "123456")
        self.assertEqual(r.get("PAN"), "4111111111111111")

    def test_repr_masks_pan(self):
        m = Iso8583Message.request(MTI.AUTH_REQ)
        m.set("PAN", "4111111111111111")
        s = repr(m)
        self.assertIn("411111******1111", s)
        self.assertNotIn("4111111111111111", s)


if __name__ == "__main__":
    unittest.main()
