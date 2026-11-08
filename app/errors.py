from flask import jsonify


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def bad_request(message, details=None, code="VALIDATION_ERROR"):
    return ApiError(400, code, message, details)


def unauthorized(message="Authentication required", code="UNAUTHENTICATED"):
    return ApiError(401, code, message)


def forbidden(message="You do not have permission to perform this action"):
    return ApiError(403, "FORBIDDEN", message)


def not_found(message="Resource not found"):
    return ApiError(404, "NOT_FOUND", message)


def conflict(message, code="CONFLICT", details=None):
    return ApiError(409, code, message, details)


def unprocessable(message, code="RULE_VIOLATION", details=None):
    return ApiError(422, code, message, details)


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        body = {"error": {"code": err.code, "message": err.message}}
        if err.details is not None:
            body["error"]["details"] = err.details
        return jsonify(body), err.status

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Endpoint not found"}}), 404

    @app.errorhandler(405)
    def handle_405(_):
        return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": "Method not allowed"}}), 405

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        app.logger.exception("Unhandled error: %s", err)
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}}), 500
