import discord
from discord.ext import commands

import constants
from lib.misc import ContextProxy
from lib.reports import DOWNVOTE_REACTION, Report, ReportException, UPVOTE_REACTION

BUG_HUNTER_MSG_ID = 590642451266535461
BUG_HUNTER_REACTION_ID = 454031039375867925
BUG_HUNTER_ROLE_ID = 469137394742853642


class Reactions(commands.Cog):
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
        if msg_id == BUG_HUNTER_MSG_ID and emoji.id == BUG_HUNTER_REACTION_ID:
            return await self.handle_bug_hunter(member)

        if emoji.name not in (UPVOTE_REACTION, DOWNVOTE_REACTION):
            return

        try:
            report = Report.from_message_id(msg_id)
        except ReportException:
            return

        if report.is_bug:
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
                await member.send(str(e))
        if member.id not in report.subscribers:
            report.subscribers.append(member.id)
        report.commit()
        await report.update(ContextProxy(self.bot))

    async def handle_bug_hunter(self, member):
        role = discord.utils.get(member.guild.roles, id=BUG_HUNTER_ROLE_ID)
        if role in member.roles:
            await member.remove_roles(role)
        else:
            await member.add_roles(role)


def setup(bot):
    bot.add_cog(Reactions(bot))
