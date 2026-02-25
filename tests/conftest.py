# conftest.py - Shared test fixtures
# No sys.modules mocking here. Each test file should use its own mocking strategy
# to avoid cross-test pollution.
#
# Files that test KernelManager internals use unittest.mock.patch for main.DOCKER_CLIENT
# Files that use FastAPI TestClient import real docker and main modules
