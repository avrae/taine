import logging
import os
import re
from decimal import Decimal

import discord
from boto3.dynamodb.conditions import Key
from cachetools import LRUCache

import constants
import lib.db as ddb
from lib.github import GitHubClient

PRIORITY = {
    -2: "Patch Pending", -1: "Resolved",
    0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low", 5: "P5: Trivial",
    6: "Pending/Other"
}
PRIORITY_LABELS = {
    0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low", 5: "P5: Trivial"
}
VALID_LABELS = (
    'bug', 'duplicate', 'featurereq', 'help wanted', 'invalid', 'wontfix', 'longterm', 'enhancement',
    'P0: Critical', 'P1: Very High', 'P2: High', 'P3: Medium', 'P4: Low', 'P5: Trivial', 'stale',
    '+10', '+15'
)
MANAGED_LABELS = (
    'bug', 'featurereq',
    'P0: Critical', 'P1: Very High', 'P2: High', 'P3: Medium', 'P4: Low', 'P5: Trivial',
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

GITHUB_BASE = "https://github.com"
UPVOTE_REACTION = "\U0001f44d"
DOWNVOTE_REACTION = "\U0001f44e"
INFO_REACTION = "\u2139"
THREAD_REACTION = "\U0001f9f5"  # :thread:
# how many upvotes a feature req needs to be added to GitHub
GITHUB_THRESHOLD = int(os.environ.get("FR_APPROVE_THRESHOLD", 5))
# how many downvotes a feature req needs to be closed automatically
CLOSE_THRESHOLD = int(os.environ.get("FR_DENY_THRESHOLD", -3))

# we use 0 for a sentinel value since
# it's an invalid ID in both Discord and GitHub
# and falsy, which is compatible with old None checks
MESSAGE_SENTINEL = 0
GITHUB_ISSUE_SENTINEL = 0
log = logging.getLogger(__name__)


class Attachment:
    def __init__(self, author, message: str = None, veri: int = 0):
        self.author = author
        self.message = message or None
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

    def __init__(self, reporter, report_id: str, title: str, severity: int, verification: int, attachments: list,
                 message, upvotes: int = 0, downvotes: int = 0, github_issue: int = None, github_repo: str = None,
                 subscribers: list = None, is_bug: bool = True, pending: bool = False):
        if subscribers is None:
            subscribers = []
        if github_repo is None:
            github_repo = 'avrae/avrae'
        if message is None:
            message = 0
        if github_issue is None:
            github_issue = 0
        self.reporter = reporter
        self.report_id = report_id
        self.title = title
        self.severity = severity

        self.attachments = attachments
        self.message = int(message)
        self.subscribers = subscribers

        self.repo: str = github_repo
        self.github_issue = int(github_issue)

        self.is_bug = is_bug
        self.verification = verification
        self.upvotes = upvotes
        self.downvotes = downvotes

        self.pending = pending

    @classmethod
    async def new(cls, reporter, report_id: str, title: str, attachments: list, is_bug=True, repo=None):
        subscribers = None
        if isinstance(reporter, (int, Decimal)):
            subscribers = [reporter]
        inst = cls(reporter, report_id, title, 6, 0, attachments, None, subscribers=subscribers, is_bug=is_bug,
                   github_repo=repo)
        return inst

    @classmethod
    def new_from_issue(cls, repo_name, issue):
        attachments = [Attachment("GitHub", issue['body'])]
        title = issue['title']
        id_match = re.match(r'([A-Z]{3,})(-\d+)?\s', issue['title'])
        is_bug = 'featurereq' not in [lab['name'] for lab in issue['labels']]
        if id_match:
            identifier = id_match.group(1)
            report_num = get_next_report_num(identifier)
            report_id = f"{identifier}-{report_num}"
            title = title[len(id_match.group(0)):]
        else:
            identifier = identifier_from_repo(repo_name, is_bug)
            report_id = f"{identifier}-{get_next_report_num(identifier)}"

        return cls("GitHub", report_id, title, -1,
                   # pri is created at -1 for unresolve (which changes it to 6)
                   0, attachments, None, github_issue=issue['number'], github_repo=repo_name, is_bug=is_bug)

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
            'is_bug': self.is_bug, 'pending': self.pending
        }

    @classmethod
    def from_id(cls, report_id):
        response = ddb.reports.get_item(
            Key={"report_id": report_id.upper()}
        )
        try:
            return cls.from_dict(response['Item'])
        except KeyError:
            raise ReportException("Report not found.")

    @classmethod
    def from_message_id(cls, message_id):
        response = ddb.reports.query(
            KeyConditionExpression=Key("message").eq(message_id),
            IndexName="message_id"
        )
        try:
            return cls.from_dict(response['Items'][0])
        except IndexError:
            raise ReportException("Report not found.")

    @classmethod
    def from_github(cls, repo_name, issue_num):
        response = ddb.reports.query(
            KeyConditionExpression=Key("github_issue").eq(issue_num) & Key("github_repo").eq(repo_name),
            IndexName="github_issue"
        )
        try:
            return cls.from_dict(response['Items'][0])
        except IndexError:
            raise ReportException("Report not found.")

    def is_open(self):
        return self.severity >= 0

    @property
    def score(self):
        return self.upvotes - self.downvotes

    async def setup_github(self, ctx):
        if self.github_issue:
            raise ReportException("Issue is already on GitHub.")
        if self.is_bug:
            labels = ["bug"]
        else:
            labels = ["featurereq"]
        desc = self.get_github_desc(ctx)

        issue = await GitHubClient.get_instance().create_issue(self.repo, f"{self.report_id} {self.title}", desc,
                                                               labels)
        self.github_issue = issue.number

    async def setup_message(self, bot):
        report_message = await self.get_channel(bot).send(embed=self.get_embed())
        self.message = report_message.id
        if not self.is_bug:
            await report_message.add_reaction(UPVOTE_REACTION)
            await report_message.add_reaction(DOWNVOTE_REACTION)
        await report_message.add_reaction(INFO_REACTION)
        await report_message.add_reaction(THREAD_REACTION)
        return report_message

    def commit(self):
        ddb.reports.put_item(Item=self.to_dict())

    def get_embed(self, detailed=False, guild=None):
        embed = discord.Embed()
        if isinstance(self.reporter, (int, Decimal)):
            embed.add_field(name="Added By", value=f"<@{self.reporter}>")
        else:
            embed.add_field(name="Added By", value=self.reporter)
        embed.add_field(name="Priority", value=PRIORITY.get(self.severity, "Unknown"))
        if not self.is_bug:
            embed.colour = 0x00ff00
            embed.add_field(name="Votes", value="\u2b06" + str(self.upvotes) + "` | `\u2b07" + str(self.downvotes))
            embed.set_footer(text=f"~report {self.report_id} for details | Vote by reacting")
        else:
            embed.colour = 0xff0000
            embed.add_field(name="Verification", value=str(self.verification))
            embed.set_footer(
                text=f"~report {self.report_id} for details | Verify with ~cr/~cnr {self.report_id} [note]")

        embed.title = f"`{self.report_id}` {self.title}"
        if len(embed.title) > 256:
            embed.title = f"{embed.title[:250]}..."
        if self.github_issue:
            embed.url = f"{GITHUB_BASE}/{self.repo}/issues/{self.github_issue}"
        embed.description = f"*{len(self.attachments)} notes*"
        if detailed:
            if not guild:
                raise ValueError("Context not supplied for detailed call.")
            embed.description = f"*{len(self.attachments)} notes, showing first 10*"
            for attachment in self.attachments[:10]:
                if isinstance(attachment.author, (int, Decimal)) and guild:
                    user = guild.get_member(attachment.author)
                else:
                    user = attachment.author
                if attachment.message:
                    msg = attachment.message[:1020]
                else:
                    msg = "No details."
                embed.add_field(name=f"{VERI_EMOJI.get(attachment.veri, '')} {user}",
                                value=msg, inline=len(attachment.message or '') < 256)

        return embed

    def get_github_desc(self, ctx):
        msg = self.title
        if self.attachments:
            msg = self.attachments[0].message

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
        if self.github_issue is GITHUB_ISSUE_SENTINEL:
            return None
        return f"https://github.com/{self.repo}/issues/{self.github_issue}"

    async def add_attachment(self, ctx, attachment: Attachment, add_to_github=True, post_to_thread=True):
        self.attachments.append(attachment)
        if add_to_github and self.github_issue:
            if attachment.message:
                msg = self.get_attachment_message(ctx, attachment)
                await GitHubClient.get_instance().add_issue_comment(self.repo, self.github_issue, msg)

            if attachment.veri:
                await GitHubClient.get_instance().edit_issue_body(self.repo, self.github_issue,
                                                                  self.get_github_desc(ctx))

        if post_to_thread and (thread := await self.get_thread(ctx.bot)) is not None:
            await thread.send(self.get_attachment_message(ctx, attachment))

    def get_attachment_message(self, ctx, attachment: Attachment):
        if isinstance(attachment.author, (int, Decimal)):
            username = str(next((m for m in ctx.bot.get_all_members() if m.id == attachment.author), attachment.author))
        else:
            username = attachment.author

        if not attachment.message:
            return f"{VERI_KEY.get(attachment.veri, '')} - {username}"
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

    async def addnote(self, author, msg, ctx, add_to_github=True):
        attachment = Attachment(author, msg)
        await self.add_attachment(ctx, attachment, add_to_github)
        await self.notify_subscribers(ctx, f"New note by <@{author}>: {msg}")

    async def force_accept(self, ctx):
        await self.setup_github(ctx)

    async def force_deny(self, ctx):
        await self.resolve(ctx, "This report was closed. See #bug-discussions or #request-discussions for more "
                                "information.", author=constants.OWNER_ID)

    def subscribe(self, ctx):
        """Ensures a user is subscribed to this report."""
        if ctx.author.id not in self.subscribers:
            self.subscribers.append(ctx.author.id)

    def unsubscribe(self, ctx):
        """Ensures a user is not subscribed to this report."""
        if ctx.author.id in self.subscribers:
            self.subscribers.remove(ctx.author.id)

    def get_channel(self, bot):
        return bot.get_channel(constants.BUG_TRACKER_CHAN) if self.is_bug \
            else bot.get_channel(constants.REQ_TRACKER_CHAN)

    async def create_thread(self, bot, message_id=None):
        """Creates a thread for this report on the given message, or the report's default message."""
        if message_id is None and self.message is not MESSAGE_SENTINEL:
            message_id = self.message
        elif message_id is None:
            return

        channel = self.get_channel(bot)
        message = channel.get_partial_message(message_id)
        thread = None
        thread_name = f"{self.report_id} {self.title}"
        if len(thread_name) > 100:
            thread_name = f"{thread_name[:97]}..."
        try:
            thread = await channel.create_thread(name=thread_name, message=message)
            # remove any system message
            await channel.purge(limit=1, check=lambda m: m.type == discord.MessageType.thread_created, bulk=False)
            # send the full report detail and pin it
            msg = await thread.send(embed=self.get_embed(detailed=True, guild=channel.guild))
            await msg.pin()
            # add the report author
            reporter = bot.get_user(self.reporter)
            if reporter is not None:
                await thread.add_user(reporter)
        except discord.HTTPException as e:
            log.warning(f"error in create thread: {e}")
        return thread

    async def get_thread(self, bot, unarchive=False, create=False, message_id=None):
        """Gets the thread associated with this report, unarchiving or creating it if necessary and specified."""
        if message_id is None:
            message_id = self.message

        if message_id is MESSAGE_SENTINEL:
            return None

        # get thread channel
        channel = self.get_channel(bot)
        thread = channel.get_thread(message_id)
        if thread is None:
            try:
                thread = await bot.fetch_channel(message_id)
            except discord.NotFound:
                pass

        if thread is None and create:
            thread = await self.create_thread(bot, message_id)

        # unarchive if it archived
        if unarchive and thread.archived and not thread.locked:
            await thread.edit(archived=False)

        return thread

    async def get_message(self, ctx):
        if self.message is MESSAGE_SENTINEL:
            return None
        elif self.message in self.message_cache:
            return self.message_cache[self.message]
        else:
            try:
                msg = await self.get_channel(ctx.bot).fetch_message(self.message)
            except discord.HTTPException:
                msg = None
            if msg:
                Report.message_cache[self.message] = msg
            return msg

    async def delete_message(self, ctx):
        msg_ = await self.get_message(ctx)
        if msg_:
            try:
                await msg_.delete()
                if self.message in Report.message_cache:
                    del Report.message_cache[self.message]
            except discord.HTTPException:
                pass
            finally:
                self.message = MESSAGE_SENTINEL

    async def update(self, ctx):
        msg = await self.get_message(ctx)
        if msg is None and self.is_open() and self.github_issue:
            await self.setup_message(ctx.bot)
        elif self.is_open():
            await msg.edit(embed=self.get_embed())

    async def resolve(self, ctx, msg='', close_github_issue=True, pend=False, ignore_closed=False, author=None):
        if self.severity == -1 and not ignore_closed:
            raise ReportException("This report is already closed.")

        self.severity = -1
        if msg:
            await self.addnote(author or ctx.author.id, f"Resolved - {msg}", ctx)
        elif pend:
            await self.notify_subscribers(ctx, f"Report resolved - a patch is pending.")
        else:
            await self.notify_subscribers(ctx, f"Report closed.")

        await self.delete_message(ctx)

        if close_github_issue and self.github_issue:
            extra_labels = set()
            if msg.startswith('dupe'):
                extra_labels.add("duplicate")
            for label_match in re.finditer(r'\[(.+?)]', msg):
                label = label_match.group(1)
                if label in VALID_LABELS:
                    extra_labels.add(label)
            if extra_labels:
                await GitHubClient.get_instance().label_issue(self.repo, self.github_issue,
                                                              (await self.get_labels()) + list(extra_labels))
            await GitHubClient.get_instance().close_issue(self.repo, self.github_issue)

        if pend:
            self.pend()

    async def unresolve(self, ctx, msg='', open_github_issue=True):
        if not self.severity == -1:
            raise ReportException("This report is still open.")

        self.severity = 6
        await self.notify_subscribers(ctx, f"Report unresolved.")
        if msg:
            await self.addnote(ctx.message.author.id, f"Unresolved - {msg}", ctx)

        await self.get_message(ctx)  # sets up message again if needed

        if open_github_issue and self.github_issue:
            await GitHubClient.get_instance().open_issue(self.repo, self.github_issue)

    async def untrack(self, ctx):
        await self.delete_message(ctx)
        if self.github_issue:
            await GitHubClient.get_instance().rename_issue(self.repo, self.github_issue, self.title)

        ddb.reports.delete_item(Key={"report_id": self.report_id})

    def pend(self):
        self.pending = True

    def unpend(self):
        self.pending = False

    async def get_labels(self):
        labels = await GitHubClient.get_instance().get_issue_labels(self.repo, self.github_issue)
        labels = [l for l in labels if l not in MANAGED_LABELS]
        labels.append(PRIORITY_LABELS.get(self.severity))
        if self.is_bug:
            labels.append("bug")
        else:
            labels.append("featurereq")
            if self.score > 14:
                labels.append('+15')
            elif self.score > 9:
                labels.append('+10')
        return [l for l in labels if l]

    async def update_labels(self):
        labels = await self.get_labels()
        await GitHubClient.get_instance().label_issue(self.repo, self.github_issue, labels)

    async def edit_title(self, new_title):
        self.title = new_title
        await GitHubClient.get_instance().rename_issue(self.repo, self.github_issue, f"{self.report_id} {self.title}")

    async def notify_subscribers(self, ctx, msg):
        embed = discord.Embed(
            title=f"`{self.report_id}` - {self.title}",
            description=msg
        )
        embed.set_footer(text=f'Add a comment with "~note {self.report_id} ..." '
                              f'or view notes with "~report {self.report_id}"')
        for sub in self.subscribers:
            try:
                member = next(m for m in ctx.bot.get_all_members() if m.id == sub)
                await member.send(embed=embed)
            except (StopIteration, discord.HTTPException):
                continue


def get_next_report_num(identifier):
    """Increments the report number of an identifier and returns the latest report ID."""
    response = ddb.reportnums.update_item(
        Key={"identifier": identifier},
        UpdateExpression="ADD num :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW"
    )
    num = int(response['Attributes']['num'])
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
            if report.repo:
                return f"{report_id} ({report.repo}#{report.github_issue})"
            return f"{report_id} (#{report.github_issue})"
        return report_id

    return re.sub(r"(\w{3,}-\d{3,})", report_sub, text)


def identifier_from_repo(repo_name, is_bug=True):
    default = constants.REPO_ID_MAP.get(repo_name, 'AVR')
    if not is_bug:
        return constants.REPO_ID_MAP.get(f"{repo_name}:feature", default)
    return default


class ReportException(Exception):
    pass
