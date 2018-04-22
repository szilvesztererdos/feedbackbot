import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import logging
import os
import pymongo
from urllib.parse import urlparse
from datetime import datetime

# constants
MESSAGE_START_CONFIRMED = 'Okay. Asking feedback from **{}** to **{}**.'
MESSAGE_WRONG_FORMAT = 'Wrong usage of command.'
MESSAGE_NOT_A_COMMAND_ADMIN = 'Sorry, I can\'t recognize that command.'
MESSAGE_NOT_A_COMMAND_NOTADMIN = 'Hi! There is no feedback session currently, we will let you know when it is.'
MESSAGE_START_USAGE = 'If you want to start a session, try `start @giver @receiver`!'
MESSAGE_ASK_FOR_FEEDBACK = ('Hi! It\'s feedback time! Please write your feedback to **{}**! '
                            'Be specific, extended and give your feedback on behavior. '
                            'And don\'t forget to give more positive feedback than negative!')
MESSAGE_FEEDBACK_CONFIRMED = 'You\'ve given **{}** the following feedback: {}. Thank you!'
MESSAGE_GOT_FEEDBACK = 'You got the following feedback from **{}**: {}'
MESSAGE_LIST_FEEDBACK = 'You have got the following feedback until now: \n{}'
MESSAGE_NO_FEEDBACK_AVAILABLE = 'Sorry, you haven''t got any feedback until now. Maybe you should ask for one? ;)'
LOG_GOT_MESSAGE = 'Got message from user {}: {}'
LOG_SENDING_MESSAGE = 'Sending message to user {}: {}'
ENVVAR_TOKEN = 'FEEDBACKBOT_TOKEN'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('feedbackbot')


class MemberNotFound(Exception):
    pass


class RoleOrMemberNotFound(Exception):
    pass

# global variables
client = Bot(description="feedbackbot by Sly (test version)",
             command_prefix="", pm_help=False)

mongodb_uri = os.environ.get('MONGODB_URI')
try:
    conn = pymongo.MongoClient(mongodb_uri)
    logger.info('Database connection successful.')
except pymongo.errors.ConnectionFailure as e:
    logger.error('Could not connect to MongoDB: {}'.format(e))

db = conn[urlparse(mongodb_uri).path[1:]]


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


def get_member_or_role(name_string):
    """Returns the member/mention or members of a role/mention in a list on any of the servers 
    the bot is connected to. Otherwise, raises an exception."""
    try:
        member = get_member_by_username(name_string)
        return [member], member.nick
    except MemberNotFound:
        members = []
        name_string = name_string.strip('@')
        for server in client.servers:
            for server_role in server.roles:
                if server_role.name == name_string:
                    # search for all members with that role
                    for member in server.members:
                        for member_role in member.roles:
                            if member_role == server_role:
                                members.append(member)
                                break
                    break
        if members:
            return members, '@' + server_role.name
        else:
            raise RoleOrMemberNotFound('Username or role `{}` not found.'.format(name_string))


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


async def send_msg(user, msg):
    """Sends a message to a user or channel and logs it. """
    logger.info(LOG_SENDING_MESSAGE.format(user, msg))
    await client.send_message(user, msg)


async def process_ask_queue(giver):
    next_to_ask = db['ask-queue'].find_one(
            {
                'id': giver.id,
                'status': 'to-ask'
            }
        )
    if next_to_ask:
        receiver_id = next_to_ask['receiver_id']
        receiver_nick = next_to_ask['receiver_nick']
        msg = MESSAGE_ASK_FOR_FEEDBACK.format(receiver_nick)
        await send_msg(giver, msg)
        db['ask-queue'].update(
            {
                'id': giver.id,
                'receiver_id': receiver_id
            },
            {
                '$set': {
                    'status': 'asked'
                }
            }
        )


def push_ask_queue(receiver, giver):
    db['ask-queue'].insert(
        {
            'id': giver.id,
            'giver_nick': giver.nick,
            'receiver_id': receiver.id,
            'receiver_nick': receiver.nick,
            'status': 'to-ask'
        }
    )


