import argparse
import codecs
from datetime import datetime, timedelta
import difflib
import git
import multiprocessing
import os
from pytz import timezone, utc
import re
import shutil
import threading
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.scc import models

# Command line parser
parser = argparse.ArgumentParser(
    description="Python script to populate the SCC database tables.")
parser.add_argument("slug", help="unique name for the repository (eg. linux)")
parser.add_argument("directory", nargs='?',
                    help="directory of the git repository")
parser.add_argument("encoding", nargs='?',
                    help="encoding of the git repository")
parser.add_argument("--log", action='store_true',
                    help="enable logging")
parser.add_argument("--skip-merge", action='store_true',
                    help="skip author merging")
parser.add_argument("--skip-manual-fixes", action='store_true',
                    help="skip manual fixes")
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
    db_rawauthor_lock = threading.Lock()
    db_rawcommit_lock = threading.Lock()
    db_file_lock = threading.Lock()
    db_repository_lock = threading.Lock()
    num_threads = multiprocessing.cpu_count()

if args.log:
    # Logging functions
    def get_log_file():
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)
        log_filename = "%s.log" % datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        return codecs.open(os.path.join(log_dir, log_filename), "w", "utf-8")

    log_dir = "log"
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
else:
    # Empty functions
    def log(msg):
        pass

    def log_thread(thread, msg):
        pass

def db_get_commit(sha1):
    return models.RawCommit.objects.get(rawauthor__repository=db_repo,
                                        sha1=sha1)

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
    db_rawauthor_lock.acquire()
    rawauthor = models.RawAuthor.objects.get_or_create(repository=db_repo,
                                                    name=name, email=email)[0]
    db_rawauthor_lock.release()

    # Create the RawCommit object
    sha1 = commit.hexsha
    merge = len(commit.parents) > 1
    utc_time = datetime.utcfromtimestamp(commit.authored_date)
    local_time = datetime.utcfromtimestamp(commit.authored_date
                                           - commit.author_tz_offset)
    db_rawcommit_lock.acquire()
    rawcommit = models.RawCommit.objects.get_or_create(
        rawauthor=rawauthor, sha1=sha1, merge=merge, utc_time=utc_time,
        local_time=local_time)[0]
    db_rawcommit_lock.release()
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
        try:
            diff_iter.next()
        except StopIteration:
            break
    return diff_iter

