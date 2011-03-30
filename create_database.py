import argparse
import codecs
from datetime import datetime
import difflib
import git
import multiprocessing
import os
import re
import shutil
import threading
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.scc import models

# Command line parser
parser = argparse.ArgumentParser(
    description="Python script to create SCC database.")
parser.add_argument("slug", help="unique name for the repository (eg. linux)")
parser.add_argument("directory", nargs='?',
                    help="directory of the git repository")
parser.add_argument("encoding", nargs='?',
                    help="encoding of the git repository")
parser.add_argument("--skip-merge", action='store_true',
                    help="skip author merging")
args = parser.parse_args()

# Use easier to read names and set encoding if needed
repo_slug = args.slug
if args.directory:
    repo_dir = args.directory
if args.encoding:
    git.Commit.default_encoding = args.encoding

# Create global variables
db_repo = models.Repository.objects.get_or_create(slug=repo_slug)[0]
if args.directory:
    commits_iter = \
        git.Repo(repo_dir, odbt=git.GitCmdObjectDB).iter_commits("master")
    commits_lock = threading.Lock()
    db_author_lock = threading.Lock()
    db_commit_lock = threading.Lock()
    db_file_lock = threading.Lock()
    db_repository_lock = threading.Lock()
    num_threads = multiprocessing.cpu_count()

# Logging functions
def get_log_file():
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)
    log_filename = "%s.log" % datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return codecs.open(os.path.join(log_dir, log_filename), "w", "utf-8")

log_dir = "logs"
log_file = get_log_file()
log_lock = threading.Lock()

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

# This should only be called if we catch models.RawCommit.DoesNotExist
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
    db_author_lock.acquire()
    author = models.RawAuthor.objects.get_or_create(repository=db_repo,
                                                    name=name, email=email)[0]
    db_author_lock.release()

    # Create the RawCommit object
    sha1 = commit.hexsha
    merge = len(commit.parents) > 1
    utc_time = datetime.utcfromtimestamp(commit.authored_date)
    local_time = datetime.utcfromtimestamp(commit.authored_date
                                           - commit.author_tz_offset)
    db_commit_lock.acquire()
    rawcommit = models.RawCommit.objects.get_or_create(
        author=author, sha1=sha1, merge=merge, utc_time=utc_time,
        local_time=local_time)[0]
    db_commit_lock.release()
    return rawcommit

if args.directory:
    comment_re = re.compile(r"^\s*(/\*|\*\s|//)")
    filetypes_re = re.compile(r"\.(c|cpp|cc|cp|cxx|c\+\+"
                              "|h|hpp|hh|hp|hxx|h\+\+)$",
                              re.IGNORECASE)
    fix_re = re.compile(r"fix", re.I)
    line_numbers_re = re.compile(r"@@ -(\d+),\d+ \+(\d+),\d+ @@")

def get_diff_index(commit, previous_rev):
    # An exception occurs if this commit does not have any previous commits
    try:
        return commit.diff(previous_rev)
    except:
        return []

# Return a diff iterator object between the previous and current lines
def get_diff_iter(previous_lines, current_lines):
    # Compute the unified diff, and throw away the first two file
    # information lines
    diff_iter = difflib.unified_diff(previous_lines, current_lines)
    for i in xrange(2):
        diff_iter.next()
    return diff_iter

