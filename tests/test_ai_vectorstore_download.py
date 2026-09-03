import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from qualcoder import ai_vectorstore
from qualcoder.ai_vectorstore import AiVectorstore
from qualcoder.ai_vectorstore import _EmbeddingModelDownloadCancelled
from qualcoder.ai_vectorstore import _create_huggingface_progress_class


class RecordingSignal:
    """Small signal substitute that records emitted progress messages."""

    def __init__(self):
        self.messages = []

    def emit(self, message: str) -> None:
        self.messages.append(message)


class TestEmbeddingModelDownload(TestCase):

    def setUp(self):
        self.store = object.__new__(AiVectorstore)
        self.store.download_model_cancel = False
        self.messages = []
        self.store._ui_relay = SimpleNamespace(
            post_message=self.messages.append,
        )
        self.signal = RecordingSignal()
        self.signals = SimpleNamespace(progress=self.signal)

    def test_huggingface_progress_is_forwarded_to_qt_signal(self):
        progress_class = _create_huggingface_progress_class(
            self.store, self.signals, "folder/model.bin"
        )
        progress = progress_class(total=100, initial=20, disable=True)

        progress.update(30)
        progress.update(0)
        progress.close()

        self.assertEqual(["model.bin: 50%"], self.signal.messages)

    def test_huggingface_progress_honours_cancellation(self):
        progress_class = _create_huggingface_progress_class(
            self.store, self.signals, "model.bin"
        )
        progress = progress_class(total=100, disable=True)
        self.store.download_model_cancel = True

        with self.assertRaises(_EmbeddingModelDownloadCancelled):
            progress.update(1)

        progress.close()

    def test_huggingface_progress_handles_unknown_download_size(self):
        progress_class = _create_huggingface_progress_class(
            self.store, self.signals, "metadata.json"
        )
        progress = progress_class(total=None, disable=True)

        progress.update(10)
        progress.update(10)
        progress.close()

        self.assertEqual(["metadata.json: 50%"], self.signal.messages)

    def test_download_uses_legacy_hub_progress_bridge_and_restores_it(self):
        self.store.model_name = "organization/model"
        self.store.model_folder = "model-folder"
        original_progress_class = ai_vectorstore._HUGGINGFACE_TQDM_MODULE.tqdm

        def fake_download(**kwargs):
            progress = ai_vectorstore._HUGGINGFACE_TQDM_MODULE.tqdm(
                total=100, disable=True
            )
            progress.update(25)
            progress.close()
            self.assertEqual("organization/model", kwargs["repo_id"])
            self.assertEqual("model.bin", kwargs["filename"])
            self.assertEqual("model-folder", kwargs["local_dir"])
            return "downloaded-model"

        with patch.object(ai_vectorstore, "_HF_DOWNLOAD_SUPPORTS_TQDM_CLASS", False), \
                patch.object(ai_vectorstore, "hf_hub_download", side_effect=fake_download):
            result = self.store._download_model_file("model.bin", self.signals)

        self.assertEqual("downloaded-model", result)
        self.assertEqual(["model.bin: 25%"], self.signal.messages)
        self.assertIs(
            original_progress_class, ai_vectorstore._HUGGINGFACE_TQDM_MODULE.tqdm
        )

    def test_download_passes_progress_class_to_newer_hub_versions(self):
        self.store.model_name = "organization/model"
        self.store.model_folder = "model-folder"

        def fake_download(**kwargs):
            progress_class = kwargs.pop("tqdm_class")
            progress = progress_class(total=100, disable=True)
            progress.update(75)
            progress.close()
            return "downloaded-model"

        with patch.object(ai_vectorstore, "_HF_DOWNLOAD_SUPPORTS_TQDM_CLASS", True), \
                patch.object(ai_vectorstore, "hf_hub_download", side_effect=fake_download):
            result = self.store._download_model_file("model.bin", self.signals)

        self.assertEqual("downloaded-model", result)
        self.assertEqual(["model.bin: 75%"], self.signal.messages)

    def test_download_embedding_model_downloads_only_missing_files(self):
        with TemporaryDirectory() as temp_dir:
            self.store.model_folder = temp_dir
            self.store.model_files = ["present.json", "nested/missing.json"]
            self.store.download_model_running = False
            Path(temp_dir, "present.json").write_text("present", encoding="utf-8")
            downloaded = []

            def fake_download(file_name: str, signals) -> str:
                downloaded.append(file_name)
                destination = Path(temp_dir, *file_name.split("/"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("downloaded", encoding="utf-8")
                return os.fspath(destination)

            self.store._download_model_file = fake_download
            self.store._download_embedding_model(self.signals)

            self.assertEqual(["nested/missing.json"], downloaded)
            self.assertTrue(self.store.embedding_model_is_cached())
            self.assertEqual(
                ["missing.json: 0%", "missing.json: 100%"], self.signal.messages
            )

    def test_download_worker_preserves_an_early_cancellation(self):
        with TemporaryDirectory() as temp_dir:
            self.store.model_folder = temp_dir
            self.store.model_files = ["missing.json"]
            self.store.download_model_cancel = True
            self.store._download_model_file = lambda *args: self.fail(
                "Download started after cancellation"
            )

            self.store._download_embedding_model(self.signals)

            self.assertTrue(self.store.download_model_cancel)
            self.assertEqual([], self.signal.messages)

    def test_failed_download_is_not_reported_as_successful(self):
        self.store.app = SimpleNamespace(settings={"ai_enable": "True"})
        self.store.download_model_running = True
        self.store.embedding_model_is_cached = lambda: False

        with patch.object(ai_vectorstore, "_", lambda text: text, create=True):
            self.store._download_embedding_model_finished()

        self.assertFalse(self.store.download_model_running)
        self.assertEqual("False", self.store.app.settings["ai_enable"])
        self.assertIn("Could not download", self.messages[0])
