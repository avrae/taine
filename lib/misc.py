import asyncio
import random
from itertools import zip_longest

import discord
from fuzzywuzzy import fuzz, process


class ContextProxy:  # just to pass the bot on to functions that need it
    def __init__(self, bot, **kwargs):
        self.bot = bot
        for k, v in kwargs.items():
            self.__setattr__(k, v)


# all of this is copied from Avrae code
def search(list_to_search: list, value, key, cutoff=5, return_key=False, strict=False):
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param return_key: Whether to return the key of the object that matched or the object itself.
    :param strict: If True, will only search for exact matches.
    :returns: A two-tuple (result, strict)"""
    # there is nothing to search
    if len(list_to_search) == 0:
        return [], False

    # full match, return result
    exact_matches = [a for a in list_to_search if value.lower() == key(a).lower()]
    if not (exact_matches or strict):
        partial_matches = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(partial_matches) > 1 or not partial_matches:
            names = [key(d).lower() for d in list_to_search]
            fuzzy_map = {key(d).lower(): d for d in list_to_search}
            fuzzy_results = [r for r in process.extract(value.lower(), names, scorer=fuzz.ratio) if r[1] >= cutoff]
            fuzzy_sum = sum(r[1] for r in fuzzy_results)
            fuzzy_matches_and_confidences = [(fuzzy_map[r[0]], r[1] / fuzzy_sum) for r in fuzzy_results]

            # display the results in order of confidence
            weighted_results = []
            weighted_results.extend((match, confidence) for match, confidence in fuzzy_matches_and_confidences)
            weighted_results.extend((match, len(value) / len(key(match))) for match in partial_matches)
            sorted_weighted = sorted(weighted_results, key=lambda e: e[1], reverse=True)

            # build results list, unique
            results = []
            for r in sorted_weighted:
                if r[0] not in results:
                    results.append(r[0])
        else:
            results = partial_matches
    else:
        results = exact_matches

    if len(results) > 1:
        if return_key:
            return [key(r) for r in results], False
        else:
            return results, False
    elif not results:
        return [], False
    else:
        if return_key:
            return key(results[0]), True
        else:
            return results[0], True


async def search_and_select(ctx, list_to_search: list, query, key, cutoff=5, return_key=False, pm=False, message=None,
                            list_filter=None, selectkey=None, search_func=search):
    """
    Searches a list for an object matching the key, and prompts user to select on multiple matches.

    :param ctx: The context of the search.
    :param list_to_search: The list of objects to search.
    :param query: The value to search for.
    :param key: How to search - compares key(obj) to value
    :param cutoff: The cutoff percentage of fuzzy searches.
    :param return_key: Whether to return key(match) or match.
    :param pm: Whether to PM the user the select prompt.
    :param message: A message to add to the select prompt.
    :param list_filter: A filter to filter the list to search by.
    :param selectkey: If supplied, each option will display as selectkey(opt) in the select prompt.
    :param search_func: The function to use to search.
    :return:
    """
    if list_filter:
        list_to_search = list(filter(list_filter, list_to_search))

    if search_func is None:
        search_func = search

    if asyncio.iscoroutinefunction(search_func):
        result = await search_func(list_to_search, query, key, cutoff, return_key)
    else:
        result = search_func(list_to_search, query, key, cutoff, return_key)

    if result is None:
        return None
    strict = result[1]
    results = result[0]

    if strict:
        return results
    else:
        if len(results) == 0:
            return None

        first_result = results[0]
        confidence = fuzz.partial_ratio(key(first_result).lower(), query.lower())
        if len(results) == 1 and confidence > 75:
            return first_result
        else:
            if selectkey:
                options = [(selectkey(r), r) for r in results]
            elif return_key:
                options = [(r, r) for r in results]
            else:
                options = [(key(r), r) for r in results]
            return await get_selection(ctx, options, pm=pm, message=message, force_select=True)


def paginate(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return [i for i in zip_longest(*args, fillvalue=fillvalue) if i is not None]


async def get_selection(ctx, choices, delete=True, pm=False, message=None, force_select=False):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If delete is True, will delete the selection message and the response.
    If length of choices is 1, will return the only choice unless force_select is True.

    :raises NoSelectionElements: if len(choices) is 0.
    :raises SelectionCancelled: if selection is cancelled."""
    if len(choices) == 0:
        return None
    elif len(choices) == 1 and not force_select:
        return choices[0][1]

    page = 0
    pages = paginate(choices, 10)
    m = None
    select_msg = None

    def chk(msg):
        valid = [str(v) for v in range(1, len(choices) + 1)] + ["c", "n", "p"]
        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.lower() in valid

    for n in range(200):
        _choices = pages[page]
        names = [o[0] for o in _choices if o]
        embed = discord.Embed()
        embed.title = "Multiple Matches Found"
        select_str = "Which one were you looking for? (Type the number or \"c\" to cancel)\n"
        if len(pages) > 1:
            select_str += "`n` to go to the next page, or `p` for previous\n"
            embed.set_footer(text=f"Page {page + 1}/{len(pages)}")
        for i, r in enumerate(names):
            select_str += f"**[{i + 1 + page * 10}]** - {r}\n"
        embed.description = select_str
        embed.colour = random.randint(0, 0xffffff)
        if message:
            embed.add_field(name="Note", value=message, inline=False)
        if select_msg:
            try:
                await select_msg.delete()
            except:
                pass
        if not pm:
            select_msg = await ctx.channel.send(embed=embed)
        else:
            embed.add_field(name="Instructions",
                            value="Type your response in the channel you called the command. This message was PMed to "
                                  "you to hide the monster name.", inline=False)
            select_msg = await ctx.author.send(embed=embed)

        try:
            m = await ctx.bot.wait_for('message', timeout=30, check=chk)
        except asyncio.TimeoutError:
            m = None

        if m is None:
            break
        if m.content.lower() == 'n':
            if page + 1 < len(pages):
                page += 1
            else:
                await ctx.channel.send("You are already on the last page.")
        elif m.content.lower() == 'p':
            if page - 1 >= 0:
                page -= 1
            else:
                await ctx.channel.send("You are already on the first page.")
        else:
            break

    if delete and not pm:
        try:
            await select_msg.delete()
            await m.delete()
        except:
            pass
    if m is None or m.content.lower() == "c":
        return None
    return choices[int(m.content) - 1][1]
