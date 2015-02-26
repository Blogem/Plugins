from cloudbot import hook
from cloudbot.util import timeformat, formatting, botvars

import time
import re

CAN_DOWNVOTE = True

from sqlalchemy import Table, Column, Integer, Float, String, PrimaryKeyConstraint
from sqlalchemy import select

karma_table = Table(
    'karma',
    botvars.metadata,
    Column('nick_vote', String),
    Column('up_karma', Integer, default=0),
    Column('down_karma', Integer, default=0),
    Column('total_karma', Integer, default=0),
    PrimaryKeyConstraint('nick_vote')
)

voter_table = Table(
    'karma_voters',
    botvars.metadata,
    Column('voter', String),
    Column('votee', String),
    Column('timestamp', Float),
    PrimaryKeyConstraint('voter', 'votee')
)


def up(db, nick_vote):
    query = karma_table.update().values(
        up_karma=karma_table.c.up_karma + 1,
        total_karma=karma_table.c.total_karma + 1
    ).where(karma_table.c.nick_vote == nick_vote.lower())
    db.execute(query)
    db.commit()


def down(db, nick_vote):
    query = karma_table.update().values(
        down_karma=karma_table.c.down_karma + 1,
        total_karma=karma_table.c.total_karma - 1
    ).where(karma_table.c.nick_vote == nick_vote.lower())
    db.execute(query)
    db.commit()


def allowed(db, nick, nick_vote):
    time_restriction = 3600.0

    db.execute(voter_table.delete().where((time.time() - voter_table.c.timestamp) >= time_restriction))
    db.commit()

    check = db.execute(
        select([voter_table.c.timestamp])
        .where(voter_table.c.voter == nick.lower())
        .where(voter_table.c.votee == nick_vote.lower())
    ).scalar()

    if check:
        print(check)
        if time.time() - check >= time_restriction:
            db.execute("""INSERT OR REPLACE INTO karma_voters(
                       voter,
                       votee,
                       timestamp) values(:voter, :votee, :timestamp)""",
                       {'voter': nick.lower(), 'votee': nick_vote.lower(), 'timestamp': time.time()})
            db.commit()
            return True, 0
        else:
            return False, timeformat.time_until(check, now=time.time() - time_restriction)
    else:
        db.execute("""INSERT OR REPLACE INTO karma_voters(
                   voter,
                   votee,
                   timestamp) values(:voter, :votee, :timestamp)""",
                   {'voter': nick.lower(), 'votee': nick_vote.lower(), 'timestamp': time.time()})
        db.commit()
        return True, 0

karma_re = re.compile('^([a-z0-9_\-\[\]\\^{}|`]+)(\+\+|\-\-)$', re.I)


@hook.regex(karma_re)
def karma_add(match, nick, db, notice):
    nick_vote = match.group(1).strip().replace("+", "")
    if nick.lower() == nick_vote.lower():
        return "You can't vote on yourself!"
        return
    if len(nick_vote) < 1 or " " in nick_vote:
        return  # ignore anything below 3 chars in length or with spaces

    vote_allowed, when = allowed(db, nick, nick_vote)
    if vote_allowed:
        if match.group(2) == '++':
            db.execute("""INSERT or IGNORE INTO karma(
                       nick_vote,
                       up_karma,
                       down_karma,
                       total_karma) values(:nick,0,0,0)""", {'nick': nick_vote.lower()})
            db.commit()
            up(db, nick_vote)
            return "Gave {} 1 karma!".format(nick_vote)
        if match.group(2) == '--' and CAN_DOWNVOTE:
            db.execute("""INSERT or IGNORE INTO karma(
                       nick_vote,
                       up_karma,
                       down_karma,
                       total_karma) values(:nick,0,0,0)""", {'nick': nick_vote.lower()})
            db.commit()
            down(db, nick_vote)

            return "Took away 1 karma from {}.".format(nick_vote)
        else:
            return
    else:
        return "You are trying to vote too often. You can vote on this user again in {}!".format(when)


@hook.command('karma', 'k')
def karma(text, chan, db):
    """k/karma <nick> | list -- returns karma stats for <nick>. list returns top 5 karma."""

    if not chan.startswith('#'):
        return

    nick_vote = text

    if nick_vote != "list":

        query = db.execute(
            select([karma_table])
            .where(karma_table.c.nick_vote == nick_vote.lower())
        ).fetchall()

        if not query:
            return "That user has no karma."
        else:
            query = query[0]
            karma_text = formatting.pluralize(query['up_karma'] - query['down_karma'], 'karma point')
            return "{} has {}.".format(nick_vote, karma_text)
    else:
        query = db.execute(
            select([karma_table]).order_by(karma_table.c.total_karma.desc()).limit(5)
        ).fetchall()

        if not query:
            return "No karma registered yet."
        else:
            output = "Five users with most karma:"
            for q in query:
                total_karma = str(q['total_karma'])
                nick_vote = str(q['nick_vote'])
                output += "\n" + nick_vote + " has " + total_karma + " karma."

            return output
