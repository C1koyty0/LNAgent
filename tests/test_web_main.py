import os
import unittest
from unittest.mock import patch

import web_main


class WebMainArgsTest(unittest.TestCase):
    def test_parse_args_accepts_host_and_port(self) -> None:
        args = web_main.parse_args(["--host", "0.0.0.0", "--port", "9001"])

        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9001)

    def test_parse_args_uses_environment_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LNAGENT_WEB_HOST": "0.0.0.0",
                "LNAGENT_WEB_PORT": "9100",
            },
            clear=False,
        ):
            args = web_main.parse_args([])

        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9100)


if __name__ == "__main__":
    unittest.main()
