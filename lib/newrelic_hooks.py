import os

import newrelic.agent
import newrelic.api.function_trace
from discord.ext import commands


application = newrelic.agent.application()


def hook_all():
    hook_discord()


def hook_discord():
    # The normal New Relic API doesn't work here, let's replace the existing `Command.invoke` function with a version
    # that wraps it in a background task transaction
    async def _command_invoke(self, *args, **kwargs):
        with newrelic.agent.BackgroundTask(application, name='command:%s' % self.name):
            await self._invoke(*args, **kwargs)

    commands.Command._invoke = commands.Command.invoke
    commands.Command.invoke = _command_invoke


if os.getenv('NEW_RELIC_LICENSE_KEY') is not None:
    hook_all()
