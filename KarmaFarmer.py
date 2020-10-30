"""
KarmaFarmer 2.0

Connects to links in reddit posts, finds a comment in the link, dresses it up and posts it back to Reddit
Dynamically scheduled: A custom timetable is set up according to minimum times to post and minimum time between posts
"""
import logging
import configparser
import time
import threading
import re
import requests
from threading import Lock
from os import listdir
from sys import stdout
from os.path import join
from os.path import exists
from os import mkdir, makedirs
from random import randrange, choice, randint
from datetime import datetime, timedelta
import schedule
from tweepy import OAuthHandler, API, Cursor
from bs4 import BeautifulSoup
from praw import Reddit

# ******************************************* Globals *******************************************

lock = Lock()

year = 1996
month = 9
day = 4
runtime = 0
entry_id = 0

thread_count = 0

# ******************************************* Helper functions *******************************************

def check_create_dir(dirname):
    '''
    Checks if directory exists and if it doesn't creates a new directory
    :param dirname: Path to directory
    '''
    if not exists(dirname):
        if '/' in dirname:
            makedirs(dirname)
        else:
            mkdir(dirname)


def finalize(textInput):
    '''
    Processes strings, changes synonyms
    :param textInput: Initial string
    :return: Processed string
    '''
    textInput = textInput.replace('you', choice(['you', 'u', 'u']))\
        .replace('lol', choice([' lol ',' haha ',' haha ']))\
        .replace('amazing', choice(['great', 'impressive']))\
        .replace(' video ', choice([' clip ', ' video ']))\
        .replace(', but', choice([', but', ', however']))\
        .replace(' god ', choice([' God ', ' god ']))\
        .replace(' problem ', choice([' issue ', ' problem ']))\
        .replace('this', choice(['this', 'that', 'this']))\
        .replace(' incredible ', choice(['amazing', 'awesome', 'incredible']))\
        .replace('person ', choice(['person', 'individual']))\
        .replace(' hated ', choice(['hated', 'despised']))\
        .replace('thanks', choice(['thanks', 'thank you']))\
        .replace('Thanks', choice(['Thanks', 'Thank you']))\
        .replace('money', choice(['money', 'cash']))\
        .replace(' he is ', choice([' he\'s ', ' he is ']))\
        .replace('he\'s', choice([' he\'s ', ' he i s']))\
        .replace(' she\'s ', choice([' she\'s ', ' she is ']))\
        .replace(' she is ', choice([' she\'s ', ' she is ']))\
        .replace(' it\'s ', choice([' it\'s ', ' it is ']))\
        .replace(' it is ', choice([' it\'s ', ' it is ']))
    if 'donald' not in textInput.lower():
        textInput = textInput.replace('Trump', choice(['The President', 'Trump']))\
            .replace('trump', choice(['the president', 'trump']))
    if textInput.lower().rstrip() != 'first':
        
        return textInput
    else:
        raise Exception("Annoying First Comment -- Ignore!")


def noEmoji(text):
    '''
    Removes emojis from string
    :param text: initial string
    :return: Processed string
    '''
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"  # emoticons
                               u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                               u"\U0001F680-\U0001F6FF"  # transport & map symbols
                               u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                               "]+", flags=re.UNICODE)
    newText = emoji_pattern.sub(r'', text) # no emoji
    finalText = re.sub('https:\/\/t.co\/\S*( |$)', '', newText)
    return finalText


def spider(url):
    '''
    processes url
    :param url: initial url
    :return: processed url
    '''
    source_code = requests.get(url)
    plain_text = source_code.text
    soup = BeautifulSoup(plain_text, "html.parser")
    x = soup.prettify()
    x = str(x)
    x = x.replace("\\u003cb\\u003e", " ")
    x = x.replace("\\u003c/b\\u003e", " ")
    x = x.replace("\\u003cbr /\\u003e", " ")
    return x


