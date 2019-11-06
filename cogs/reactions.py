import discord
from discord.ext import commands

import constants
from lib.misc import ContextProxy
from lib.reports import DOWNVOTE_REACTION, Report, ReportException, UPVOTE_REACTION

README_MSG_ID = 590642451266535461
BUG_HUNTER_REACTION_ID = 454031039375867925
BUG_HUNTER_ROLE_ID = 469137394742853642
ACCEPT_REACTION_ID = 434140566834511872
ACCEPT_ROLE_ID = 641756218955792394
NO_REPORTS_ROLE_ID = 513457946366312478


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
        if msg_id == README_MSG_ID:
            if emoji.id == BUG_HUNTER_REACTION_ID:
                return await self.toggle_role(member, id=BUG_HUNTER_ROLE_ID)
            elif emoji.id == ACCEPT_REACTION_ID:
                return await self.toggle_role(member, id=ACCEPT_ROLE_ID)

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

    @staticmethod
    async def toggle_role(member, **kwargs):
        if NO_REPORTS_ROLE_ID in [r.id for r in member.roles]:  # this member is not allowed to self-assign
            return
        role = discord.utils.get(member.guild.roles, **kwargs)
        if role in member.roles:
            await member.remove_roles(role)
            await member.send(f"Okay! You no longer have {role.name}.")
        else:
            await member.add_roles(role)
            await member.send(f"Okay! You now have {role.name}.")


def setup(bot):
    bot.add_cog(Reactions(bot))
