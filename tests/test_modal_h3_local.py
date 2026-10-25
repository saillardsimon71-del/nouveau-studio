"""Zero GPU / zero network contract tests for native H3 Modal worker."""
import base64
import importlib.util
from pathlib import Path
import sys
import types
import unittest


class FakeImage:
    @staticmethod
    def debian_slim(**kwargs):
        return FakeImage()

    def pip_install(self, *args, **kwargs):
        return self

    def apt_install(self, *args, **kwargs):
        return self

    def run_commands(self, *args, **kwargs):
        return self


class FakeApp:
    def __init__(self, *args, **kwargs):
        pass

    def function(self, *args, **kwargs):
        return lambda f: f

    def local_entrypoint(self, *args, **kwargs):
        return lambda f: f


class FakeVolume:
    @classmethod
    def from_name(cls, *args, **kwargs):
        return cls()


modal = types.ModuleType("modal")
modal.Image = FakeImage
modal.App = FakeApp
modal.Volume = FakeVolume
path = Path(__file__).resolve().parents[1] / "deploy" / "modal_h3_worker.py"
spec = importlib.util.spec_from_file_location("h3_worker_for_tests", path)
h3 = importlib.util.module_from_spec(spec)
from unittest.mock import patch

with patch.dict(sys.modules, {"modal": modal}):
    spec.loader.exec_module(h3)


class H3NativeContractTests(unittest.TestCase):
    def test_four_compact_model_weights(self):
        self.assertEqual(len(h3.FILES), 4)
        self.assertIn("fl2va_pruned_int8_convrot", h3.FILES["diffusion_models"])
        self.assertIn("nvfp4_awq", h3.FILES["text_encoders"])

    def test_duration_and_frame_grid(self):
        d = h3.validate({"prompt": "Luxury fashion film", "duration_s": 5, "aspect_ratio": "9:16"})
        self.assertEqual((d["width"], d["height"]), (768, 1344))
        self.assertEqual(d["frames"] % 17, 5)

    def test_short_clips_refused(self):
        with self.assertRaises(ValueError):
            h3.validate({"prompt": "Test", "duration_s": 3})

    def test_empty_prompt_refused(self):
        with self.assertRaises(ValueError):
            h3.validate({"prompt": "", "duration_s": 5})

    def test_real_reference_png_contract(self):
        one_png = b"\x89PNG\r\n\x1a\n" + b"0" * 30
        data = h3.validate({"prompt": "Portrait", "duration_s": 5,
                            "image_png_base64": base64.b64encode(one_png).decode()})
        self.assertTrue(data["image_png_base64"])
        with self.assertRaises(ValueError):
            h3.validate({"prompt": "Portrait", "duration_s": 5,
                         "image_png_base64": base64.b64encode(b"not-a-png").decode()})

    def test_h3_i2v_native_graph(self):
        d = h3.validate({"prompt": "Model adjusts jacket collar.", "duration_s": 5})
        g = h3.build_graph(d, "real_photo.png")
        self.assertEqual(g["104"]["class_type"], "MiniMaxH3ImageToVideo")
        self.assertEqual(g["104"]["inputs"]["first_frame"], ["1", 0])
        self.assertEqual(g["91"]["class_type"], "CreateVideo")
        self.assertEqual(g["91"]["inputs"]["audio"], ["23", 0])
        self.assertEqual(g["92"]["class_type"], "SaveVideo")
        self.assertEqual(g["14"]["inputs"]["latent_image"], ["104", 1])

    def test_no_reference_for_text_to_video(self):
        d = h3.validate({"prompt": "Silk over marble", "duration_s": 4})
        g = h3.build_graph(d)
        self.assertNotIn("1", g)
        self.assertNotIn("first_frame", g["104"]["inputs"])


if __name__ == "__main__":
    unittest.main()
