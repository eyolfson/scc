# Modes:
# Init - Populates Repository, RawAuthor, RawCommit and Author models
# Find Bugs - Populates the rest

import codecs
from datetime import datetime
import git
import multiprocessing
import os
import re
import shutil
import threading

os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.scc import models

# repo_slug = "test"
# repo_dir = "/home/jon/workspace/scc_test"

repo_slug = "linux"
repo_dir = "/home/jon/workspace/linux-2.6"


# This is needed to actually decode the Linux repository
git.Commit.default_encoding = "iso-8859-1"

commits_iter = git.Repo(repo_dir).iter_commits("master")
commits_lock = threading.Lock()

def get_log_file():
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)
    log_filename = "log.log"
    # Remove the line above when finished
    # log_filename = "%s.log" % datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return codecs.open(os.path.join(log_dir, log_filename), "w", "utf-8")

log_dir = "logs"
log_file = get_log_file()
log_lock = threading.Lock()

num_threads = multiprocessing.cpu_count()

db_repo = models.Repository.objects.get_or_create(slug=repo_slug)[0]

def log(msg):
    log_lock.acquire()
    try:
        time_stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        log_file.write("[%s] %s\n" % (time_stamp, msg))
        log_file.flush()
    finally:
        log_lock.release()

def log_thread(thread, msg):
    log("<T%d> %s" % (thread.id, msg))

def db_get_commit(sha1):
    return models.RawCommit.objects.get(author__repository=db_repo, sha1=sha1)

# This should only be called if you catch models.RawCommit.DoesNotExist
def db_create_commit(commit):
    # Get the RawAuthor object
    if commit.author.name:
        name = commit.author.name
    else:
        name = u""
    if commit.author.email:
        email = commit.author.email
    else:
        email = ""        
    author = models.RawAuthor.objects.get_or_create(repository=db_repo,
                                                    name=name,
                                                    email=email)[0]
    # Create the RawCommit object
    merge = len(commit.parents) > 1
    utc_time = datetime.utcfromtimestamp(commit.authored_date)
    local_time = datetime.utcfromtimestamp(commit.authored_date
                                           - commit.author_tz_offset)
    return models.RawCommit.objects.create(author=author, sha1=sha1,
                                           merge=merge, utc_time=utc_time,
                                           local_time=local_time)

def find_bugs(commit):
    sha1 = commit.hexsha
    try:
        db_commit = db_get_commit(sha1)
    except models.RawCommit.DoesNotExist:
        db_commit = db_create_commit(commit)

