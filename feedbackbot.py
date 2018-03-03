import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import logging
import os

# constants
MESSAGE_START_CONFIRMED = 'Okay. Asking feedback from <@{}> to <@{}>.'
MESSAGE_WRONG_FORMAT = 'Wrong usage of command.'
MESSAGE_NOT_A_COMMAND_ADMIN = 'Sorry, I can\'t recognize that command.'
MESSAGE_NOT_A_COMMAND_NOTADMIN = 'Hi! There is no feedback session currently, we will let you know when it is.'
MESSAGE_START_USAGE = 'Try `start @giver @receiver`!'
MESSAGE_ASK_FOR_FEEDBACK = ('Hi! It\'s feedback time! Please write your feedback to <@{}>! '
                            'Be specific, extended and give your feedback on behavior. '
                            'And don\'t forget to give more positive feedback than negative!')
MESSAGE_FEEDBACK_CONFIRMED = 'You\'ve given <@{}> the following feedback: {}. Thank you!'
MESSAGE_GOT_FEEDBACK = 'You got the following feedback from <@{}>: {}'
LOG_GOT_MESSAGE = 'Got message from user {}: {}'
LOG_SENDING_MESSAGE = 'Sending message to user {}: {}'
ENVVAR_TOKEN = 'FEEDBACKBOT_TOKEN'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('feedbackbot')

class MemberNotFound(Exception):
    pass


# global variables
client = Bot(description="feedbackbot by Sly (test version)",
             command_prefix="", pm_help=False)
database = {
        'members-asked': {},
        'feedbacks': {}
    }


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


def get_member_by_username(username_string):
    """Returns the Member object if it's found on any of the servers the bot is connected to.
    Otherwise, raises an exception."""

    # username and discriminator like @szilveszter.erdos#7945
    elements = username_string.strip('@').split('#')
    username = elements[0]
    if len(elements) > 1:
        discriminator = elements[1]
    else:
        discriminator = ''

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
    return await client.change_presence(game=discord.Game(name='Feedback game ;)'))


@client.event
async def on_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return
    elif is_admin(message.author.id):
        if message.content.startswith('start'):
            msg_elements = message.content.split()
            # because usage is `start @giver @receiver`
            if len(msg_elements) == 3:
                try:
                    giver = get_member_by_username(msg_elements[1])
                    receiver = get_member_by_username(msg_elements[2])
                    msg = MESSAGE_START_CONFIRMED.format(
                        giver.id, receiver.id)

                    # asking for feedback
                    msg2 = MESSAGE_ASK_FOR_FEEDBACK.format(receiver.id)
                    logger.info(LOG_SENDING_MESSAGE.format(giver.name, msg2))
                    await client.send_message(giver, msg2)
                    database['members-asked'][giver.id] = {'receiver': receiver}

                except MemberNotFound as e:
                    msg = str(e)
            else:
                msg = MESSAGE_WRONG_FORMAT + ' ' + MESSAGE_START_USAGE
        else:
            msg = MESSAGE_NOT_A_COMMAND_ADMIN + ' ' + MESSAGE_START_USAGE
    else:
        if message.author.id in database['members-asked']:
            giver = message.author
            # if there is no feedback for this receiver yet, create list
            receiver = database['members-asked'][giver.id]['receiver']
            if receiver.id not in database['feedbacks']:
                database['feedbacks'][receiver.id] = []
            
            database['feedbacks'][receiver.id].append(
                {
                    'giver': giver.id,
                    'message': message.content
                }
            )
            msg = MESSAGE_FEEDBACK_CONFIRMED.format(receiver.id, message.content)
            msg2 = MESSAGE_GOT_FEEDBACK.format(giver.id, database['feedbacks'][receiver.id][0]['message'])
            logger.info(LOG_SENDING_MESSAGE.format(receiver.name, msg2))
            await client.send_message(receiver, msg2)
            del database['members-asked'][giver.id]
        else:
            msg = MESSAGE_NOT_A_COMMAND_NOTADMIN
    logger.info(LOG_GOT_MESSAGE.format(message.channel.user.name, message.content))
    logger.info(LOG_SENDING_MESSAGE.format(message.channel.user.name, msg))
    await client.send_message(message.channel, msg)


if __name__ == '__main__':
    if ENVVAR_TOKEN in os.environ:
        token = os.environ.get(ENVVAR_TOKEN)
        client.run(token)
    else:
        print("Please define an environment variable named {} and put the secret token into it!".format(ENVVAR_TOKEN))