def find_bugs(thread, commit):
    sha1 = commit.hexsha
    previous_rev = "%s~1" % sha1
    merge = len(commit.parents) > 1
    
    try:
        db_current_rawcommit = db_get_commit(sha1)
    except models.RawCommit.DoesNotExist:
        db_current_rawcommit = db_create_commit(commit)

    # Create the Commit object if needed
    # Note: We don't need a lock here because it will only be accessed once
    try:
        models.Commit.objects.get(rawcommit=db_current_rawcommit)
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
        models.Commit.objects.create(rawcommit=db_current_rawcommit,
            lines_changed_code=lines_changed_code,
            lines_changed_comments=lines_changed_comments,
            lines_changed_other=lines_changed_other)

    log_thread(thread, "Commit object done for ID %d" % db_current_rawcommit.pk)

    # Set the first commit to the earliest commit without parents
    if len(commit.parents) == 0:
        db_repository_lock.acquire()
        if db_repo.first_rawcommit:
            if db_current_rawcommit.utc_time < db_repo.first_rawcommit.utc_time:
                db_repo.first_rawcommit = db_current_rawcommit
                db_repo.save()
                log_thread(thread, "Changed first commit to %s" % sha1)
        else:
            db_repo.first_rawcommit = db_current_rawcommit
            db_repo.save()
            log_thread(thread, "Set first commit to %s" % sha1)
        db_repository_lock.release()

    # Ignore any merges or commits which are not fixes
    if merge or not fix_re.search(commit.message):
        return

    # We do not need to use a lock here since this will only be called once
    # per fix commit
    db_bug = models.Bug.objects.get_or_create(
        fixing_rawcommit=db_current_rawcommit)[0]
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
                # We should ignore here, because there's no context before
                ignore_next_add = True
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
        # TODO: The blame also includes the file location if it was different
        #       before, we could take this into account. Currently the file
        #       stored in the database is the most recent name, which is
        #       arguably better, but less correct
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
            db_introducing_rawcommit = db_get_commit(introducing_sha1)
        except models.RawCommit.DoesNotExist:
            introducing_commit = thread.repo.commit(introducing_sha1)
            db_introducing_rawcommit = db_create_commit(introducing_commit)

        # Don't need a lock here, since it'll be the only one
        db_bugsource = models.BugSource.objects.get_or_create(
            rawcommit=db_introducing_rawcommit, bug=db_bug)[0]

        # Add the files for this source
        for filename in filename_list:
            db_file_lock.acquire()
            db_file = models.File.objects.get_or_create(name=filename)[0]
            db_file_lock.release()
            db_bugsource.files.add(db_file)

    log_thread(thread, "Bug object done for ID %d" % db_current_rawcommit.pk)

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
        if rawauthor.email.lower() in email_dict:
            email_dict[rawauthor.email.lower()].append(rawauthor)
        else:
            email_dict[rawauthor.email.lower()] = [rawauthor]

    # Attempt to fix people who put their email in the name field
    for rawauthor in rawauthor_qs.filter(email=''):
        match = email_re.search(rawauthor.name)
        if match:
            email = match.group(0)
            if email.lower() in email_dict:
                email_dict[email.lower()].append(rawauthor)
            else:
                email_dict[email.lower()] = [rawauthor]

    # Create a name lookup to a list of emails
    name_dict = {}
    for rawauthor in rawauthor_qs.all():
        name = rawauthor.name
        if name != "":
            email = rawauthor.email
            if name in name_dict:
                name_dict[name].append(email.lower())
            else:
                name_dict[name] = [email.lower()]

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
                    models.RawCommit.objects.filter(rawauthor__in=rawauthors)
                recent_commit = rawcommits_qs.order_by("-utc_time")[0]
                recent_rawauthor = recent_commit.rawauthor
                name = recent_rawauthor.name
                email = recent_rawauthor.email
                author = models.Author.objects.create(repository=db_repo,
                                                      name=name,
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
            author = models.Author.objects.create(repository=db_repo, name=name,
                                                  email=email)
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
        author = models.Author.objects.create(repository=db_repo,
                                              name=rawauthor.name,
                                              email=rawauthor.email)
        rawauthor.author = author
        rawauthor.save()
        log("Unmerged RawAuthor %d" % rawauthor.pk)

def classify_authors():
    author_qs = models.Author.objects.filter(
        rawauthors__repository=db_repo).distinct()

    first_utc_datetime = db_repo.first_rawcommit.utc_time
    last_utc_datetime = db_repo.last_rawcommit.utc_time

    for author in author_qs:
        # Get all their datetimes in a sorted list
        commit_datetimes = []
        for rawauthor in author.rawauthors.all():
            for commit in rawauthor.rawcommits.all():
                # Make sure the commit is valid
                if commit.utc_time >= first_utc_datetime and \
                   commit.utc_time <= last_utc_datetime:
                    # Add the datetime to the list (we're using local time here
                    # so we can compute whether or not this is their day job)
                    commit_datetimes.append(commit.local_time)
        commit_datetimes.sort()

        # The main classification
        if len(commit_datetimes) == 1:
            author.classification = 'S'
        elif len(commit_datetimes) < 20:
            author.classification = 'O'
        else:
            daily_commits = 0
            weekly_commits = 0
            monthly_commits = 0

            last_datetime = commit_datetimes[0]
            ignore_before_datetime = last_datetime + timedelta(minutes=30)
            for dt in commit_datetimes[1:]:
                if dt >= ignore_before_datetime:
                    # Use the delta to see how close the commits are
                    delta = dt - last_datetime
                    if delta.days < 7:
                        daily_commits += 1
                    elif delta.days < 31:
                        weekly_commits += 1
                    else:
                        monthly_commits += 1

                    # Update the ignore and the last datetime
                    ignore_before_datetime = dt + timedelta(minutes=30)
                    last_datetime = dt

            # Whatever has the higher count, classify the author as such
            if daily_commits >= weekly_commits and \
               daily_commits >= monthly_commits:
                author.classification = 'D'
            elif weekly_commits >= daily_commits and \
                 weekly_commits >= monthly_commits:
                author.classification = 'W'
            else:
                author.classification = 'M'

            # Check to see if this is their job
            if author.classification == 'D':
                # Count the number of normal work hour commits
                day_commits = 0
                for dt in commit_datetimes:
                    if not (dt.weekday == 5 or dt.weekday == 6) and \
                       (dt.hour >=8 and dt.hour <= 16):
                        day_commits += 1

                # We conclude if >85% of their commits are within normal work
                # then this is their day job
                if float(day_commits)/float(len(commit_datetimes)) > 0.85:
                    author.classification = 'J'

        author.save()

def adjust_timezone():
    if repo_slug == 'postgresql':
        # Timezone information
        tzs = {}
        tzs['proff@suburbia.net'] = 'Australia/Melbourne'
        tzs['bryanh@giraffe.netgate.net'] = 'America/Los_Angeles'
        tzs['E.Mergl@bawue.de'] = 'Europe/Berlin'
        tzs['byronn@insightdist.com'] = 'America/New_York'
        tzs['peter@retep.org.uk'] = 'Europe/London'
        tzs['vadim4o@yahoo.com'] = 'America/Los_Angeles'
        tzs['vev@michvhf.com'] = 'America/Detroit'
        tzs['pjw@rhyme.com.au'] = 'Australia/Melbourne'
        tzs['lockhart@fourpalms.org'] = 'America/Los_Angeles'
        tzs['inoue@tpf.co.jp'] = 'Asia/Tokyo'
        tzs['barry@xythos.com'] = 'America/Los_Angeles'
        tzs['davec@fastcrypt.com'] = 'America/Toronto'
        tzs['books@ejurka.com'] = 'America/Los_Angeles'
        tzs['db@zigo.dhs.org'] = 'Europe/London'
        tzs['webmaster@postgresql.org'] = 'UTC'
        tzs['JanWieck@Yahoo.com'] = 'America/New_York'
        tzs['darcy@druid.net'] = 'America/Toronto'
        tzs['stark@mit.edu'] = 'Europe/Dublin'
        tzs['teodor@sigaev.ru'] = 'Europe/Moscow'
        tzs['ishii@postgresql.org'] = 'Asia/Tokyo'
        tzs['scrappy@hub.org'] = 'America/Halifax'
        tzs['mail@joeconway.com'] = 'America/Los_Angeles'
        tzs['simon@2ndQuadrant.com'] = 'Europe/London'
        tzs['itagaki.takahiro@gmail.com'] = 'Asia/Tokyo'
        tzs['meskes@postgresql.org'] = 'Europe/Berlin'
        tzs['alvherre@alvh.no-ip.org'] = 'America/Santiago'
        tzs['andrew@dunslane.net'] = 'America/New_York'
        tzs['tgl@sss.pgh.pa.us'] = 'America/New_York'
        tzs['magnus@hagander.net'] = 'Europe/Stockholm'
        tzs['heikki.linnakangas@iki.fi'] = 'Europe/Helsinki'
        tzs['rhaas@postgresql.org'] = 'America/New_York'
        tzs['peter_e@gmx.net'] = 'Europe/Helsinki'
        tzs['bruce@momjian.us'] = 'America/New_York'

        for c in models.RawCommit.objects.filter(rawauthor__repository=db_repo):
            # Check if there's possibly no timezone information
            if c.local_time == c.utc_time:
                try:
                    # Get the timezone
                    tz = timezone(tzs[c.rawauthor.author.email])
                except KeyError:
                    # Handle the special cases
                    if c.rawauthor.author.email == 'neilc@samurai.com':
                        if c.utc_time.year <= 2007:
                            tz = timezone('America/Toronto')
                        else:
                            tz = timezone('America/Los_Angeles')
                    else:
                        # Reraise the exception
                        raise KeyError

                # Modify and save
                time_utc = c.local_time.replace(tzinfo=utc)
                c.local_time = time_utc.astimezone(tz).replace(tzinfo=None)
                c.save()

class SCCThread(threading.Thread):

    def __init__(self, id):
        threading.Thread.__init__(self)
        self.id = id

        # Copy the repository, if needed
        copy_dir = "work/%s-%d" % (repo_slug, id)
        if not os.path.exists(copy_dir):
            log_thread(self, "Copying '%s' to '%s'" % (repo_dir, copy_dir))
            shutil.copytree(repo_dir, copy_dir, symlinks=True)
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
            # The commits lock just protects the shared commit iterator
            commits_lock.acquire()
            try:
                commit_sha1 = commits_iter.next().hexsha
            except StopIteration:
                break
            finally:
                commits_lock.release()
            commit = self.repo.commit(commit_sha1)
            find_bugs(self, commit)

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
        db_repo.last_rawcommit = db_commit
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
    log("Classifying Authors starting")
    classify_authors()
    log("Classifying Authors finished")

if not args.skip_manual_fixes:
    log("Adjusting timezones starting")
    adjust_timezone()
    log("Adjusting timezones finished")

if args.log:
    log_file.close()
