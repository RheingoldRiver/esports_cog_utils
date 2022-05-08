class BayesBadRequestException(Exception):
    def __init__(self, reason):
        super().__init__(reason)


class BayesBadAPIKeyException(Exception):
    pass


class BayesUnexpectedResponseException(KeyError):
    def __init__(self, service, response):
        super().__init__()
        self.service = service
        self.response = response


class BayesRateLimitException(Exception):
    pass
