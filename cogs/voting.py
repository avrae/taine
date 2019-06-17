from discord.ext import commands

import constants
from lib.misc import ContextProxy
from lib.reports import DOWNVOTE_REACTION, Report, ReportException, UPVOTE_REACTION


class Voting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, event):
        if not event.guild_id:
            return

        msg_id = event.message_id
        server = self.bot.get_guild(event.guild_id)
        member = server.get_member(event.user_id)
        emoji = event.emoji

        await self.handle_reaction(msg_id, member, emoji)

    async def handle_reaction(self, msg_id, member, emoji):
        if emoji.name not in (UPVOTE_REACTION, DOWNVOTE_REACTION):
            return

        try:
            report = Report.from_message_id(msg_id)
        except ReportException:
            return

        if not report.report_id.startswith('AFR'):
            return
        if member.bot:
            return

        if member.id == constants.OWNER_ID:
            if emoji.name == UPVOTE_REACTION:
                await report.force_accept(ContextProxy(self.bot))
            else:
                print(f"Force denying {report.title}")
                await report.force_deny(ContextProxy(self.bot))
                report.commit()
                return
        else:
            try:
                if emoji.name == UPVOTE_REACTION:
                    await report.upvote(member.id, '', ContextProxy(self.bot))
                else:
                    await report.downvote(member.id, '', ContextProxy(self.bot))
            except ReportException as e:
                await self.bot.send_message(member, str(e))
        if member.id not in report.subscribers:
            report.subscribers.append(member.id)
        report.commit()
        await report.update(ContextProxy(self.bot))


def setup(bot):
    bot.add_cog(Voting(bot))
