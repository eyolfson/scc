from datetime import datetime
from time import sleep
import argparse
import git
import threading

git_cmd = git.Git("/home/jon/workspace/linux-2.6")
repository = git.Repo("/home/jon/workspace/linux-2.6")
repository_lock = threading.Lock()

commit_generator = repository.iter_commits('master')
commit_lock = threading.Lock()
log_file = open("scc.log", "ab")
log_lock = threading.Lock()

parser = argparse.ArgumentParser(description='Source Control Correlator')
parser.add_argument("--author", action='store_true')
parser.add_argument("--skip", action='store_true')
parser.add_argument("--config", default="linux.ini")
args = parser.parse_args()

print args
exit(0)

def log(string):
    log_lock.acquire()
    log_file.write(
        "[%s] %s\n" % (datetime.now().strftime('%Y/%m/%d %H:%M:%S.%f'),
                       string))
    log_file.flush()
    log_lock.release()

class SCCThread(threading.Thread):

    def run(self):
        pass

    def author_run(self):
        pass

    def analysis_run(self):
        global commits
        while True:
            # Get the next commit if available, stop otherwise
            commit_lock.acquire()
            try:
                commit = commit_generator.next()
            except StopIteration:
                break
            finally:
                commit_lock.release()

            log(commit)

# Spawn the threads, wait, and clean-up
for x in xrange(8):
   SCCThread().start()
while not threading.active_count() == 1:
    sleep(1)
log_file.close()
