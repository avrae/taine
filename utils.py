class DiscordEmbedTextPaginator:
    DESC_MAX = 2048
    FIELD_MAX = 1024

    def __init__(self):
        self.texts = []
        self._last_text = ""

    def add(self, text: str):
        if len(self.texts) == 0 and len(text) > self.DESC_MAX:
            raise ValueError("Text is too long to fit.")
        elif len(text) > self.FIELD_MAX:
            raise ValueError("Text is too long to fit.")

        if len(self.texts) == 0:
            _max = self.DESC_MAX
        else:
            _max = self.FIELD_MAX

        if len(text) + len(self._last_text) > _max:
            self.texts.append(self._last_text.strip())
            self._last_text = text
        else:
            self._last_text += f"\n{text.strip()}"

    def write_to(self, embed):
        if self._last_text:
            self.texts.append(self._last_text)

        if not self.texts:
            return embed

        embed.description = self.texts[0]

        for field in self.texts[1:]:
            embed.add_field(name="** **", value=field, inline=False)

        return embed
