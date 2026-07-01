from rest_framework.renderers import JSONRenderer
import json

class EnvelopeRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get('response') if renderer_context else None
        status_code = response.status_code if response else 200
        success = status_code < 400

        if success:
            envelope = {'success': True, 'data': data}
            if isinstance(data, dict) and 'count' in data:
                envelope['meta'] = {
                    'count': data.pop('count'),
                    'next': data.pop('next', None),
                    'previous': data.pop('previous', None),
                }
                envelope['data'] = data.get('results', data)
        else:
            envelope = {'success': False, 'error': data}

        return super().render(envelope, accepted_media_type, renderer_context)
