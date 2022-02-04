import discord
import sqlite3
import re

from prettytable import PrettyTable

client = discord.Client()

con = sqlite3.connect('wordledb.db')
cur = con.cursor()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))
    for server in client.guilds:
        print('Connected to server: {0.id}'.format(server))


@client.event
async def on_message(message):

    user_id = message.author.id
    server_id = message.guild.id
    user = await get_user(user_id)

    # Help
    if message.content.startswith("!help"):
        content = "```\nCommands:\n\n!help: Display this message...\n\n!avg: Returns your average score\n\n!leaderboard: Displays the full leaderboard\n\n!lb: Displays a smaller leaderboard that looks better on mobile\n\n!streak: Displays your current win streak\n```"
        await message.channel.send(content=content)


    # Average
    if message.content.startswith("!avg"):
        print("Command: !avg, User: {0}".format(user_id))
        avg_score, n = get_avg_score(user_id, server_id)
        if n == 0:
            await message.channel.send(content="{0} hasn't submitted any scores on this server yet.".format('<@{0}>'.format(user_id)))
        else:
            await message.channel.send(content="{0} has an average score of {1:.2f} with {2} scores submitted!".format('<@{0}>'.format(user_id), avg_score, n))


    # Leaderboard
    elif message.content.startswith("!leaderboard") or message.content.startswith("!lb"):
        print("Command: !leaderboard, User: {0}".format(user_id))

        leaderboard = get_leaderboard(server_id)

        command = "!leaderboard" if message.content.startswith("!leaderboard") else "!lb"

        table = PrettyTable()

        if command == "!leaderboard":
            table.field_names = ["Rank", "User", "Average Score", "Successes", "Failures", "Current Streak"]
        else:
            table.field_names = ["Rank", "User", "Average Score"]


        table.align["User"] = 'l'

        i = 1
        for user_id, score in leaderboard:
            n = get_num_scores(user_id, server_id)
            f = get_num_failed(user_id, server_id)
            streak = get_current_streak(user_id, server_id)
            user_obj = await get_user(user_id)

            # If the user only has failed scores skip them lol
            if n == 0:
                continue

            row = [i, user_obj.display_name, "{:.2f}".format(score)]
            if command == "!leaderboard":
                row = row + [n, f, streak]

            table.add_row(row)
            i += 1


        await message.channel.send(content='Leaderboard:\n```\n'+table.get_string()+'\n```')


    # Streak
    if message.content.startswith("!streak"):
        print("Command: !streak, User: {0}".format(user_id))
        streak = get_current_streak(user_id, server_id)
        await message.channel.send(content='<@{0}> has a current win streak of {1}!'.format(user_id, streak))


    # Non command message, try to parse for score submission
    else:
        try:
            success, day, score = parse_message_for_score(message.content.splitlines()[0])
            if success:
                print("Adding score for user: {0}".format(user_id))
                if score_already_exists(user_id, day, server_id):
                    await message.add_reaction('\N{OK HAND SIGN}')
                else:
                    add_score(user_id, int(day), int(score), server_id)
                    await message.add_reaction('\N{THUMBS UP SIGN}')
        except:
            pass


# Returns the user object given their ID
async def get_user(user_id):
    user = await client.fetch_user(user_id)
    return user


# Parses a message to see if it's a Wordle score submission
def parse_message_for_score(message):
    m = re.match("^Wordle \d+ ([0-6]|X)\/6", message)
    if m:
        wordle_score = m.group(0).split(" ")
        day = wordle_score[1]
        score = wordle_score[2][0]
        if score == 'X':
            score = -1

        return True, day, score
    return False, 0, 0


# Adds the score to the DB
def add_score(user_id, day, score, server_id):
    cur.execute(
            'INSERT INTO scores VALUES ({0}, {1}, {2}, {3});'.format(user_id, day, score, server_id))
    con.commit()


# Gets non failed scores for a given user & server
def get_scores(user_id, server_id):
    res = cur.execute('SELECT * FROM scores WHERE user_id={0} AND server_id={1} AND score>-1 ORDER BY 2 desc;'.format(user_id, server_id))
    return res.fetchall()


# Gets all scores for a given user & server
def get_all_scores(user_id, server_id):
    res = cur.execute('SELECT * FROM scores WHERE user_id={0} AND server_id={1} ORDER BY 2 desc;'.format(user_id, server_id))
    return res.fetchall()


# Gets the users current streak
# It's kinda bugged since if a user goes on a 10 win streak then stops submitting, it will still say their streak is 10
# Too lazy, don't care enough about fixing this since it would include keeping track of the current day
def get_current_streak(user_id, server_id):
    scores = get_all_scores(user_id, server_id)

    if len(scores) == 0:
        return 0
    if len(scores) == 1:
        return 1
    if scores[0][2] == -1:
        return 0

    streak = 1
    prev = scores[0][1]
    for row in scores[1:]:
        if row[2] == -1:
            break
        if row[1] == prev - 1:
            streak += 1
            prev = row[1]

    return streak


# Gets the number of sucessful scores submitted for a given user & server
def get_num_scores(user_id, server_id):
    return len(get_scores(user_id, server_id))

# Gets the number of failed scores submitted for a given user & server
def get_num_failed(user_id, server_id):
    for row in cur.execute('SELECT count(*) FROM scores WHERE user_id={0} AND server_id={1} AND score=-1'.format(user_id, server_id)):
        return row[0]


# Returns some leaderboard info like avg score for a given server
def get_leaderboard(server_id):
    avg_scores = cur.execute('SELECT user_id, AVG(score) from scores where server_id={0} and score>=1 GROUP BY user_id;'.format(server_id))
    leaderboard = sorted(avg_scores, key=lambda x: x[1])
    return leaderboard


# Checks if a submitted score already exists for a given user, day, and server
def score_already_exists(user_id, day, server_id):
    res = cur.execute('SELECT * from scores where user_id={0} AND server_id={1} and day={2}'.format(user_id, server_id, day))
    return len(res.fetchall()) > 0


# Get the average score for a user 
def get_avg_score(user_id, server_id):
    res = cur.execute('SELECT AVG(score), count(*) FROM scores WHERE user_id={0} and score>-1 and server_id={1};'.format(user_id, server_id))
    return res.fetchall()[0]

client.run('<discord app_id>')
