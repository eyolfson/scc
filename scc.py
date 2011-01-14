from datetime import datetime
from time import sleep
import ConfigParser
import argparse
import codecs
import git
import os
import re
import threading
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.repositories import models

# Command line parser
parser = argparse.ArgumentParser(description='Source Control Correlator')
parser.add_argument("--author", action='store_true')
parser.add_argument("--config", default="linux.ini")
parser.add_argument("--debug", action='store_true')
parser.add_argument("--init-db", action='store_true')
parser.add_argument("--skip", action='store_true')
args = parser.parse_args()

# Config parsing
config = ConfigParser.RawConfigParser()
config.read(args.config)
repository_id = config.getint('repository', 'id')
repository_directory = config.get('repository', 'directory')
if not args.skip:
    fix_regex = re.compile(config.get('repository', 'regex'), re.I)

# Variables
django_repository = models.Repository.objects.get(pk=repository_id)
database_lock = threading.Lock()
git_cmd = git.Git(repository_directory)
repository = git.Repo(repository_directory)
repository_lock = threading.Lock()
commit_generator = repository.iter_commits('master')
commit_lock = threading.Lock()
log_file = codecs.open("scc.log", "ab", "utf8")
log_lock = threading.Lock()

# Regular expressions
email_re = re.compile(r'[A-Z0-9._%+-]+@([A-Z0-9_%+-]+\.)+'
                      r'(\(NONE\)|[A-Z0-9_%+-]+)', re.IGNORECASE)

# Logging function
def log(string):
    log_lock.acquire()
    try:
        log_file.write(
            "[%s] %s\n" % (datetime.now().strftime('%Y/%m/%d %H:%M:%S.%f'),
                           string))
        log_file.flush()
    finally:
        log_lock.release()

def clean_author(name, email):
    # Someone doesn't know how to fill out the email section
    if email is None:
        re_search = email_re.search(name)
        name = u""
        if re_search:
            email = re_search.group(0)
        else:
            email = ""

    # Fix up the name if needed
    if type(name).__name__ == 'str':
        name = unicode(name, 'iso_8859_1')

    # Someone decided to try and be tricky
    email = email.replace(' at ', '@')
    email = email.replace('-at-', '@')
    email = email.replace(' dot ', '.')
    email = email.replace('-dot-', '.')

    # Fixing invalid e-mails
    re_search = email_re.search(email)
    if re_search and (email != re_search.group(0) or re_search.group(0) == ""):
        if args.debug:
            old_email = email
            
        email = re_search.group(0)

        if args.debug:
            log("Author('%s', '%s') changed e-mail from '%s'" % (name, email, old_email))
    elif not re_search and email != "":
        if args.debug:
            old_email = email

        email = email.lower()
        email = email.replace(' ', '-')
        email = "%s@unknown.com" % email
        
        if args.debug:
            log("Author('%s', '%s') changed e-mail from '%s'" % (name, email, old_email))
    return (name, email)

def init_author(name, email):
    # Need a lock so we don't get 2 entries with the same e-mail
    database_lock.acquire()
    try:
        try:
            author = models.Author.objects.get(repository=django_repository, email=email)
            if args.debug and author.name != name:
                log("Author('%s', '%s') ignoring name '%s'" % (author.name, email, name))
        except:
            author = models.Author.objects.create(repository=django_repository, name=name, email=email)
    finally:
        database_lock.release()

def get_author(email):
    return models.Author.objects.get(repository=django_repository, email=email)

class SCCThread(threading.Thread):

    def run(self):
        while True:
            # Get the next commit if available, stop otherwise
            commit_lock.acquire()
            try:
                commit = commit_generator.next()
                name = commit.author.name
                email = commit.author.email
            except StopIteration:
                break
            finally:
                commit_lock.release()
                
            (name, email) = clean_author(name, email)
            if args.init_db:
                init_author(name, email)

# Spawn the threads, wait, and clean-up
for x in xrange(8):
   SCCThread().start()
while not threading.active_count() == 1:
    sleep(1)
log_file.close()
