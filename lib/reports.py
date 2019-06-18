import re

import discord
from cachetools import LRUCache

import constants
from lib.github import GitHubClient
from lib.jsondb import JSONDB

db = JSONDB()  # something something instancing

PRIORITY = {
    -2: "Patch Pending", -1: "Resolved",
    0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low", 5: "P5: Trivial",
    6: "Pending/Other"
}
PRIORITY_LABELS = {
    0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low", 5: "P5: Trivial"
}
VALID_LABELS = (
    'bug', 'duplicate', 'featurereq', 'help wanted', 'invalid', 'wontfix', 'longterm',
    'P0: Critical', 'P1: Very High', 'P2: High', 'P3: Medium', 'P4: Low', 'P5: Trivial', 'stale',
    '+10', '+15'
)
VERI_EMOJI = {
    -2: "\u2b07",  # DOWNVOTE
    -1: "\u274c",  # CROSS MARK
    0: "\u2139",  # INFORMATION SOURCE
    1: "\u2705",  # WHITE HEAVY CHECK MARK
    2: "\u2b06",  # UPVOTE
}
VERI_KEY = {
    -2: "Downvote",
    -1: "Cannot Reproduce",
    0: "Note",
    1: "Can Reproduce",
    2: "Upvote"
}

TRACKER_CHAN = 360855116057673729  # AVRAE DEV "360855116057673729"
GITHUB_BASE = "https://github.com"
UPVOTE_REACTION = "\U0001f44d"
DOWNVOTE_REACTION = "\U0001f44e"
GITHUB_THRESHOLD = 5


class Attachment:
    def __init__(self, author, message: str = '', veri: int = 0):
        self.author = author
        self.message = message
        self.veri = veri

    @classmethod
    def from_dict(cls, attachment):
        return cls(**attachment)

    def to_dict(self):
        return {"author": self.author, "message": self.message, "veri": self.veri}

    @classmethod
    def upvote(cls, author, msg=''):
        return cls(author, msg, 2)

    @classmethod
    def downvote(cls, author, msg=''):
        return cls(author, msg, -2)

    @classmethod
    def cr(cls, author, msg=''):
        return cls(author, msg, 1)

    @classmethod
    def cnr(cls, author, msg=''):
        return cls(author, msg, -1)


