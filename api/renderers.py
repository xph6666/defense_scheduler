from rest_framework.renderers import JSONRenderer


class EnvelopeJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return super().render(data, accepted_media_type, renderer_context)

        response = renderer_context.get('response') if renderer_context else None
        status_code = getattr(response, 'status_code', 200)

        if isinstance(data, dict) and 'success' in data and ('data' in data or 'message' in data):
            return super().render(data, accepted_media_type, renderer_context)

        if status_code >= 400:
            message = self._extract_error_message(data)
            payload = {
                'success': False,
                'data': None,
                'message': message,
            }
        else:
            payload = {
                'success': True,
                'data': data,
                'message': 'ok',
            }

        return super().render(payload, accepted_media_type, renderer_context)

    def _extract_error_message(self, data):
        if isinstance(data, dict):
            for key in ('message', 'error', 'detail'):
                if key in data:
                    value = data[key]
                    return value[0] if isinstance(value, list) and value else str(value)
            first_value = next(iter(data.values()), None)
            if isinstance(first_value, list) and first_value:
                return str(first_value[0])
            if first_value is not None:
                return str(first_value)
        if isinstance(data, list) and data:
            return str(data[0])
        return '请求处理失败'
