import asyncio

from github import Github


class GitHubClient:
    _instance = None

    def __init__(self, access_token, org):
        self.client = Github(access_token)
        self.repos = {}

        for repo in self.client.get_organization(org).get_repos("public"):  # build a method to access our repos
            print(f"Loaded repo {repo.full_name}")
            self.repos[repo.full_name] = repo

    @classmethod
    def initialize(cls, access_token, org='avrae'):
        if cls._instance:
            raise RuntimeError("Client already initialized")
        inst = cls(access_token, org)
        cls._instance = inst
        return inst

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("Client not initialized")
        return cls._instance

    async def create_issue(self, repo, title, description, labels=None):
        if labels is None:
            labels = []

        def _():
            return repo.create_issue(title, description, labels=labels)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def add_issue_comment(self, repo, issue_num, description):
        def _():
            issue = repo.get_issue(issue_num)
            return issue.create_comment(description)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def label_issue(self, repo, issue_num, labels):
        def _():
            issue = repo.get_issue(issue_num)
            issue.edit(labels=labels)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def close_issue(self, repo, issue_num, comment=None):
        def _():
            issue = repo.get_issue(issue_num)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="closed")

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def open_issue(self, repo, issue_num, comment=None):
        def _():
            issue = repo.get_issue(issue_num)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="open")

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def rename_issue(self, repo, issue_num, new_title):
        def _():
            issue = repo.get_issue(issue_num)
            issue.edit(title=new_title)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def edit_issue_body(self, repo, issue_num, new_body):
        def _():
            issue = repo.get_issue(issue_num)
            issue.edit(body=new_body)

        return await asyncio.get_event_loop().run_in_executor(None, _)