class Report:
    message_cache = LRUCache(maxsize=100)
    message_ids = {report.get('message'): id_ for id_, report in db.jget('reports', {}).items() if
                   report.get('message')}

    def __init__(self, reporter, report_id: str, title: str, severity: int, verification: int, attachments: list,
                 message, upvotes: int = 0, downvotes: int = 0, github_issue: int = None, github_repo: str = None,
                 subscribers: list = None, is_bug: bool = True):
        if subscribers is None:
            subscribers = []
        if github_repo is None:
            github_repo = 'avrae/avrae'
        self.reporter = reporter
        self.report_id = report_id
        self.title = title
        self.severity = severity

        self.attachments = attachments
        self.message: int = message
        self.subscribers = subscribers

        self.repo: str = github_repo
        self.github_issue = github_issue

        self.is_bug = is_bug
        self.upvotes = upvotes
        self.downvotes = downvotes

        self.verification = verification

    @classmethod
    async def new(cls, reporter, report_id: str, title: str, attachments: list, is_bug=True, repo=None):
        subscribers = None
        if isinstance(reporter, int):
            subscribers = [reporter]
        inst = cls(reporter, report_id, title, 6, 0, attachments, None, subscribers=subscribers, is_bug=is_bug,
                   github_repo=repo)
        return inst

    @classmethod
    def from_issue(cls, issue):
        attachments = [Attachment(issue['body'], "GitHub")]
        title = issue['title']
        id_match = re.match(r'([A-Z]{3,})(-\d+)?\s', issue['title'])
        if id_match:
            identifier = id_match.group(1)
            report_num = get_next_report_num(identifier)
            report_id = f"{identifier}-{report_num}"
            title = title[len(id_match.group(0)):]
        else:
            report_id = f"AVR-{get_next_report_num('AVR')}"
        return cls("GitHub", report_id, title, 6,
                   # pri is created at -1 for unresolve
                   0, attachments, None, github_issue=issue['number'])

    @classmethod
    def from_dict(cls, report_dict):
        report_dict['attachments'] = [Attachment.from_dict(a) for a in report_dict['attachments']]
        return cls(**report_dict)

    def to_dict(self):
        return {
            'reporter': self.reporter, 'report_id': self.report_id, 'title': self.title, 'severity': self.severity,
            'verification': self.verification, 'upvotes': self.upvotes, 'downvotes': self.downvotes,
            'attachments': [a.to_dict() for a in self.attachments], 'message': self.message,
            'github_issue': self.github_issue, 'github_repo': self.repo, 'subscribers': self.subscribers,
            'is_bug': self.is_bug
        }

    @classmethod
    def from_id(cls, report_id):
        reports = db.jget("reports", {})
        try:
            return cls.from_dict(reports[report_id.upper()])
        except KeyError:
            raise ReportException("Report not found.")

    @classmethod
    def from_message_id(cls, message_id):
        report_id = Report.message_ids.get(message_id)
        if report_id:
            reports = db.jget("reports", {})
            try:
                return cls.from_dict(reports[report_id.upper()])
            except KeyError:
                raise ReportException("Report not found.")
        raise ReportException("Report not found.")

    @classmethod
    def from_github(cls, issue_num):
        reports = db.jget("reports", {})
        try:
            return cls.from_dict(next(r for r in reports.values() if r.get('github_issue') == issue_num))
        except StopIteration:
            raise ReportException("Report not found.")

    def is_open(self):
        return self.severity >= 0

    async def post_to_github(self, ctx):  # todo
        if self.github_issue:
            raise ReportException("Issue is already on GitHub.")
        if self.is_bug:
            labels = ["bug"]
        else:
            labels = ["featurereq"]
        desc = self.get_github_desc(ctx)

        issue = await GitHubClient.get_instance().create_issue(f"{self.report_id} {self.title}", desc, labels)
        self.github_issue = issue.number

    async def setup_message(self, bot):
        report_message = await bot.get_channel(constants.TRACKER_CHAN).send(embed=self.get_embed())
        self.message = report_message.id
        Report.message_ids[report_message.id] = self.report_id
        if not self.is_bug:
            await report_message.add_reaction(UPVOTE_REACTION)
            await report_message.add_reaction(DOWNVOTE_REACTION)

    def commit(self):
        reports = db.jget("reports", {})
        reports[self.report_id] = self.to_dict()
        db.jset("reports", reports)

    def get_embed(self, detailed=False, ctx=None):
        embed = discord.Embed()
        if isinstance(self.reporter, int):
            embed.add_field(name="Added By", value=f"<@{self.reporter}>")
        else:
            embed.add_field(name="Added By", value=self.reporter)
        embed.add_field(name="Priority", value=PRIORITY.get(self.severity, "Unknown"))
        if self.report_id.startswith("AFR"):
            # These statements bought to you by: Dusk-Argentum! Dusk-Argentum: Added Useless Features since 2018!
            embed.colour = 0x00ff00
            embed.add_field(name="Votes", value="\u2b06" + str(self.upvotes) + "` | `\u2b07" + str(self.downvotes))
            vote_msg = "Vote by reacting"
            if not self.github_issue:
                vote_msg += f" | {GITHUB_THRESHOLD} upvotes required to track"
            embed.set_footer(text=f"~report {self.report_id} for details | {vote_msg}")
        elif self.report_id.startswith("WEB"):
            embed.colour = 0x57235c
            embed.add_field(name="Votes", value="\u2b06" + str(self.upvotes) + "` | `\u2b07" + str(self.downvotes),
                            inline=True)
            embed.add_field(name="Verification", value=str(self.verification))
            embed.set_footer(
                text=f"~report {self.report_id} for details | "
                f"Verify with ~cr/~cnr {self.report_id} [note], or vote by reacting")
        else:
            if self.report_id.startswith("AVR"):
                embed.colour = 0xff0000
            elif self.report_id.startswith("DDB"):
                embed.colour = 0xe30910
            embed.add_field(name="Verification", value=str(self.verification))
            embed.set_footer(
                text=f"~report {self.report_id} for details |  Verify with ~cr/~cnr {self.report_id} [note]")

        embed.title = f"`{self.report_id}` {self.title}"
        if len(embed.title) > 256:
            embed.title = f"{embed.title[:250]}..."
        if self.github_issue:
            embed.url = f"{GITHUB_BASE}/{self.repo}/issues/{self.github_issue}"
        embed.description = f"*{len(self.attachments)} notes*"
        if detailed:
            if not ctx:
                raise ValueError("Context not supplied for detailed call.")
            embed.description = f"*{len(self.attachments)} notes, showing first 10*"
            for attachment in self.attachments[:10]:
                if isinstance(attachment.author, int):
                    user = ctx.guild.get_member(attachment.author)
                else:
                    user = attachment.author
                msg = attachment.message[:1020] or "No details."
                embed.add_field(name=f"{VERI_EMOJI.get(attachment.veri, '')} {user}",
                                value=msg)

        return embed

    def get_github_desc(self, ctx):
        msg = self.title
        if self.attachments:
            msg = self.attachments[0]['msg']

        author = next((m for m in ctx.bot.get_all_members() if m.id == self.reporter), None)
        if author:
            desc = f"{msg}\n\n- {author}"
        else:
            desc = msg

        if not self.is_bug:
            i = 0
            for attachment in self.attachments[1:]:
                if attachment.message and i >= GITHUB_THRESHOLD:
                    continue
                i += attachment.veri // 2
                msg = ''
                for line in self.get_attachment_message(ctx, attachment).strip().splitlines():
                    msg += f"> {line}\n"
                desc += f"\n\n{msg}"
            desc += f"\nVotes: +{self.upvotes} / -{self.downvotes}"
        else:
            for attachment in self.attachments[1:]:
                if attachment.message:
                    continue
                msg = ''
                for line in self.get_attachment_message(ctx, attachment).strip().splitlines():
                    msg += f"> {line}\n"
                desc += f"\n\n{msg}"
            desc += f"\nVerification: {self.verification}"

        return desc

    def get_issue_link(self):
        if self.github_issue is None:
            return None
        return f"https://github.com/{self.repo}/issues/{self.github_issue}"

    async def add_attachment(self, ctx, attachment: Attachment, add_to_github=True):  # todo
        self.attachments.append(attachment)
        if add_to_github and self.github_issue:
            if attachment.message:
                msg = self.get_attachment_message(ctx, attachment)
                await GitHubClient.get_instance().add_issue_comment(self.github_issue, msg)

            if attachment.veri:
                await GitHubClient.get_instance().edit_issue_body(self.github_issue, self.get_github_desc(ctx))

    def get_attachment_message(self, ctx, attachment: Attachment):
        if isinstance(attachment.author, int):
            username = str(next((m for m in ctx.bot.get_all_members() if m.id == attachment.author), attachment.author))
        else:
            username = attachment.author
        msg = f"{VERI_KEY.get(attachment.veri, '')} - {username}\n\n" \
            f"{reports_to_issues(attachment.message)}"
        return msg

    async def canrepro(self, author, msg, ctx):
        if [a for a in self.attachments if a.author == author and a.veri]:
            raise ReportException("You have already verified this report.")
        if not self.is_bug:
            raise ReportException("You cannot CR a feature request.")
        attachment = Attachment.cr(author, msg)
        self.verification += 1
        await self.add_attachment(ctx, attachment)
        await self.notify_subscribers(ctx, f"New CR by <@{author}>: {msg}")

    async def upvote(self, author, msg, ctx):
        if [a for a in self.attachments if a.author == author and a.veri]:
            raise ReportException("You have already upvoted this report.")
        if self.is_bug:
            raise ReportException("You cannot upvote a bug report.")
        attachment = Attachment.upvote(author, msg)
        self.upvotes += 1
        await self.add_attachment(ctx, attachment)
        if msg:
            await self.notify_subscribers(ctx, f"New Upvote by <@{author}>: {msg}")
        if self.is_open() and not self.github_issue and self.upvotes - self.downvotes >= GITHUB_THRESHOLD:
            await self.post_to_github(ctx)
        if self.upvotes - self.downvotes in (15, 10):
            await self.update_labels()

    async def cannotrepro(self, author, msg, ctx):
        if [a for a in self.attachments if a.author == author and a.veri]:
            raise ReportException("You have already verified this report.")
        if not self.is_bug:
            raise ReportException("You cannot CNR a feature request.")
        attachment = Attachment.cnr(author, msg)
        self.verification -= 1
        await self.add_attachment(ctx, attachment)
        await self.notify_subscribers(ctx, f"New CNR by <@{author}>: {msg}")

    async def downvote(self, author, msg, ctx):  # lol Dusk was here
        if [a for a in self.attachments if a.author == author and a.veri]:
            raise ReportException("You have already downvoted this report.")
        if self.is_bug:
            raise ReportException("You cannot downvote a bug report.")
        attachment = Attachment.downvote(author, msg)
        self.downvotes += 1
        await self.add_attachment(ctx, attachment)
        if msg:
            await self.notify_subscribers(ctx, f"New downvote by <@{author}>: {msg}")
        if self.upvotes - self.downvotes in (14, 9):
            await self.update_labels()

    async def addnote(self, author, msg, ctx, add_to_github=True):
        attachment = Attachment(author, msg)
        await self.add_attachment(ctx, attachment, add_to_github)
        await self.notify_subscribers(ctx, f"New note by <@{author}>: {msg}")

    async def force_accept(self, ctx):
        await self.post_to_github(ctx)

    async def force_deny(self, ctx):
        self.severity = -1
        await self.notify_subscribers(ctx, f"Report closed.")
        await self.addnote(constants.OWNER_ID, f"Resolved - This report was denied.", ctx)

        msg_ = await self.get_message(ctx)
        if msg_:
            try:
                await msg_.delete()
                if self.message in Report.message_cache:
                    del Report.message_cache[self.message]
                if self.message in Report.message_ids:
                    del Report.message_ids[self.message]
            finally:
                self.message = None

        if self.github_issue:  # todo
            await GitHubClient.get_instance().close_issue(self.github_issue)

    def subscribe(self, ctx):
        """Ensures a user is subscribed to this report."""
        if ctx.message.author.id not in self.subscribers:
            self.subscribers.append(ctx.message.author.id)

    def unsubscribe(self, ctx):
        """Ensures a user is not subscribed to this report."""
        if ctx.message.author.id in self.subscribers:
            self.subscribers.remove(ctx.message.author.id)

    async def get_message(self, ctx):
        if self.message is None:
            return None
        elif self.message in self.message_cache:
            return self.message_cache[self.message]
        else:
            msg = await ctx.bot.get_channel(TRACKER_CHAN).fetch_message(self.message)
            if msg:
                Report.message_cache[self.message] = msg
            return msg

    async def update(self, ctx):
        try:
            msg = await self.get_message(ctx)
            await msg.edit(embed=self.get_embed())
        except AttributeError:
            return

    async def resolve(self, ctx, msg='', close_github_issue=True, pend=False, ignore_closed=False):
        if self.severity == -1 and not ignore_closed:
            raise ReportException("This report is already closed.")

        self.severity = -1
        if pend:
            await self.notify_subscribers(ctx, f"Report resolved - a patch is pending.")
        else:
            await self.notify_subscribers(ctx, f"Report closed.")
        if msg:
            await self.addnote(ctx.message.author.id, f"Resolved - {msg}", ctx)

        msg_ = await self.get_message(ctx)
        if msg_:
            try:
                await msg_.delete()
                if self.message in Report.message_cache:
                    del Report.message_cache[self.message]
                if self.message in Report.message_ids:
                    del Report.message_ids[self.message]
            finally:
                self.message = None

        if close_github_issue and self.github_issue:
            extra_labels = set()
            if msg.startswith('dupe'):
                extra_labels.add("duplicate")
            for label_match in re.finditer(r'\[(.+?)]', msg):
                label = label_match.group(1)
                if label in VALID_LABELS:
                    extra_labels.add(label)
            if extra_labels:  # todo
                await GitHubClient.get_instance().label_issue(self.github_issue, self.get_labels() + list(extra_labels))
            await GitHubClient.get_instance().close_issue(self.github_issue)

        if pend:
            self.pend()

    async def unresolve(self, ctx, msg='', open_github_issue=True):
        if not self.severity == -1:
            raise ReportException("This report is still open.")

        self.severity = 6
        await self.notify_subscribers(ctx, f"Report unresolved.")
        if msg:
            await self.addnote(ctx.message.author.id, f"Unresolved - {msg}", ctx)

        await self.setup_message(ctx.bot)

        if open_github_issue and self.github_issue:  # todo
            await GitHubClient.get_instance().open_issue(self.github_issue)

    def pend(self):
        pending = db.jget("pending-reports", [])
        pending.append(self.report_id)
        db.jset("pending-reports", pending)

    def get_labels(self):
        labels = [PRIORITY_LABELS.get(self.severity)]
        if self.is_bug:
            labels.append("bug")
        else:
            labels.append("featurereq")
            if self.upvotes - self.downvotes > 14:
                labels.append('+15')
            elif self.upvotes - self.downvotes > 9:
                labels.append('+10')
        return [l for l in labels if l]

    async def update_labels(self):  # todo
        labels = self.get_labels()
        await GitHubClient.get_instance().label_issue(self.github_issue, labels)

    async def edit_title(self, new_title):  # todo
        self.title = new_title
        await GitHubClient.get_instance().rename_issue(self.github_issue, new_title)

    async def notify_subscribers(self, ctx, msg):
        msg = f"`{self.report_id}` - {self.title}: {msg}"
        for sub in self.subscribers:
            try:
                member = next(m for m in ctx.bot.get_all_members() if m.id == sub)
                await member.send(msg)
            except (StopIteration, discord.HTTPException):
                continue


def get_next_report_num(identifier):
    id_nums = db.jget("reportnums", {})
    num = id_nums.get(identifier, 0) + 1
    id_nums[identifier] = num
    db.jset("reportnums", id_nums)
    return f"{num:0>3}"


def reports_to_issues(text):
    """
    Parses all XYZ-### identifiers and adds a link to their GitHub Issue numbers.
    """

    def report_sub(match):
        report_id = match.group(1)
        try:
            report = Report.from_id(report_id)
        except ReportException:
            return report_id

        if report.github_issue:
            return f"{report_id} (#{report.github_issue})"
        return report_id

    return re.sub(r"(\w{3,}-\d{3,})", report_sub, text)


class ReportException(Exception):
    pass
