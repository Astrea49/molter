import functools
import logging

import dis_snek
from dis_snek import Embed
from dis_snek.ext.paginators import Paginator

import molter

__all__ = ("HelpCommand",)

log = logging.getLogger(dis_snek.const.logger_name)


class HelpCommand:
    show_hidden: bool
    """Should hidden commands be shown"""
    show_disabled: bool
    """Should disabled commands be shown"""
    run_checks: bool
    """Should only commands that's checks pass be shown"""
    show_self: bool
    """Should this command be shown in the help message"""
    show_params: bool
    """Should parameters for commands be shown"""
    show_aliases: bool
    """Should aliases for commands be shown"""
    show_prefix: bool
    """Should the prefix be shown"""

    embed_title: str
    """The title to use in the embed. {username} will be replaced by the client's username"""
    not_found_message: str
    """The message to send when a command was not found. {cmd_name} will be replaced by the requested command."""

    _client: dis_snek.Snake

    def __init__(
        self,
        client: dis_snek.Snake,
        *,
        show_hidden: bool = False,
        run_checks: bool = False,
        show_self: bool = False,
        show_params: bool = False,
        show_aliases: bool = False,
        show_prefix: bool = False,
        embed_title: str | None = None,
        not_found_message: str | None = None,
    ) -> None:
        self._client = client
        self.show_hidden = show_hidden
        self.run_checks = run_checks
        self.show_self = show_self
        self.show_params = show_params
        self.show_aliases = show_aliases
        self.show_prefix = show_prefix
        self.embed_title = embed_title or "{username} Help Command"
        self.not_found_message = not_found_message or "Sorry! No command called `{cmd_name}` was found."
        self.cmd = self._callback

    def register(self) -> None:
        """Register the help command in dis-snek"""
        if not isinstance(self.cmd.callback, functools.partial):
            # prevent wrap-nesting
            self.cmd.callback = functools.partial(self.cmd.callback, self)

        # replace existing help command if found
        if "help" in self._client.commands:
            log.warning("Replacing existing help command.")
            del self._client.commands["help"]

        self._client.add_message_command(self.cmd)  # type: ignore

    async def send_help(self, ctx: dis_snek.MessageContext, cmd_name: str | None) -> None:
        """
        Send a help message to the given context.

        args:
            ctx: The context to use
            cmd_name: An optional command name to send help for
        """
        await self._callback.callback(ctx, cmd_name)  # type: ignore

    @molter.msg_command(name="help")
    async def _callback(self, ctx: dis_snek.MessageContext, cmd_name: str = None) -> None:
        if cmd_name:
            return await self._help_specific(ctx, cmd_name)
        await self._help_list(ctx)

    async def _help_list(self, ctx: dis_snek.MessageContext) -> None:
        cmds = await self._gather(ctx)

        output = []
        for cmd in cmds.values():
            _temp = self._generate_command_string(cmd, ctx)
            _temp += f"\n{cmd.brief}"

            output.append(self._sanitise_mentions(_temp))
        if len("\n".join(output)) > 500:
            paginator = Paginator.create_from_list(self._client, output, page_size=500)
            paginator.default_title = self.embed_title.format(username=self._client.user.username)
            await paginator.send(ctx)
        else:
            embed = Embed(
                title=self.embed_title.format(username=self._client.user.username),
                description="\n".join(output),
                color=dis_snek.BrandColors.BLURPLE,
            )
            await ctx.reply(embeds=embed)

    async def _help_specific(self, ctx: dis_snek.MessageContext, cmd_name: str) -> None:
        cmds = await self._gather(ctx)

        if cmd := cmds.get(cmd_name.lower()):
            _temp = self._generate_command_string(cmd, ctx)
            _temp += f"\n{cmd.help}"
            await ctx.reply(self._sanitise_mentions(_temp))
        else:
            await ctx.reply(self.not_found_message.format(cmd_name=cmd_name))

    async def _gather(self, ctx: dis_snek.MessageContext | None = None) -> dict[str, molter.MolterCommand]:
        """
        Gather commands based on the rules set out in the class attribs

        args:
            ctx: The context to use to establish usability

        returns:
            dict[str, MolterCommand]: A list of commands fit the class attrib configuration
        """
        out: dict[str, molter.MolterCommand] = {}

        for cmd in self._client.commands.values():
            cmd: molter.MolterCommand

            if not cmd.enabled and not self.show_disabled:
                continue

            if cmd == self.cmd and not self.show_self:
                continue

            elif cmd.hidden and not self.show_hidden:
                continue

            if ctx and cmd.checks and not self.run_checks:
                # cmd._can_run would check the cooldowns, we don't want that so manual calling is required
                for _c in cmd.checks:
                    if not await _c(ctx):
                        continue

                if cmd.scale and cmd.scale.scale_checks:
                    for _c in cmd.scale.scale_checks:
                        if not await _c(ctx):
                            continue

            out[cmd.qualified_name] = cmd

        return out

    def _sanitise_mentions(self, text: str) -> str:
        """
        Replace mentions with a format that won't ping or look weird in code blocks.

        args:
            The text to sanitise
        """
        mappings = {
            "@everyone": "@\u200beveryone",
            "@here": "@\u200bhere",
            f"<@{self._client.user.id}>": f"@{self._client.user.username}",
            f"<@!{self._client.user.id}>": f"@{self._client.user.username}",
        }
        for source, target in mappings.items():
            text = text.replace(source, target)

        return text

    def _generate_command_string(self, cmd: molter.MolterCommand, ctx: dis_snek.MessageContext) -> str:
        """
        Generate a string based on a command, class attributes, and the context.

        args:
            cmd: The command in question
            ctx:
        """
        _temp = f"`{ctx.prefix if self.show_prefix else ''}{cmd.qualified_name}`"

        if cmd.aliases and self.show_aliases:
            _temp += "|" + "|".join([f"`{a}`" for a in cmd.aliases])

        if cmd.params and self.show_params:
            for param in cmd.params:
                wrapper = ("[", "]") if param.optional else ("<", ">")
                _temp += f" `{wrapper[0]}{param.name}{wrapper[1]}`"

        return _temp