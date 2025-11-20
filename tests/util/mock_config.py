from cloudbot.config import Config


class MockConfig(Config):
    def load_config(self) -> None:
        self._api_keys.clear()