def getIND(url):

    '''
    Gets comments from comment sections in articles thendependent.uk
    :param url: link to article
    :return: randomized comment, None if no comment found
    '''
    sid = url[url.index('.html')-8:-5]
    template = '''https://comments.us1.gigya.com/comments.getComments?categoryID=ArticleComments&streamID={}&includeSettings=true&threaded=true&includeStreamInfo=true&includeUserOptions=true&includeUserHighlighting=true&lang=en&ctag=comments_v2&APIKey=2_bkQWNsWGVZf-fA4GnOiUOYdGuROCvoMoEN4WMj6_YBq4iecWA-Jp9D2GZCLbzON4&cid=&source=showCommentsUI&sourceData=%7B%22categoryID%22%3A%22ArticleComments%22%2C%22streamID%22%3A%22a7788651%22%7D&sdk=js_7.2.40&authMode=cookie&format=jsonp&callback=gigya.callback&context=R1267091514'''.format(sid)
    rtext = requests.get(template).text
    found = re.findall('\"commentText\":.*",', rtext)
    if len(found) > 1:
        x=0
        ccom = choice(found)
        while 'you' in ccom.lower():
            if x > 50:
                
                raise Exception('No appropriate comments; avoiding loop!')
            ccom = choice(found)
            x+=1
        pproc = re.sub('\<[^>]*\>', '', ccom)
        pproc = pproc.strip('"commentText":')
        return pproc[2:-2]


def getTwitterReply(api, url):
    '''
    Gets a random reply from replies to a twitter post
    :param api: Twitter api handle
    :param url: url to post
    :return: Reply in srt, None if no comment found
    '''
    authName = url.split('.com/')[1].split('/status')[0]
    tweetID = api.get_status(url.split('status/')[1]).id
    results = [status for status in Cursor(api.search, q='@{}'.format(authName), since_id=tweetID)
               .items(10) if str(status.in_reply_to_status_id) == str(tweetID)]
    if len(results) == 0:
        
        return None
    filtered = [result.text for result in results if 'you' not in str(result.text).lower()]
    if len(filtered) == 0:
        
        return None
    farray = list()
    for pros in filtered:
        newPros = []
        for word in pros.split(' '):
            if '@' not in word:
                newPros.append(word)
        if ' '.join(newPros).replace(' ','') != '':
            farray.append(' '.join(newPros))
    return choice(farray)


def getYT(website):
    '''
    Gets a random comment from youtube video (Only if total comments exceed 60)
    :param website: Link to video
    :return: Comment in str, None if no comments found
    '''
    index = website.index('=')
    end_dex = len(website)
    if any(key in website for key in '&'):
        end_dex = website.index('&')
    video_id = (website[index+1:end_dex])
    template = 'https://www.googleapis.com/youtube/v3/commentThreads?part=snippet&maxResults=100&order=relevance&videoId=variable&key=AIzaSyBdtDtCgUBBIu8BmrxbNQLNRsm2DKh8ix4'
    final = template.replace("variable", video_id)
    x = spider(final)
    top_comment = re.findall('"textDisplay":.*",', x)
    alength = len(top_comment)
    if alength > 60:
        top_comment = top_comment[randrange(40, len(top_comment)-1)].strip('"textDisplay":')
        top_comment = top_comment[2:len(top_comment)-2]
        
        return top_comment
    else:
        return None


