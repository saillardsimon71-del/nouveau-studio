"""Pure local tests for the official MiniMax H3 API payload. No network or spend."""
import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts/production/minimax_h3_official_api.py"
spec = importlib.util.spec_from_file_location("minimax_h3_official_api", PATH)
h3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3)


class MiniMaxH3PayloadTests(unittest.TestCase):
    def test_text_only_ratio(self):
        p = h3.build_payload(prompt="Luxury lighting.", duration=5, resolution="2K", ratio="9:16")
        self.assertEqual(p["model"], "MiniMax-H3")
        self.assertEqual(p["ratio"], "9:16")
        self.assertEqual(len(p["content"]), 1)

    def test_authentic_first_frame_schema(self):
        p = h3.build_payload(prompt="Slow portrait.", image_url="https://images.pexels.com/photos/7814730/pexels-photo-7814730.jpeg")
        self.assertEqual(p["ratio"], "adaptive")
        self.assertEqual(p["content"][1]["role"], "first_frame")
        self.assertEqual(p["content"][1]["image_url"]["url"].split("/")[2], "images.pexels.com")

    def test_invalid_resolution_blocked(self):
        with self.assertRaises(ValueError):
            h3.build_payload(prompt="Action.", resolution="2K", model="MiniMax-H3-Highspeed")

    def test_localhost_blocked(self):
        with self.assertRaises(ValueError):
            h3.build_payload(prompt="Test", image_url="https://localhost/private.png")

    def test_no_api_request_for_preflight(self):
        self.assertEqual(h3.main(["--mode", "preflight", "--prompt", "Studio fashion"]), 0)

    def test_render_requires_spend_consent(self):
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            h3.main(["--mode", "render", "--prompt", "Studio fashion"])


if __name__ == "__main__":
    unittest.main()
