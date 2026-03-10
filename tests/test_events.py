import unittest

from cryptobot.nlp.events import _extract_json_object


class EventsTests(unittest.TestCase):
    def test_extracts_wrapped_json(self) -> None:
        text = "Here is output:\n```json\n{\"sentiment\":\"bullish\"}\n```"
        out = _extract_json_object(text)
        self.assertEqual(out, '{"sentiment":"bullish"}')


if __name__ == "__main__":
    unittest.main()
