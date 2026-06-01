# api/utils.py
from rest_framework.response import Response

def success_response(data=None, message="成功", status=200):
    return Response({
        'success': True,
        'message': message,
        'data': data
    }, status=status)

def error_response(message="失败", status=400, errors=None):
    result = {
        'success': False,
        'message': message,
    }
    if errors:
        result['errors'] = errors
    return Response(result, status=status)