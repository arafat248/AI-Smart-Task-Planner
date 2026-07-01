import json
import logging
import traceback
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'message': record.getMessage(),
        }
        if record.exc_info:
            log_data['exception'] = traceback.format_exception(*record.exc_info)
        return json.dumps(log_data)