def find_bugs(thread, commit):
    sha1 = commit.hexsha
    previous_rev = "%s~1" % sha1
    merge = len(commit.parents) > 1
    
    try:
        db_root_commit = db_get_commit(sha1)
    except models.RawCommit.DoesNotExist:
        db_root_commit = db_create_commit(commit)

    # Create the Commit object if needed
    # Note: We don't need a lock here because it will only be accessed once
    try:
        models.Commit.objects.get(commit=db_root_commit)
    except models.Commit.DoesNotExist:
        lines_changed_code = 0
        lines_changed_comments = 0
        lines_changed_other = 0
        
        diff_index = get_diff_index(commit, previous_rev)
        for diff in diff_index:
            # This diff is a deleted or new file, so ignore it
            if diff.deleted_file or diff.new_file:
                continue

            assert diff.a_blob.path == diff.b_blob.path
            filename = diff.a_blob.path

            # Keep track whether or not the changes are for code or not
            if filetypes_re.search(filename):
                is_code_change = True
            else:
                is_code_change = False

            # Read the data and get the lines (yes I know it seems backwards) and
            # remove Windows' stupid newline character which messes things up on
            # UNIX
            previous_lines = \
                diff.b_blob.data_stream.read().replace("\r","").splitlines()
            current_lines = \
                diff.a_blob.data_stream.read().replace("\r","").splitlines()

            # We're just keeping track of how many lines changed and added,
            # which are all just additions in the unified diff
            for line in get_diff_iter(previous_lines, current_lines):
                if line.startswith("+"):
                    if is_code_change:
                        if not comment_re.match(line[1:]):
                            lines_changed_code += 1
                        else:
                            lines_changed_comments += 1
                    else:
                        lines_changed_other += 1

        # Finally, create the Commit object
        models.Commit.objects.create(commit=db_root_commit,
            lines_changed_code=lines_changed_code,
            lines_changed_comments=lines_changed_comments,
            lines_changed_other=lines_changed_other)

    log_thread(thread, "Commit object done for ID %d" % db_root_commit.pk)

    # Set the first commit to the earliest commit without parents
    if len(commit.parents) == 0:
        db_repository_lock.acquire()
        if db_repo.first_commit:
            if db_root_commit.utc_time < db_repo.first_commit.utc_time:
                db_repo.first_commit = db_root_commit
                db_repo.save()
                log_thread(thread, "Changed first commit to %s" % sha1)
        else:
            db_repo.first_commit = db_root_commit
            db_repo.save()
            log_thread(thread, "Set first commit to %s" % sha1)
        db_repository_lock.release()

    # Ignore any merges or commits which are not fixes
    if merge or not fix_re.search(commit.message):
        return

    # We do not need to use a lock here since this will only be called once
    # per fix commit
    db_bug = models.Bug.objects.get_or_create(fix_commit=db_root_commit)[0]
    bug_introduction = {}

    diff_index = get_diff_index(commit, previous_rev)
    for diff in diff_index:
        # NOTE: Rename detection doesn't seem to work, maybe a bug with
        # GitPython?

        # This diff is a deleted or new file, so ignore it
        if diff.deleted_file or diff.new_file:
            continue

        assert diff.a_blob.path == diff.b_blob.path
        filename = diff.a_blob.path

        # This file isn't a valid filetype, so ignore it
        if not filetypes_re.search(filename):
            continue

        # Read the data and get the lines (yes I know it seems backwards) and
        # remove Windows' stupid newline character which messes things up on
        # UNIX
        previous_lines = \
            diff.b_blob.data_stream.read().replace("\r","").splitlines()
        current_lines = \
            diff.a_blob.data_stream.read().replace("\r","").splitlines()

        # Remember: only the previous file's line number matters when we do the
        # blaming, so we only need to record that
        blame_lines = []
        # We can ignore the next add line if the line before it was a removal
        # otherwise, we cannot.
        # If we're in an add block and not ignoring we look for the first line
        # added which is not a comment; in this case add the current line number
        # to the blame (which is the line before the add block in the previous
        # file) and ignore the rest of the block.
        for line in get_diff_iter(previous_lines, current_lines):
            if line.startswith("@@"):
                match = line_numbers_re.match(line)
                # Subtract one so our increment on the next line is correct
                line_number = int(match.group(1)) - 1
                ignore_next_add = False
            elif line.startswith("-"):
                line_number += 1
                if not comment_re.match(line[1:]):
                    blame_lines.append(line_number)
                # TODO: Actually, this probably shouldn't be ignored if the
                # entire remove block was comments
                ignore_next_add = True
            elif line.startswith("+"):
                if not ignore_next_add:
                    if not comment_re.match(line[1:]):
                        blame_lines.append(line_number)
                        ignore_next_add = True
            else:
                line_number += 1
                ignore_next_add = False

        # Nothing to blame, so carry on (my wayward son)
        if len(blame_lines) == 0:
            continue

        # If the blame doesn't work, it's because the file doesn't exist in the
        # currently checked out branch, so switch the branch to the revision of
        # the blame
        try:
            blame = thread.git.blame(["-l", "-s", "-w", "--root", previous_rev,
                                      filename]).replace('\r','').splitlines()
        except:
            thread.switch_to_rev(previous_rev)
            blame = thread.git.blame(["-l", "-s", "-w", "--root", previous_rev,
                                      filename]).replace('\r','').splitlines()

        # Populate the bug_introduction dictionary along with all the filenames
        # TODO: Maybe do something more efficient than checking if the filename
        #       is already in the list
        for line in blame_lines:
            # The line is 1-indexed since it is a line number, and the blame is
            # 0-indexed, so adjust
            introducing_sha1 = blame[line-1].split()[0]

            if introducing_sha1 in bug_introduction:
                if not filename in bug_introduction[introducing_sha1]:
                    bug_introduction[introducing_sha1].append(filename)
            else:
                bug_introduction[introducing_sha1] = [filename]

    # Creating the BugSources for this bug-fix
    for (introducing_sha1, filename_list) in bug_introduction.iteritems():
        # Get the introducing commit
        try:
            db_introducing_commit = db_get_commit(introducing_sha1)
        except models.RawCommit.DoesNotExist:
            introducing_commit = thread.repo.commit(introducing_sha1)
            db_introducing_commit = db_create_commit(introducing_commit)

        # Don't need a lock here, since it'll be the only one
        db_bugsource = models.BugSource.objects.get_or_create(
            commit=db_introducing_commit, bug=db_bug)[0]

        # Add the files for this source
        for filename in filename_list:
            db_file_lock.acquire()
            db_file = models.File.objects.get_or_create(name=filename)[0]
            db_file_lock.release()
            db_bugsource.files.add(db_file)

    log_thread(thread, "Bug object done for ID %d" % db_root_commit.pk)

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
            log_thread(self, "Copying finished")

        self.repo = git.Repo(copy_dir, odbt=git.GitCmdObjectDB)
        self.git = git.Git(copy_dir)
        self._current_branch = "scc_left"
        self._free_branch = "scc_right"
        self.git.checkout(["-b", self._current_branch, "master"])

    def switch_to_rev(self, rev):
        self.git.checkout(["-b", self._free_branch, rev])
        # Swap
        self._current_branch, self._free_branch = \
            self._free_branch, self._current_branch
        self.git.branch(["-D", self._free_branch])

    def run(self):
        log_thread(self, "Finding bugs starting")
        while True:
            commits_lock.acquire()
            try:
                commit_sha1 = commits_iter.next().hexsha
                commit = self.repo.commit(commit_sha1)
                find_bugs(self, commit)
            except StopIteration:
                break
            finally:
                commits_lock.release()
        # Clean-up
        log_thread(self, "Finding bugs cleaning up")
        self.git.checkout(["master"])
        self.git.branch(["-D", self._current_branch])
        log_thread(self, "Finding bugs finished")

if args.directory:
    # Set the last commit to master
    last_commit = git.Repo(repo_dir, odbt=git.GitCmdObjectDB).commit("master")
    try:
        db_commit = db_get_commit(last_commit.hexsha)
    except models.RawCommit.DoesNotExist:
        db_commit = db_create_commit(last_commit)
        db_repo.last_commit = db_commit
        db_repo.save()
        log("Set last commit to %s" % last_commit.hexsha)

    log("Creating %d threads." % num_threads)
    threads = [SCCThread(i) for i in xrange(num_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

if not args.skip_merge:
    log("Merging RawAuthors starting")
    merge_rawauthors()
    log("Merging RawAuthors finished")

log_file.close()