async def handle_start(message):
    """Handles the `start @giver @receiver` command issued by an admin and starts a
    feedback session. """
    msg_elements = message.content.split()
    # because usage is `start @giver @receiver`
    if len(msg_elements) == 3:
        # get member or role and confirm command
        try:
            givers, giver_mention = get_member_or_role(msg_elements[1])
            receivers, receiver_mention = get_member_or_role(msg_elements[2])
        except RoleOrMemberNotFound as e:
            msg = str(e)
            await send_msg(message.channel.user, msg)
        else:
            msg = MESSAGE_START_CONFIRMED.format(giver_mention, receiver_mention)
            await send_msg(message.channel.user, msg)

            # asking for feedback
            for giver in givers:
                for receiver in receivers:
                    if receiver is not giver:
                        push_ask_queue(receiver, giver)
                await process_ask_queue(giver)

    else:
        msg = MESSAGE_WRONG_FORMAT + ' ' + MESSAGE_START_USAGE
        await send_msg(message.channel.user, msg)


async def handle_list(message):
    """Handles `list` command and lists given feedback messages. """
    receiver_details = db['feedbacks'].find_one({'id': message.author.id})
    if receiver_details is not None:
        feedback_list = []
        for feedback in receiver_details['feedback']:
            feedback_list.append('**{}** ({:%Y.%m.%d. %H:%M}): {}\n'.format(
                feedback['giver_nick'], feedback['datetime'], feedback['message']))

        feedback_list_str = '\n'.join(feedback_list)
        msg = MESSAGE_LIST_FEEDBACK.format(feedback_list_str)
    else:
        msg = MESSAGE_NO_FEEDBACK_AVAILABLE
    await send_msg(message.channel.user, msg)


async def handle_send_feedback(message):
    """Handles feedback sent as an answer to the bot's question. """
    giver_details = db['ask-queue'].find_one({'id': message.author.id, 'status': 'asked'})
    giver_nick = giver_details['giver_nick']
    giver = message.author
    receiver_id = giver_details['receiver_id']
    receiver_nick = giver_details['receiver_nick']
    db['feedbacks'].update_one(
        {
            'id': receiver_id,
            'receiver_nick': receiver_nick
        },
        {
            '$push': {
                'feedback': {
                    'giver': giver.id,
                    'giver_nick': giver_nick,
                    'message': message.content,
                    'datetime': datetime.now()
                }
            }
        },
        upsert=True
    )

    # confirm feedback
    msg = MESSAGE_FEEDBACK_CONFIRMED.format(receiver_nick, message.content)
    await send_msg(message.channel.user, msg)

    # notify receiver
    received_feedbacks = db['feedbacks'].find_one({'id': receiver_id})['feedback']
    current_feedback = max(received_feedbacks, key=lambda feedback: feedback['datetime'])
    msg = MESSAGE_GOT_FEEDBACK.format(giver_nick, current_feedback['message'])
    await send_msg(await client.get_user_info(receiver_id), msg)
    db['ask-queue'].remove({'id': giver.id, 'receiver_id': receiver_id})
    await process_ask_queue(giver)


@client.event
async def on_message(message):
    """This is what happens every time when the bot sees a message. """
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return
    # we do not want the bot to reply not in a pm
    elif message.channel.type.name != 'private':
        return
    # admin starting the session
    elif message.content.startswith('start') and is_admin(message.author.id):
        await handle_start(message)
    # receiver listing feedback
    elif message.content.startswith('list'):
        await handle_list(message)
    # giver sending a feedback
    elif db['ask-queue'].find_one({'id': message.author.id, 'status': 'asked'}):
        await handle_send_feedback(message)
    # not matching any case
    else:
        if is_admin(message.author.id):
            msg = MESSAGE_NOT_A_COMMAND_ADMIN + ' ' + MESSAGE_START_USAGE
            await send_msg(message.channel, msg)
        else:
            msg = MESSAGE_NOT_A_COMMAND_NOTADMIN
            await send_msg(message.channel, msg)
    
    try:
        logger.info(LOG_GOT_MESSAGE.format(message.channel.user.name, message.content))
    except AttributeError:
        logger.info(LOG_GOT_MESSAGE.format(message.channel, message.content))


if __name__ == '__main__':
    if ENVVAR_TOKEN in os.environ:
        token = os.environ.get(ENVVAR_TOKEN)
        client.run(token)
    else:
        print("Please define an environment variable named {} and put the secret token into it!".format(ENVVAR_TOKEN))