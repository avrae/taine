import random
from itertools import zip_longest

import discord
from fuzzywuzzy import fuzz, process


def search(list_to_search: list, value, key, cutoff=5, return_key=False):
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param return_key: Whether to return the key of the object that matched or the object itself.
    :returns: A two-tuple (result, strict) or None"""
    try:
        result = next(a for a in list_to_search if value.lower() == key(a).lower())
    except StopIteration:
        result = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(result) is 0:
            names = [key(d) for d in list_to_search]
            result = process.extract(value, names, scorer=fuzz.ratio)
            result = [r for r in result if r[1] >= cutoff]
            if len(result) is 0:
                return None
            else:
                if return_key:
                    return [r[0] for r in result], False
                else:
                    return [a for a in list_to_search if key(a) in [r[0] for r in result]], False
        else:
            if return_key:
                return [key(r) for r in result], False
            else:
                return result, False
    if return_key:
        return key(result), True
    else:
        return result, True


async def search_and_select(ctx, list_to_search: list, value, key, cutoff=5, return_key=False, pm=False,
                            message=None, list_filter=None, selectkey=None):
    """
    Searches a list for an object matching the key, and prompts user to select on multiple matches.
    :param ctx: The context of the search.
    :param list_to_search: The list of objects to search.
    :param value: The value to search for.
    :param key: How to search - compares key(obj) to value
    :param cutoff: The cutoff percentage of fuzzy searches.
    :param return_key: Whether to return key(match) or match.
    :param pm: Whether to PM the user the select prompt.
    :param message: A message to add to the select prompt.
    :param list_filter: A filter to filter the list to search by.
    :param selectkey: If supplied, each option will display as selectkey(opt) in the select prompt.
    :return:
    """
    if list_filter:
        list_to_search = list(filter(list_filter, list_to_search))
    result = search(list_to_search, value, key, cutoff, return_key)
    if result is None:
        raise NoSelectionElements("No matches found.")
    strict = result[1]
    results = result[0]

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            if selectkey:
                result = await get_selection(ctx, [(selectkey(r), r) for r in results], pm=pm, message=message)
            elif return_key:
                result = await get_selection(ctx, [(r, r) for r in results], pm=pm, message=message)
            else:
                result = await get_selection(ctx, [(key(r), r) for r in results], pm=pm, message=message)
    return result


def paginate(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return [i for i in zip_longest(*args, fillvalue=fillvalue) if i is not None]


async def get_selection(ctx, choices, delete=True, return_name=False, pm=False, message=None):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If delete is True, will delete the selection message and the response.
    If length of choices is 1, will return the only choice.
    :raises NoSelectionElements if len(choices) is 0.
    :raises SelectionCancelled if selection is cancelled."""
    if len(choices) < 2:
        if len(choices):
            return choices[0][1] if not return_name else choices[0]
        else:
            raise NoSelectionElements()
    page = 0
    pages = paginate(choices, 10)
    m = None

    def chk(msg):
        valid = [str(v) for v in range(1, len(choices) + 1)] + ["c", "n", "p"]
        return msg.content.lower() in valid

    for n in range(200):
        _choices = pages[page]
        names = [o[0] for o in _choices if o]
        embed = discord.Embed()
        embed.title = "Multiple Matches Found"
        selectStr = "Which one were you looking for? (Type the number or \"c\" to cancel)\n"
        if len(pages) > 1:
            selectStr += "`n` to go to the next page, or `p` for previous\n"
            embed.set_footer(text=f"Page {page+1}/{len(pages)}")
        for i, r in enumerate(names):
            selectStr += f"**[{i+1+page*10}]** - {r}\n"
        embed.description = selectStr
        embed.colour = random.randint(0, 0xffffff)
        if message:
            embed.add_field(name="Note", value=message)
        if not pm:
            if n == 0:
                selectMsg = await ctx.bot.send_message(ctx.message.channel, embed=embed)
            else:
                newSelectMsg = await ctx.bot.send_message(ctx.message.channel, embed=embed)
        else:
            embed.add_field(name="Instructions",
                            value="Type your response in the channel you called the command. This message was PMed to "
                                  "you to hide the monster name.")
            if n == 0:
                selectMsg = await ctx.bot.send_message(ctx.message.author, embed=embed)
            else:
                newSelectMsg = await ctx.bot.send_message(ctx.message.author, embed=embed)

        if n > 0:  # clean up old messages
            try:
                await ctx.bot.delete_message(selectMsg)
                await ctx.bot.delete_message(m)
            except:
                pass
            finally:
                selectMsg = newSelectMsg

        m = await ctx.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel,
                                           check=chk)
        if m is None:
            break
        if m.content.lower() == 'n':
            if page + 1 < len(pages):
                page += 1
            else:
                await ctx.bot.send_message(ctx.message.channel, "You are already on the last page.")
        elif m.content.lower() == 'p':
            if page - 1 >= 0:
                page -= 1
            else:
                await ctx.bot.send_message(ctx.message.channel, "You are already on the first page.")
        else:
            break

    if delete and not pm:
        try:
            await ctx.bot.delete_message(selectMsg)
            await ctx.bot.delete_message(m)
        except:
            pass
    if m is None or m.content.lower() == "c": raise SelectionCancelled()
    if return_name:
        return choices[int(m.content) - 1]
    return choices[int(m.content) - 1][1]


class NoSelectionElements(Exception):
    def __init__(self, msg):
        msg = msg or "There are no choices to select from."
        super(NoSelectionElements, self).__init__(msg)


class SelectionCancelled(Exception):
    def __init__(self):
        super(SelectionCancelled, self).__init__("Selection timed out or was cancelled.")
