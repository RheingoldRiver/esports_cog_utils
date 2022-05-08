class BadRequestException(Exception):
    def __init__(self, reason):
        super().__init__(reason)


class BayesBadAPIKeyException(Exception):
    pass


class BayesUnexpectedResponseError(KeyError):
    def __init__(self, service, response):
        super().__init__()
        self.service = service
        self.response = response