def getWP(url):
    '''
    Gets random comment from comment section of Washington Post
    :param url: link to article
    :return: comment in str, None if no comment found
    '''
    ourl = url.split('?')[0].strip('https').strip('http').replace('://', '').strip(':').replace('/', '%2F')
    template = '''https://comments-api.ext.nile.works/v2/mux?appkey=prod.washpost.com&requests=%5B%7B%22id%22%3A%22featuredPosts-search%22%2C%22method%22%3A%22search%22%2C%22q%22%3A%22((childrenof%3A+https%3A%2F%2F{url}+source%3Awashpost.com+(((state%3AUntouched++AND+user.state%3AModeratorApproved)+OR+(state%3AModeratorApproved++AND+user.state%3AModeratorApproved%2CUntouched)+OR+(state%3ACommunityFlagged%2CModeratorDeleted+AND+user.state%3AModeratorApproved)+)++AND+(+markers%3A+featured_comment++-markers%3Aignore+)+)+++))+itemsPerPage%3A+15+sortOrder%3AreverseChronological+safeHTML%3Aaggressive+children%3A+2+childrenSortOrder%3Achronological+childrenItemsPerPage%3A3++(((state%3AUntouched++AND+user.state%3AModeratorApproved)+OR+(state%3AModeratorApproved++AND+user.state%3AModeratorApproved%2CUntouched)+OR+(state%3ACommunityFlagged%2CModeratorDeleted+AND+user.state%3AModeratorApproved)+)++AND+(+markers%3A+featured_comment++-markers%3Aignore+)+)+%22%7D%2C%7B%22id%22%3A%22allPosts-search%22%2C%22method%22%3A%22search%22%2C%22q%22%3A%22((childrenof%3A+https%3A%2F%2F{url}+source%3Awashpost.com+(((state%3AUntouched++AND+user.state%3AModeratorApproved)+OR+(state%3AModeratorApproved++AND+user.state%3AModeratorApproved%2CUntouched)+OR+(state%3ACommunityFlagged%2CModeratorDeleted+AND+user.state%3AModeratorApproved)+)+)+++))+itemsPerPage%3A+15+sortOrder%3AreverseChronological+safeHTML%3Aaggressive+children%3A+2+childrenSortOrder%3Achronological+childrenItemsPerPage%3A3++(((state%3AUntouched++AND+user.state%3AModeratorApproved)+OR+(state%3AModeratorApproved++AND+user.state%3AModeratorApproved%2CUntouched)+OR+(state%3ACommunityFlagged%2CModeratorDeleted+AND+user.state%3AModeratorApproved)+)+)+%22%7D%5D'''.format(
        url=ourl)
    rtext = str(requests.get(template).text)
    found = re.findall('\"content\":.*",', rtext)
    if len(found) > 20:
        found = [f for f in found[10:] if 'you' not in f.lower()]
        comment = found[randrange(0, len(found) - 1)].strip('"content":')
        comment = comment[2:-2]
        return re.sub('\<[^>]*\>', '', comment)
    else:
        return None


def validate_entry(user, p_url, p_id):
    '''
    Validates if entry has been visited before
    :param user: username of reddit account
    :param p_url: post url
    :param p_id: post id
    :return: true if record exists, false if new record
    '''
    return p_url not in open('cache/{}.txt'.format(user), 'r').read().split('\n')\
           and p_id not in open('cache/{}.txt'.format(user), 'r').read().split('\n')\



def add_cache(user, p_url, p_id):
    '''
    Adds new record to cache
    :param user: username of reddit account
    :param p_url: post url
    :param p_id: post id
    '''
    open('cache/{}.txt'.format(user), 'a').write(p_url + '\n')
    open('cache/{}.txt'.format(user), 'a').write(p_id + '\n')


def leaveRandom(chc, r_user, rdt_a, twt_a):
    '''
    Commenting logic
    :param chc: Platform choice
    :param r_user: Reddit username
    :param rdt_a: Reddit API handle
    :param twt_a: Twitter API handle
    :return: True if successful comment, false if unsuccessful
    '''
    logger = logging.getLogger(__name__ + '.leaverandom')
    logger.info('Posting from: {}'.format(chc))
    limit = 100
    if chc == 'ind':
        for post in rdt_a.domain('independent.co.uk').new(limit=limit):
            if validate_entry(r_user, post.url, post.id)\
               and time.time() - post.created_utc > 300 and\
               'auto' not in post.subreddit.display_name.lower():
                try:
                    comment = getIND(post.url)
                    if comment is None:
                        add_cache(r_user, post.url, post.id)
                        raise Exception('No comments found')
                    else:
                        post.reply(finalize(comment.replace('\\n', '\n').replace('\\', '')))
                        logger.info("Successfully posted comment")
                        add_cache(r_user, post.url, post.id)
                        return True
                except Exception as exc:
                    logger.error('Was not able to post comment: {}'.format(exc))
                    return False
    elif chc == 'tw':
        for post in rdt_a.domain('twitter.com').new(limit=limit):
            if validate_entry(r_user, post.url, post.id)\
               and time.time() - post.created_utc > 100\
               and 'auto' not in post.subreddit.display_name.lower():
                try:
                    comment = getTwitterReply(twt_a, post.url)
                    if comment is None:
                        add_cache(r_user, post.url, post.id)
                        raise Exception('No comments found')
                    else:
                        tocomment = noEmoji(comment)
                        if 'href' not in tocomment:
                            post.reply(finalize(tocomment))
                        add_cache(r_user, post.url, post.id)
                        logger.info("Successfully posted comment")
                        return True
                except Exception as e:
                    logger.error('Was not able to post comment: {}'.format(e))
                    return False
    elif chc == 'yt':
        for post in rdt_a.domain('youtube.com').new(limit=limit):
            if validate_entry(r_user, post.url, post.id)\
               and time.time() - post.created_utc > 300\
               and 'auto' not in post.subreddit.display_name.lower():
                try:
                    comment = getYT(post.url)
                    if comment is None:
                        add_cache(r_user, post.url, post.id)
                        raise Exception('No comments found')
                    else:
                        tocomment = noEmoji(comment.replace('\\n', '\n').replace('\\', ''))
                        if 'href' not in tocomment:
                            post.reply(finalize(tocomment))
                        logger.info("Successfully posted comment")
                        add_cache(r_user, post.url, post.id)
                        return True
                except Exception as exc:
                    logger.error('Was not able to post comment: {}'.format(exc))
                    return False
    elif chc == 'wp':
        for post in rdt_a.domain('washingtonpost.com').new(limit=limit):
            if validate_entry(r_user, post.url, post.id)\
               and time.time() - post.created_utc > 300\
               and 'auto' not in post.subreddit.display_name.lower():
                try:
                    print(post.url)
                    # post.reply(finalize(getWP(post.url).replace('\\n','\n').replace('\\','')))
                    add_cache(r_user, post.url, post.id)
                    logger.info("Successfully posted comment")
                    return True
                except Exception as exc:
                    logger.error('Was not able to post comment: {}'.format(exc))
                    return False