def merge_rawauthors():
    # Email regular expression modified from django.core.validators.email_re
    email_re = re.compile(
        r"([-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
        r'|"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\'
        r'[\001-011\013\014\016-\177])*")'
        r'@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?',
        re.IGNORECASE)

    # Restrict all of the RawAuthor objects to be from the current repository
    rawauthor_qs = models.RawAuthor.objects.filter(repository=db_repo)

    # Create an email lookup to a list of RawAuthors
    email_dict = {}
    for rawauthor in rawauthor_qs.exclude(email=''):
        if rawauthor.email in email_dict:
            email_dict[rawauthor.email].append(rawauthor)
        else:
            email_dict[rawauthor.email] = [rawauthor]

    # Attempt to fix people who put their email in the name field
    for rawauthor in rawauthor_qs.filter(email=''):
        match = email_re.search(rawauthor.name)
        if match:
            email = match.group(0)
            print email
            if email in email_dict:
                email_dict[email].append(rawauthor)
            else:
                email_dict[email] = [rawauthor]

    # Create a name lookup to a list of emails
    name_dict = {}
    for rawauthor in rawauthor_qs.all():
        name = rawauthor.name
        if name != "":
            email = rawauthor.email
            if name in name_dict:
                name_dict[name].append(email)
            else:
                name_dict[name] = [email]

    # Merge the rawauthors in the email dict until there's no more
    # Note: If an rawauthor still has no corresponding author there are 2 cases,
    #       1) they have an email and no name (rawauthors still in email_dict
    #          after the break)
    #       2) they have no email and an unmerged name (the rawauthor was never
    #          in email_dict)
    while len(email_dict) > 0:
        try:
            name_stack = [name_dict.iterkeys().next()]
        # We ran out of names, but there are still some emails unaccounted for
        except StopIteration:
            break
        rawauthors = []
        # Go until we run out of names to merge
        while len(name_stack) > 0:
            name = name_stack.pop()
            if name in name_dict:
                # Get all the emails associated with this name
                for email in name_dict[name]:
                    # Claim the email for this author and remove it from
                    # email_dict
                    if email in email_dict:
                        email_rawauthors = email_dict[email]
                        del email_dict[email]
                        # Add any non-duplicate names to the name_stack
                        for rawauthor in email_rawauthors:
                            if name != rawauthor.name:
                                name_stack.append(rawauthor.name)
                        # Merge the rawauthors
                        rawauthors += email_rawauthors
                del name_dict[name]

        # If we're merging
        if len(rawauthors) > 0:
            # Ensure all the authors are the same
            author = rawauthors[0].author
            for rawauthor in rawauthors[1:]:
                assert author == rawauthor.author

            # They don't have an author, so create one
            if not author:
                rawcommits_qs = \
                    models.RawCommit.objects.filter(author__in=rawauthors)
                recent_commit = rawcommits_qs.order_by("-utc_time")[0]
                recent_rawauthor = recent_commit.author
                name = recent_rawauthor.name
                email = recent_rawauthor.email
                author = models.Author.objects.create(name=name,
                                                      email=email)
                for rawauthor in rawauthors:
                    rawauthor.author = author
                    rawauthor.save()

    # QuerySet for unmerged authors
    unmerged_qs = rawauthor_qs.filter(author__isnull=True)

    # Helper function for manual merging of unmerged email to merged name
    def manual_merge_email_to_name(email, name):
        try:
            rawauthor = unmerged_qs.get(email=email)
        except models.RawAuthor.DoesNotExist:
            # We already added the author or it actually doesn't exist, so just
            # return
            return
        merged_rawauthor_qs = rawauthor_qs.filter(name=name)
        if merged_rawauthor_qs.count() > 0:
            author = merged_rawauthor_qs[0].author
            assert author != None
        else:
            author = models.Author.objects.create(name=name, email=email)
        rawauthor.author = author
        rawauthor.save()
        log("Manually merged RawAuthor %d" % rawauthor.pk)

    # Manual merging for Linux
    if repo_slug == "linux":
        manual_merge_email_to_name("jejb@titanic.il.steeleye.com",
                                   "James Bottomley")
        manual_merge_email_to_name("jketreno@io.(none)", "James Ketrenos")
        manual_merge_email_to_name("greg@echidna.(none)", "Greg Kroah-Hartman")
        manual_merge_email_to_name("felipewd@terra.com.br", "Felipe W Damasio")

    # Report unmerged RawAuthors
    for rawauthor in unmerged_qs.all():
        author = models.Author.objects.create(name=rawauthor.name,
                                              email=rawauthor.email)
        rawauthor.author = author
        rawauthor.save()
        log("Unmerged RawAuthor %d" % rawauthor.pk)

class SCCThread(threading.Thread):

    def __init__(self, id):
        threading.Thread.__init__(self)
        self.id = id

        # Copy the repository, if needed
        copy_dir = "work/%s-%d" % (repo_slug, id)
        if not os.path.exists(copy_dir):
            log_thread(self, "Copying '%s' to '%s'" % (repo_dir, copy_dir))
            shutil.copytree(repo_dir, copy_dir)
            log_thread(self, "Copying finished" % (repo_dir, copy_dir))

        self.repo = git.Repo(copy_dir)

    def run(self):
        log_thread(self, "Finding bugs starting")
        while mode == MODE_INIT:
            commits_lock.acquire()
            try:
                commit_sha1 = commits_iter.next().hexsha
                commit = self.repo.commit(commit_sha1)
                find_bugs(commit)
            except StopIteration:
                break
            finally:
                commits_lock.release()
        log_thread(self, "Finding bugs finished")

# log("Creating %d threads." % num_threads)
# threads = [SCCThread(i) for i in xrange(num_threads)]
# for thread in threads:
#     thread.start()
# for thread in threads:
#     thread.join()

log("Merging RawAuthors starting")
merge_rawauthors()
log("Merging RawAuthors finished")

log_file.close()
