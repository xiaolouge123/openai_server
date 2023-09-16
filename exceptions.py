class OpenaiApiException(Exception):
    """Base class for exceptions in this module."""

    def __init__(self, *args: object, **kwargs) -> None:
        super().__init__(*args)
        self.msg = kwargs.pop("msg", None)
        self.status_code = kwargs.pop("status_code", None)

    def __str__(self) -> str:
        return (
            "openai api error: " + self.msg + " status_code: " + str(self.status_code)
        )


class NoValidKey(Exception):
    def __init__(self, *args: object, **kwargs) -> None:
        super().__init__(*args)
        self.msg = kwargs.pop("msg", None)
        self.status_code = kwargs.pop("status_code", None)

    def __str__(self) -> str:
        return "No valid key in keypool: " + self.msg
