import json

from discord import Emoji

from lib.misc import ContextProxy
from lib.reports import DOWNVOTE_REACTION, Report, ReportException, UPVOTE_REACTION


class Voting:
    def __init__(self, bot):
        self.bot = bot

    async def on_socket_raw_receive(self, msg):
        if isinstance(msg, bytes):
            return
        msg = json.loads(msg)
        if msg.get('t') != "MESSAGE_REACTION_ADD":
            return

        data = msg['d']
        if not data.get('guild_id'):
            return

        server = self.bot.get_server(data['guild_id'])
        msg_id = data['message_id']
        member = server.get_member(data['user_id'])
        emoji = self.get_emoji(**data.pop('emoji'))
        await self.handle_reaction(msg_id, member, emoji, server)

    async def handle_reaction(self, msg_id, member, emoji, server):
        if emoji not in (UPVOTE_REACTION, DOWNVOTE_REACTION):
            return
        try:
            report = Report.from_message_id(msg_id)
        except ReportException:
            return
        if not report.report_id.startswith('AFR'):
            return
        if member.bot:
            return

        if member.id == '187421759484592128':
            if str(emoji) == UPVOTE_REACTION:
                await report.force_accept(ContextProxy(self.bot))
            else:
                print(f"Force denying {report.title}")
                await report.force_deny(ContextProxy(self.bot))
        else:
            try:
                if str(emoji) == UPVOTE_REACTION:
                    await report.upvote(member.id, '', ContextProxy(self.bot))
                else:
                    await report.downvote(member.id, '', ContextProxy(self.bot))
            except ReportException as e:
                await self.bot.send_message(member, str(e))
        if member.id not in report.subscribers:
            report.subscribers.append(member.id)
        report.commit()
        await report.update(ContextProxy(self.bot))

    def get_emoji(self, **data):
        id_ = data['id']

        if not id_:
            return data['name']

        for server in self.bot.servers:
            for emoji in server.emojis:
                if emoji.id == id_:
                    return emoji
        return Emoji(server=None, **data)


def setup(bot):
    bot.add_cog(Voting(bot))
