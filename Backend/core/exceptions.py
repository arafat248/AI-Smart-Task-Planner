from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            'success': False,
            'error': {
                'code': response.status_code,
                'detail': response.data,
            },
        }
    else:
        logger.exception('Unhandled exception in view: %s', context.get('view'))
        response = Response(
            {'success': False, 'error': {'code': 500, 'detail': 'Internal server error'}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
