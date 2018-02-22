import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform

# constants
MESSAGE_START_CONFIRMED = 'Okay. Asking feedback from {} to {}.'
MESSAGE_WRONG_FORMAT = 'Wrong usage of command.'
MESSAGE_NOT_A_COMMAND_ADMIN = 'Sorry, I can''t recognize that command.'
MESSAGE_START_USAGE = 'Try `start @giver @receiver`!'
MESSAGE_NOT_A_COMMAND_NOTADMIN = 'Hi! There is no feedback session currently, we will let you know when it is.'

# custom exceptions
class MemberNotFound(Exception):
    pass

# basic info
client = Bot(description="feedbackbot by Sly (test version)",
             command_prefix="", pm_help=False)


def is_admin(user_id):
    """Checks whether the giver user is in the 'admins' role in any of the servers the bot is connected to."""
    for server in client.servers:
        for member in server.members:
            if member.id == user_id:
                for role in member.roles:
                    if role.name == 'admins':
                        return True
                return False
    return False


def get_member_by_username(username, discriminator):
    """Returns the Member object if it's found on any of the servers the bot is connected to.
    Otherwise, raises an exception."""
    for server in client.servers:
        for member in server.members:
            if member.name == username and member.discriminator == discriminator:
                return member
    raise MemberNotFound('Username `{}` not found.'.format(username))


@client.event
async def on_ready():
    """This is what happens everytime the bot launches. """
    print('Logged in as '+client.user.name+' (ID:'+client.user.id+') | Connected to ' +
          str(len(client.servers))+' servers | Connected to '+str(len(set(client.get_all_members())))+' users')
    print('--------')
    print('Current Discord.py Version: {} | Current Python Version: {}'.format(
        discord.__version__, platform.python_version()))
    print('--------')
    print('Use this link to invite {}:'.format(client.user.name))
    print('https://discordapp.com/oauth2/authorize?client_id={}&scope=bot&permissions=8'.format(client.user.id))

    # This is buggy, let us know if it doesn't work.
    return await client.change_presence(game=discord.Game(name='PLAYING STATUS HERE'))


@client.event
async def on_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return
    elif is_admin(message.author.id):
        if message.content.startswith('start'):
            msg_elements = message.content.split()
            # username and discriminator like @szilveszter.erdos#7945
            giver_elements = msg_elements[1].strip('@').split('#')
            receiver_elements = msg_elements[2].strip('@').split('#')
            # because usage is `start @giver @receiver`
            if len(msg_elements) == 3:
                try:
                    # TODO: check if there is a discriminator
                    giver = get_member_by_username(giver_elements[0], giver_elements[1])
                    receiver = get_member_by_username(receiver_elements[0], receiver_elements[1])
                    msg = MESSAGE_START_CONFIRMED.format(giver.mention, receiver.mention)
                except MemberNotFound as e:
                    msg = str(e)
                
                # TODO: asking for feedback
            else:
                msg = MESSAGE_WRONG_FORMAT + ' ' + MESSAGE_START_USAGE

        else:
            msg = MESSAGE_NOT_A_COMMAND_ADMIN + ' ' + MESSAGE_START_USAGE
    else:
        msg = MESSAGE_NOT_A_COMMAND_NOTADMIN
    await client.send_message(message.channel, msg)

client.run('NDE0NjY4NzM2MDc1NjYxMzIz.DWquiw.IDGdnR_vw6SYPbPs-7ZBVCk8H7Y')