def process_entries():
    '''
    Loops through entries in  the folder Entries
    :return: Two dictionaries; scheduler with scheduling data and socials with Reddit and Twitter credentials
    '''
    logger = logging.getLogger(__name__ + '.process_entries')
    logger.debug('Module called')
    global entry_id
    for entry in listdir('Entries'):
        entry_id += 1
        entry_reader = configparser.ConfigParser()
        entry_reader.read(join('Entries', entry))
        try:
            min_times = int(entry_reader['scheduler']['min_times'])
            min_int = int(entry_reader['scheduler']['min_interval'])
            r_client_id = entry_reader['reddit']['client_id']
            r_client_secret = entry_reader['reddit']['client_secret']
            r_user_agent = entry_reader['reddit']['user_agent']
            r_username = entry_reader['reddit']['username']
            r_password = entry_reader['reddit']['password']
            t_con_key = entry_reader['twitter']['consumer_key']
            t_con_secret = entry_reader['twitter']['consumer_secret']
            t_key = entry_reader['twitter']['key']
            t_secret = entry_reader['twitter']['secret']
        except KeyError:
            logger.error('Could not get data from {0}. Ignoring entry'.format(entry))
            continue
        scheduler = {'min_times': min_times, 'min_int': min_int}
        socials = {'entry_id': entry_id, 'reddit_client_id': r_client_id, 'reddit_client_secret': r_client_secret,
                   'reddit_user_agent': r_user_agent, 'reddit_username': r_username, 'reddit_password': r_password,
                   'twitter_consumer_key': t_con_key, 'twitter_consumersecret': t_con_secret, 'twitter_key': t_key,
                   'twitter_secret': t_secret}
        yield (scheduler, socials)


def run_threaded(*args):
    '''
    Spins new thread
    :param args: Reddit and Twitter credentials
    '''
    # Spins threads and calls posting function
    global thread_count
    logger = logging.getLogger(__name__ + '.run_threaded')
    logger.debug('Module called')
    entry = dict()
    for key, value in args[0].items():
        entry[key] = value
    thread_count += 1
    logger.info('Creating thread...')
    job_thread = threading.Thread(target=init_comment, args=args, name='Poster{0}-{1}'.format(entry['entry_id'], thread_count))
    job_thread.start()


