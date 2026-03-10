import os
import tempfile
import unittest

from cryptobot.config import BotSettings


class ConfigTests(unittest.TestCase):
    def test_loads_from_dotenv(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("BOT_SYMBOL=ETH/USDT\nBOT_TARGET_VOL=0.03\n")
            path = f.name
        try:
            settings = BotSettings.from_env(path)
            self.assertEqual(settings.symbol, "ETH/USDT")
            self.assertAlmostEqual(settings.target_volatility, 0.03)
        finally:
            os.remove(path)

    def test_mysql_enabled(self) -> None:
        settings = BotSettings(
            mysql_host="127.0.0.1",
            mysql_database="cryptobot",
            mysql_user="u",
            mysql_password="p",
        )
        self.assertTrue(settings.mysql_enabled)


if __name__ == "__main__":
    unittest.main()
