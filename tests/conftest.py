import sys
from unittest.mock import MagicMock

# Define common exception classes for Docker
class MockDockerError(Exception): pass
class MockAPIError(MockDockerError): pass
class MockNotFound(MockDockerError):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response

# Mock docker module
mock_docker = MagicMock()
mock_docker.errors.APIError = MockAPIError
mock_docker.errors.NotFound = MockNotFound

# Mock docker.errors sub-module
mock_errors = MagicMock()
mock_errors.APIError = MockAPIError
mock_errors.NotFound = MockNotFound

sys.modules["docker"] = mock_docker
sys.modules["docker.errors"] = mock_errors

# Define common exception classes for FastAPI
class MockHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        self.status_code = status_code
        self.detail = detail

# Mock fastapi
mock_fastapi = MagicMock()
mock_fastapi.HTTPException = MockHTTPException
sys.modules["fastapi"] = mock_fastapi
sys.modules["fastapi.security"] = MagicMock()
sys.modules["fastapi.responses"] = MagicMock()

# Mock pydantic
class MockBaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    def dict(self):
        return self.__dict__

mock_pydantic = MagicMock()
mock_pydantic.BaseModel = MockBaseModel
sys.modules["pydantic"] = mock_pydantic
