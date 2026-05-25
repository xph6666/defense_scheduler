"""响应信封中间件 - 将所有 JSON 响应包装为 { success, data, message } 格式"""

from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse, StreamingHttpResponse, FileResponse
import json


class ResponseEnvelopeMiddleware(MiddlewareMixin):
    """将 DRF 响应包装为前端期望的信封格式"""

    def process_response(self, request, response):
        # 跳过非 API 请求
        if not request.path.startswith('/api/'):
            return response

        # 跳过文件下载响应（Excel 导出等）
        if isinstance(response, (StreamingHttpResponse, FileResponse)):
            return response

        content_type = response.get('Content-Type', '')
        if 'application/json' not in content_type:
            return response

        try:
            data = json.loads(response.content.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return response

        # 已经是信封格式则跳过
        if isinstance(data, dict) and 'success' in data and 'data' in data:
            return response

        # 根据状态码判断成功/失败
        if 200 <= response.status_code < 300:
            envelope = {
                'success': True,
                'data': data,
                'message': 'ok'
            }
        else:
            # 提取错误信息
            message = '请求失败'
            if isinstance(data, dict):
                message = data.get('error') or data.get('message') or data.get('detail') or '请求失败'
            elif isinstance(data, list) and data:
                message = str(data[0])
            envelope = {
                'success': False,
                'data': None,
                'message': message
            }

        response.content = json.dumps(envelope, ensure_ascii=False).encode('utf-8')
        response['Content-Length'] = len(response.content)
        # 成功的信封始终返回 200
        if 200 <= response.status_code < 300:
            pass
        else:
            response.status_code = response.status_code

        return response
