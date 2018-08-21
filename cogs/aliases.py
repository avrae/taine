import asyncio
import random
import re
from urllib import parse

import discord
from discord.ext import commands

from lib.github import GitHubClient
from lib.search import search_and_select

ALIAS_REPO = "avrae/avrae-docs"
IGNORED = ("template.md", ".gitattributes", ".gitignore", "CODE_OF_CONDUCT.md", "LICENSE", "README.md")


class Aliases:
    def __init__(self, bot):
        self.bot = bot
        self.repo = GitHubClient.get_instance().client.get_repo(ALIAS_REPO)
        self.bot.loop.create_task(self.poll_github())
        self.aliases = []

    def update_aliases(self):
        tree = self.repo.get_git_tree("master", True).tree
        for file in tree:
            if not file.type == "blob":
                continue
            filename = file.path.split("/")[-1]
            if filename in IGNORED:
                continue
            if filename.endswith(".md"):
                aliasname = filename[:-3]
            else:
                aliasname = filename

            alias = {
                "name": aliasname,
                "sha": file.sha,
                "path": file.path,
                "cached": False
            }

            if [a for a in self.aliases if a['sha'] == alias['sha']]:
                continue  # already loaded

            for a in self.aliases.copy():
                if a['path'] == alias['path']:
                    self.aliases.remove(a)

            print(f"Updated alias path {alias['path']}")
            self.aliases.append(alias)

    async def poll_github(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed:
            await self.bot.loop.run_in_executor(None, self.update_aliases)
            await asyncio.sleep(3600)

    def get_file(self, path):
        contentfile = self.repo.get_file_contents(path)
        content = contentfile.decoded_content
        return content.decode()

    async def ensure_alias_loaded(self, alias):
        index = self.aliases.index(alias)
        if alias['cached']:
            return alias
        data = await self.bot.loop.run_in_executor(None, self.get_file, alias['path'])
        alias['cached'] = True
        alias['data'] = data
        self.aliases[index] = alias
        return alias

    @commands.command(pass_context=True, name="repo")
    async def search_repo(self, ctx, *, alias_name):
        alias = await search_and_select(ctx, self.aliases, alias_name, lambda e: e['name'],
                                        selectkey=lambda e: e['path'])
        alias = await self.ensure_alias_loaded(alias)

        embed = discord.Embed(colour=random.randint(0, 0xffffff))
        embed.url = f"https://github.com/{ALIAS_REPO}/blob/master/{parse.quote(alias['path'])}"
        embed.title = alias['name']
        embed.set_footer(text="Click the title for full details.")

        author = re.search(r'[*_]By (.+?)[*_]', alias['data'])
        command = re.search(r'```[a-zA-Z]*\s*!((.|\n)+?)```', alias['data'])

        if command:
            embed.description = f"```py\n!{command.group(1)}\n```"
        else:
            embed.description = "I was unable to find the command. Click the title to go to the alias page."

        if author:
            embed.add_field(name="Author", value=author.group(1))

        await self.bot.say(embed=embed)


def setup(bot):
    bot.add_cog(Aliases(bot))
