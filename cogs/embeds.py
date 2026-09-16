import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re


class EditModal(Modal):
    def __init__(self, field_name, current_value, on_submit_callback):
        super().__init__(title=f"Edit {field_name}")
        self.field_name = field_name
        self.on_submit_callback = on_submit_callback

        self.value_input = TextInput(
            label=f"New {field_name}",
            default=current_value or "",
            style=discord.TextStyle.paragraph if field_name == "Description" else discord.TextStyle.short,
            required=False,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.value_input.value)


class EmbedEditor(View):
    def __init__(
        self,
        embed: discord.Embed,
        original_interaction: discord.Interaction,
        original_message: discord.Message = None,
    ):
        super().__init__(timeout=None)
        self.embed = embed
        self.original_interaction = original_interaction
        self.original_message = original_message

    async def interaction_check(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def update_preview(self, interaction: discord.Interaction):
        try:
            await interaction.message.edit(embed=self.embed, view=self)
        except:
            pass

    @discord.ui.button(label="General", emoji="<:blGeneral:1449512337643016504>", row=0)
    async def button_general(self, i, b):
        await i.response.send_modal(EditMainModal(self))

    @discord.ui.button(label="Images", emoji="<:blImage:1449500070742327298>", row=0)
    async def button_images(self, i, b):
        await i.response.send_modal(EditImagesModal(self))

    @discord.ui.button(label="Author", emoji="<:blAuthor:1449510979980492861>", row=0)
    async def button_author(self, i, b):
        await i.response.send_modal(AuthorModal(self))

    @discord.ui.button(label="Footer", emoji="<:blFooter:1449508664598593717>", row=0)
    async def button_footer(self, i, b):
        await i.response.send_modal(FooterModal(self))

    @discord.ui.button(label="Add Field", emoji="<:blAdd:1449508551176355930>", style=discord.ButtonStyle.primary, row=1)
    async def button_add_field(self, i, b):
        await i.response.send_modal(AddFieldModal(self))

    @discord.ui.button(label="Remove Field", emoji="<:blRemove:1449508621649051690>", style=discord.ButtonStyle.danger, row=1)
    async def button_remove_field(self, i, b):
        await i.response.send_modal(RemoveFieldModal(self))

    @discord.ui.button(label="Edit Field", emoji="<:blEdit:1449499754970218508>", style=discord.ButtonStyle.primary, row=1)
    async def button_edit_field(self, i, b):
        await i.response.send_modal(EditFieldModal(self))

    @discord.ui.button(label="Confirm", emoji="<a:blCheck:1449402971879116856>", style=discord.ButtonStyle.success, row=2)
    async def button_send(self, interaction: discord.Interaction, button: Button):
        if self.original_message:
            await self.original_message.edit(embed=self.embed)
        else:
            await interaction.channel.send(embed=self.embed)
        await interaction.message.delete()

    @discord.ui.button(label="Cancel", emoji="<a:blCross:1449403184232534198>", style=discord.ButtonStyle.danger, row=2)
    async def button_cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.message.delete()


class EditMainModal(Modal, title="General"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.title_input = TextInput(
            label="Title",
            default=parent.embed.title or "",
            required=False,
        )
        self.desc_input = TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            default=parent.embed.description or "",
            required=False,
        )
        self.color_input = TextInput(
            label="Color (hex)",
            default=f"#{parent.embed.color.value:06X}" if parent.embed.color else "",
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        e = self.parent.embed
        e.title = self.title_input.value or None
        e.description = self.desc_input.value or None
        c = self.color_input.value.strip()
        if c and re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", c):
            try:
                e.color = discord.Color(int(c.replace("#", ""), 16))
            except:
                pass
        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Main updated.", ephemeral=True)


class EditImagesModal(Modal, title="Images"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.thumb_input = TextInput(
            label="Thumbnail URL",
            default=parent.embed.thumbnail.url if parent.embed.thumbnail else "",
            required=False,
        )
        self.image_input = TextInput(
            label="Image URL",
            default=parent.embed.image.url if parent.embed.image else "",
            required=False,
        )
        self.add_item(self.thumb_input)
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        e = self.parent.embed
        thumb = self.thumb_input.value.strip()
        img = self.image_input.value.strip()

        if thumb.startswith("http"):
            try:
                e.set_thumbnail(url=thumb)
            except:
                pass
        else:
            e.set_thumbnail(url=None)

        if img.startswith("http"):
            try:
                e.set_image(url=img)
            except:
                pass
        else:
            e.set_image(url=None)

        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Images updated.", ephemeral=True)


class AuthorModal(Modal, title="Author"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.name_input = TextInput(
            label="Author Name",
            default=parent.embed.author.name if parent.embed.author else "",
            required=False,
        )
        self.icon_input = TextInput(
            label="Author Icon URL",
            default=parent.embed.author.icon_url if parent.embed.author else "",
            required=False,
        )
        self.add_item(self.name_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: discord.Interaction):
        icon = self.icon_input.value if self.icon_input.value.startswith("http") else None
        self.parent.embed.set_author(
            name=self.name_input.value or "\u200b",
            icon_url=icon,
        )
        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Author updated.", ephemeral=True)


class FooterModal(Modal, title="Footer"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.text_input = TextInput(
            label="Footer Text",
            default=parent.embed.footer.text if parent.embed.footer else "",
            required=False,
        )
        self.icon_input = TextInput(
            label="Footer Icon URL",
            default=parent.embed.footer.icon_url if parent.embed.footer else "",
            required=False,
        )
        self.add_item(self.text_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: discord.Interaction):
        icon = self.icon_input.value if self.icon_input.value.startswith("http") else None
        self.parent.embed.set_footer(
            text=self.text_input.value or "\u200b",
            icon_url=icon,
        )
        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Footer updated.", ephemeral=True)


class AddFieldModal(Modal, title="Add Field"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.name_input = TextInput(label="Field Name", required=False)
        self.value_input = TextInput(
            label="Field Value",
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.inline_input = TextInput(label="Inline (true/false)", required=False)
        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(self.inline_input)

    async def on_submit(self, interaction: discord.Interaction):
        inline = self.inline_input.value.strip().lower() == "true"
        self.parent.embed.add_field(
            name=self.name_input.value or "\u200b",
            value=self.value_input.value or "\u200b",
            inline=inline,
        )
        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Field added.", ephemeral=True)


class EditFieldModal(Modal, title="Edit Field"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.number_input = TextInput(label="Field Number", required=True)
        self.name_input = TextInput(label="New Field Name", required=False)
        self.value_input = TextInput(
            label="New Field Value",
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.inline_input = TextInput(label="Inline (true/false)", required=False)
        self.add_item(self.number_input)
        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(self.inline_input)

    async def on_submit(self, interaction: discord.Interaction):
        index = int(self.number_input.value) - 1
        f = self.parent.embed.fields[index]
        inline = (
            f.inline
            if self.inline_input.value == ""
            else self.inline_input.value.lower() == "true"
        )
        self.parent.embed.set_field_at(
            index,
            name=self.name_input.value or f.name,
            value=self.value_input.value or f.value,
            inline=inline,
        )
        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Field updated.", ephemeral=True)


class RemoveFieldModal(Modal, title="Remove Field"):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.number_input = TextInput(label="Field Number", required=True)
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent.embed.remove_field(int(self.number_input.value) - 1)
        await self.parent.update_preview(interaction)
        await interaction.response.send_message("✅ Field removed.", ephemeral=True)


class Embeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="embed_copy", description="Copy and edit an existing embed by its message ID.")
    @app_commands.checks.has_permissions(administrator=True)
    async def embed_copy(self, interaction: discord.Interaction, message_id: str):
        embed_to_copy = None
        for channel in interaction.guild.text_channels:
            try:
                message = await channel.fetch_message(int(message_id))
                if message.embeds:
                    embed_to_copy = message.embeds[0]
                    break
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        if not embed_to_copy:
            await interaction.response.send_message("❌ No embed found with that message ID.", ephemeral=True)
            return

        copied_embed = embed_to_copy.copy()
        view = EmbedEditor(copied_embed, interaction)
        await interaction.response.send_message("📝 Embed copied! You can edit it below:", embed=copied_embed, view=view)

    @app_commands.command(name="embed_create", description="Create a new interactive embed.")
    @app_commands.checks.has_permissions(administrator=True)
    async def embed_create(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Embed Builder", description="Use the buttons below to edit this embed.", color=discord.Color.blue())
        view = EmbedEditor(embed, interaction)
        await interaction.response.send_message("📝 New embed builder created! Edit it below:", embed=embed, view=view)

    @app_commands.command(name="embed_edit", description="Edit an existing embed by its message ID.")
    @app_commands.checks.has_permissions(administrator=True)
    async def embed_edit(self, interaction: discord.Interaction, message_id: str):
        embed_to_edit = None
        for channel in interaction.guild.text_channels:
            try:
                message = await channel.fetch_message(int(message_id))
                if message.embeds:
                    embed_to_edit = message.embeds[0]
                    break
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        if not embed_to_edit:
            await interaction.response.send_message("❌ No embed found with that message ID.", ephemeral=True)
            return

        copied_embed = embed_to_edit.copy()
        view = EmbedEditor(copied_embed, interaction, message)
        await interaction.response.send_message("📝 Editing existing embed! Modify it below:", embed=copied_embed, view=view)


async def setup(bot):
    await bot.add_cog(Embeds(bot))