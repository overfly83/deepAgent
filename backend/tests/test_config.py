
from deepagent.config import Settings
from deepagent.logger import get_logger


def test_config_defaults():
    settings = Settings()
    assert settings.recursion_limit == 25
    assert settings.max_concurrency == 5
    assert settings.log_dir == "./logs"

def test_logger_creation(tmp_path):
    # Set log dir to tmp path for testing
    settings = Settings(log_dir=str(tmp_path), debug=True)
    # Patch get_settings to return our test settings
    from unittest.mock import patch
    with patch("deepagent.logger.get_settings", return_value=settings):
        logger = get_logger("test.logger")
        assert logger.name == "test.logger"
        logger.info("Test message")
        
        # Check if file created
        log_file = tmp_path / "backend.log"
        assert log_file.exists()
