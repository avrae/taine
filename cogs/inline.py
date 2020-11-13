import re

from discord.ext import commands

import constants
from lib.reports import Report, ReportException

REPORT_ID_RE = re.compile(r'#(\w{3}-\d{3,})')  # e.g. #AVR-001, #AFR-120
ISSUE_NUM_RE = re.compile(r'##(\d+)')  # e.g. ##1127, ##100


class Inline(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        for match in REPORT_ID_RE.finditer(message.content):
            try:
                report = Report.from_id(match.group(1))
            except ReportException:
                return
            await self.send_report(message.channel, report)

        for match in ISSUE_NUM_RE.finditer(message.content):
            try:
                report = Report.from_github(constants.DEFAULT_REPO, int(match.group(1)))
            except ReportException:
                return
            await self.send_report(message.channel, report)

    @staticmethod
    async def send_report(channel, report):
        embed = report.get_embed()
        embed.set_footer()  # clear it - cannot vote with reactions in inline messages
        embed.description = report.attachments[0].message
        await channel.send(embed=embed)


def setup(bot):
    bot.add_cog(Inline(bot))
