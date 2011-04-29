# Modes:
# Init - Populates Repository, RawAuthor, RawCommit and Author models
# Find Bugs - Populates the rest

import codecs
from datetime import datetime
import git
import multiprocessing
import os
import shutil
import threading

os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.scc import models

# MODE_INIT = 1
# MODE_FIND_BUGS = 2

# mode = MODE_INIT

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

# print db_repo

# models.RawAuthor.objects.create(repository=db_repo, name='Jon Eyolfson',email='jon@eyolfson.com')

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

log("Creating %d threads." % num_threads)
threads = [SCCThread(i) for i in xrange(num_threads)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()

log_file.close()
