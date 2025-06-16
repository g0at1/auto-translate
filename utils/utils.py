class TypeUtils:

    @staticmethod
    def is_null_or_empty(value, default=None):
        if value is None:
            return default

        if isinstance(value, str) and not value.strip():
            return default

        try:
            if len(value) == 0:
                return default
        except (TypeError, AttributeError):
            pass

        return value
