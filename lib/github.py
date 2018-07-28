import asyncio

from github import Github


class GitHubClient:
    _instance = None

    def __init__(self, access_token, repo):
        self.client = Github(access_token)
        self.repo = self.client.get_repo(repo)  # should be safe blocking, since only called in initialize
        self.repo_name = repo

    @classmethod
    def initialize(cls, access_token, repo):
        if cls._instance:
            raise ValueError("Client already initialized")
        inst = cls(access_token, repo)
        cls._instance = inst
        return inst

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise ValueError("Client not initialized")
        return cls._instance

    async def create_issue(self, title, description):
        def _():
            return self.repo.create_issue(title, description)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def add_issue_comment(self, issue_num, description):
        def _():
            issue = self.repo.get_issue(issue_num)
            return issue.create_comment(description)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def close_issue(self, issue_num, comment=None):
        def _():
            issue = self.repo.get_issue(issue_num)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="closed")

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def open_issue(self, issue_num, comment=None):
        def _():
            issue = self.repo.get_issue(issue_num)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="open")

        return await asyncio.get_event_loop().run_in_executor(None, _)
