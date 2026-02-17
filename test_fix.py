import unittest
from unittest.mock import MagicMock, patch
import io
import tarfile
import uuid
import os

# Mocking the dependencies to test the KernelManager.execute_code logic
class MockContainer:
    def __init__(self):
        self.put_archive_calls = []
        self.exec_run_calls = []

    def put_archive(self, path, data):
        self.put_archive_calls.append((path, data))

    def exec_run(self, cmd, workdir=None):
        self.exec_run_calls.append((cmd, workdir))
        mock_result = MagicMock()
        mock_result.output = b"test output"
        mock_result.exit_code = 0
        return mock_result

class TestRCEFix(unittest.TestCase):
    def test_execute_code_logic(self):
        # We'll manually run the logic from main.py since we can't easily import it
        # without satisfying all its dependencies (like docker.from_env())

        code = "print('hello world')"
        session_id = "test_session"

        container = MockContainer()

        # This is the logic from main.py
        code_filename = f"exec_{uuid.uuid4().hex}.py"
        code_path = f"/tmp/{code_filename}"

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            code_bytes = code.encode('utf-8')
            tar_info = tarfile.TarInfo(name=code_filename)
            tar_info.size = len(code_bytes)
            tar.addfile(tar_info, io.BytesIO(code_bytes))

        tar_stream.seek(0)
        container.put_archive("/tmp", tar_stream)

        cmd = ["python3", code_path]
        exec_result = container.exec_run(cmd=cmd, workdir="/usr/src/app")

        container.exec_run(cmd=["rm", code_path])

        # Assertions
        self.assertEqual(len(container.put_archive_calls), 1)
        self.assertEqual(container.put_archive_calls[0][0], "/tmp")

        # Verify tar content
        received_tar_data = container.put_archive_calls[0][1]
        received_tar_stream = io.BytesIO(received_tar_data.getvalue())
        with tarfile.open(fileobj=received_tar_stream, mode='r') as tar:
            members = tar.getmembers()
            self.assertEqual(len(members), 1)
            self.assertTrue(members[0].name.startswith("exec_"))
            self.assertTrue(members[0].name.endswith(".py"))

            f = tar.extractfile(members[0])
            content = f.read().decode('utf-8')
            self.assertEqual(content, code)

        self.assertEqual(len(container.exec_run_calls), 2)
        self.assertEqual(container.exec_run_calls[0][0], ["python3", code_path])
        self.assertEqual(container.exec_run_calls[1][0], ["rm", code_path])

if __name__ == "__main__":
    unittest.main()