def init_comment(*args):
    '''
    Creates cache directory, creates specific cache file, logs in to Reddit and Twitter and initializes leaveRandom
    :param args: Reddit and Twitter credentials
    '''
    entry = dict()
    logger = logging.getLogger(__name__ + '.init_comment')
    logger.info('Getting args...')
    for key, value in args[0].items():
        entry[key] = value
    logger.info('Initializing files...')
    check_create_dir('cache')
    print('directory created')
    open('cache/{}.txt'.format(entry['reddit_username']), 'w')
    logger.info('Logging in with credentials...')
    r = Reddit(
        client_id=entry['reddit_client_id'],
        client_secret=entry['reddit_client_secret'],
        password=entry['reddit_password'],
        user_agent=entry['reddit_user_agent'],
        username=entry['reddit_username'],
    )
    auth = OAuthHandler(entry['twitter_consumer_key'], entry['twitter_consumersecret'])
    auth.set_access_token(entry['twitter_key'], entry['twitter_secret'])
    api = API(auth)
    logger.info('Starting commenting...')
    tries = 5
    posted = leaveRandom(choice(['ind', 'tw', 'yt']), entry['reddit_username'], r, api)
    while not posted and tries > 0:
        tries -= 1
        logger.info('Retrying comment. Tries left: {}'.format(tries))
        posted = leaveRandom(choice(['ind', 'tw', 'yt']), entry['reddit_username'], r, api)
    if tries == 0:
        logger.error('Maximum tries exceeded. Ignoring post')
    return schedule.CancelJob


# ******************************************* Control logic *******************************************
if __name__ == '__main__':
    print('--------------------------------------- Karma Farmer ---------------------------------------')

    print('Reading Master config')
    # init config
    config = configparser.ConfigParser()
    config.read('masterconfig.ini')
    runtime = int(config['operation']['runtime'])
    stop_time = config['operation']['stop_time'].split(',')
    debug = config.getboolean('debug', 'debugMode')
    print('Config OK')

    # Init logging
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    consoleHandler = logging.StreamHandler(stdout)
    consoleHandler.setFormatter(logging.Formatter('[%(threadName)s]-[%(name)s] - %(levelname)s - %(message)s'))
    check_create_dir('logs')
    fileHandler = logging.FileHandler(
        join('logs', 'Scraper{0}.log'.format(datetime.now().strftime('%d-%m-%y-%H-%M-%S'))))
    fileHandler.setFormatter(logging.Formatter('%(asctime)s:[%(threadName)s]-[%(name)s] - %(levelname)s - %(message)s'))
    consoleHandler.setLevel(logging.INFO)
    rootLogger.addHandler(consoleHandler)
    fileHandler.setLevel(logging.DEBUG)
    rootLogger.addHandler(fileHandler)

    if debug:
        # Debug mode
        consoleHandler.setLevel(logging.DEBUG)
        rootLogger.debug('Debug mode activated. Ignoring scheduling routine')
        for scheduler, socials in process_entries():
            run_threaded(socials)
    else:
        # Dynamic scheduling routine
        for scheduler, socials in process_entries():
            min_int = 0
            interval_offset = scheduler['min_int']
            min_times = scheduler['min_times']
            rootLogger.debug('{0}: min_times = {1}'.format(socials['entry_id'], min_times))
            max_times = int(runtime / (min_int + interval_offset))
            rootLogger.debug('{0}: max_times = {1}'.format(socials['entry_id'], max_times))
            blanktime = datetime(year=year, month=month, day=day, hour=0, minute=0)
            times = randint(min_times, max_times)
            rootLogger.debug('{0}: times = {1}'.format(socials['entry_id'], times))
            int_multiplier = int(runtime / times)
            max_int = int_multiplier
            rootLogger.debug('{0}: max_int init = {1}'.format(socials['entry_id'], timedelta(minutes=max_int)))
            for i in range(1, times + 1):
                new_int = timedelta(minutes=randint(min_int + interval_offset, max_int))
                new_time = blanktime + new_int
                rootLogger.info('scheduled {entry} at {hour}:{min}'.format(entry=socials['entry_id'],
                                                                           hour=new_time.strftime('%H'),
                                                                           min=new_time.strftime('%M')))
                schedule.every().day.at(new_time.strftime('%H:%M')).do(run_threaded, socials)
                min_int = int(new_int.seconds / 60)
                rootLogger.debug('{0}: New min_int = {1}'.format(socials['entry_id'], timedelta(minutes=min_int)))
                max_int = int_multiplier * (i + 1)
                rootLogger.debug('{0}: New max_int = {1}'.format(socials['entry_id'], timedelta(minutes=max_int)))
        # Schedule execution loop
        rootLogger.info('Starting thread executions...')
        now = datetime.now()
        while now.hour != int(stop_time[0]) or now.minute > int(stop_time[1]):
            schedule.run_pending()
            time.sleep(1)
            now = datetime.now()
        rootLogger.info('Stop time reached. Exiting script')
