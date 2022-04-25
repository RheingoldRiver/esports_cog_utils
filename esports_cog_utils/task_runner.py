from abc import ABCMeta, abstractmethod


class TaskRunner(metaclass=ABCMeta):
    def __init__(self):
        self.warnings = []

    @abstractmethod
    def run(self):
        ...

    async def send_warnings(self, ctx):
        if len(self.warnings) == 0:
            return
        warning_text = '\n  '.join(self.warnings)
        ret = f"**Warnings:**\n{warning_text}"
        await ctx.send(ret)

        # in case we want to reuse the same runner
        self.warnings = []
