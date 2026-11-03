class FoundryError(Exception):
    status = 400

class ValidationError(FoundryError):
    pass

class NotFound(FoundryError):
    status = 404

class Conflict(FoundryError):
    status = 409

class PermissionDenied(FoundryError):
    status = 403

class ProviderUnavailable(FoundryError):
    status = 503

